"""Read one bounded staging address-add incident without exporting log payloads.

This manual diagnostic covers hosted run 36553799873 only. Its time window is
the entire hosted mail step because the failed CLI request ID was discarded.
Even one matching request is therefore a time-window inference, not identity
proof. The script makes only dry Cloudflare Observability requests.
"""

from __future__ import annotations

import os
import sys

from staging_address_failure_logs import SAFE_FAILURES, classify, print_query_shape
from staging_trace_canary import (
    CanaryError, HEX32, WORKER, need, preflight, retained_events,
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
        label = classify(records)
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
