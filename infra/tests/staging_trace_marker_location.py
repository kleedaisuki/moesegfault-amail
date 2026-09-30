"""Classify one historical retained URL canary without emitting telemetry values.

This manual, read-only diagnostic is bound to the failed staging Actions step
from run 36703733769. It never generates a request, creates a marker, or
changes Cloudflare settings. A classification is not a privacy acceptance.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import re

from staging_trace_canary import (
    HEX32, WORKER, CanaryError, preflight, retained_events, retained_record_ids,
)


CONFIRM = "READ_STAGING_TRACE_MARKER_LOCATION"
START = int(datetime(2026, 9, 30, 10, 42, 0, tzinfo=timezone.utc).timestamp() * 1000)
END = int(datetime(2026, 9, 30, 10, 42, 37, tzinfo=timezone.utc).timestamp() * 1000)
MARKER = re.compile(r"amail_(path|query)_canary_([0-9a-f]{32})(?![0-9a-f])")
PATH_PREFIX = "amail_path_canary_"
QUERY_PREFIX = "amail_query_canary_"


class LocationError(Exception):
    """Carry only one of the fixed, non-sensitive classifier failure codes."""


def carrier(path: tuple[str, ...]) -> str:
    """Map a leaf's structural path to a bounded, non-value-bearing label."""

    if path == ("$metadata", "url"):
        return "metadata_url"
    if path == ("$metadata", "message") or path[:1] == ("source",):
        return "source_or_message"
    if len(path) >= 3 and path[:3] == ("$workers", "event", "request"):
        return "workers_event_request"
    if path[:1] == ("$metadata",):
        return "metadata_other"
    return "other_or_multiple"


def string_leaves(value: object, path: tuple[str, ...] = (),
                  depth: int = 0) -> list[tuple[tuple[str, ...], str]]:
    """Find bounded-depth string leaves; never return or print them from main."""

    if depth > 20:
        raise LocationError("record_shape_unverified")
    if isinstance(value, str):
        return [(path, value)]
    leaves: list[tuple[tuple[str, ...], str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > 256:
                raise LocationError("record_shape_unverified")
            if PATH_PREFIX in key or QUERY_PREFIX in key:
                raise LocationError("marker_in_key_unverified")
            leaves.extend(string_leaves(child, path + (key,), depth + 1))
    elif isinstance(value, list):
        if len(value) > 1600:
            raise LocationError("record_shape_unverified")
        for child in value:
            leaves.extend(string_leaves(child, path + ("*",), depth + 1))
    return leaves


def one_or_multiple(values: set[str], single: str) -> str:
    """Suppress heterogeneous fields/types rather than selecting a favorite."""

    return single if values == {single} else "other_or_multiple"


def classify(records: list[dict]) -> tuple[str, str, str, str]:
    """Return only fixed carrier, type, component, and hit-count bins.

    The path/query random suffix is compared only in memory and never appears
    in the result. A zero/ambiguous result is not a contrary privacy finding.
    """

    if not records:
        raise LocationError("marker_not_located")
    try:
        retained_record_ids(records)
    except CanaryError:
        raise LocationError("record_scope_unverified") from None
    matched_records = 0
    carriers: set[str] = set()
    types: set[str] = set()
    suffixes: dict[str, set[str]] = {"path": set(), "query": set()}
    for record in records:
        metadata = record.get("$metadata")
        timestamp = record.get("timestamp")
        if (not isinstance(metadata, dict) or metadata.get("service") != WORKER
                or type(timestamp) is not int or not START <= timestamp <= END):
            raise LocationError("record_scope_unverified")
        record_type = metadata.get("type")
        safe_type = record_type if record_type in ("cf-worker-event", "cf-worker-log") \
            else "other_or_mixed"
        found = False
        for path, value in string_leaves(record):
            if PATH_PREFIX not in value and QUERY_PREFIX not in value:
                continue
            matches = list(MARKER.finditer(value))
            if len(matches) != value.count(PATH_PREFIX) + value.count(QUERY_PREFIX):
                raise LocationError("marker_shape_unverified")
            for match in matches:
                suffixes[match.group(1)].add(match.group(2))
            carriers.add(carrier(path))
            found = True
        if found:
            matched_records += 1
            types.add(safe_type)
    if not matched_records:
        raise LocationError("marker_not_located")
    path = suffixes["path"]
    query = suffixes["query"]
    if len(path) > 1 or len(query) > 1 or (path and query and path != query):
        raise LocationError("marker_shape_unverified")
    component = "both_same_suffix" if path and query else "path_only" if path else "query_only"
    kind = one_or_multiple(carriers, next(iter(carriers)))
    record_type = one_or_multiple(types, next(iter(types)))
    count = "1" if matched_records == 1 else "2_plus"
    return kind, record_type, component, count


def main() -> int:
    """Perform a single private dry query after exact confirmation and preflight."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", choices=[CONFIRM], required=True)
    parser.parse_args()
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    obs_token = os.environ.get("CF_OBSERVABILITY_TOKEN", "")
    deploy_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if HEX32.fullmatch(account) is None or not obs_token or not deploy_token:
        print("staging_trace_marker_location: UNVERIFIED (credential_unavailable)")
        return 1
    try:
        preflight(account, obs_token, deploy_token)
    except Exception:
        print("staging_trace_marker_location: UNVERIFIED (preflight_unverified)")
        return 1
    try:
        labels = classify(retained_events(account, obs_token, START, END))
    except LocationError as error:
        code = error.args[0] if error.args and error.args[0] in {
            "record_shape_unverified", "record_scope_unverified", "marker_in_key_unverified",
            "marker_shape_unverified", "marker_not_located",
        } else "classification_unverified"
        print(f"staging_trace_marker_location: UNVERIFIED ({code})")
        return 1
    except Exception:
        print("staging_trace_marker_location: UNVERIFIED (query_unverified)")
        return 1
    print("staging_trace_marker_location: CLASSIFIED " + " ".join((
        f"carrier={labels[0]}", f"type={labels[1]}",
        f"component={labels[2]}", f"records={labels[3]}",
    )))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
