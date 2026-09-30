"""Describe a reduced historical GraphQL response without delivery claims."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

import staging_worker_r2_delivery_history as history

CONFIRM = "READ_WORKER_R2_HISTORY_BASELINE_SHAPE_36751791789"
QUERY = """query WorkerR2HistoryBaselineShape($zoneTag: string!, $start: Time!, $end: Time!) {
  viewer { zones(filter: {zoneTag: $zoneTag}) {
    sendingShape: emailSendingAdaptive(filter: {datetime_geq: $start, datetime_leq: $end}, limit: 100, orderBy: [datetime_ASC]) { datetime status }
    routingShape: emailRoutingAdaptive(filter: {datetime_geq: $start, datetime_leq: $end}, limit: 100, orderBy: [datetime_ASC]) { datetime status }
  } }
}"""
ALIASES = ("sendingShape", "routingShape")
FIELDS = ("envelope", "graphql", "error_path", "zones", "sending_rows",
          "sending_datetime", "sending_status", "routing_rows",
          "routing_datetime", "routing_status")
BINS = frozenset({"exact", "extra_keys", "invalid", "none", "empty_errors",
                  "errors", "sending", "routing", "both", "unscoped",
                  "zero", "one", "multiple", "full", "no_rows",
                  "utc_in_window", "utc_outside_window", "string_other",
                  "null", "mixed", "string"})


def fetch(zone: str, token: str, window: tuple) -> dict:
    """Make one reduced no-redirect query; no mail identity fields are selected."""
    history.need(re.fullmatch(r"[0-9a-f]{32}", zone) is not None and bool(token),
                 "credential")
    body = json.dumps({"query": QUERY, "variables": {
        "zoneTag": zone,
        "start": window[0].isoformat(timespec="seconds").replace("+00:00", "Z"),
        "end": window[1].isoformat(timespec="seconds").replace("+00:00", "Z"),
    }}, separators=(",", ":")).encode()
    request = urllib.request.Request(history.API, data=body, method="POST", headers={
        "Authorization": "Bearer " + token, "Accept": "application/json",
        "Content-Type": "application/json",
    })
    try:
        with history.OPENER.open(request, timeout=20) as response:
            history.need(response.status == 200, "provider")
            raw = response.read(history.MAX_BODY + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        raise history.HistoryError("provider") from None
    history.need(len(raw) <= history.MAX_BODY, "provider")
    try:
        payload = json.loads(raw, object_pairs_hook=history.unique_object)
    except (ValueError, UnicodeError):
        raise history.HistoryError("schema") from None
    history.need(isinstance(payload, dict), "schema")
    return payload


def group(values: list[str]) -> str:
    """Reduce bounded closed bins without exposing counts or values."""
    bins = set(values)
    return "no_rows" if not bins else next(iter(bins)) if len(bins) == 1 else "mixed"


def error_bins(value: object) -> tuple[str, str]:
    """Inspect error presence and canonical alias paths, never error messages."""
    if value is None:
        return "none", "none"
    if not isinstance(value, list) or len(value) > history.LIMIT:
        return "invalid", "invalid"
    if not value:
        return "empty_errors", "none"
    paths = set()
    for error in value:
        if not isinstance(error, dict):
            return "invalid", "invalid"
        path = error.get("path")
        if path is None:
            paths.add("unscoped")
            continue
        if not isinstance(path, list) or len(path) > 10:
            return "errors", "invalid"
        if len(path) >= 4 and path[:2] == ["viewer", "zones"] \
                and type(path[2]) is int and path[2] == 0:
            paths.add("sending" if path[3] == ALIASES[0] else
                      "routing" if path[3] == ALIASES[1] else "unscoped")
        else:
            paths.add("unscoped")
    if paths == {"sending", "routing"}:
        return "errors", "both"
    return "errors", next(iter(paths)) if len(paths) == 1 else "unscoped"


def date_bin(value: object, window: tuple) -> str:
    """Classify timestamp format and scope without returning timestamps."""
    if value is None:
        return "null"
    if not isinstance(value, str) or len(value) > 32:
        return "invalid"
    try:
        instant = history.utc(value)
    except history.HistoryError:
        return "string_other"
    return "utc_in_window" if window[0] <= instant <= window[1] else "utc_outside_window"


def row_bins(rows: object, window: tuple) -> tuple[str, str, str]:
    """Validate minimal bounded rows without selecting candidate identity."""
    if not isinstance(rows, list) or len(rows) > history.LIMIT:
        return "invalid", "invalid", "invalid"
    cardinality = "full" if len(rows) == history.LIMIT else \
                  "zero" if not rows else "one" if len(rows) == 1 else "multiple"
    dates, statuses = [], []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"datetime", "status"}:
            return cardinality, "invalid", "invalid"
        dates.append(date_bin(row["datetime"], window))
        status = row["status"]
        statuses.append("null" if status is None else "string"
                        if isinstance(status, str) and len(status) <= 512 else "invalid")
    return cardinality, group(dates), group(statuses)


def diagnose(payload: dict, window: tuple) -> dict[str, str]:
    """Describe schema only; even errors and full pages never attest history."""
    result = dict.fromkeys(FIELDS, "invalid")
    result["envelope"] = "exact" if set(payload) in ({"data"}, {"data", "errors"}) \
                         else "extra_keys" if "data" in payload else "invalid"
    result["graphql"], result["error_path"] = error_bins(payload.get("errors"))
    data = payload.get("data")
    viewer = data.get("viewer") if isinstance(data, dict) else None
    zones = viewer.get("zones") if isinstance(viewer, dict) else None
    if not isinstance(zones, list) or len(zones) > history.LIMIT:
        return result
    result["zones"] = "zero" if not zones else "one" if len(zones) == 1 else "multiple"
    if len(zones) != 1 or not isinstance(zones[0], dict):
        return result
    for prefix, alias in zip(("sending", "routing"), ALIASES):
        for suffix, value in zip(("rows", "datetime", "status"),
                                 row_bins(zones[0].get(alias), window)):
            result[prefix + "_" + suffix] = value
    return result


def run(confirm: str, original: str) -> dict[str, str]:
    """Bind the distinct query to exactly the unchanged original experiment."""
    history.need(confirm == CONFIRM, "confirmation")
    history.need(original == history.RUN and os.environ.get("GITHUB_REPOSITORY")
                 == history.REPOSITORY, "identity")
    window = history.historical_window(os.environ.get("GITHUB_TOKEN", ""))
    return diagnose(fetch(os.environ.get("CF_ZONE_ID", ""),
                          os.environ.get("CF_OBSERVABILITY_TOKEN", ""), window), window)


def main() -> int:
    """Print only closed bins; diagnostic success is never delivery acceptance."""
    try:
        result = run(sys.argv[1] if len(sys.argv) == 3 else "",
                     sys.argv[2] if len(sys.argv) == 3 else "")
        history.need(set(result) == set(FIELDS)
                     and all(value in BINS for value in result.values()), "schema")
        print("worker_r2_history_shape=SHAPE_DIAGNOSED delivery=UNVERIFIED " +
              " ".join(field + "=" + result[field] for field in FIELDS))
        return 0
    except history.HistoryError as error:
        reason = error.args[0] if error.args and error.args[0] in history.REASONS else "internal"
        print("worker_r2_history_shape=UNVERIFIED reason=" + reason)
        return 1
    except Exception:
        print("worker_r2_history_shape=UNVERIFIED reason=internal")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
