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
            or len({row["id"] for row in rows}) != len(rows)
            or any(row["id"] == "amail-role-monitor-staging" for row in rows)):
        raise ValueError("split_role_absence_unverified")
    return "staging-direct"


def verify(realm: str, state: str, *, old_crons: tuple[str, ...] = ()) -> dict:
    """Require exact selected graph, independent privacy and unchanged serving brackets."""
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
    held_send(realm)
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
    held_send(realm)
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
    args = parser.parse_args()
    try:
        verify(args.realm, args.state)
    except (ValueError, KeyError, TypeError, OSError):
        print("mail_split_graph=UNVERIFIED")
        return 1
    print("mail_split_graph=exact_selected_graph population_isolation=UNVERIFIED drain=UNVERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
