"""Bounded staging-only retained-span witness; never expose provider log envelopes.

This consumes existing persisted safe console records, not native tracing, live
tailing or a new capture service. All network errors are fixed labels and every
payload is validated in memory before any summary can be returned to a caller.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import uuid


SCRIPTS = {"mail_api": "amail-trace-sink-staging"}
SERVICE_ORIGINS = {"billing": "https://billing-staging.moesegfault.dev",
                   "subscribe": "https://subscribe-staging.moesegfault.dev"}
MAX_REPLY = 2_000_000
MAX_EVENTS = 128
# Identify the actual test client; Python's default identifier receives an edge 403 on staging.
# This is not browser impersonation and does not change authentication or edge policy.
USER_AGENT = "amail-staging-witness/0.2.0"
SAFE_INTEGER = (1 << 53) - 1
BASE_FIELDS = {"schema_version", "event_id", "service", "operation", "phase",
               "trace_id", "span_id", "parent_span_id", "occurred_at_ms",
               "duration_ms", "outcome", "http_status"}
MAIL_FIELDS = BASE_FIELDS | {
    "request_id", "error_code", "http_status_class", "client_phase",
    "client_error_kind", "duration_ms_bucket", "request_bytes_bucket",
    "response_bytes_bucket", "provider_http_status", "provider_error_code",
    "diagnostic_code",
    "linked_trace_id", "linked_span_id",
}
BILLING_OPERATIONS = {"billing_status", "billing_session_create",
                      "billing_session_status", "billing_authorize", "billing_usage_record"}
SUBSCRIBE_OPERATIONS = {"amail.authorization.approve", "amail.authorization.cancel",
                        "amail.authorization.get", "amail.authorization.page", "auth.login",
                        "auth.callback", "billing.activate", "billing.account", "session.get",
                        "session.logout", "subscribe.other"}
MAIL_PHASES = {"request_exit", "operation_exit", "billing_http", "d1_read",
               "d1_write", "r2_write", "provider_send", "routing_list", "routing_create"}
MAIL_OPERATIONS = BILLING_OPERATIONS | {"messages_send", "maintenance"}
HTTP_FAILURE_KINDS = {"unauthorized", "forbidden", "not_found", "rate_limited",
                      "server_error", "redirect_rejected", "client_error", "unexpected_status"}
FAILURE_LABELS = {
    "retained_span_shape_invalid", "retained_span_fields_invalid",
    "retained_span_identity_or_clock_invalid", "retained_span_operation_invalid",
    "retained_span_phase_invalid", "retained_span_error_invalid",
    "retained_span_link_invalid", "retained_span_measurement_invalid",
    "retained_span_outcome_invalid", "retained_span_redelivery_conflict",
    "retained_trace_scope_invalid", "retained_trace_window_invalid",
    "retained_trace_credentials_missing", "retained_trace_provider_unavailable",
    "retained_trace_response_invalid", "retained_trace_response_truncated_or_invalid",
    "retained_trace_scope_or_credentials_invalid", "retained_trace_service_unavailable",
    "retained_trace_chain_incomplete",
} | {f"retained_trace_{boundary}_{kind}" for boundary in ("provider", "service")
     for kind in HTTP_FAILURE_KINDS}


class TraceWitnessError(Exception):
    """A fixed content-free diagnostic, safe for the hosted execution log."""

    @property
    def safe_label(self) -> str:
        """Expose only a reviewed label; arbitrary exception text never reaches diagnostics."""
        label = str(self)
        return label if label in FAILURE_LABELS else "retained_trace_unexpected_failure"


def http_failure_label(boundary: str, status: object) -> str:
    """Classify only numeric HTTP facts; never inspect URL, headers, reason or body."""
    if boundary not in {"provider", "service"}:
        return "retained_trace_unexpected_failure"
    kind = {401: "unauthorized", 403: "forbidden", 404: "not_found",
            429: "rate_limited"}.get(status) if type(status) is int else None
    if kind is None:
        kind = ("server_error" if type(status) is int and 500 <= status <= 599 else
                "redirect_rejected" if type(status) is int and 300 <= status <= 399 else
                "client_error" if type(status) is int and 400 <= status <= 499 else
                "unexpected_status")
    return f"retained_trace_{boundary}_{kind}"


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    """Do not forward a privileged API credential after any redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Keep credentials on the fixed Cloudflare API origin only."""
        return None


def hex_id(value: object, length: int) -> bool:
    """Accept canonical W3C identifiers, never raw correlation text."""
    return isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value)) and any(c != "0" for c in value)


def integer(value: object, maximum: int = SAFE_INTEGER) -> bool:
    """Reject bool, floats, negative values and JavaScript precision overflow."""
    return type(value) is int and 0 <= value <= maximum


def canonical_uuid(value: object) -> bool:
    """Accept only random canonical lower-case UUIDv4 event identities."""
    if not isinstance(value, str):
        return False
    try:
        parsed = uuid.UUID(value)
        return parsed.version == 4 and str(parsed) == value
    except ValueError:
        return False


def decode_source(source: object) -> dict:
    """Decode only documented console shapes, never search arbitrary provider text."""
    if isinstance(source, dict) and "schema_version" not in source:
        source = source.get("message")
    if isinstance(source, list) and len(source) == 1:
        source = source[0]
    if isinstance(source, str) and len(source.encode("utf-8")) <= 1024:
        try:
            source = json.loads(source)
        except (ValueError, UnicodeError):
            raise TraceWitnessError("retained_span_shape_invalid") from None
    if not isinstance(source, dict) or len(json.dumps(source).encode("utf-8")) > 2048:
        raise TraceWitnessError("retained_span_shape_invalid")
    return source


def validate_span(record: dict, service: str, trace_id: str) -> dict:
    """Fail closed before projecting a content-free span identity/timing view."""
    allowed = MAIL_FIELDS if service in {"mail_api", "mail_cli"} else BASE_FIELDS
    if service not in {*SCRIPTS, *SERVICE_ORIGINS, "mail_cli"} or set(record) - allowed or record.get("service") != service or type(record.get("schema_version")) is not int or record.get("schema_version") != 1:
        raise TraceWitnessError("retained_span_fields_invalid")
    parent = record.get("parent_span_id")
    if not (canonical_uuid(record.get("event_id")) and record.get("trace_id") == trace_id
            and hex_id(record.get("span_id"), 16)
            and (parent is None or (hex_id(parent, 16) and parent != record["span_id"]))
            and integer(record.get("occurred_at_ms")) and integer(record.get("duration_ms"))):
        raise TraceWitnessError("retained_span_identity_or_clock_invalid")
    operations = SUBSCRIBE_OPERATIONS if service == "subscribe" else MAIL_OPERATIONS if service in {"mail_api", "mail_cli"} else BILLING_OPERATIONS
    if record.get("operation") not in operations:
        raise TraceWitnessError("retained_span_operation_invalid")
    if service in {"mail_api", "mail_cli"}:
        scheduled_root = (service == "mail_api" and record.get("operation") == "maintenance"
                          and record.get("phase") == "scheduled_exit" and parent is None)
        if record.get("phase") not in MAIL_PHASES and not scheduled_root:
            raise TraceWitnessError("retained_span_phase_invalid")
        if record.get("error_code") not in {None, "invalid_request", "unauthorized", "forbidden", "not_found", "conflict", "rate_limited", "service_unavailable", "other_client", "other_server", "dependency_failure"}:
            raise TraceWitnessError("retained_span_error_invalid")
        if record.get("client_phase") not in {None, "auth", "transport", "response_body", "complete"}:
            raise TraceWitnessError("retained_span_error_invalid")
        if record.get("client_error_kind") not in {None, "credential_unavailable", "connect", "timeout", "transport", "decode", "body"}:
            raise TraceWitnessError("retained_span_error_invalid")
        if record.get("diagnostic_code") is not None:
            raise TraceWitnessError("retained_span_error_invalid")
        link_trace, link_span = record.get("linked_trace_id"), record.get("linked_span_id")
        if (link_trace is not None or link_span is not None) and not (
                service == "mail_api" and record["operation"] == "maintenance"
                and record["phase"] == "billing_http" and hex_id(link_trace, 32)
                and hex_id(link_span, 16) and (link_trace, link_span) != (trace_id, record["span_id"])):
            raise TraceWitnessError("retained_span_link_invalid")
        for key in {"duration_ms_bucket", "request_bytes_bucket", "response_bytes_bucket", "provider_error_code"}:
            if key in record and not integer(record[key]):
                raise TraceWitnessError("retained_span_measurement_invalid")
        if "request_id" in record and not canonical_uuid(record["request_id"]):
            raise TraceWitnessError("retained_span_identity_or_clock_invalid")
    elif record.get("phase") not in {"request_exit", "dependency_exit"}:
        raise TraceWitnessError("retained_span_phase_invalid")
    if record.get("outcome") not in {"success", "client_error", "server_error", "phase_failure"}:
        raise TraceWitnessError("retained_span_outcome_invalid")
    for key in {"http_status", "provider_http_status"}:
        if key in record and not (integer(record[key], 599) and record[key] >= 100):
            raise TraceWitnessError("retained_span_measurement_invalid")
    projection = BASE_FIELDS | {"linked_trace_id", "linked_span_id"}
    return {key: record.get(key) for key in projection if key in record}


def query_body(script: str, trace_id: str, start_ms: int, end_ms: int, *, exact_span_id: str | None = None) -> dict:
    """Construct a fixed dry query; no adaptive field discovery or broad account scan."""
    if (script not in SCRIPTS.values() or not hex_id(trace_id, 32)
            or (exact_span_id is not None and not hex_id(exact_span_id, 16))):
        raise TraceWitnessError("retained_trace_scope_invalid")
    if not (integer(start_ms) and integer(end_ms) and 0 < end_ms - start_ms <= 900_000):
        raise TraceWitnessError("retained_trace_window_invalid")
    return {"queryId": "amail-v020-retained-witness", "dry": True, "view": "events",
            "limit": MAX_EVENTS, "timeframe": {"from": start_ms, "to": end_ms},
            "parameters": {"datasets": ["cloudflare-workers"], "filterCombination": "and",
                           "filters": [{"key": "$workers.scriptName", "type": "string", "operation": "eq", "value": script}],
                           "needle": {"value": exact_span_id or trace_id, "isRegex": False, "matchCase": True}}}


def read_records(account: str, token: str, script: str, trace_id: str, start_ms: int, end_ms: int, *, exact_span_id: str | None = None) -> list[dict]:
    """Read at most one bounded persisted-log page without retaining its raw envelope."""
    if not re.fullmatch(r"[0-9a-f]{32}", account) or not token:
        raise TraceWitnessError("retained_trace_credentials_missing")
    if exact_span_id is not None and not hex_id(exact_span_id, 16):
        raise TraceWitnessError("retained_trace_scope_invalid")
    body = query_body(script, trace_id, start_ms, end_ms, exact_span_id=exact_span_id)
    request = urllib.request.Request(f"https://api.cloudflare.com/client/v4/accounts/{account}/workers/observability/telemetry/query",
                                    data=json.dumps(body).encode(), method="POST",
                                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                             "User-Agent": USER_AGENT})
    try:
        with urllib.request.build_opener(RejectRedirect).open(request, timeout=20) as response:
            raw = response.read(MAX_REPLY + 1)
            status = response.status
    except urllib.error.HTTPError as error:
        label = http_failure_label("provider", error.code)
        # Close without reading: HTTPError finalizer warnings can otherwise include its private reason.
        try:
            error.close()
        except (OSError, ValueError):
            pass
        raise TraceWitnessError(label) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise TraceWitnessError("retained_trace_provider_unavailable") from None
    if status != 200 or len(raw) > MAX_REPLY:
        raise TraceWitnessError("retained_trace_response_invalid")
    try:
        payload = json.loads(raw)
        events = payload["result"]["events"]
        rows = events["events"]
    except (ValueError, KeyError, TypeError):
        raise TraceWitnessError("retained_trace_response_invalid") from None
    count = events.get("count", len(rows)) if isinstance(rows, list) else None
    if payload.get("success") is not True or not isinstance(rows, list) or not integer(count) or len(rows) >= MAX_EVENTS or count > MAX_EVENTS:
        raise TraceWitnessError("retained_trace_response_truncated_or_invalid")
    result = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("$workers"), dict) or row["$workers"].get("scriptName") != script:
            raise TraceWitnessError("retained_trace_scope_invalid")
        record = decode_source(row.get("source"))
        if exact_span_id is not None and (record.get("span_id") != exact_span_id
                                          or record.get("phase") != "scheduled_exit"):
            continue
        service = record.get("service")
        expected = "mail_api" if script == SCRIPTS["mail_api"] else next(key for key, value in SCRIPTS.items() if value == script)
        if service not in ({"mail_api", "mail_cli"} if expected == "mail_api" else {expected}):
            raise TraceWitnessError("retained_trace_scope_invalid")
        result.append(validate_span(record, service, trace_id))
    return result


def read_service_records(service: str, service_key: str, trace_id: str) -> list[dict]:
    """Read only typed D1 spans from fixed staging origins; never query HTTP logs.

    The key is passed in memory and must come from the protected staging secret.
    It is never a command-line argument, URL parameter or returned diagnostic.
    """
    if service not in SERVICE_ORIGINS or not service_key or not hex_id(trace_id, 32):
        raise TraceWitnessError("retained_trace_scope_or_credentials_invalid")
    request = urllib.request.Request(f"{SERVICE_ORIGINS[service]}/v1/service/amail/trace-query",
                                    data=json.dumps({"trace_id": trace_id}).encode(), method="POST",
                                    headers={"Authorization": f"Bearer {service_key}", "Content-Type": "application/json",
                                             "User-Agent": USER_AGENT})
    try:
        with urllib.request.build_opener(RejectRedirect).open(request, timeout=20) as response:
            raw = response.read(MAX_REPLY + 1)
            status = response.status
    except urllib.error.HTTPError as error:
        label = http_failure_label("service", error.code)
        try:
            error.close()
        except (OSError, ValueError):
            pass
        raise TraceWitnessError(label) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise TraceWitnessError("retained_trace_service_unavailable") from None
    if status != 200 or len(raw) > MAX_REPLY:
        raise TraceWitnessError("retained_trace_response_invalid")
    try:
        payload = json.loads(raw)
        rows = payload["spans"]
    except (ValueError, KeyError, TypeError):
        raise TraceWitnessError("retained_trace_response_invalid") from None
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "spans"} or payload.get("schema_version") != 1 or not isinstance(rows, list) or len(rows) >= MAX_EVENTS:
        raise TraceWitnessError("retained_trace_response_truncated_or_invalid")
    if any(not isinstance(row, dict) for row in rows):
        raise TraceWitnessError("retained_span_shape_invalid")
    return [validate_span(row, service, trace_id) for row in rows]


def connected_authorization(spans: list[dict], reachable: set[str]) -> bool:
    """The approval's real remote parent must be a retained Subscribe client span."""
    by_id = {span["span_id"]: span for span in spans}
    for authorization in spans:
        client = by_id.get(authorization.get("parent_span_id"), {})
        server = by_id.get(client.get("parent_span_id"), {})
        if (authorization["service"] == "billing" and authorization["operation"] == "billing_authorize"
                and authorization["outcome"] == "success" and authorization["span_id"] in reachable
                and client.get("service") == "subscribe" and client.get("phase") == "dependency_exit"
                and server.get("service") == "subscribe" and server.get("phase") == "request_exit"
                and server.get("operation") == "amail.authorization.approve"):
            return True
    return False


def witness(records: list[dict], trace_id: str, *, require_cli: bool = True, require_authorization: bool = False) -> dict:
    """Prove actual retained CLI→Mail→Billing parentage and return only safe summary."""
    unique = {}
    for record in records:
        record = validate_span(record, record.get("service"), trace_id)
        key = record["event_id"]
        if key in unique and unique[key] != record:
            raise TraceWitnessError("retained_span_redelivery_conflict")
        unique[key] = record
    spans = list(unique.values())
    servers = [span for span in spans if span["service"] == "mail_api" and span["phase"] == "request_exit"]
    for server in servers:
        dependencies = [span for span in spans if span["service"] == "mail_api" and span["phase"] == "billing_http" and span["operation"] == server["operation"] and span.get("parent_span_id") == server["span_id"]]
        for dependency in dependencies:
            billing = next((span for span in spans if span["service"] == "billing" and span["phase"] == "request_exit" and span.get("parent_span_id") == dependency["span_id"]), None)
            cli = next((span for span in spans if span["service"] == "mail_cli" and span["phase"] == "operation_exit" and span["span_id"] == server.get("parent_span_id")), None)
            reachable = {dependency["span_id"]}
            for _ in spans:
                reachable.update(span["span_id"] for span in spans if span.get("parent_span_id") in reachable)
            authorized = connected_authorization(spans, reachable)
            if billing and (cli or not require_cli) and (authorized or not require_authorization):
                return {"schema_version": 1, "trace_id": trace_id, "retained_span_count": len(spans),
                        "mail_span_id": server["span_id"], "billing_client_span_id": dependency["span_id"],
                        "billing_server_span_id": billing["span_id"], "cli_retained": cli is not None,
                        "human_authorization_retained": authorized}
    raise TraceWitnessError("retained_trace_chain_incomplete")


def async_usage_witness(records: list[dict], trace_id: str, read_scheduled) -> dict:
    """Join a charged origin's actual human/CLI ancestry to a separate scheduler root.

    The callback performs one bounded exact-span read using only validated link
    IDs. Parent IDs prove causality; cross-host wall-clock ordering is irrelevant.
    A scheduler may report an unrelated phase failure after successful delivery.
    """
    origin = witness(records, trace_id, require_cli=True, require_authorization=True)
    spans = [validate_span(row, row.get("service"), trace_id) for row in records]
    for dependency in spans:
        if not (dependency["service"] == "mail_api" and dependency["operation"] == "maintenance"
                and dependency["phase"] == "billing_http" and dependency["outcome"] == "success"
                and dependency.get("parent_span_id") == origin["mail_span_id"]
                and dependency.get("linked_trace_id") not in {None, trace_id}):
            continue
        billing = next((row for row in spans if row["service"] == "billing"
                        and row["operation"] == "billing_usage_record" and row["phase"] == "request_exit"
                        and row["outcome"] == "success"
                        and row.get("parent_span_id") == dependency["span_id"]), None)
        if billing is None:
            continue
        linked_trace, linked_span = dependency["linked_trace_id"], dependency["linked_span_id"]
        roots = [validate_span(row, row.get("service"), linked_trace)
                 for row in read_scheduled(linked_trace, linked_span)]
        root = next((row for row in roots if row["service"] == "mail_api"
                     and row["operation"] == "maintenance" and row["phase"] == "scheduled_exit"
                     and row["span_id"] == linked_span and row.get("parent_span_id") is None), None)
        if root is not None:
            return {"trace_id": trace_id, "origin_mail_span_id": origin["mail_span_id"],
                    "retained_span_count": origin["retained_span_count"],
                    "usage_client_span_id": dependency["span_id"],
                    "usage_server_span_id": billing["span_id"],
                    "scheduled_trace_id": linked_trace, "scheduled_span_id": linked_span,
                    "scheduled_retained_span_count": len(roots)}
    raise TraceWitnessError("retained_trace_chain_incomplete")
