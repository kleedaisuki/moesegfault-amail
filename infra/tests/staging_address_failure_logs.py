"""Classify one historic staging address-add failure from retained logs only.

The fixed incident window prevents this tool from becoming a general-purpose
log exporter. It sends no mail or address request, and never prints raw events,
request identifiers, mailbox data, provider text, or Cloudflare credentials.
"""

from __future__ import annotations

import os
import sys

from staging_trace_canary import (
    CanaryError, HEX16, HEX32, QUERY_SHAPE_FIELDS, UUID, WORKER, allowlisted_event,
    embedded_events, empty_log_payload, need, preflight, request_json, retained_events,
)


# Hosted job 36533465672: the acceptance step began at 06:55:31 and ended
# at 06:56:02 UTC. One-second margins cover event timestamp granularity.
START_MS = 1790664930000
END_MS = 1790664963000
CONFIRMATION = "READ_STAGING_ADDRESS_INCIDENT_36533465672"
SAFE_FAILURES = frozenset({
    "explicit_incident_confirmation_required", "account_id_missing_or_invalid",
    "observability_or_deploy_token_missing", "deployed_privacy_settings_unverified",
    "observability_permission_denied", "observability_http_unavailable",
    "observability_network_unavailable", "observability_response_too_large",
    "observability_response_malformed", "observability_query_failed",
    "observability_result_malformed", "observability_run_malformed",
    "observability_query_incomplete", "observability_query_status_unverified",
    "observability_query_echo_unverified",
    "observability_events_view_absent",
    "observability_keys_malformed", "service_filter_key_unverified",
    "observability_events_malformed", "observability_window_too_busy",
    "observability_count_malformed", "observability_page_incomplete",
    "observability_cursor_missing", "observability_cursor_stalled",
    "service_filter_unverified", "unreviewed_log_payload", "unreviewed_event_schema",
    "retained_event_echo_disagrees",
    "address_add_root_missing_or_ambiguous", "address_add_root_correlation_unverified",
    "address_add_root_outcome_inconsistent", "address_add_root_status_unverified",
    "routing_phase_missing_or_ambiguous", "routing_phase_order_inconsistent",
    "routing_list_outcome_unverified", "routing_create_outcome_unverified",
    "service_value_result_list_missing", "service_value_row_schema_invalid",
    "service_value_absent", "service_value_present_with_others",
    "service_value_explicit_empty",
    "service_value_unverified",
})


def service_value_status(account: str, token: str) -> str:
    """Classify only the exact-window values response, never echoing its rows."""

    body = {
        "datasets": [], "key": "$metadata.service", "type": "string",
        "timeframe": {"from": START_MS, "to": END_MS},
        "filters": [{"key": "$metadata.service", "operation": "eq",
                     "type": "string", "value": WORKER}],
    }
    payload = request_json(account, token, "values", body)
    if "result" not in payload:
        return "result_list_missing"
    rows = payload["result"]
    if not isinstance(rows, list) or not all(
        isinstance(row, dict) and isinstance(row.get("dataset"), str)
        and row.get("key") == "$metadata.service"
        and row.get("type") == "string" and isinstance(row.get("value"), str)
        for row in rows
    ):
        return "row_schema_invalid"
    if not rows:
        return "explicit_empty"
    expected = any(row["value"] == WORKER for row in rows)
    others = any(row["value"] != WORKER for row in rows)
    if expected and others:
        return "present_with_others"
    return "present" if expected else "absent"


def print_query_shape(reports: list[dict[str, str]]) -> None:
    """Emit only fixed component categories, merging differing page echoes."""

    for field in QUERY_SHAPE_FIELDS:
        states = {report[field] for report in reports}
        state = "unavailable"
        if len(states) == 1:
            state = states.pop()
        elif states:
            state = "inconsistent"
        print(f"staging_address_query_{field}: {state}")


def reviewed_events(records: list[dict]) -> list[dict]:
    """Extract only reviewed application events from a complete service window."""

    events: list[dict] = []
    for record in records:
        metadata = record.get("$metadata")
        need(isinstance(metadata, dict) and metadata.get("service") == WORKER,
             "service_filter_unverified")
        source = record.get("source")
        message = metadata.get("message")
        from_source = embedded_events(source)
        from_message = embedded_events(message)
        need(empty_log_payload(source) or bool(from_source), "unreviewed_log_payload")
        need(empty_log_payload(message) or bool(from_message), "unreviewed_log_payload")
        need(all(allowlisted_event(event) for event in from_source + from_message),
             "unreviewed_event_schema")
        need(not (from_source and from_message) or from_source == from_message,
             "retained_event_echo_disagrees")
        events.extend(from_source or from_message)
    return events


def classify(records: list[dict]) -> str:
    """Require one causal address-add request, then report bounded numeric facts."""

    events = reviewed_events(records)
    roots = [event for event in events if event.get("service") == "mail_api"
             and event.get("operation") == "addresses_add"
             and event.get("phase") == "request_exit"]
    need(len(roots) == 1, "address_add_root_missing_or_ambiguous")
    root = roots[0]
    need(isinstance(root.get("request_id"), str)
         and UUID.fullmatch(root["request_id"]) is not None
         and isinstance(root.get("span_id"), str)
         and HEX16.fullmatch(root["span_id"]) is not None,
         "address_add_root_correlation_unverified")
    status_class = root.get("http_status_class")
    need(status_class in (4, 5), "address_add_root_status_unverified")
    need(root.get("outcome") == {4: "client_error", 5: "server_error"}[status_class],
         "address_add_root_outcome_inconsistent")
    phases = [event for event in events if event.get("request_id") == root.get("request_id")
              and event.get("trace_id") == root.get("trace_id")
              and event.get("parent_span_id") == root.get("span_id")
              and event.get("operation") == "addresses_add"]
    lists = [event for event in phases if event.get("phase") == "routing_list"]
    creates = [event for event in phases if event.get("phase") == "routing_create"]
    need(len(lists) == 1 and len(creates) <= 1, "routing_phase_missing_or_ambiguous")
    listed = lists[0]
    if listed.get("outcome") == "phase_failure":
        need(not creates, "routing_phase_order_inconsistent")
        return f"routing_list_failed_outer_class_{root['http_status_class']}"
    need(listed.get("outcome") == "success", "routing_list_outcome_unverified")
    if not creates:
        return f"routing_list_succeeded_create_not_observed_outer_class_{root['http_status_class']}"
    created = creates[0]
    outcome = created.get("outcome")
    need(outcome in ("success", "phase_failure"), "routing_create_outcome_unverified")
    status = created.get("provider_http_status")
    code = created.get("provider_error_code")
    status_label = f"provider_http_{status}" if status is not None else "provider_http_absent"
    code_label = f"provider_code_{code}" if code is not None else "provider_code_absent"
    return f"routing_create_{outcome}_outer_class_{root['http_status_class']}_{status_label}_{code_label}"


def main() -> int:
    """Probe values and events independently after privacy and key preflight."""

    try:
        need(sys.argv[1:] == [CONFIRMATION], "explicit_incident_confirmation_required")
        account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        obs_token = os.environ.get("CF_OBSERVABILITY_TOKEN", "")
        deploy_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
        need(HEX32.fullmatch(account) is not None, "account_id_missing_or_invalid")
        need(bool(obs_token and deploy_token), "observability_or_deploy_token_missing")
        preflight(account, obs_token, deploy_token)
        service_error = None
        try:
            service_status = service_value_status(account, obs_token)
        except CanaryError as error:
            service_status = "unverified"
            service_error = str(error)
        except Exception:
            service_status = "unverified"
            service_error = "unexpected_failure"
        print(f"staging_address_service: service_value_{service_status}")
        if service_error is not None:
            cause = service_error if service_error in SAFE_FAILURES else "unexpected_failure"
            print(f"staging_address_service_cause: {cause}")
        query_shapes: list[dict[str, str]] = []
        try:
            records = retained_events(account, obs_token, START_MS, END_MS,
                                      shape_reporter=query_shapes.append)
        except CanaryError as error:
            print_query_shape(query_shapes)
            label = str(error)
            cause = label if label in SAFE_FAILURES else "unexpected_failure"
            print(f"staging_address_events: UNVERIFIED ({cause})")
            raise
        except Exception:
            print_query_shape(query_shapes)
            print("staging_address_events: UNVERIFIED (unexpected_failure)")
            raise CanaryError("unexpected_failure") from None
        print_query_shape(query_shapes)
        print(f"staging_address_events: {'view_present' if records else 'explicit_empty'}")
        # Values may include unrelated account services even with a filter.
        # Positive membership suffices here only because classify() independently
        # requires the exact service on every retained event in the complete view.
        need(service_status in ("present", "present_with_others"),
             service_error or f"service_value_{service_status}")
        label = classify(records)
    except CanaryError as error:
        label = str(error)
        print(f"staging_address_incident: UNVERIFIED ({label if label in SAFE_FAILURES else 'unexpected_failure'})")
        return 1
    except Exception:
        print("staging_address_incident: UNVERIFIED (unexpected_failure)")
        return 1
    print(f"staging_address_incident: {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
