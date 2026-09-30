"""Read-only, version-pinned transition from API-only to API-plus-role tracing.

The three serving versions are bracketed together around Queue and capture-off
checks. Queue names never supply ownership: reviewed exact resource IDs are
mandatory. This does not attest Email/Cron retained-record privacy or delivery.
"""

from __future__ import annotations

import argparse
import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "crates/mail-worker"))
import check_observability as capture
import ensure_trace_queues as queues
import verify_role_monitor_staging as role
from pin_staging_mail import serving_deployment, bindings_match
from trace_rollout_attestation import UUID, ID

API_WORKER = "amail-mail-staging"
SINK_WORKER = "amail-trace-sink-staging"


def pins() -> tuple[str, str, dict[str, str]]:
    """Require all independent reviewed identities before the first provider read."""
    account, token = os.getenv("CLOUDFLARE_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_API_TOKEN", "")
    expected = {API_WORKER: os.getenv("AMAIL_EXPECTED_WORKER_VERSION", ""),
                SINK_WORKER: os.getenv("AMAIL_EXPECTED_TRACE_SINK_VERSION", ""),
                role.WORKER: os.getenv("AMAIL_EXPECTED_ROLE_WORKER_VERSION", "")}
    queue, dlq = os.getenv("AMAIL_TRACE_QUEUE_ID", ""), os.getenv("AMAIL_TRACE_DLQ_ID", "")
    if (ID.fullmatch(account) is None or not token
            or any(UUID.fullmatch(value) is None for value in expected.values())
            or ID.fullmatch(queue) is None or ID.fullmatch(dlq) is None or queue == dlq):
        raise ValueError("pins_unverified")
    return account, token, expected


def serving_pins(account: str, token: str, expected: dict[str, str]) -> dict[str, tuple[str, str]]:
    """Retain exact deployment identities as well as single-100 version identities."""
    result = {}
    for script, version in expected.items():
        active = serving_deployment(capture.readback(account, token, script, "deployments?per_page=1&page=1"))
        if active is None or active[1] != version:
            raise ValueError("serving_version_unverified")
        result[script] = active
    return result


def route_absent() -> None:
    """Recheck the sole synthetic route immediately before replacement, without writing."""
    result = subprocess.run([sys.executable, str(ROOT / "workers/role-monitor/staging_route.py")],
                            cwd=ROOT, capture_output=True, text=True, check=False, timeout=90)
    if result.returncode != 0 or result.stdout.strip() != "absent":
        raise ValueError("synthetic_route_unverified")


def verify(phase: str) -> None:
    """Require phase1 before mutation and exact phase2 after one reviewed role deploy."""
    if phase not in ("before", "after"):
        raise ValueError("phase_unreviewed")
    topology = "api-only" if phase == "before" else "api-role"
    # A caller cannot accidentally reuse phase1's permissive sink-initialization
    # attachment policy after introducing a second producer.
    if os.getenv("AMAIL_TRACE_TOPOLOGY", "api-only") != topology:
        raise ValueError("topology_unreviewed")
    account, token, expected = pins()
    before = serving_pins(account, token, expected)
    queues.reconcile(account, token, "staging", "readback", topology)
    if not bindings_match(capture.readback(account, token, API_WORKER,
                                          f"versions/{expected[API_WORKER]}"),
                          expected[API_WORKER], phase="queue-api",
                          queue_id=os.environ["AMAIL_TRACE_QUEUE_ID"]):
        raise ValueError("source_queue_unverified")
    if (not capture.verify("staging", account, token)
            or not capture.verify("staging", account, token, sink=True)):
        raise ValueError("privacy_or_sink_isolation_unverified")
    if phase == "after":
        # The role gate also verifies an absent synthetic route and initial
        # empty isolated D1/expired lease. It never touches production forwards.
        role.audit()
    else:
        route_absent()
        # Replacing a previously deployed role Worker is not a schema bootstrap:
        # require its existing isolated ledger to be empty and its lease at the
        # initial expired value before migration or replacement. A pristine DB
        # without these tables needs a separately reviewed bootstrap, not an
        # implicit fallback that hides pending role mail.
        role.inspect_d1()
    # Queue attachments are non-versioned too: reread exact topology, never
    # infer stability merely because the three Worker versions did not change.
    queues.reconcile(account, token, "staging", "readback", topology)
    after = serving_pins(account, token, expected)
    if before != after:
        raise ValueError("deployment_changed")


def main() -> int:
    """Emit fixed verdicts only; unknown provider values never enter diagnostics."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    args = parser.parse_args()
    try:
        verify(args.phase)
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.TimeoutExpired):
        print("role_trace_topology=UNVERIFIED")
        return 1
    print(f"role_trace_topology_{args.phase}=exact_serving_and_queue_pins_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
