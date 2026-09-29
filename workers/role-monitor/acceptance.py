"""Guard one staging-only SMTP role-mail probe and leave its exact route absent.

This is an operator tool, not a CI deployment step. It submits at most one
message; rerunning after an ambiguous SMTP or forwarding result is unsafe.
Only fixed status labels are emitted, never provider bodies, mail or secrets.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
MARKER = ROOT / ".temp" / "role-monitor-acceptance" / "route-open.marker"
ORACLE_DIR = MARKER.parent
ZONE = "6edff81c6ed02f412e70868076411a5e"
ROLES = frozenset({
    "abuse@moesegfault.dev", "postmaster@moesegfault.dev",
    "abuse@mail.moesegfault.dev", "postmaster@mail.moesegfault.dev",
})


class ProbeError(Exception):
    """A fixed, privacy-safe stage label suitable for an operator ledger."""


def load(name: str, relative: str):
    """Reuse reviewed provider and SMTP helpers without copying their contracts."""

    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise ProbeError("helper_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROUTE = load("role_route", "workers/role-monitor/staging_route.py")
AUDIT = load("role_audit", "infra/deploy/verify_role_monitor_staging.py")
SMTP = load("role_smtp", "infra/tests/staging_mail_e2e.py")


def require(ok: bool, label: str) -> None:
    """Fail closed without interpolating provider or message content."""

    if not ok:
        raise ProbeError(label)


def credentials(send: bool = False) -> tuple[str, str, str]:
    """Require explicit staging-scoped credentials without printing values."""

    zone = os.environ.get("CF_ZONE_ID", "")
    routing = os.environ.get("CF_EMAIL_ROUTING_TOKEN", "")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    require(zone == ZONE and bool(routing) and len(account) == 32, "credentials_unavailable")
    require(bool(os.environ.get("CLOUDFLARE_API_TOKEN")), "audit_credential_unavailable")
    if send:
        require(bool(os.environ.get("AMAIL_TEST_SMTP_TOKEN")), "smtp_credential_unavailable")
    return zone, routing, account


def standard_rules(zone: str, token: str) -> dict[str, tuple[str, str]]:
    """Read four exact direct-forward rules; preserve ID and target in memory."""

    found: dict[str, tuple[str, str]] = {}
    targets: set[str] = set()
    for rule in ROUTE.rules(zone, token):
        matchers = rule.get("matchers")
        if not isinstance(matchers, list):
            raise ProbeError("standard_rule_inventory_invalid")
        touched = [m.get("value") for m in matchers if isinstance(m, dict)
                   and m.get("type") == "literal" and m.get("field") == "to"
                   and m.get("value") in ROLES]
        if not touched:
            continue
        require(len(touched) == 1 and touched[0] not in found, "standard_rule_conflict")
        actions = rule.get("actions")
        require(rule.get("enabled") is True and rule.get("source") == "api"
                and matchers == [{"type": "literal", "field": "to", "value": touched[0]}]
                and isinstance(actions, list) and len(actions) == 1
                and isinstance(actions[0], dict) and actions[0].get("type") == "forward",
                "standard_rule_not_direct_forward")
        value = actions[0].get("value")
        require(isinstance(value, list) and len(value) == 1 and isinstance(value[0], str)
                and isinstance(rule.get("id"), str), "standard_rule_target_invalid")
        found[touched[0]] = (rule["id"], value[0])
        targets.add(value[0])
    require(found.keys() == ROLES and len(targets) == 1, "standard_rules_differ")
    return found


def row(sql: str) -> dict:
    """Read one aggregate remote D1 row; no IDs or source content are queried."""

    result = AUDIT.d1_query(sql)
    require(len(result) == 1 and isinstance(result[0], dict), "role_d1_shape_invalid")
    return result[0]


def baseline() -> int:
    """Permit historical resolved rows but not unresolved or unalerted work."""

    state = row(
        "SELECT COUNT(*) AS n, COALESCE(MAX(arrival_seq),0) AS seq, "
        "SUM(CASE WHEN forward_state='unknown' THEN 1 ELSE 0 END) AS unknown_n, "
        "SUM(CASE WHEN alerted_at IS NULL THEN 1 ELSE 0 END) AS unalerted_n "
        "FROM role_arrivals"
    )
    require(type(state.get("seq")) is int and state["seq"] >= 0
            and state.get("unknown_n") in (None, 0)
            and state.get("unalerted_n") in (None, 0), "role_d1_not_clean")
    return state["seq"]


def preflight(zone: str, routing: str, account: str) -> tuple[dict[str, tuple[str, str]], int]:
    """Check deployed privacy/bindings, exact route absence, and prior D1 state."""

    token = os.environ["CLOUDFLARE_API_TOKEN"]
    base = f"/accounts/{account}/workers/scripts/amail-role-monitor-staging"
    settings = AUDIT.api_get(f"{base}/settings", token)
    script = AUDIT.api_get(f"{base}/script-settings", token)
    AUDIT.inspect_bindings(settings)
    AUDIT.inspect_observability(script, settings)
    AUDIT.inspect_surfaces(
        AUDIT.api_get(f"{base}/subdomain", token),
        AUDIT.api_get(f"/zones/{zone}/workers/routes", token),
        AUDIT.api_get(f"/accounts/{account}/workers/domains?service=amail-role-monitor-staging", token),
    )
    require(ROUTE.reconcile(zone, routing, "audit") == "absent", "synthetic_route_not_absent")
    require(not MARKER.exists(), "prior_route_marker_requires_recovery")
    rules = standard_rules(zone, routing)
    return rules, baseline()


def arm_marker() -> None:
    """Write a crash-recovery marker before attempting any route mutation."""

    MARKER.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = os.open(MARKER, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ProbeError("prior_route_marker_requires_recovery") from None
    with os.fdopen(handle, "w", encoding="ascii") as output:
        output.write('{"version":1,"route_id":null}\n')
        output.flush()
        os.fsync(output.fileno())


def marker_id() -> str | None:
    """Read the private provider ID; an unknown ID never authorizes deletion."""

    try:
        raw = MARKER.read_bytes()
        require(len(raw) <= 512, "route_marker_invalid")
        value = json.loads(raw)
    except (OSError, ValueError):
        raise ProbeError("route_marker_invalid") from None
    require(isinstance(value, dict) and value.get("version") == 1, "route_marker_invalid")
    route_id = value.get("route_id")
    require(route_id is None or isinstance(route_id, str), "route_marker_invalid")
    return route_id


def record_id(route_id: str) -> None:
    """Atomically upgrade the crash marker after provider ID-bound readback."""

    temporary = MARKER.with_name(f"route-open-{secrets.token_hex(8)}.tmp")
    try:
        with os.fdopen(os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w", encoding="ascii") as output:
            json.dump({"version": 1, "route_id": route_id}, output, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, MARKER)
    finally:
        temporary.unlink(missing_ok=True)


def cleanup(zone: str, routing: str, before: dict[str, tuple[str, str]], route_id: str | None) -> None:
    """Remove only the recorded ID, or merely audit absence when ID is unknown."""

    if route_id is not None:
        try:
            result = ROUTE.remove_if_id(zone, routing, route_id)
        except Exception:
            raise ProbeError("route_id_remove_failed") from None
        require(result in ("removed", "absent"), "route_id_remove_unexpected")
    try:
        absent = ROUTE.reconcile(zone, routing, "audit") == "absent"
        same = standard_rules(zone, routing) == before
    except Exception:
        raise ProbeError("route_cleanup_readback_failed") from None
    require(absent, "route_cleanup_not_absent")
    require(same, "standard_rules_changed")
    # A create timeout can race provider propagation. Require a second inventory
    # after the same observed propagation wait used before SMTP submission.
    time.sleep(60)
    try:
        stable = ROUTE.reconcile(zone, routing, "audit") == "absent"
        same = standard_rules(zone, routing) == before
    except Exception:
        raise ProbeError("route_cleanup_late_readback_failed") from None
    require(stable, "route_cleanup_late_rule")
    require(same, "standard_rules_changed")
    MARKER.unlink(missing_ok=True)


def message() -> EmailMessage:
    """Build one private synthetic RFC 5322 probe, never a user report."""

    nonce = secrets.token_hex(12)
    result = EmailMessage()
    result["From"] = SMTP.SENDER
    result["To"] = ROUTE.ALIAS
    result["Subject"] = f"Role monitor staging probe {nonce}"
    result["Message-ID"] = f"<amail-role-{nonce}@{SMTP.DOMAIN}>"
    result["Date"] = format_datetime(datetime.now(timezone.utc))
    result.set_content(f"Synthetic role monitor acceptance only. Reference {nonce}.\n")
    # Keep the private oracle in the repository's ignored .temp, not in stdout.
    ORACLE_DIR.mkdir(parents=True, exist_ok=True)
    oracle = ORACLE_DIR / f"smtp-oracle-{secrets.token_hex(8)}.private"
    with os.fdopen(os.open(oracle, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w", encoding="ascii") as output:
        output.write(nonce + "\n")
        output.flush()
        os.fsync(output.fileno())
    return result


def arrival(baseline_seq: int) -> dict:
    """Query only current-run state counts, not mail fields or opaque references."""

    return row(
        "SELECT COUNT(*) AS n, "
        "SUM(CASE WHEN role='staging_probe' AND forward_state='accepted' THEN 1 ELSE 0 END) AS accepted_n, "
        "SUM(CASE WHEN forward_state='unknown' THEN 1 ELSE 0 END) AS unknown_n, "
        "SUM(CASE WHEN alerted_at IS NULL THEN 1 ELSE 0 END) AS unalerted_n, "
        "SUM(CASE WHEN length(id)!=36 OR received_at<=0 THEN 1 ELSE 0 END) AS malformed_n "
        f"FROM role_arrivals WHERE arrival_seq>{baseline_seq}"
    )


def poll(baseline_seq: int, submitted_ms: int) -> tuple[bool, bool]:
    """Allow transient unknown, then require durable accepted/alerted and live lease.

    D1 heartbeat is not a Cloudflare Cron Past Events oracle, and neither it nor
    SMTP submission proves provider forwarding or destination Inbox placement.
    """

    deadline = time.monotonic() + 900
    unknown_deadline: float | None = None
    saw_unalerted = False
    while time.monotonic() < deadline:
        state = arrival(baseline_seq)
        require(state.get("n") in (0, 1) and state.get("malformed_n") in (None, 0),
                "role_arrival_unexpected")
        if state["n"] == 1:
            if state.get("unknown_n") == 1:
                unknown_deadline = unknown_deadline or time.monotonic() + 120
                require(time.monotonic() < unknown_deadline, "role_forward_persistently_unknown")
                time.sleep(5)
                continue
            require(state.get("accepted_n") == 1 and state.get("unknown_n") == 0,
                    "role_forward_not_accepted")
            saw_unalerted |= state.get("unalerted_n") == 1
            if state.get("unalerted_n") == 0:
                health = row("SELECT lease_until, checked_at FROM role_monitor_health WHERE singleton=1")
                if (type(health.get("checked_at")) is int and health["checked_at"] >= submitted_ms
                        and type(health.get("lease_until")) is int
                        and health["lease_until"] > int(time.time() * 1000)):
                    return saw_unalerted, True
        time.sleep(10)
    raise ProbeError("role_arrival_or_cron_timeout")


def recover(zone: str, routing: str) -> None:
    """Close only a recorded ID; unknown ownership permits absence audit only."""

    require(MARKER.exists(), "no_route_marker")
    route_id = marker_id()
    before = standard_rules(zone, routing)
    cleanup(zone, routing, before, route_id)


def main() -> int:
    """Run preflight, one guarded SMTP probe, or explicit crash recovery."""

    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--confirm-staging-smtp", action="store_true")
    mode.add_argument("--recover-exact-route", action="store_true")
    args = parser.parse_args()
    armed = False
    created_id: str | None = None
    failure: str | None = None
    cleanup_failure: str | None = None
    before: dict[str, tuple[str, str]] | None = None
    try:
        zone, routing, account = credentials(send=args.confirm_staging_smtp)
        if args.recover_exact_route:
            recover(zone, routing)
            print("route=absent; recovery=complete")
            return 0
        before, seq = preflight(zone, routing, account)
        print("preflight=passed", flush=True)
        if args.preflight:
            print("smtp_sender=not_checked; no_route_created")
            return 0
        SMTP.assert_staging_sender(zone, os.environ["AMAIL_TEST_SMTP_TOKEN"])
        arm_marker()
        armed = True  # A timed-out create may still have reached the provider.
        created_id = ROUTE.create_owned(zone, routing)
        record_id(created_id)
        require(ROUTE.reconcile(zone, routing, "audit") == "enabled", "route_not_enabled")
        print("route=enabled", flush=True)
        time.sleep(60)
        require(ROUTE.reconcile(zone, routing, "audit") == "enabled", "route_propagation_drift")
        submitted_ms = int(time.time() * 1000)
        try:
            SMTP.smtp_send(os.environ["AMAIL_TEST_SMTP_TOKEN"], ROUTE.ALIAS, [message()])
        except Exception:
            raise ProbeError("smtp_submission_failed_or_ambiguous") from None
        print("smtp=submitted; receipt=not_proven", flush=True)
        saw_unalerted, lease = poll(seq, submitted_ms)
        print(f"d1_forward=accepted; d1_alerted=yes; d1_unalerted_seen={'yes' if saw_unalerted else 'no'}; "
              f"lease_fresh={'yes' if lease else 'no'}", flush=True)
        print("cron_past_events=not_checked; provider_forward=not_checked; "
              "provider_alert=not_checked; external_inbox=not_checked", flush=True)
    except Exception as error:
        failure = str(error) if isinstance(error, ProbeError) else "probe_unexpected_failure"
    finally:
        if armed and before is not None and created_id is not None:
            try:
                cleanup(zone, routing, before, created_id)
                print("route=absent", flush=True)
            except Exception as error:
                cleanup_failure = str(error) if isinstance(error, ProbeError) else "route_cleanup_unexpected"
                print("route_cleanup=failed; freeze staging; run explicit exact-route recovery",
                      file=sys.stderr, flush=True)
        elif armed:
            cleanup_failure = "route_ownership_ambiguous"
            print("route_cleanup=not_attempted; freeze staging; audit exact-route owner",
                  file=sys.stderr, flush=True)
    if failure or cleanup_failure:
        print(f"acceptance=failed; stage={failure or 'none'}; cleanup={cleanup_failure or 'none'}",
              file=sys.stderr)
        return 1
    print("acceptance=machine_d1_only; smtp=submitted; external_oracles=not_checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
