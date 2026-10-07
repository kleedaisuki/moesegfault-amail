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


SCRIPTS = {
    "mail_api": "amail-trace-sink-staging",
    "billing": "moesegfault-billing-staging",
    "subscribe": "moesegfault-subscribe-staging",
}
MAX_REPLY = 2_000_000
MAX_EVENTS = 128
SAFE_INTEGER = (1 << 53) - 1
BASE_FIELDS = {"schema_version", "event_id", "service", "operation", "phase",
               "trace_id", "span_id", "parent_span_id", "occurred_at_ms",
               "duration_ms", "outcome", "http_status"}
MAIL_FIELDS = BASE_FIELDS | {
    "request_id", "error_code", "http_status_class", "client_phase",
    "client_error_kind", "duration_ms_bucket", "request_bytes_bucket",
    "response_bytes_bucket", "provider_http_status", "provider_error_code",
    "diagnostic_code",
}
BILLING_OPERATIONS = {"billing_status", "billing_session_create",
                      "billing_session_status", "billing_authorize", "billing_usage_record"}
SUBSCRIBE_OPERATIONS = {"amail.authorization.approve", "amail.authorization.cancel",
                        "amail.authorization.get", "amail.authorization.page", "auth.login",
                        "auth.callback", "billing.activate", "billing.account", "session.get",
                        "session.logout", "subscribe.other"}
MAIL_PHASES = {"request_exit", "operation_exit", "billing_http", "d1_read",
               "d1_write", "r2_write", "provider_send", "routing_list", "routing_create"}


class TraceWitnessError(Exception):
    """A fixed content-free diagnostic, safe for the hosted execution log."""


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
    if service not in {*SCRIPTS, "mail_cli"} or set(record) - allowed or record.get("service") != service or type(record.get("schema_version")) is not int or record.get("schema_version") != 1:
        raise TraceWitnessError("retained_span_fields_invalid")
    parent = record.get("parent_span_id")
    if not (canonical_uuid(record.get("event_id")) and record.get("trace_id") == trace_id
            and hex_id(record.get("span_id"), 16)
            and (parent is None or (hex_id(parent, 16) and parent != record["span_id"]))
            and integer(record.get("occurred_at_ms")) and integer(record.get("duration_ms"))):
        raise TraceWitnessError("retained_span_identity_or_clock_invalid")
    if record.get("operation") not in (SUBSCRIBE_OPERATIONS if service == "subscribe" else BILLING_OPERATIONS):
        raise TraceWitnessError("retained_span_operation_invalid")
    if service in {"mail_api", "mail_cli"}:
        if record.get("phase") not in MAIL_PHASES:
            raise TraceWitnessError("retained_span_phase_invalid")
        if record.get("error_code") not in {None, "invalid_request", "unauthorized", "forbidden", "not_found", "conflict", "rate_limited", "service_unavailable", "other_client", "other_server", "dependency_failure"}:
            raise TraceWitnessError("retained_span_error_invalid")
        if record.get("client_phase") not in {None, "auth", "transport", "response_body", "complete"}:
            raise TraceWitnessError("retained_span_error_invalid")
        if record.get("client_error_kind") not in {None, "credential_unavailable", "connect", "timeout", "transport", "decode", "body"}:
            raise TraceWitnessError("retained_span_error_invalid")
        if record.get("diagnostic_code") is not None:
            raise TraceWitnessError("retained_span_error_invalid")
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
    return {key: record.get(key) for key in BASE_FIELDS if key in record}


def query_body(script: str, trace_id: str, start_ms: int, end_ms: int) -> dict:
    """Construct a fixed dry query; no adaptive field discovery or broad account scan."""
    if script not in SCRIPTS.values() or not hex_id(trace_id, 32):
        raise TraceWitnessError("retained_trace_scope_invalid")
    if not (integer(start_ms) and integer(end_ms) and 0 < end_ms - start_ms <= 900_000):
        raise TraceWitnessError("retained_trace_window_invalid")
    return {"queryId": "amail-v020-retained-witness", "dry": True, "view": "events",
            "limit": MAX_EVENTS, "timeframe": {"from": start_ms, "to": end_ms},
            "parameters": {"datasets": ["cloudflare-workers"], "filterCombination": "and",
                           "filters": [{"key": "$workers.scriptName", "type": "string", "operation": "eq", "value": script}],
                           "needle": {"value": trace_id, "isRegex": False, "matchCase": True}}}


def read_records(account: str, token: str, script: str, trace_id: str, start_ms: int, end_ms: int) -> list[dict]:
    """Read at most one bounded persisted-log page without retaining its raw envelope."""
    if not re.fullmatch(r"[0-9a-f]{32}", account) or not token:
        raise TraceWitnessError("retained_trace_credentials_missing")
    body = query_body(script, trace_id, start_ms, end_ms)
    request = urllib.request.Request(f"https://api.cloudflare.com/client/v4/accounts/{account}/workers/observability/telemetry/query",
                                    data=json.dumps(body).encode(), method="POST",
                                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(RejectRedirect).open(request, timeout=20) as response:
            raw = response.read(MAX_REPLY + 1)
            status = response.status
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
        service = record.get("service")
        expected = "mail_api" if script == SCRIPTS["mail_api"] else next(key for key, value in SCRIPTS.items() if value == script)
        if service not in ({"mail_api", "mail_cli"} if expected == "mail_api" else {expected}):
            raise TraceWitnessError("retained_trace_scope_invalid")
        result.append(validate_span(record, service, trace_id))
    return result


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
            authorized = any(span["service"] == "billing" and span["operation"] == "billing_authorize" and span["outcome"] == "success" and span["span_id"] in reachable for span in spans)
            if billing and (cli or not require_cli) and (authorized or not require_authorization):
                return {"schema_version": 1, "trace_id": trace_id, "retained_span_count": len(spans),
                        "mail_span_id": server["span_id"], "billing_client_span_id": dependency["span_id"],
                        "billing_server_span_id": billing["span_id"], "cli_retained": cli is not None,
                        "human_authorization_retained": authorized}
    raise TraceWitnessError("retained_trace_chain_incomplete")
