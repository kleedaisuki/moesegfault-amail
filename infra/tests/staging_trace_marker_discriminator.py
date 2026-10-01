"""Refine the same historical marker incident using fixed structural bins only.

This read-only follow-up creates no traffic and cannot attest privacy. Unknown
keys and provider values are compared privately, never exported or interpolated.

The completed workflow lane is retired; retain this module for synthetic safety
tests and historical evidence, not as a current provider-read runbook.
"""

from __future__ import annotations

import argparse
import os

import staging_trace_marker_location as first
from staging_trace_canary import allowlisted_event, embedded_events


CONFIRM = "READ_STAGING_TRACE_MARKER_DISCRIMINATOR"


def structural_carrier(path: tuple[str, ...], *, wrapped: bool = False) -> str:
    """Separate known envelopes without disclosing unknown leaf key names."""

    if not wrapped and path[:1] == ("$cloudflare",):
        return "cloudflare_" + structural_carrier(path[1:], wrapped=True)
    if len(path) == 2 and path[0] == "$metadata":
        if path[1] == "url":
            return "metadata_url"
        if path[1] in {"trigger", "spanName", "transactionName"}:
            return "metadata_context"
        if path[1] in {"message", "messageTemplate"}:
            return "metadata_message"
        if path[1] in {"error", "errorTemplate"}:
            return "metadata_error"
    if path[:1] == ("$metadata",):
        return "metadata_other"
    if path[:3] == ("$workers", "event", "request"):
        return "workers_event_request"
    if path[:2] == ("$workers", "event"):
        return "workers_event_other"
    if path[:2] == ("$workers", "diagnosticsChannelEvents"):
        return "workers_diagnostic_channel"
    if path[:1] == ("$workers",):
        return "workers_other"
    if path[:1] == ("source",):
        return "source"
    return "top_level_other"


def fixed_field(container: dict, key: str, known: dict[str, str]) -> str:
    """Classify missing, recognized, unknown-string, and malformed fields."""

    if key not in container:
        return "absent"
    value = container[key]
    if not isinstance(value, str):
        return "malformed"
    return known.get(value, "unrecognized")


def collapse(values: set[str]) -> str:
    """Return one fixed enum or a distinct mixed bin, never an arbitrary value."""

    return next(iter(values)) if len(values) == 1 else "mixed"


def discriminate(records: list[dict]) -> dict[str, str]:
    """Validate the entire window, then refine only marker-bearing records.

    Leaf count counts string leaves, not marker repeats or path tuples: array elements
    must not collapse merely because the shared walker anonymizes their indexes.
    Producer hints are schema categories, not a causal attribution to a logger.
    """

    coarse = first.classify(records)
    carriers: set[str] = set()
    metadata_types: set[str] = set()
    wrapper_types: set[str] = set()
    triggers: set[str] = set()
    payloads: set[str] = set()
    leaf_count = 0
    for record in records:
        wrapper = record.get("$cloudflare")
        if "$cloudflare" in record:
            if not isinstance(wrapper, dict):
                raise first.LocationError("record_shape_unverified")
            workers = wrapper.get("$workers")
            if "$workers" in wrapper and (not isinstance(workers, dict) or (
                    "truncated" in workers and workers["truncated"] is not False)):
                raise first.LocationError("record_truncated_unverified")
        hits = [path for path, value in first.string_leaves(record)
                if first.PATH_PREFIX in value or first.QUERY_PREFIX in value]
        if not hits:
            continue
        leaf_count += len(hits)
        carriers.update(structural_carrier(path) for path in hits)
        metadata_types.add(fixed_field(record["$metadata"], "type", {
            "cf-worker-event": "cf_worker_event", "cf-worker-log": "cf_worker_log",
        }))
        if wrapper is None:
            wrapper_types.add("wrapper_absent")
        elif not isinstance(wrapper, dict) or not isinstance(wrapper.get("$metadata", {}), dict):
            wrapper_types.add("malformed")
        else:
            wrapper_types.add(fixed_field(wrapper.get("$metadata", {}), "type", {
                "cf-worker-event": "cf_worker_event", "cf-worker-log": "cf_worker_log",
            }))
        triggers.add(fixed_field(record.get("$workers", {}), "eventType", {
            "fetch": "fetch", "email": "email", "scheduled": "scheduled",
            "queue": "queue", "alarm": "alarm", "rpc": "rpc",
            "websocket": "websocket",
        }))
        events = embedded_events(record["source"])
        payloads.add("allowlisted_application" if events and all(
            allowlisted_event(event) for event in events) else
            "unallowlisted_application" if events else "not_application_schema")
    return {
        "carrier": "+".join(sorted(carriers)),
        "carriers": "1" if len(carriers) == 1 else "2_plus",
        "leaves": "1" if leaf_count == 1 else "2_plus",
        "metadata_type": collapse(metadata_types),
        "wrapper_type": collapse(wrapper_types),
        "trigger": collapse(triggers),
        "source_shape": collapse(payloads),
        "component": coarse[2], "records": coarse[3],
    }


def main() -> int:
    """Query only the unchanged service/window after exact guarded preflight."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", choices=[CONFIRM], required=True)
    parser.parse_args()
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    obs_token = os.environ.get("CF_OBSERVABILITY_TOKEN", "")
    deploy_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if first.HEX32.fullmatch(account) is None or not obs_token or not deploy_token:
        print("staging_trace_marker_discriminator: UNVERIFIED (credential_unavailable)")
        return 1
    try:
        first.preflight(account, obs_token, deploy_token)
    except Exception:
        print("staging_trace_marker_discriminator: UNVERIFIED (preflight_unverified)")
        return 1
    try:
        labels = discriminate(first.retained_events(account, obs_token, first.START, first.END))
    except Exception:
        print("staging_trace_marker_discriminator: UNVERIFIED (classification_unverified)")
        return 1
    print("staging_trace_marker_discriminator: CLASSIFIED " + " ".join(
        f"{key}={value}" for key, value in labels.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
