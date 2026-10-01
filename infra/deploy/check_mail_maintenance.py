"""Closed scheduled-only Mail source and immutable capability contracts.

This checker does not deploy, probe HTTP, migrate data, infer a transition from
inventory, or admit drain/privacy/resources. Provider reads select fixed names.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "crates/mail-worker"))
import check_observability as capture
from pin_staging_mail import ACCOUNT, UUID, _bindings_match, mail_resources, serving_deployment

REALMS = ("production", "staging")
SECRETS = ("CF_EMAIL_ROUTING_TOKEN", "OPENROUTER_API_KEY")
VARS = ("CF_ZONE_ID", "EMAIL_INGRESS_WORKER_NAME", "OPENROUTER_EMBEDDING_MODEL")
CADENCE = ("*/5 * * * *",)
STATES = ("legacy-pinned", "prepared", "old-draining", "paused", "active", "new-draining", "legacy-recovery")


def script_name(realm: str, *, maintenance: bool = True) -> str:
    """Select only the reviewed two names; no arbitrary script input exists."""
    if realm not in REALMS:
        raise ValueError("realm_unreviewed")
    return "amail-mail" + ("-maintenance" if maintenance else "") + ("-staging" if realm == "staging" else "")


def config_realm(path: Path, realm: str) -> dict:
    """Read explicit realm data; capability arrays and vars never inherit."""
    script_name(realm)
    with path.open("rb") as source:
        config = tomllib.load(source)
    return config if realm == "production" else config["env"]["staging"]


def api_config(realm: str) -> dict:
    """Every normal API config/rollback retains an explicitly empty trigger set."""
    path = ROOT / "crates/mail-worker/wrangler.toml"
    selected = config_realm(path, realm)
    with path.open("rb") as source:
        root = tomllib.load(source)
    if root.get("main") != "entry/api.mjs" or selected.get("triggers") != {"crons": []}:
        raise ValueError("api_schedule_unreviewed")
    return selected


def maintenance_config(realm: str, *, active: bool = False) -> dict:
    """Require same-realm state and only reviewed non-send maintenance capabilities."""
    path = ROOT / "crates/mail-worker/wrangler-maintenance.toml"
    selected = config_realm(path, realm)
    allowed = {"name", "main", "compatibility_date", "workers_dev", "preview_urls", "routes", "logpush",
               "vars", "d1_databases", "r2_buckets", "queues", "version_metadata", "triggers", "observability", "env"}
    api = api_config(realm)
    with path.open("rb") as source:
        root = tomllib.load(source)
    if (set(selected) - allowed or selected.get("name") != script_name(realm)
            or root.get("main") != "entry/maintenance.mjs"
            or selected.get("compatibility_date") != "2026-09-25"
            or selected.get("workers_dev") is not False or selected.get("preview_urls") is not False
            or selected.get("logpush") is not False or selected.get("routes") != []
            or not capture.safe_observability(selected.get("observability"))
            or selected.get("triggers") != {"crons": list(CADENCE) if active else []}
            or selected.get("vars") != {name: api["vars"][name] for name in VARS}
            or mail_resources(selected) != mail_resources(api)
            or selected.get("version_metadata") != {"binding": "VERSION_METADATA"}
            or selected.get("queues") != {"producers": [{"binding": "TRACE_EVENTS", "queue":
                  "amail-trace-events" + ("-staging" if realm == "staging" else "")}]}):
        raise ValueError("maintenance_config_unreviewed")
    return selected


def reject_inbound_bindings() -> None:
    """Scan tracked application configuration only, not an account-wide crawl.

    Dashboard/out-of-band caller creation still requires an operational freeze;
    static absence is not account-wide population-isolation evidence.
    """
    names = {script_name(realm) for realm in REALMS}
    for folder in ("crates", "workers"):
        for path in (ROOT / folder).glob("*/wrangler*.toml"):
            with path.open("rb") as source:
                config = tomllib.load(source)
            realms = [config, *config.get("env", {}).values()]
            for selected in realms:
                if any(binding.get("service") in names for binding in selected.get("services", [])):
                    raise ValueError("maintenance_caller_unreviewed")


def check_source_configs() -> None:
    """Validate each realm's checked-in desired pause/cadence, never infer live state."""
    path = ROOT / "crates/mail-worker/wrangler-maintenance.toml"
    for realm in REALMS:
        desired = config_realm(path, realm).get("triggers")
        if desired not in ({"crons": []}, {"crons": list(CADENCE)}):
            raise ValueError("maintenance_schedule_unreviewed")
        maintenance_config(realm, active=desired == {"crons": list(CADENCE)})
    reject_inbound_bindings()


def expected_bindings(realm: str, queue_id: str, *, active: bool = False) -> dict:
    """Immutable readback checks exact names/types/resources; secret values stay private."""
    if ACCOUNT.fullmatch(queue_id) is None:
        raise ValueError("queue_pin_unreviewed")
    selected = maintenance_config(realm, active=active)
    database, bucket = mail_resources(selected)
    return {"MAIL_DB": ("d1", database), "MAIL_BODIES": ("r2_bucket", bucket),
            "TRACE_EVENTS": ("queue", queue_id), "VERSION_METADATA": ("version_metadata", None),
            **{name: ("secret_text", None) for name in SECRETS},
            **{name: ("plain_text", selected["vars"][name]) for name in VARS}}


def schedules_match(result: object, expected: tuple[str, ...] = ()) -> bool:
    """Require the complete documented result.schedules list, never omitted-as-empty."""
    if not isinstance(result, dict) or set(result) != {"schedules"}:
        return False
    rows = result["schedules"]
    return (isinstance(rows, list) and len(rows) == len(expected)
            and all(isinstance(row, dict) and set(row) <= {"cron", "created_on", "modified_on"}
                    and isinstance(row.get("cron"), str) for row in rows)
            and sorted(row["cron"] for row in rows) == sorted(expected))


def entry_surface_match(version: object, expected: str, handler: str) -> bool:
    """Immutable upload exposes exactly one handler and no named RPC entrypoint."""
    if not isinstance(version, dict) or version.get("id") != expected:
        return False
    resources = version.get("resources")
    script = resources.get("script") if isinstance(resources, dict) else None
    return (isinstance(script, dict) and script.get("handlers") == [handler]
            and script.get("named_handlers", []) == [])


def expected_schedules(state: str) -> tuple[str, ...]:
    """Only stable split states are normal replacement contracts, not drain/recovery."""
    if state not in ("prepared", "old-draining", "paused", "active", "new-draining"):
        raise ValueError("split_state_unreviewed")
    return CADENCE if state == "active" else ()


def verify(realm: str, state: str, account: str, token: str, version: str, queue_id: str,
           *, api_crons: tuple[str, ...] = ()) -> None:
    """Bracket the exact serving deployment around immutable and non-versioned reads.

    Routes/domains/callers are checked by the enclosing realm graph, not inferred
    from a failed fetch; this function never claims complete population isolation.
    """
    cadence = expected_schedules(state)
    expected = expected_bindings(realm, queue_id, active=state == "active")
    if ACCOUNT.fullmatch(account) is None or not token or UUID.fullmatch(version) is None:
        raise ValueError("maintenance_pin_unreviewed")
    script = script_name(realm)
    read = lambda suffix: capture.readback(account, token, script, suffix)
    first = serving_deployment(read("deployments?per_page=1&page=1"))
    if first is None or first[1] != version:
        raise ValueError("maintenance_serving_unverified")
    immutable = read(f"versions/{version}")
    if not _bindings_match(immutable, version, expected) or not entry_surface_match(immutable, version, "scheduled"):
        raise ValueError("maintenance_bindings_unverified")
    settings, script_settings = read("settings"), read("script-settings")
    worker = capture.worker_readback(account, token, script)
    if not capture.effective_api_settings(worker, script, settings, script_settings):
        raise ValueError("maintenance_privacy_unverified")
    subdomain = read("subdomain")
    if subdomain.get("enabled") is not False or subdomain.get("previews_enabled") is not False:
        raise ValueError("maintenance_surface_unverified")
    public_surfaces_absent(account, token, script)
    if not schedules_match(read("schedules"), cadence):
        raise ValueError("maintenance_schedule_unverified")
    api = script_name(realm, maintenance=False)
    if api_crons not in ((), CADENCE) or not schedules_match(capture.readback(account, token, api, "schedules"), api_crons):
        raise ValueError("api_schedule_unverified")
    if serving_deployment(read("deployments?per_page=1&page=1")) != first:
        raise ValueError("maintenance_deployment_changed")


def public_surfaces_absent(account: str, token: str, script: str) -> None:
    """Reuse the established bounded domain/route reader without crawling caller bindings."""
    import check_trace_sink_isolation as isolation
    if any(row["service"] == script for row in isolation.worker_domains(account, token)):
        raise ValueError("maintenance_surface_unverified")
    zones = isolation.inventory(token, f"/zones?account.id={account}&type=full,partial,secondary,internal")
    if not zones or len(zones) > 20:
        raise ValueError("maintenance_surface_unverified")
    for zone in zones:
        if not isinstance(zone.get("account"), dict) or zone["account"].get("id") != account:
            raise ValueError("maintenance_surface_unverified")
        envelope = isolation.envelope(token, f"/zones/{zone['id']}/workers/routes")
        routes = envelope.get("result")
        if (not isinstance(routes, list) or len(routes) > 1000 or envelope.get("result_info") not in (None, {})
                or not all(isinstance(row, dict) and isinstance(row.get("id"), str)
                           and ACCOUNT.fullmatch(row["id"]) and isinstance(row.get("pattern"), str)
                           and (row.get("script") is None or isinstance(row["script"], str)) for row in routes)
                or len({row["id"] for row in routes}) != len(routes)
                or any(row.get("script") == script for row in routes)):
            raise ValueError("maintenance_surface_unverified")


def main() -> int:
    """Default source checks require no credentials and make no provider calls."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--realm", choices=REALMS)
    parser.add_argument("--state", choices=STATES, default="paused")
    parser.add_argument("--readback", action="store_true")
    args = parser.parse_args()
    try:
        check_source_configs()
        if args.readback:
            if not args.realm:
                raise ValueError("realm_unreviewed")
            verify(args.realm, args.state, os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
                   os.getenv("CLOUDFLARE_API_TOKEN", ""), os.getenv("AMAIL_EXPECTED_MAINTENANCE_VERSION", ""),
                   os.getenv("AMAIL_TRACE_QUEUE_ID", ""))
    except (ValueError, KeyError, TypeError, OSError):
        print("mail_maintenance_contract=UNVERIFIED")
        return 1
    print("mail_maintenance_contract=verified readback=" + ("selected" if args.readback else "not_requested"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
