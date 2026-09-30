"""Read one bounded staging address-add incident without exporting log payloads.

This manual diagnostic covers hosted run 36553799873 only. Its time window is
the entire hosted mail step because the failed CLI request ID was discarded.
Even one matching request is therefore a time-window inference, not identity
proof. The script makes only dry Cloudflare Observability requests.
"""

from __future__ import annotations

import json
import os
import sys

from staging_address_failure_logs import SAFE_FAILURES, classify, print_query_shape
from staging_trace_canary import (
    CanaryError, HEX16, HEX32, UUID, WORKER, allowlisted_event, need, preflight,
    retained_events,
)


# Hosted mail step: 10:11:42--10:16:05 UTC, with two-second margins.
# The final cleanup can consume minutes; a narrower window could miss add.
START_MS = 1790676700000
END_MS = 1790676967000
CONFIRMATION = "READ_STAGING_ADDRESS_INCIDENT_36553799873"
SHAPE_FIELDS = (
    "source", "source_object_message", "source_object_level",
    "source_object_logs", "source_object_event", "source_object_timestamp",
    "source_object_data", "source_object_other_keys", "source_object_key_bucket",
    "metadata_message", "metadata_type",
)
REVIEWED_SOURCE_KEYS = frozenset({
    "message", "event", "data", "level", "logs", "timestamp",
    "schema_version", "service",
    "operation", "phase", "trace_id", "span_id", "parent_span_id",
    "request_id", "outcome", "error_code", "http_status_class",
    "duration_ms_bucket", "request_bytes_bucket", "response_bytes_bucket",
    "provider_http_status", "provider_error_code",
})
CANDIDATE_FAILURES = frozenset({
    "candidate_root_missing_or_ambiguous", "candidate_root_schema_unverified",
    "candidate_phase_missing_or_ambiguous", "candidate_phase_schema_unverified",
    "candidate_phase_order_unverified", "candidate_message_schema_unverified",
    "candidate_source_echo_unverified", "candidate_timestamp_unverified",
})
REQUIRED_EVENT_KEYS = frozenset({
    "schema_version", "service", "operation", "phase", "trace_id", "span_id",
    "request_id", "outcome", "duration_ms_bucket",
})


class DuplicateKeyError(ValueError):
    """Private malformed JSON marker; never copy its source into diagnostics."""


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    """Reject duplicate JSON keys rather than allowing the last value to win."""

    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError("duplicate key")
        result[key] = value
    return result


def candidate_event(record: dict) -> tuple[dict, int] | None:
    """Accept only a producer-shaped console trace with an exact source echo.

    Opaque extra source fields remain unreviewed. This does not turn the record
    into a privacy-canary pass or prove the console entry's E2E provenance.
    """

    metadata = record.get("$metadata")
    need(isinstance(metadata, dict) and metadata.get("service") == WORKER,
         "service_filter_unverified")
    message = metadata.get("message")
    if not isinstance(message, str) or not message.isascii() \
            or not message.startswith("{") or not message.endswith("}") \
            or "\n" in message or "\r" in message \
            or len(message.encode("utf-8")) > 4096:
        return None
    try:
        event = json.loads(message, object_pairs_hook=unique_object)
    except DuplicateKeyError:
        raise CanaryError("candidate_message_schema_unverified") from None
    except (ValueError, TypeError):
        return None
    if not isinstance(event, dict) or event.get("schema_version") != 1 \
            or event.get("service") != "mail_api" \
            or event.get("operation") != "addresses_add":
        return None
    need(type(event.get("schema_version")) is int
         and REQUIRED_EVENT_KEYS.issubset(event)
         and allowlisted_event(event)
         and "response_bytes_bucket" not in event
         and event.get("phase") in ("request_exit", "routing_list", "routing_create")
         and isinstance(event.get("span_id"), str)
         and HEX16.fullmatch(event["span_id"]) is not None
         and any(c != "0" for c in event["span_id"])
         and isinstance(event.get("request_id"), str)
         and UUID.fullmatch(event["request_id"]) is not None
         and isinstance(event.get("trace_id"), str)
         and HEX32.fullmatch(event["trace_id"]) is not None
         and any(c != "0" for c in event["trace_id"]),
         "candidate_message_schema_unverified")
    source = record.get("source")
    need(isinstance(source, dict) and source.get("message") == message
         and ("level" not in source or source["level"] == "log")
         and ("level" not in metadata or metadata["level"] == "log"),
         "candidate_source_echo_unverified")
    timestamp = record.get("timestamp")
    need(type(timestamp) is int and START_MS <= timestamp <= END_MS,
         "candidate_timestamp_unverified")
    return event, timestamp


def candidate_classify(records: list[dict]) -> str:
    """Report only an observed failed routing phase, never an absent phase.

    Unknown records may conceal other requests or events. Even a coherent
    candidate chain is not an exhaustive log or exact CLI request binding.
    """

    observed = [item for record in records if (item := candidate_event(record)) is not None]
    roots = [(event, stamp) for event, stamp in observed
             if event["phase"] == "request_exit"]
    need(len(roots) == 1, "candidate_root_missing_or_ambiguous")
    root, root_time = roots[0]
    status_class = root.get("http_status_class")
    need(type(status_class) is int and status_class in (4, 5)
         and root.get("outcome") == {4: "client_error", 5: "server_error"}[status_class]
         and root.get("error_code") is not None
         and "provider_http_status" not in root
         and "provider_error_code" not in root,
         "candidate_root_schema_unverified")
    phases = [(event, stamp) for event, stamp in observed
              if event["phase"] != "request_exit"
              and event.get("request_id") == root["request_id"]
              and event.get("trace_id") == root["trace_id"]
              and event.get("parent_span_id") == root["span_id"]]
    lists = [(event, stamp) for event, stamp in phases if event["phase"] == "routing_list"]
    creates = [(event, stamp) for event, stamp in phases if event["phase"] == "routing_create"]
    need(len(lists) == 1 and len(creates) <= 1,
         "candidate_phase_missing_or_ambiguous")
    need(len({event["span_id"] for event, _ in lists + creates}) == len(lists + creates)
         and all(event["span_id"] != root["span_id"] for event, _ in lists + creates),
         "candidate_phase_schema_unverified")
    listed, list_time = lists[0]
    for phase, _ in lists + creates:
        success = phase.get("outcome") == "success"
        need(phase.get("outcome") in ("success", "phase_failure")
             and "http_status_class" not in phase
             and "request_bytes_bucket" not in phase
             and ("error_code" not in phase if success else
                  phase.get("error_code") == "dependency_failure")
             and (phase["phase"] == "routing_create"
                  or "provider_http_status" not in phase
                  and "provider_error_code" not in phase),
             "candidate_phase_schema_unverified")
    need(list_time <= root_time, "candidate_phase_order_unverified")
    if listed["outcome"] == "phase_failure":
        need(not creates, "candidate_phase_order_unverified")
        return f"routing_list_phase_failure_outer_class_{status_class}"
    if not creates:
        raise CanaryError("candidate_phase_missing_or_ambiguous")
    created, create_time = creates[0]
    need(list_time <= create_time <= root_time,
         "candidate_phase_order_unverified")
    if created["outcome"] == "success":
        need(created.get("provider_http_status") is None
             and created.get("provider_error_code") is None,
             "candidate_phase_schema_unverified")
        return f"routing_create_success_later_failure_outer_class_{status_class}"
    status = created.get("provider_http_status")
    code = created.get("provider_error_code")
    status_label = f"provider_http_{status}" if status is not None else "provider_http_absent"
    code_label = f"provider_code_{code}" if code is not None else "provider_code_absent"
    return f"routing_create_phase_failure_outer_class_{status_class}_{status_label}_{code_label}"


def value_type(value: object, present: bool = True) -> str:
    """Reduce a private value to a fixed primitive/container type."""

    if not present:
        return "absent"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "list"
    if value is None:
        return "null"
    return "other"


def metadata_type(value: object, present: bool) -> str:
    """Recognize only Cloudflare's documented fixed event type examples."""

    if not present:
        return "absent"
    if value == "cf-worker-log":
        return "worker_log"
    if value == "cf-worker-event":
        return "worker_event"
    return "other"


def shape_summary(records: list[dict]) -> dict[str, str]:
    """Summarize fixed key/type presence, never a key name or value from rows.

    Unknown source object keys are detected but neither inspected nor emitted.
    This is a schema discriminator only: it never licenses an unknown wrapper
    for causal classification or the full retained-log privacy canary.
    """

    states: dict[str, set[str]] = {field: set() for field in SHAPE_FIELDS}
    for record in records:
        metadata = record.get("$metadata")
        need(isinstance(metadata, dict) and metadata.get("service") == WORKER,
             "service_filter_unverified")
        source = record.get("source")
        states["source"].add(value_type(source, "source" in record))
        if isinstance(source, dict):
            for field, key in (("source_object_message", "message"),
                               ("source_object_level", "level"),
                               ("source_object_logs", "logs"),
                               ("source_object_event", "event"),
                               ("source_object_timestamp", "timestamp"),
                               ("source_object_data", "data")):
                states[field].add(value_type(source.get(key), key in source))
            states["source_object_other_keys"].add(
                "present" if set(source) - REVIEWED_SOURCE_KEYS else "absent"
            )
            size = len(source)
            states["source_object_key_bucket"].add(
                "zero" if size == 0 else "one" if size == 1
                else "two_to_four" if size <= 4 else "five_or_more"
            )
        states["metadata_message"].add(
            value_type(metadata.get("message"), "message" in metadata)
        )
        states["metadata_type"].add(
            metadata_type(metadata.get("type"), "type" in metadata)
        )
    return {field: "none" if not values else next(iter(values)) if len(values) == 1
            else "mixed" for field, values in states.items()}


def main() -> int:
    """Emit only fixed statuses after exact-scope, complete event retrieval."""

    shapes: list[dict[str, str]] = []
    shape_reported = False
    try:
        need(sys.argv[1:] == [CONFIRMATION], "explicit_incident_confirmation_required")
        account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        obs_token = os.environ.get("CF_OBSERVABILITY_TOKEN", "")
        deploy_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
        need(HEX32.fullmatch(account) is not None, "account_id_missing_or_invalid")
        need(bool(obs_token and deploy_token), "observability_or_deploy_token_missing")
        preflight(account, obs_token, deploy_token)
        records = retained_events(account, obs_token, START_MS, END_MS,
                                  shape_reporter=shapes.append)
        print_query_shape(shapes)
        shape_reported = True
        summary = shape_summary(records)
        for field in SHAPE_FIELDS:
            print(f"staging_current_address_{field}: {summary[field]}")
        if not records:
            raise CanaryError("address_add_root_missing_or_ambiguous")
        # The historic classifier rejects every unreviewed source/message and
        # demands a single root with linked routing phases. No D1 phase is
        # emitted by addresses_add, so absence of routing cannot imply D1.
        try:
            label = classify(records)
        except CanaryError as strict_error:
            if str(strict_error) != "unreviewed_source_object":
                raise
            # This positive-only fallback does not bless the opaque source.
            # Retained-log privacy remains unverified even if a candidate
            # metadata-message chain is observed.
            print("staging_current_address_retained_privacy: "
                  "UNVERIFIED (unreviewed_source_object)")
            try:
                candidate = candidate_classify(records)
            except CanaryError as candidate_error:
                cause = str(candidate_error)
                cause = cause if cause in CANDIDATE_FAILURES else "unexpected_failure"
                print(f"staging_current_address_incident: UNVERIFIED ({cause})")
            else:
                print("staging_current_address_incident: "
                      f"candidate_window_consistent_{candidate}")
            return 1
    except CanaryError as error:
        if not shape_reported:
            print_query_shape(shapes)
        cause = str(error)
        print("staging_current_address_incident: UNVERIFIED ("
              + (cause if cause in SAFE_FAILURES else "unexpected_failure") + ")")
        return 1
    except Exception:
        if not shape_reported:
            print_query_shape(shapes)
        print("staging_current_address_incident: UNVERIFIED (unexpected_failure)")
        return 1
    print(f"staging_current_address_incident: window_consistent_{label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
