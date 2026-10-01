"""Exact fresh paused graph observation; no provider writer or v1 policy override.

Only the two immutable storage targets are replaced with typed Scope identities.
Every other capability/capture predicate comes from the normal source contracts.
The protected executor supplies a bounded provider and separately authorized S3
metadata reader. A successful graph is an observation, never activation/drain.
"""

from copy import deepcopy
import fnmatch
import json
import sqlite3
import sys

from fresh_bootstrap_contract import Scope
from mail_lifecycle_receipt import checked_graph, scripts
import check_mail_maintenance as maintenance
from pin_staging_mail import ACCOUNT, UUID, _bindings_match, expected_bindings, serving_deployment
from mail_schema_contract import MIGRATIONS, expected_schema, verify_schema

sys.path.insert(0, str(maintenance.ROOT / "infra/provider"))
import ensure_role_forwarding as forwards
import check_observability as capture
import check_trace_sink_isolation as isolation
import ensure_trace_queues as queues

API = "amail-mail"
MAINTENANCE = "amail-mail-maintenance"
SINK = "amail-trace-sink"
_OBSERVED = object()


def canonical(value: object) -> str:
    """Canonical operational data forbids non-finite numbers and mutable aliases."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class VerifiedGraph(dict):
    """Dict-compatible exact observation with an invocation-local success witness.

    This guards accidental JSON-only persistence, not malicious Python execution.
    Durable authority still requires the reviewed protected producer and loader.
    """

    def __init__(self, value: dict, scope: Scope, queue: str, dlq: str, *, _witness=None):
        """Keep independent backing metadata so later caller edits invalidate proof."""
        if _witness is not _OBSERVED:
            raise ValueError("fresh_successful_readback_required")
        super().__init__(deepcopy(value))
        self._observed = canonical(value)
        self._scope, self._queue, self._dlq = scope, queue, dlq

    def checked(self, scope: Scope, queue: str, dlq: str) -> dict:
        """Return a copy only while exact observed content and coordinates survive."""
        if ((scope, queue, dlq) != (self._scope, self._queue, self._dlq)
                or canonical(self) != self._observed):
            raise ValueError("fresh_graph_witness_changed")
        return json.loads(self._observed)


def envelope(provider, method: str, path: str, body=None) -> dict:
    """Require successful closed API envelopes even from a synthetic transport."""
    value = provider.envelope(method, path, body)
    if (not isinstance(value, dict) or value.get("success") is not True
            or set(value) - isolation.ENVELOPE_FIELDS):
        raise ValueError("fresh_provider_read_unverified")
    return value


def complete(provider, path: str, key: str = "id", limit: int = 1000, *, unpaginated: bool = False) -> list[dict]:
    """Read complete bounded single-page endpoints without absent-as-empty fallback."""
    value = envelope(provider, "GET", path)
    rows, info = value.get("result"), value.get("result_info")
    if unpaginated and info not in (None, {}):
        raise ValueError("fresh_inventory_incomplete")
    if (not isinstance(rows, list) or len(rows) > limit
            or not all(isinstance(row, dict) and isinstance(row.get(key), str)
                       and row[key] for row in rows)
            or len({row[key] for row in rows}) != len(rows)):
        raise ValueError("fresh_inventory_unverified")
    if info is not None:
        if not isinstance(info, dict) or set(info) - {"page", "count", "total_count", "total_pages", "per_page"}:
            raise ValueError("fresh_inventory_incomplete")
        checks = {"page": lambda n: n == 1, "count": lambda n: n == len(rows),
                  "total_count": lambda n: n == len(rows),
                  "total_pages": lambda n: n in ((0, 1) if not rows else (1,)),
                  "per_page": lambda n: n > 0 and n >= len(rows)}
        if any(type(info[key]) is not int or not checks[key](info[key]) for key in info):
            raise ValueError("fresh_inventory_incomplete")
    return rows


def serving(provider, base: str, pins: dict) -> dict:
    """Preserve exact deployment IDs and single100 pins around every mutable read."""
    result = {}
    for script, version in pins.items():
        value = provider.get(f"{base}/workers/scripts/{script}/deployments?per_page=1&page=1")
        pin = serving_deployment(value) if isinstance(value, dict) else None
        if pin is None or pin[1] != version:
            raise ValueError("fresh_serving_unverified")
        result[script] = {"deployment": pin[0], "version": pin[1]}
    return result


def query(provider, base: str, scope: Scope, sql: str) -> list[dict]:
    """Read only source-owned SELECT/PRAGMA on the NEW response-bound database."""
    if not sql.startswith(("SELECT ", "PRAGMA ")) or ";" in sql:
        raise ValueError("fresh_query_unreviewed")
    value = envelope(provider, "POST", f"{base}/d1/database/{scope.database}/query",
                     {"sql": sql, "params": []}).get("result")
    if (not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict)
            or value[0].get("success") is not True or not isinstance(value[0].get("results"), list)
            or len(value[0]["results"]) > 1000
            or not all(isinstance(row, dict) for row in value[0]["results"])):
        raise ValueError("fresh_d1_read_unverified")
    return value[0]["results"]


def held_empty(provider, base: str, scope: Scope) -> None:
    """Prove full source schema, held/no-grant policy and migration-only population.

    Counts include every application table, including contact policies/projections
    and migration-created audit rows. They establish current fresh storage facts,
    not universal absence of old external work or termination of invocations.
    """
    read = lambda sql: query(provider, base, scope, sql)
    contract = expected_schema()
    verify_schema(read, contract)
    policy = read("SELECT scope,owner_iss,owner_sub,state FROM send_policy")
    if policy != [{"scope": "global", "owner_iss": "*", "owner_sub": "*", "state": "held"}]:
        raise ValueError("fresh_send_hold_unverified")
    gates = read("SELECT feedback_verified,abuse_contact_verified,delivery_canary_verified,preview_reviewed,"
                 "canary_owner_iss,canary_owner_sub,canary_recipient_sha256,canary_expires_at,canary_used_by "
                 "FROM send_release_gates WHERE id=1")
    wanted = {key: 0 for key in ("feedback_verified", "abuse_contact_verified", "delivery_canary_verified", "preview_reviewed")}
    wanted.update({key: None for key in ("canary_owner_iss", "canary_owner_sub", "canary_recipient_sha256", "canary_expires_at", "canary_used_by")})
    if (gates != [wanted] or any(type(gates[0][key]) is not int for key in wanted if wanted[key] == 0)):
        raise ValueError("fresh_grant_unverified")
    with sqlite3.connect(":memory:") as reference:
        for name in contract.migrations:
            reference.executescript((MIGRATIONS / name).read_text(encoding="utf-8"))
        for table in sorted(contract.columns):
            sql = f'SELECT COUNT(*) AS n FROM "{table}"'
            count = reference.execute(sql).fetchone()[0]
            actual = read(sql)
            if actual != [{"n": count}] or type(actual[0].get("n")) is not int:
                raise ValueError("fresh_population_unverified")


class ForwardReader:
    """Read-only adapter for established direct-forward complete-page predicates."""

    def __init__(self, provider, account: str):
        """Bind one exact account; never permit arbitrary writes from old helpers."""
        self.provider, self.account = provider, account

    def request(self, method: str, path: str, body=None) -> dict:
        """Only source-fixed forwarding GET paths reach the authorized transport."""
        if method != "GET" or body is not None:
            raise ValueError("fresh_forward_write_forbidden")
        return envelope(self.provider, "GET", path.lstrip("/"))


def forward_snapshot(provider, account: str) -> dict:
    """Keep verified external destination and exact four full forward shapes private."""
    # The executor binds this adapter to the established direct-forward reader
    # and its separate CF_EMAIL_ROUTING_TOKEN, never the general provider token.
    return deepcopy(provider.forward_snapshot(account))


def queue_graph(provider, base: str, queue: str, dlq: str, *, reader_only: bool = False) -> None:
    """Require strict two-producer main/DLQ and no hidden sink subscription."""
    rows = complete(provider, f"{base}/queues", "queue_id", 100)
    main = queues.exact_queue(rows, "amail-trace-events")
    dead = queues.exact_queue(rows, "amail-trace-dlq")
    if main is None or dead is None or (main["queue_id"], dead["queue_id"]) != (queue, dlq):
        raise ValueError("fresh_queue_identity_unverified")
    for row in rows:
        identity = row["queue_id"]
        if ACCOUNT.fullmatch(identity) is None:
            raise ValueError("fresh_queue_identity_unverified")
        detail = provider.get(f"{base}/queues/{identity}")
        if not isinstance(detail, dict) or detail.get("queue_id") != identity:
            raise ValueError("fresh_queue_detail_unverified")
        consumers = detail.get("consumers")
        if (not isinstance(consumers, list) or type(detail.get("consumers_total_count")) is not int
                or detail["consumers_total_count"] != len(consumers)
                or not all(isinstance(item, dict) and isinstance(item.get("script_name"), str) for item in consumers)):
            raise ValueError("fresh_queue_consumers_unverified")
        if identity in (queue, dlq):
            name = "amail-trace-events" if identity == queue else "amail-trace-dlq"
            if reader_only:
                # This stage positively requires the installed consumer while
                # admitting no writer, unlike provisioning's empty graph case.
                if detail.get("producers") != [] or detail.get("producers_total_count") != 0:
                    raise ValueError("fresh_reader_has_producer")
                if identity == queue and len(consumers) != 1:
                    raise ValueError("fresh_reader_missing_consumer")
                queues.validate_detail(detail, name, identity, "", "queues", "api-only")
            else:
                queues.validate_detail(detail, name, identity, "", "readback", "api-scheduled")
        elif any(item["script_name"] == SINK for item in consumers):
            raise ValueError("fresh_sink_extra_subscription")


def surfaces(provider, base: str, *, reader_only: bool = False) -> None:
    """Preserve exact production API ingress; maintenance/sink have no public surface.

    Domain validation deliberately preserves the current strict normal predicate;
    opaque-ID reader debt remains failure, never a first-bootstrap exception.
    """
    domains = isolation.worker_domain_rows(envelope(provider, "GET", f"{base}/workers/domains"))
    api_domains = [row for row in domains if row["service"] == API]
    ingress = (not api_domains if reader_only else len(api_domains) == 1
               and api_domains[0].get("hostname") == "mail.moesegfault.dev"
               and api_domains[0].get("zone_id") == forwards.ZONE)
    if not ingress or any(row["service"] in (MAINTENANCE, SINK) for row in domains):
        raise ValueError("fresh_public_domain_unverified")
    zones = forwards.pages(ForwardReader(provider, base.split("/")[1]),
                           f"/zones?account.id={base.split('/')[1]}&type=full,partial,secondary,internal")
    if not zones or len(zones) > 20:
        raise ValueError("fresh_zones_unverified")
    seen = set()
    for zone in zones:
        identity = zone.get("id")
        if (not isinstance(identity, str) or ACCOUNT.fullmatch(identity) is None or identity in seen
                or not isinstance(zone.get("account"), dict) or zone["account"].get("id") != base.split("/")[1]):
            raise ValueError("fresh_zones_unverified")
        seen.add(identity)
        routes = complete(provider, f"zones/{identity}/workers/routes", unpaginated=True)
        if any(ACCOUNT.fullmatch(row["id"]) is None or not isinstance(row.get("pattern"), str)
               or row.get("script") is not None and not isinstance(row["script"], str)
               or row.get("script") in scripts("production") for row in routes):
            raise ValueError("fresh_public_route_unverified")
        for route in routes:
            pattern = route["pattern"].removeprefix("https://").removeprefix("http://").split("/", 1)[0]
            if fnmatch.fnmatchcase("mail.moesegfault.dev", pattern):
                raise ValueError("fresh_api_ingress_shadowed")


def capabilities(provider, base: str, scope: Scope, pins: dict, queue: str,
                 *, maintenance_crons: tuple[str, ...] = (), source_active: bool = False) -> None:
    """Independent API/maintenance/sink immutable and effective capture/surface checks."""
    for script, version in pins.items():
        path = f"{base}/workers/scripts/{script}"
        immutable = provider.get(f"{path}/versions/{version}")
        if not isinstance(immutable, dict):
            raise ValueError("fresh_version_unverified")
        if script == SINK:
            safe = isolation.version_isolated(immutable, version)
        else:
            expected = (expected_bindings("queue-api", queue, realm="production") if script == API
                        else maintenance.expected_bindings("production", queue, active=source_active))
            expected.update({"MAIL_DB": ("d1", scope.database), "MAIL_BODIES": ("r2_bucket", scope.bucket)})
            safe = _bindings_match(immutable, version, expected) and maintenance.entry_surface_match(
                immutable, version, "fetch" if script == API else "scheduled")
        if not safe:
            raise ValueError("fresh_capabilities_unverified")
        settings, legacy = provider.get(f"{path}/settings"), provider.get(f"{path}/script-settings")
        worker = provider.get(f"{base}/workers/workers/{script}")
        if script == SINK:
            safe = (all(capture.safe_settings(value, sink=True) for value in (settings, legacy, worker))
                    and isinstance(worker, dict) and worker.get("name") == script
                    and isinstance(worker.get("id"), str) and bool(worker["id"])
                    and worker.get("logpush") is False and worker.get("tail_consumers") == []
                    and all(isinstance(value.get("observability", {}).get("issues"), dict)
                            and value["observability"]["issues"].get("enabled") is False
                            and value.get("streaming_tail_consumers", []) == [] for value in (settings, legacy, worker)))
        else:
            safe = capture.effective_api_settings(worker, script, settings, legacy)
        subdomain = provider.get(f"{path}/subdomain")
        if (not safe or not isinstance(subdomain, dict) or subdomain.get("enabled") is not False
                or subdomain.get("previews_enabled") is not False
                or not maintenance.schedules_match(provider.get(f"{path}/schedules"),
                     maintenance_crons if script == MAINTENANCE else ())):
            raise ValueError("fresh_capture_or_surface_unverified")


def verify_sink_replacement(scope: Scope, version: str, queue: str, dlq: str, provider) -> None:
    """Re-observe the admitted old sink before its authorized source-changed replacement.

    This is not a successful isolation witness: the old SDK module has incidental
    named exports, which the new source-owned wrapper removes. Require its exact
    observed serving version, queue-only default handler, empty capabilities and
    exact zero-producer Queue ownership before submitting the replacement once.
    No named-export policy exception is granted to the new target.
    """
    base, pins = f"accounts/{provider.account}", {SINK: version}
    before = serving(provider, base, pins)
    queue_graph(provider, base, queue, dlq, reader_only=True)
    immutable = provider.get(f"{base}/workers/scripts/{SINK}/versions/{version}")
    resources = immutable.get("resources") if isinstance(immutable, dict) else None
    bindings = resources.get("bindings") if isinstance(resources, dict) else None
    if isinstance(bindings, dict) and set(bindings) == {"result"}:
        bindings = bindings["result"]
    script = resources.get("script") if isinstance(resources, dict) else None
    if (not isinstance(immutable, dict) or immutable.get("id") != version or bindings != []
            or not isinstance(script, dict) or script.get("handlers") != ["queue"]):
        raise ValueError("fresh_sink_replacement_precondition_unverified")
    if serving(provider, base, pins) != before:
        raise ValueError("fresh_reader_changed")


def verify_sink_reader(scope: Scope, version: str, queue: str, dlq: str, provider) -> None:
    """Admit the exact private reader before either producer can be submitted.

    The executor separately verifies all same-run module bytes immediately before
    each submission. The sink's immutable Queue handler and empty capabilities,
    exact single100 version/deployment, independent capture settings, complete
    subscription graph and private ingress are read back, not inferred from a
    producer binding. This stage requires zero producers and one installed sink.
    No message is sent, read, acknowledged or replayed by this checker.
    """
    account = getattr(provider, "account", None)
    if (not isinstance(scope, Scope) or not isinstance(version, str) or UUID.fullmatch(version) is None
            or not isinstance(account, str) or ACCOUNT.fullmatch(account) is None
            or any(not isinstance(pin, str) or ACCOUNT.fullmatch(pin) is None for pin in (queue, dlq)) or queue == dlq):
        raise ValueError("fresh_coordinates_unreviewed")
    base, pins = f"accounts/{account}", {SINK: version}
    before = serving(provider, base, pins)
    queue_graph(provider, base, queue, dlq, reader_only=True)
    capabilities(provider, base, scope, pins, queue)
    surfaces(provider, base, reader_only=True)
    queue_graph(provider, base, queue, dlq, reader_only=True)
    if serving(provider, base, pins) != before:
        raise ValueError("fresh_reader_changed")


def verify(scope: Scope, pins: dict, queue: str, dlq: str, provider,
           *, maintenance_crons: tuple[str, ...] = (), source_active: bool = False) -> dict:
    """Bracket the full fresh graph; only successful complete observations persist.

    Usage: ``persist(scope, verify(scope, pins, queue, dlq, provider), queue,
    dlq, receipt_path)``. Protected executor authorization and storage creation
    provenance are separately required; this function performs no migrations.
    """
    if maintenance_crons not in ((), maintenance.CADENCE):
        raise ValueError("fresh_schedule_unreviewed")
    account = getattr(provider, "account", None)
    if (not isinstance(scope, Scope) or not isinstance(pins, dict) or set(pins) != scripts("production")
            or any(not isinstance(pin, str) or UUID.fullmatch(pin) is None for pin in pins.values())
            or not isinstance(account, str) or ACCOUNT.fullmatch(account) is None
            or any(not isinstance(pin, str) or ACCOUNT.fullmatch(pin) is None for pin in (queue, dlq)) or queue == dlq):
        raise ValueError("fresh_coordinates_unreviewed")
    base = f"accounts/{account}"
    before = serving(provider, base, pins)
    forwards_before = forward_snapshot(provider, account)
    held_empty(provider, base, scope)
    if provider.r2_empty(scope.bucket) is not True:
        raise ValueError("fresh_r2_empty_unverified")
    queue_graph(provider, base, queue, dlq)
    capabilities(provider, base, scope, pins, queue, maintenance_crons=maintenance_crons, source_active=source_active)
    surfaces(provider, base)
    queue_graph(provider, base, queue, dlq)
    held_empty(provider, base, scope)
    if provider.r2_empty(scope.bucket) is not True:
        raise ValueError("fresh_r2_empty_unverified")
    if forward_snapshot(provider, account) != forwards_before or serving(provider, base, pins) != before:
        raise ValueError("fresh_graph_changed")
    value = checked_graph({"pins": before, "api_crons": [], "maintenance_crons": list(maintenance_crons),
                           "topology": "api-scheduled"}, "production")
    return VerifiedGraph(value, scope, queue, dlq, _witness=_OBSERVED)
