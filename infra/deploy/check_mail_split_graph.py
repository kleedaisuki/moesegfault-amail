"""Read-only exact split graph bracket; source-only checks never contact providers.

No role ledger, schema migration, remote scheduled dispatch, retained-record
canary, grant, purge, HTTP maintenance health check or provider writer exists here.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "crates/mail-worker"))
import check_observability as capture
import ensure_trace_queues as queues
from check_mail_maintenance import CADENCE, api_config, entry_surface_match, expected_schedules, schedules_match, script_name, verify as maintenance_verify
from pin_staging_mail import ACCOUNT, UUID, bindings_match, serving_deployment

FAILURES = frozenset({"split_graph_state_unreviewed", "split_pins_unverified", "split_serving_unverified",
                      "split_hold_unverified", "split_role_absence_unverified", "split_api_unverified",
                      "split_privacy_unverified", "split_graph_changed", "maintenance_absence_unverified",
                      "split_role_boundary_unverified", "split_policy_unverified"})


def role_capabilities(version: dict) -> dict:
    """Project Mail graph edges, never secret values or contact destinations."""
    resources = version.get("resources", {})
    bindings = resources.get("bindings")
    if isinstance(bindings, dict) and set(bindings) == {"result"}:
        bindings = bindings["result"]
    handlers = resources.get("script", {}).get("handlers")
    if (not isinstance(bindings, list) or not all(isinstance(row, dict) for row in bindings)
            or not isinstance(handlers, list) or any(item not in ("fetch", "scheduled", "email", "queue") for item in handlers)):
        raise ValueError("split_role_boundary_unverified")
    for row in bindings:
        field = {"d1": "database_id", "r2_bucket": "bucket_name", "service": "service"}.get(row.get("type"))
        if field and (not isinstance(row.get(field), str) or not row[field].strip()):
            raise ValueError("split_role_boundary_unverified")
        if row.get("type") != "queue":
            continue
        # Version APIs use queue_id or id; name-only views must have passed the
        # existing catalog normalizer. Missing targets cannot prove separation.
        targets = [row[key] for key in ("queue_id", "id") if key in row]
        if (not targets or any(not isinstance(value, str) or ACCOUNT.fullmatch(value) is None for value in targets)
                or len(set(targets)) != 1 or ("queue_name" in row and
                (not isinstance(row["queue_name"], str) or not row["queue_name"].strip()))):
            raise ValueError("split_role_boundary_unverified")
    queue_ids = {os.getenv(name, "") for name in ("AMAIL_TRACE_QUEUE_ID", "AMAIL_TRACE_DLQ_ID")} - {""}
    return {
        "handlers": handlers,
        "mail_database_bound": any(row.get("type") == "d1" and row.get("database_id") == "74f35f95-42ce-482c-86e6-dffbdd35cbbe" for row in bindings),
        "mail_service_bound": any(row.get("type") == "service" and row.get("service") in
                                  ("amail-mail-staging", "amail-mail-maintenance-staging", "amail-trace-sink-staging") for row in bindings),
        "mail_body_bucket_bound": any(row.get("type") == "r2_bucket" and row.get("bucket_name") == "moesegfault-mail-raw-staging" for row in bindings),
        "mail_trace_queue_bound": any(row.get("type") == "queue" and
                                       ((row.get("queue_id") or row.get("id")) in queue_ids or row.get("queue_name") in
                                        ("amail-trace-events-staging", "amail-trace-dlq-staging")) for row in bindings),
    }


def independent_role_snapshot(account: str, token: str) -> dict:
    """Bracket the historical independent staging contact Worker without altering it.

    Mail API exact bindings and the sole trace producer pair remain separately
    mandatory. This proves capability separation, not contact-monitor correctness,
    general network/population isolation or authority to change its routes/Cron.
    """
    script = "amail-role-monitor-staging"
    before = serving_deployment(capture.readback(account, token, script, "deployments?per_page=1&page=1"))
    if before is None:
        raise ValueError("split_role_boundary_unverified")
    version = capture.readback(account, token, script, f"versions/{before[1]}")
    if version.get("id") != before[1]:
        raise ValueError("split_role_boundary_unverified")
    facts = role_capabilities(version)
    if any(value is not False for key, value in facts.items() if key != "handlers"):
        raise ValueError("split_role_boundary_unverified")
    schedules = capture.readback(account, token, script, "schedules").get("schedules")
    if not isinstance(schedules, list) or any(not isinstance(row, dict) or not isinstance(row.get("cron"), str) for row in schedules):
        raise ValueError("split_role_boundary_unverified")
    if serving_deployment(capture.readback(account, token, script, "deployments?per_page=1&page=1")) != before:
        raise ValueError("split_role_boundary_unverified")
    return {"serving": before, "capabilities": facts, "crons": [row["cron"] for row in schedules]}


def failure_reason(error: Exception) -> str:
    """Project only known structural labels, never provider bodies or values."""
    return str(error) if isinstance(error, ValueError) and str(error) in FAILURES else "unknown"


def serving(account: str, token: str, pins: dict[str, str]) -> dict:
    """Preserve deployment IDs as well as exact single-version percentages."""
    result = {}
    for script, expected in pins.items():
        pin = serving_deployment(capture.readback(account, token, script, "deployments?per_page=1&page=1"))
        if pin is None or pin[1] != expected:
            raise ValueError("split_serving_unverified")
        result[script] = pin
    return result


def held_send(realm: str) -> None:
    """Use existing realm-aware held-send guard; no gate or ledger is changed."""
    import subprocess
    result = subprocess.run([sys.executable, str(ROOT / "infra/operator/check_send_hold.py"), "--target", realm],
                            cwd=ROOT, capture_output=True, text=True, timeout=90, check=False)
    if result.returncode or len(result.stdout) + len(result.stderr) > 262144:
        raise ValueError("split_hold_unverified")


def global_policy() -> dict:
    """Read the exact existing production global policy without changing its state.

    Only normal active-split replacement uses this contract. Historical activation
    and staging paths continue to require the established held-send guard.
    """
    sys.path.insert(0, str(ROOT / "infra/operator"))
    from direct_contact_health import DatabaseClient, one_row
    row = one_row(DatabaseClient(os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
                                os.getenv("CLOUDFLARE_API_TOKEN", ""), "production")
                  .query("SELECT * FROM send_policy WHERE scope='global'"))
    if (set(row) != {"scope", "owner_iss", "owner_sub", "state", "reason_code", "actor", "note_ref", "updated_at"}
            or row["scope"] != "global" or row["owner_iss"] != "*" or row["owner_sub"] != "*"
            or row["state"] not in ("allowed", "held") or type(row["updated_at"]) is not int or row["updated_at"] < 0
            or any(not isinstance(row[key], str) or not 1 <= len(row[key]) <= 256 for key in ("reason_code", "actor"))
            or row["note_ref"] is not None and (not isinstance(row["note_ref"], str) or len(row["note_ref"]) > 256)):
        raise ValueError("split_policy_unverified")
    return row


def direct_forward_snapshot(realm: str, account: str, token: str) -> object:
    """Production retains exact four direct forwards; staging uses existing ingress graph.

    Neither realm acquires historical role routing. Staging has no production
    contact forwards and is statically pinned to its existing API service target.
    """
    if realm == "production":
        from check_production_role_graph import forward_snapshot, role_absent
        role_absent(account, token)
        return forward_snapshot(account)
    from check_staging import check
    check()
    from check_production_role_graph import role
    rows = role.api_get(f"/accounts/{account}/workers/scripts", token)
    if (not isinstance(rows, list) or len(rows) > 10000
            or not all(isinstance(row, dict) and isinstance(row.get("id"), str) for row in rows)
            or len({row["id"] for row in rows}) != len(rows)):
        raise ValueError("split_role_absence_unverified")
    if any(row["id"] == "amail-role-monitor-staging" for row in rows):
        return independent_role_snapshot(account, token)
    return {"role": None}


def verify(realm: str, state: str, *, old_crons: tuple[str, ...] = (), expected_policy: dict | None = None) -> dict:
    """Require exact selected graph, independent privacy and unchanged serving brackets."""
    if expected_policy is not None and (realm != "production" or state != "active" or old_crons):
        raise ValueError("split_policy_unverified")

    def check_policy() -> None:
        """Preserve every global policy field, or retain the historical hold gate."""
        if expected_policy is None:
            held_send(realm)
        elif global_policy() != expected_policy:
            raise ValueError("split_policy_unverified")

    legacy = state == "legacy-pinned"
    if not legacy:
        expected_schedules(state)
    api_config(realm)
    if state not in ("legacy-pinned", "prepared", "paused", "active", "old-draining", "new-draining") or old_crons not in ((), CADENCE):
        raise ValueError("split_graph_state_unreviewed")
    account, token = os.getenv("CLOUDFLARE_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_API_TOKEN", "")
    queue, dlq = os.getenv("AMAIL_TRACE_QUEUE_ID", ""), os.getenv("AMAIL_TRACE_DLQ_ID", "")
    api, maintenance = script_name(realm, maintenance=False), script_name(realm)
    sink = "amail-trace-sink" + ("-staging" if realm == "staging" else "")
    pins = {api: os.getenv("AMAIL_EXPECTED_WORKER_VERSION", ""),
            sink: os.getenv("AMAIL_EXPECTED_TRACE_SINK_VERSION", "")}
    if not legacy:
        pins[maintenance] = os.getenv("AMAIL_EXPECTED_MAINTENANCE_VERSION", "")
    topology = "api-only" if legacy else "api-scheduled"
    if (ACCOUNT.fullmatch(account) is None or not token or ACCOUNT.fullmatch(queue) is None
            or ACCOUNT.fullmatch(dlq) is None or queue == dlq
            or os.getenv("AMAIL_TRACE_TOPOLOGY") != topology
            or any(UUID.fullmatch(value) is None for value in pins.values())
            or os.getenv("AMAIL_EXPECTED_ROLE_WORKER_VERSION", "")
            or os.getenv("AMAIL_ROLE_ROUTED_COUNT", "") not in ("", "0")):
        raise ValueError("split_pins_unverified")
    before = serving(account, token, pins)
    check_policy()
    forwards = direct_forward_snapshot(realm, account, token)
    queues.reconcile(account, token, realm, "readback", topology)
    version = capture.readback(account, token, api, f"versions/{pins[api]}")
    api_crons = old_crons if state in ("legacy-pinned", "prepared") else ()
    # Legacy mixed code is a pinned migration predecessor, never a normal deploy.
    if (not bindings_match(version, pins[api], phase="queue-api", queue_id=queue, realm=realm)
            or (state not in ("legacy-pinned", "prepared") and not entry_surface_match(version, pins[api], "fetch"))
            or not schedules_match(capture.readback(account, token, api, "schedules"), api_crons)):
        raise ValueError("split_api_unverified")
    if not capture.verify(realm, account, token) or not capture.verify(realm, account, token, sink=True):
        raise ValueError("split_privacy_unverified")
    if legacy:
        maintenance_absent(account, token, maintenance)
    else:
        maintenance_verify(realm, state, account, token, pins[maintenance], queue, api_crons=api_crons)
    queues.reconcile(account, token, realm, "readback", topology)
    check_policy()
    if direct_forward_snapshot(realm, account, token) != forwards or serving(account, token, pins) != before:
        raise ValueError("split_graph_changed")
    return {"pins": before, "api_crons": list(api_crons),
            "maintenance_crons": list(CADENCE) if state == "active" else [], "topology": topology}


def maintenance_absent(account: str, token: str, script: str) -> None:
    """Preparation selects successful complete absence; a failed GET never means absent."""
    from check_production_role_graph import role
    rows = role.api_get(f"/accounts/{account}/workers/scripts", token)
    if (not isinstance(rows, list) or len(rows) > 10000
            or not all(isinstance(row, dict) and isinstance(row.get("id"), str) for row in rows)
            or len({row["id"] for row in rows}) != len(rows) or any(row["id"] == script for row in rows)):
        raise ValueError("maintenance_absence_unverified")


def main() -> int:
    """Emit fixed labels only; no provider IDs/body or inferred release state."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--realm", choices=("production", "staging"), required=True)
    parser.add_argument("--state", choices=("paused", "active", "old-draining", "new-draining"), required=True)
    parser.add_argument("--diagnostic", action="store_true", help="Emit a closed staging failure reason without provider prose")
    args = parser.parse_args()
    if args.diagnostic and args.realm != "staging":
        parser.error("diagnostic is staging-only")
    try:
        verify(args.realm, args.state)
    except (ValueError, KeyError, TypeError, OSError) as error:
        print("mail_split_graph=UNVERIFIED" + (f" reason={failure_reason(error)}" if args.diagnostic else ""))
        return 1
    print("mail_split_graph=exact_selected_graph population_isolation=UNVERIFIED drain=UNVERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
