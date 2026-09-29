"""Offline-only, fail-closed observer for staging mail Worker live-tail JSON.

This module has no network, subprocess, mail, or routing capability. A future
transport must establish and own a real Tail WebSocket, call ``connected`` only
after its handshake, forward complete JSON frames, signal every loss or warning,
    and call ``finish`` only after an orderly, operator-controlled stop. This
    parser never emits an operational ``observer_ready`` gate. No raw input
or exception is written to stdout or a file by this module.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass


WORKER = "amail-mail-staging"
MAX_FRAME_BYTES = 65_536
MAX_TOTAL_BYTES = 2_000_000
MAX_FRAMES = 200
MAX_EVENTS = 200
MAX_SECONDS = 600
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
HEX16 = re.compile(r"[0-9a-f]{16}\Z")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
EVENT_KEYS = frozenset({
    "schema_version", "service", "operation", "phase", "trace_id", "span_id",
    "parent_span_id", "request_id", "outcome", "error_code",
    "http_status_class", "duration_ms_bucket", "request_bytes_bucket",
    "provider_http_status", "provider_error_code",
})
ENVELOPE_KEYS = frozenset({
    "outcome", "scriptName", "exceptions", "logs", "eventTimestamp", "event",
    "diagnosticsChannelEvents", "sampleRate", "samplingRate",
})
ERROR_CODES = frozenset({
    "invalid_request", "unauthorized", "forbidden", "not_found", "conflict",
    "rate_limited", "service_unavailable", "other_client", "other_server",
    "dependency_failure",
})
REASONS = frozenset({
    "not_connected", "stream_loss", "stream_limit", "stream_malformed",
    "service_unverified", "sampled_stream", "unreviewed_record",
    "event_schema", "causal_ambiguity", "phase_missing", "phase_order",
    "outcome_inconsistent", "transport_unverified", "provenance_unbound",
    "provenance_mismatch",
})


@dataclass(frozen=True)
class Event:
    """A small allowlisted projection; raw request and console data are discarded."""

    phase: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    request_id: str
    outcome: str
    http_status_class: int | None
    provider_http_status: int | None
    provider_error_code: int | None


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    """Reject duplicate JSON keys rather than trusting last-value-wins parsing."""

    value: dict = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _reject_constant(_value: str) -> None:
    """Reject Python's nonstandard NaN/Infinity JSON extension."""

    raise ValueError("nonstandard JSON constant")


def _decode(raw: str) -> object:
    """Decode strict JSON without preserving any raw input in exceptions."""

    return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


def _valid_event(value: object) -> Event | None:
    """Accept only schema-v1 address-add events with valid causal identifiers."""

    if not isinstance(value, dict) or not set(value).issubset(EVENT_KEYS):
        return None
    if (type(value.get("schema_version")) is not int or value["schema_version"] != 1
            or value.get("service") != "mail_api"
            or value.get("operation") != "addresses_add"
            or not isinstance(value.get("phase"), str)
            or value.get("phase") not in {"request_exit", "routing_list", "routing_create"}
            or not isinstance(value.get("outcome"), str)
            or value.get("outcome") not in {
                "success", "client_error", "server_error", "phase_failure"
            }):
        return None
    trace, span, parent, request = (
        value.get("trace_id"), value.get("span_id"),
        value.get("parent_span_id"), value.get("request_id"),
    )
    if (not isinstance(trace, str) or HEX32.fullmatch(trace) is None
            or not isinstance(span, str) or HEX16.fullmatch(span) is None
            or not isinstance(request, str) or UUID.fullmatch(request) is None
            or (parent is not None and
                (not isinstance(parent, str) or HEX16.fullmatch(parent) is None))):
        return None
    if "duration_ms_bucket" not in value:
        return None
    # Rust's skip_serializing_if omits None; explicit JSON null is not a
    # producer shape and must not become a second spelling of missing.
    if any(value[key] is None for key in (
        "parent_span_id", "error_code", "http_status_class", "request_bytes_bucket",
        "provider_http_status", "provider_error_code",
    ) if key in value):
        return None
    for key in ("duration_ms_bucket", "request_bytes_bucket"):
        item = value.get(key)
        if item is not None and (type(item) is not int or not 0 <= item <= 1 << 32
                                 or (item != 0 and item & (item - 1) != 0)):
            return None
    duration = value["duration_ms_bucket"]
    if duration is None or duration > 1 << 22:
        return None
    status, code, status_class = (
        value.get("provider_http_status"), value.get("provider_error_code"),
        value.get("http_status_class"),
    )
    if (status is not None and (type(status) is not int or not 100 <= status <= 599)):
        return None
    if code is not None and (type(code) is not int or not 0 <= code <= 0xFFFFFFFF):
        return None
    if status_class is not None and (type(status_class) is not int
                                     or not 0 <= status_class <= 5):
        return None
    error = value.get("error_code")
    if error is not None and (not isinstance(error, str) or error not in ERROR_CODES):
        return None
    phase = value["phase"]
    if phase == "request_exit":
        # Authenticated CLI requests legitimately give the server root a CLI
        # parent; only its routing children must name this server root span.
        if status_class is None or status is not None or code is not None:
            return None
        if ((value["outcome"] == "success" and status_class not in (2, 3))
                or (value["outcome"] == "client_error" and status_class != 4)
                or (value["outcome"] == "server_error" and status_class != 5)
                or value["outcome"] == "phase_failure"):
            return None
        if ((value["outcome"] == "success" and error is not None)
                or (value["outcome"] == "client_error" and error not in {
                    "invalid_request", "unauthorized", "forbidden", "not_found",
                    "conflict", "rate_limited", "other_client",
                })
                or (value["outcome"] == "server_error" and error not in {
                    "service_unavailable", "other_server",
                })):
            return None
    elif parent is None or status_class is not None:
        return None
    elif ((value["outcome"] == "success" and error is not None)
          or (value["outcome"] == "phase_failure" and error != "dependency_failure")
          or value["outcome"] in {"client_error", "server_error"}):
        return None
    elif value.get("request_bytes_bucket") is not None:
        return None
    if phase != "routing_create" and (status is not None or code is not None):
        return None
    if phase == "routing_create" and value["outcome"] == "success" and (status is not None or code is not None):
        return None
    return Event(phase, trace, span, parent, request, value["outcome"],
                 status_class, status, code)


def _label(events: list[Event], expected_request_id: str) -> str:
    """Classify a single complete observed causal chain, not event absence."""

    roots = [event for event in events if event.phase == "request_exit"]
    if len(roots) != 1:
        return "UNVERIFIED (causal_ambiguity)"
    root = roots[0]
    if root.request_id != expected_request_id:
        return "UNVERIFIED (provenance_mismatch)"
    if any(event.trace_id != root.trace_id or event.request_id != root.request_id
           or (event.phase != "request_exit" and event.parent_span_id != root.span_id)
           for event in events):
        return "UNVERIFIED (causal_ambiguity)"
    spans = [event.span_id for event in events]
    if len(spans) != len(set(spans)):
        return "UNVERIFIED (causal_ambiguity)"
    lists = [event for event in events if event.phase == "routing_list"]
    creates = [event for event in events if event.phase == "routing_create"]
    if len(lists) != 1 or len(creates) > 1:
        return "UNVERIFIED (phase_missing)"
    listed = lists[0]
    # The Worker emits the request exit last, and a create can only follow a list.
    if events.index(listed) >= events.index(root) or (
        creates and not events.index(listed) < events.index(creates[0]) < events.index(root)
    ):
        return "UNVERIFIED (phase_order)"
    if listed.outcome == "phase_failure":
        if creates or root.outcome not in {"client_error", "server_error"}:
            return "UNVERIFIED (outcome_inconsistent)"
        return "routing_list_failed"
    if listed.outcome != "success":
        return "UNVERIFIED (outcome_inconsistent)"
    if not creates:
        return "e2e_address_add_succeeded" if root.outcome == "success" else "UNVERIFIED (phase_missing)"
    created = creates[0]
    if created.outcome == "phase_failure":
        if root.outcome not in {"client_error", "server_error"}:
            return "UNVERIFIED (outcome_inconsistent)"
        status = created.provider_http_status
        code = created.provider_error_code
        return (f"routing_create_failed_provider_http_{status if status is not None else 'absent'}"
                f"_code_{code if code is not None else 'absent'}")
    if created.outcome != "success":
        return "UNVERIFIED (outcome_inconsistent)"
    if root.outcome == "success":
        return "e2e_address_add_succeeded"
    if root.outcome in {"client_error", "server_error"}:
        return "routing_create_succeeded_later_failure"
    return "UNVERIFIED (outcome_inconsistent)"


class TailObserver:
    """Bounded state machine for an already-established staging Tail connection.

    This cannot establish readiness itself: ``connected`` is a transport callback,
    not a declaration that a queued mutation may proceed. A separate reviewed
    runner must prove WebSocket handshake, POST server filter, privacy preflight,
    and cleanup gates before emitting an operational ``observer_ready``.
    """

    def __init__(self, now=time.monotonic) -> None:
        """Start a bounded observation window without allocating a raw log file."""

        self._now = now
        self._start = now()
        self._connected = False
        self._reason: str | None = None
        self._bytes = 0
        self._frames = 0
        self._events: list[Event] = []

    def connected(self) -> str:
        """Record a *real transport* WebSocket handshake, not E2E readiness."""

        if self._connected or self._reason is not None or self._now() - self._start > MAX_SECONDS:
            self._reason = "transport_unverified"
            return "UNVERIFIED (transport_unverified)"
        self._connected = True
        return "stream_connected"

    def lost(self) -> None:
        """Fail closed on sampling, dropped frames, warning, disconnect, or overflow."""

        self._reason = "stream_loss"

    def feed(self, frame: bytes) -> None:
        """Consume one complete WebSocket text frame; never expose its content."""

        if self._reason is not None:
            return
        if not self._connected:
            self._reason = "not_connected"
            return
        if self._now() - self._start > MAX_SECONDS:
            self._reason = "stream_limit"
            return
        self._frames += 1
        if type(frame) is not bytes or len(frame) > MAX_FRAME_BYTES:
            self._reason = "stream_limit"
            return
        self._bytes += len(frame)
        if self._frames > MAX_FRAMES or self._bytes > MAX_TOTAL_BYTES:
            self._reason = "stream_limit"
            return
        try:
            item = _decode(frame.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            self._reason = "stream_malformed"
            return
        if not isinstance(item, dict) or not set(item).issubset(ENVELOPE_KEYS):
            self._reason = "unreviewed_record"
            return
        if item.get("scriptName") != WORKER:
            self._reason = "service_unverified"
            return
        if (any(type(item[key]) not in (int, float) or item[key] != 1
                for key in ("sampleRate", "samplingRate") if key in item)):
            self._reason = "sampled_stream"
            return
        if item.get("outcome") != "ok":
            self._reason = "unreviewed_record"
            return
        if item.get("exceptions") != [] or item.get("diagnosticsChannelEvents", []) != []:
            self._reason = "unreviewed_record"
            return
        request = item.get("event")
        request = request.get("request") if isinstance(request, dict) else None
        if (not isinstance(request, dict) or request.get("method") != "POST"
                or type(item.get("eventTimestamp")) is not int):
            self._reason = "unreviewed_record"
            return
        logs = item.get("logs")
        if not isinstance(logs, list) or len(logs) > MAX_EVENTS:
            self._reason = "unreviewed_record"
            return
        for log in logs:
            if (not isinstance(log, dict) or not set(log).issubset({"message", "level", "timestamp"})
                    or log.get("level") != "log" or type(log.get("timestamp")) is not int
                    or not isinstance(log.get("message"), list)
                    or len(log["message"]) != 1 or not isinstance(log["message"][0], str)):
                self._reason = "unreviewed_record"
                return
            try:
                value = _decode(log["message"][0])
            except (ValueError, RecursionError):
                self._reason = "unreviewed_record"
                return
            event = _valid_event(value)
            if event is None:
                self._reason = "event_schema"
                return
            self._events.append(event)
            if len(self._events) > MAX_EVENTS:
                self._reason = "stream_limit"
                return

    def finish(self, *, clean_end: bool, expected_request_id: str | None = None) -> str:
        """Classify only after private CLI-derived request-ID binding and clean stop."""

        if self._reason is not None:
            return f"UNVERIFIED ({self._reason})"
        if not self._connected:
            return "UNVERIFIED (not_connected)"
        if not clean_end:
            return "UNVERIFIED (stream_loss)"
        if self._now() - self._start > MAX_SECONDS:
            return "UNVERIFIED (stream_limit)"
        if not isinstance(expected_request_id, str) or UUID.fullmatch(expected_request_id) is None:
            return "UNVERIFIED (provenance_unbound)"
        return _label(self._events, expected_request_id)
