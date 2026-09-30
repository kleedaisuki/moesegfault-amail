"""Authorize production graph bootstrap versus strict api-role maintenance.

The lifecycle is explicit and cannot be selected from a provider's latest
inventory. Bootstrap rejects an existing API or role; partial first-deploy
recovery requires a separately reviewed reconciliation rather than replay.
"""
from __future__ import annotations
import argparse
import os
import subprocess
from check_production_role_graph import API, ROLE, ID, role, forwards, role_absent, forward_snapshot, storage, held_send, verify


def prepare(phase: str) -> None:
    """Stop a wrong graph phase before Queue creation, sink replacement or API migration."""
    if os.getenv("GITHUB_REF") != "refs/heads/main" or os.getenv("AMAIL_PRODUCTION_GRAPH_FREEZE") != "FREEZE_PRODUCTION_GRAPH_WRITERS":
        raise ValueError("writer_freeze_unverified")
    expected = {"bootstrap": "RUN_PRODUCTION_API_ONLY_BOOTSTRAP", "api-role-maintenance": "RUN_PRODUCTION_API_ROLE_MAINTENANCE"}
    if phase not in expected or os.getenv("AMAIL_PRODUCTION_GRAPH_CONFIRM") != expected[phase]:
        raise ValueError("phase_unverified")
    if phase == "api-role-maintenance":
        verify("maintenance", "replacement")
        return
    account, token = os.getenv("CLOUDFLARE_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_API_TOKEN", "")
    if ID.fullmatch(account) is None or not token or os.getenv("AMAIL_TRACE_TOPOLOGY") != "api-only":
        raise ValueError("bootstrap_unverified")
    held_send()
    before = role.api_get(f"/accounts/{account}/workers/scripts", token)
    if (not isinstance(before, list) or len(before) > 10000
            or not all(isinstance(row, dict) and isinstance(row.get("id"), str) for row in before)
            or len({row["id"] for row in before}) != len(before)
            or any(row["id"] in (API, ROLE) for row in before)):
        raise ValueError("bootstrap_absence_unverified")
    # A sink from a partial bootstrap is reconciled by the exact Queue ownership
    # checker; never interpret a previously live API as a first bootstrap.
    snapshot = forward_snapshot(account)
    storage("first-bootstrap")
    role_absent(account, token)
    if forward_snapshot(account) != snapshot:
        raise ValueError("bootstrap_routes_changed")


def main() -> int:
    """Emit one fixed outcome without confidential destination or provider data."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("bootstrap", "api-role-maintenance"), required=True)
    args = parser.parse_args()
    try:
        prepare(args.phase)
    except (ValueError, RuntimeError, KeyError, TypeError, OSError, subprocess.TimeoutExpired, forwards.ProvisionError):
        print("production_graph_prepare=UNVERIFIED")
        return 1
    print("production_graph_prepare=explicit_phase_verified")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
