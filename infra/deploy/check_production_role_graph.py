"""Read-only direct-only production graph and historical role research gates.

Queue ownership, serving deployments, independent capture switches and four
forwards are bracketed. Absence is a complete successful script inventory, never
a failed GET. No function mutates routing, storage, settings or sending policy.
The active v0.1 phase is api-only. Historical role phases are not release
authorization and must not be called by the current production promotion.
"""
from __future__ import annotations
import argparse
import os
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "crates/mail-worker"))
sys.path.insert(0, str(ROOT / "infra/provider"))
sys.path.insert(0, str(Path(__file__).parent))
import check_observability as capture
import ensure_trace_queues as queues
import ensure_role_forwarding as forwards
import verify_role_monitor_staging as role
from pin_staging_mail import bindings_match, serving_deployment
from trace_rollout_attestation import UUID, ID

API, SINK, ROLE = "amail-mail", "amail-trace-sink", "amail-role-monitor"
DATABASE = "06e84adb-fe29-4183-b131-5042a48bcdee"


def query(binding: str, sql: str) -> list[dict]:
    """Read bounded production D1 through the reviewed binding, suppressing output."""
    import json
    folder = "workers/role-monitor" if binding == "ROLE_MONITOR" else "crates/mail-worker"
    result = subprocess.run(["wrangler", "d1", "execute", binding, "--remote", "--command", sql, "--json"],
                            cwd=ROOT / folder, capture_output=True, text=True, timeout=90, check=False)
    if result.returncode or len(result.stdout) + len(result.stderr) > 262144:
        raise ValueError("d1_unverified")
    try:
        envelope = json.loads(result.stdout)
        if not isinstance(envelope, list) or len(envelope) != 1 or envelope[0].get("success") is not True:
            raise ValueError("d1_unverified")
        rows = envelope[0]["results"]
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError("d1_unverified")
        return rows
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("d1_unverified") from error


SCHEMA_SQL = ("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE "
              "name NOT GLOB 'sqlite_*' AND NOT (type='table' AND name IN ('d1_migrations','_cf_KV'))")


def ddl_tokens(sql: str) -> tuple[str, ...]:
    """Compare conservative SQL tokens while preserving quoted literal semantics.

    SQLite may omit IF NOT EXISTS in stored CREATE text. Whitespace and keyword
    case are immaterial; changing types, defaults, constraints, index order,
    collations, predicates, quoted literal whitespace or identifiers is not.
    """
    if not isinstance(sql, str):
        raise ValueError("schema_sql_unverified")
    text = re.sub(r"\bIF\s+NOT\s+EXISTS\b", "", sql, flags=re.I).strip().rstrip(';')
    parts = re.findall(r"'(?:''|[^'])*'|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[^\s]", text)
    return tuple(part if part.startswith("'") else part.casefold() for part in parts)


def expected_schema() -> dict[str, tuple[str, tuple[str, ...]]]:
    """Derive exact production objects from the single reviewed additive migration."""
    text = (ROOT / "workers/role-monitor/migrations/0001_role_monitor.sql").read_text(encoding="utf-8")
    text = re.sub(r"--[^\n]*", "", text)
    result = {}
    for match in re.finditer(r"CREATE\s+(TABLE|INDEX)\s+IF\s+NOT\s+EXISTS\s+([a-z_]+)\b[^;]*", text, re.I):
        result[match[2]] = (match[1].lower(), ddl_tokens(match[0]))
    if set(result) != {"role_arrivals", "role_monitor_health", "role_arrivals_unalerted", "role_arrivals_forward"}:
        raise ValueError("reviewed_schema_unverified")
    return result


def exact_schema(rows: list[dict]) -> bool:
    """Reject extra views/triggers or drift in complete table/index DDL."""
    expected = expected_schema()
    if not isinstance(rows, list) or len(rows) != len(expected):
        return False
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("name") not in expected or row["name"] in seen:
            return False
        name = row["name"]
        seen.add(name)
        kind, tokens = expected[name]
        table = name if kind == "table" else "role_arrivals"
        if row.get("type") != kind or row.get("tbl_name") != table or ddl_tokens(row.get("sql")) != tokens:
            return False
    return seen == set(expected)


def storage(lifecycle: str) -> None:
    """First migration requires pristine storage; replacements require empty expired state."""
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location("production_role_schema", ROOT / "workers/role-monitor/check_staging_db.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    tables = query("ROLE_MONITOR", module.SQL)
    names = [row.get("name") for row in tables]
    if lifecycle == "first-bootstrap":
        if names or query("ROLE_MONITOR", SCHEMA_SQL):
            raise ValueError("bootstrap_storage_unverified")
        return
    if lifecycle not in ("replacement", "migrated", "maintenance") or len(names) != 2 or set(names) != module.ALLOWED:
        raise ValueError("schema_unverified")
    if not exact_schema(query("ROLE_MONITOR", SCHEMA_SQL)):
        raise ValueError("schema_unverified")
    if not module.valid_schema(query("ROLE_MONITOR", "PRAGMA table_info(role_arrivals)"),
                               query("ROLE_MONITOR", "PRAGMA table_info(role_monitor_health)")):
        raise ValueError("schema_unverified")
    indexes = query("ROLE_MONITOR", "SELECT name FROM sqlite_master WHERE type='index' AND name NOT GLOB 'sqlite_*' AND name NOT GLOB 'd1_*' AND name NOT GLOB '_cf_*'")
    if len(indexes) != 2 or {row.get("name") for row in indexes} != {"role_arrivals_unalerted", "role_arrivals_forward"}:
        raise ValueError("schema_unverified")
    if lifecycle == "maintenance":
        return  # API/sink replacement does not require erasing an operational ledger.
    if query("ROLE_MONITOR", "SELECT COUNT(*) AS n FROM role_arrivals") != [{"n": 0}]:
        raise ValueError("ledger_not_empty")
    state = query("ROLE_MONITOR", "SELECT singleton, lease_until, checked_at, lease_until <= unixepoch()*1000 AS expired FROM role_monitor_health")
    if (len(state) != 1 or set(state[0]) != {"singleton", "lease_until", "checked_at", "expired"}
            or state[0]["singleton"] != 1 or type(state[0]["lease_until"]) is not int
            or type(state[0]["checked_at"]) is not int or state[0]["expired"] != 1
            or state[0]["lease_until"] < 0 or state[0]["checked_at"] < 0):
        raise ValueError("lease_not_expired")
    if lifecycle == "migrated" and state != [{"singleton": 1, "lease_until": 0, "checked_at": 0, "expired": 1}]:
        raise ValueError("bootstrap_lease_unverified")


def held_send() -> None:
    """Require held global policy and unset role release gate without writing either."""
    if query("MAIL_DB", "SELECT state FROM send_policy WHERE scope='global' AND owner_iss='*' AND owner_sub='*'") != [{"state": "held"}]:
        raise ValueError("send_not_held")
    if query("MAIL_DB", "SELECT abuse_contact_verified FROM send_release_gates WHERE id=1") != [{"abuse_contact_verified": 0}]:
        raise ValueError("role_gate_not_held")


def role_absent(account: str, token: str) -> None:
    """Require documented successful SinglePage script inventory, not swallowed 404s."""
    rows = role.api_get(f"/accounts/{account}/workers/scripts", token)
    if (not isinstance(rows, list) or len(rows) > 10000
            or not all(isinstance(row, dict) and isinstance(row.get("id"), str) for row in rows)
            or len({row["id"] for row in rows}) != len(rows) or any(row["id"] == ROLE for row in rows)):
        raise ValueError("role_absence_unverified")


def forward_snapshot(account: str, *, switched: int = 0) -> dict:
    """Privately retain the four full shapes, verified destination and exact rule IDs."""
    destination, token = os.getenv("ROLE_FORWARD_DESTINATION", ""), os.getenv("CF_EMAIL_ROUTING_TOKEN", "")
    if not destination or not token:
        raise ValueError("role_config_unverified")
    client = forwards.Client(token, account)
    if forwards.destination_state(client, destination) != "verified":
        raise ValueError("destination_unverified")
    rules = forwards.rules(client)
    if switched == 0:
        if forwards.audit(rules, destination) != set(forwards.ROLES):
            raise ValueError("forward_unverified")
    else:
        from production_role_routes import snapshot
        snapshot(rules, destination, switched)
    result = {row.get("id", row.get("tag")): row for row in rules if forwards.matched_roles(row)}
    if len(result) != 4 or not all(isinstance(key, str) and key for key in result):
        raise ValueError("rule_identity_unverified")
    return result


def serving(account: str, token: str, pins: dict[str, str]) -> dict:
    """Require exact single-100 serving and preserve deployment IDs around nonversioned reads."""
    result = {}
    for script, pin in pins.items():
        value = serving_deployment(capture.readback(account, token, script, "deployments?per_page=1&page=1"))
        if value is None or value[1] != pin:
            raise ValueError("serving_unverified")
        result[script] = value
    return result


def role_capabilities(account: str, token: str, version: str, queue: str, *, attached: bool = True) -> None:
    """Check immutable production bindings and current private all-capture-off surfaces."""
    base = f"/accounts/{account}/workers/scripts/{ROLE}"
    value = role.api_get(f"{base}/versions/{version}", token)
    role.inspect_serving_bindings(value, version, queue, realm="production", database=DATABASE, queue_attached=attached)
    settings = role.api_get(f"{base}/settings", token)
    script = role.api_get(f"{base}/script-settings", token)
    worker = role.api_get(f"/accounts/{account}/workers/workers/{ROLE}", token)
    if not capture.effective_api_settings(worker, ROLE, settings, script):
        raise ValueError("role_capture_unverified")
    import check_trace_sink_isolation as isolation
    subdomain = role.api_get(f"{base}/subdomain", token)
    if (not isinstance(subdomain, dict) or subdomain.get("enabled") is not False
            or subdomain.get("previews_enabled") is not False):
        raise ValueError("role_surface_unverified")
    domains = isolation.worker_domains(account, token)
    if any(row["service"] == ROLE for row in domains):
        raise ValueError("role_surface_unverified")
    zones = isolation.inventory(token, f"/zones?account.id={account}&type=full,partial,secondary,internal")
    if not zones or len(zones) > 20:
        raise ValueError("role_surface_unverified")
    for zone in zones:
        if not isinstance(zone.get("account"), dict) or zone["account"].get("id") != account:
            raise ValueError("role_surface_unverified")
        envelope = isolation.envelope(token, f"/zones/{zone['id']}/workers/routes")
        routes = envelope.get("result")
        if (not isinstance(routes, list) or len(routes) > 1000 or envelope.get("result_info") not in (None, {})
                or not all(isinstance(row, dict) and isinstance(row.get("id"), str)
                           and ID.fullmatch(row["id"]) and isinstance(row.get("pattern"), str)
                           and (row.get("script") is None or isinstance(row["script"], str)) for row in routes)
                or len({row["id"] for row in routes}) != len(routes)
                or any(row.get("script") == ROLE for row in routes)):
            raise ValueError("role_surface_unverified")


def verify(phase: str, lifecycle: str, *, migrated: bool = False) -> None:
    """Attest the active direct graph or separately scoped historical role research."""
    if phase == "api-only":
        if migrated or lifecycle != "replacement":
            raise ValueError("direct_phase_unreviewed")
        verify_api_only()
        return
    if migrated and (phase != "before" or lifecycle != "first-bootstrap"):
        raise ValueError("migration_phase_unverified")
    account, token = os.getenv("CLOUDFLARE_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_API_TOKEN", "")
    topology = "api-only" if phase == "before" else "api-role"
    queue, dlq = os.getenv("AMAIL_TRACE_QUEUE_ID", ""), os.getenv("AMAIL_TRACE_DLQ_ID", "")
    pins = {API: os.getenv("AMAIL_EXPECTED_WORKER_VERSION", ""), SINK: os.getenv("AMAIL_EXPECTED_TRACE_SINK_VERSION", "")}
    role_pin = os.getenv("AMAIL_EXPECTED_ROLE_WORKER_VERSION", "")
    if (ID.fullmatch(account) is None or not token or ID.fullmatch(queue) is None
            or ID.fullmatch(dlq) is None or queue == dlq or os.getenv("AMAIL_TRACE_TOPOLOGY") != topology
            or any(UUID.fullmatch(value) is None for value in pins.values())
            or phase not in ("before", "after", "maintenance")):
        raise ValueError("pins_unverified")
    if phase != "before" or lifecycle == "replacement":
        if UUID.fullmatch(role_pin) is None:
            raise ValueError("role_pin_unverified")
        pins[ROLE] = role_pin
    elif lifecycle != "first-bootstrap" or role_pin:
        raise ValueError("lifecycle_unverified")
    before = serving(account, token, pins)
    switched = 0
    if phase == "maintenance":
        configured = os.getenv("AMAIL_ROLE_ROUTED_COUNT", "")
        if configured not in ("0", "1", "2", "3", "4"):
            raise ValueError("route_phase_unreviewed")
        switched = int(configured)
    snapshot = forward_snapshot(account, switched=switched)
    held_send()
    queues.reconcile(account, token, "production", "readback", topology)
    if ROLE not in pins:
        role_absent(account, token)
    if not bindings_match(capture.readback(account, token, API, f"versions/{pins[API]}"), pins[API],
                          phase="queue-api", queue_id=queue, realm="production"):
        raise ValueError("api_bindings_unverified")
    if not capture.verify("production", account, token) or not capture.verify("production", account, token, sink=True):
        raise ValueError("privacy_unverified")
    if ROLE in pins:
        role_capabilities(account, token, pins[ROLE], queue, attached=phase != "before")
    storage("maintenance" if phase == "maintenance" else "migrated"
            if (phase == "after" or migrated) and lifecycle == "first-bootstrap" else lifecycle)
    queues.reconcile(account, token, "production", "readback", topology)
    if ROLE not in pins:
        role_absent(account, token)
    held_send()
    if serving(account, token, pins) != before or forward_snapshot(account, switched=switched) != snapshot:
        raise ValueError("graph_changed")


def verify_api_only() -> None:
    """Bracket exact API/sink pins, sole API producer, privacy and four forwards.

    Bootstrap post-deploy and later replacements use this same contract. Role
    storage and leases are deliberately not read; an attached role producer or
    live role Worker is instead rejected without changing or deleting it.
    Configuration proof is not retained-record privacy acceptance or permission
    to allow public sending.
    """
    account, token = os.getenv("CLOUDFLARE_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_API_TOKEN", "")
    queue, dlq = os.getenv("AMAIL_TRACE_QUEUE_ID", ""), os.getenv("AMAIL_TRACE_DLQ_ID", "")
    pins = {API: os.getenv("AMAIL_EXPECTED_WORKER_VERSION", ""), SINK: os.getenv("AMAIL_EXPECTED_TRACE_SINK_VERSION", "")}
    if (ID.fullmatch(account) is None or not token or ID.fullmatch(queue) is None
            or ID.fullmatch(dlq) is None or queue == dlq or os.getenv("AMAIL_TRACE_TOPOLOGY") != "api-only"
            or any(UUID.fullmatch(value) is None for value in pins.values())
            or os.getenv("AMAIL_EXPECTED_ROLE_WORKER_VERSION", "")
            or os.getenv("AMAIL_ROLE_ROUTED_COUNT", "") not in ("", "0")):
        raise ValueError("direct_pins_unverified")
    held_send()
    before = serving(account, token, pins)
    snapshot = forward_snapshot(account)
    queues.reconcile(account, token, "production", "readback", "api-only")
    role_absent(account, token)
    if not bindings_match(capture.readback(account, token, API, f"versions/{pins[API]}"), pins[API],
                          phase="queue-api", queue_id=queue, realm="production"):
        raise ValueError("api_bindings_unverified")
    if not capture.verify("production", account, token) or not capture.verify("production", account, token, sink=True):
        raise ValueError("privacy_unverified")
    queues.reconcile(account, token, "production", "readback", "api-only")
    role_absent(account, token)
    held_send()
    if serving(account, token, pins) != before or forward_snapshot(account) != snapshot:
        raise ValueError("graph_changed")


def main() -> int:
    """Print fixed verdicts only, never destination, MIME, ledger or provider bodies."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("api-only", "before", "after", "maintenance"), required=True)
    parser.add_argument("--lifecycle", choices=("first-bootstrap", "replacement"), default="replacement")
    parser.add_argument("--migrated", action="store_true")
    args = parser.parse_args()
    try:
        verify(args.phase, args.lifecycle, migrated=args.migrated)
    except (ValueError, RuntimeError, KeyError, TypeError, OSError, subprocess.TimeoutExpired, forwards.ProvisionError):
        print("production_role_graph=UNVERIFIED")
        return 1
    print(f"production_role_graph_{args.phase}=exact_pins_and_private_state_verified")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
