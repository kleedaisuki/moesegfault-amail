"""Executable preflight/recovery guards; no provider writer or drain guess exists.

These guards must precede future protected transition/replacement writers. The
trusted receipt producer, fresh-isolated bootstrap proof, actual old-work-end
verifier and code-compatibility admission remain separately required integration.
"""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
import os

from check_mail_maintenance import script_name
import check_mail_split_graph as graph
from control_plane_trace import span
from mail_lifecycle_receipt import Receipt, checked_graph, load, validate
from mail_split_transition import Plan, State, transition


class Recovery(str, Enum):
    """A successful exact read can classify state, but never authorizes replay."""
    PREDECESSOR = "matches-predecessor"
    SUCCESSOR = "matches-successor"
    UNRESOLVED = "unrecognized-intermediate"


@dataclass(frozen=True)
class RecoveryPlan:
    """A read-only bounded disposition with no automatic rollback/write/retry."""
    outcome: Recovery
    may_replay_write: bool = field(default=False, init=False)


@contextmanager
def coordinates(receipt: Receipt):
    """Select only validated exact pins for the existing complete graph bracket."""
    value = validate(receipt.value, receipt.realm)
    pins = value["graph"]["pins"]
    suffix = "-staging" if receipt.realm == "staging" else ""
    updates = {
        "AMAIL_TRACE_TOPOLOGY": "api-scheduled",
        "AMAIL_TRACE_QUEUE_ID": value["resources"]["queue"],
        "AMAIL_TRACE_DLQ_ID": value["resources"]["dlq"],
        "AMAIL_EXPECTED_WORKER_VERSION": pins[script_name(receipt.realm, maintenance=False)]["version"],
        "AMAIL_EXPECTED_MAINTENANCE_VERSION": pins[script_name(receipt.realm)]["version"],
        "AMAIL_EXPECTED_TRACE_SINK_VERSION": pins["amail-trace-sink" + suffix]["version"],
    }
    original = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for key, value in original.items():
            os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)


def current_graph(receipt: Receipt) -> dict:
    """Fresh complete reads plus exact deployment identity; failure remains failure."""
    with span("mail.lifecycle", "predecessor_readback", realm=receipt.realm, component="mail_graph") as facts:
        facts.reason = "exact_predecessor_graph_required"
        with coordinates(receipt):
            result = graph.verify(receipt.realm, receipt.state.value,
                                  old_crons=tuple(receipt.value["graph"]["api_crons"]))
        expected = receipt.value["graph"]
        converted = {**result, "pins": {name: {"deployment": pin[0], "version": pin[1]}
                                        for name, pin in result["pins"].items()}}
        if converted != expected:
            facts.reason = "predecessor_graph_changed"
            raise ValueError("lifecycle_predecessor_graph_changed")
        facts.reason = "exact_predecessor_graph_verified"
        return converted


def guard(receipt: Receipt, operation: str) -> Plan:
    """Only source-approved stop/hold planning is possible without old-work proof.

    Paused describes an explicit empty schedule, not terminated old invocations.
    No self-authored admission string, age, row count or failed GET can activate.
    Code rollback is not schema/resource rollback and needs a separate verifier.
    """
    validate(receipt.value, receipt.realm)
    if operation == "activate":
        raise ValueError("old_work_end_verifier_unavailable")
    if operation.startswith(("replace-", "rollback-")):
        raise ValueError("code_compatibility_verifier_unavailable")
    if operation not in ("stop-old", "pause", "hold"):
        raise ValueError("lifecycle_operation_unreviewed")
    plan = transition(receipt.realm, receipt.state, operation)
    current_graph(receipt)
    return plan


def recovery(receipt: Receipt, operation: str, readback) -> RecoveryPlan:
    """Read once; recognize only exact fully checked predecessor/successor graphs.

    The reader must use the same full immutable/current capability/privacy/hold
    bracket as current_graph. Exceptions and missing/malformed reads propagate;
    they do not mean predecessor, absence, write-not-applied or safe replay.
    """
    validate(receipt.value, receipt.realm)
    if operation not in ("stop-old", "pause", "hold"):
        raise ValueError("lifecycle_recovery_operation_unreviewed")
    plan = transition(receipt.realm, receipt.state, operation)
    successor = deepcopy(receipt.value["graph"])
    if plan.script is not None:
        field = "maintenance_crons" if plan.script == script_name(receipt.realm) else "api_crons"
        successor[field] = list(plan.crons)
    checked_graph(successor, receipt.realm)
    with span("mail.lifecycle", "recovery_readback", realm=receipt.realm, component="mail_graph") as facts:
        actual = checked_graph(readback(), receipt.realm)
        if actual == receipt.value["graph"]:
            outcome = Recovery.PREDECESSOR
        elif actual == successor:
            outcome = Recovery.SUCCESSOR
        else:
            outcome = Recovery.UNRESOLVED
        facts.reason = outcome.value
        return RecoveryPlan(outcome)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--realm", required=True, choices=("production", "staging"))
    parser.add_argument("--predecessor-run", required=True)
    parser.add_argument("--operation", required=True, choices=("stop-old", "pause", "hold", "activate", "rollback-maintenance"))
    args = parser.parse_args()
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("GITHUB_REF") != "refs/heads/main":
        raise SystemExit("Hosted protected main preflight required.")
    selected = guard(load(args.predecessor_run, args.realm), args.operation)
    print(f"mail_lifecycle_preflight=plan_only successor={selected.successor.value} old_work_end=UNVERIFIED")
