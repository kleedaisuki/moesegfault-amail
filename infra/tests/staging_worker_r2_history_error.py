"""Classify public GraphQL error templates without exposing provider details.

This is one new content-free historical query, not a retry of either event
query. Even a clean response cannot establish delivery or original failure.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

import staging_worker_r2_delivery_history as history

CONFIRM = "READ_WORKER_R2_HISTORY_ERROR_CLASS_36751791789"
QUERY = """query WorkerR2HistoryErrorClass($zoneTag: string!, $start: Time!, $end: Time!) {
  viewer { zones(filter: {zoneTag: $zoneTag}) {
    sendingErrorProbe: emailSendingAdaptive(filter: {datetime_geq: $start, datetime_leq: $end}, limit: 1, orderBy: [datetime_ASC]) { __typename }
    routingErrorProbe: emailRoutingAdaptive(filter: {datetime_geq: $start, datetime_leq: $end}, limit: 1, orderBy: [datetime_ASC]) { __typename }
  } }
}"""
# Only anchored templates documented by Cloudflare are diagnostic evidence.
TEMPLATES = (
    ("authentication", r"Unauthorized"),
    ("authorization_or_dataset_access", r"not authorized for that account"),
    ("authorization_or_dataset_access", r"zones \[[^\r\n]{0,512}\] are not authorized"),
    ("authorization_or_dataset_access", r"does not have access to the path[^\r\n]{0,512}"),
    ("schema_or_field", r"unknown field[^\r\n]{0,512}"),
    ("schema_or_field", r"scalar fields must have no selections"),
    ("schema_or_field", r"object field must have selections"),
    ("arguments_or_filter", r"error parsing args[^\r\n]{0,512}"),
    ("query_invalid", r"query contains error, please review it and retry"),
    ("dataset_limit", r"cannot request data older than[^\r\n]{0,512}"),
    ("dataset_limit", r"number of fields can't be more than[^\r\n]{0,512}"),
    ("dataset_limit", r"limit must be positive number and not greater than[^\r\n]{0,512}"),
    ("dataset_limit", r"query time range is too large[^\r\n]{0,512}"),
    ("rate_or_resource", r"rate limiter budget depleted, try again after 5 minutes"),
    ("rate_or_resource", r"in combination, your request queries too many nodes, zones and accounts"),
    ("rate_or_resource", r"query consumed excessive resources, please try running smaller queries which consume fewer resources"),
    ("service_unavailable", r"unable to execute query, please try again later"),
    ("service_unavailable", r"too many queries in progress, please try again later"),
    ("internal", r"Internal server error"),
)
CATEGORIES = frozenset(category for category, _ in TEMPLATES) | {
    "no_errors", "unclassified", "invalid", "mixed",
}
SCOPES = frozenset({"none", "sending", "routing", "both", "unscoped", "invalid"})
HTTP_BINS = frozenset({"ok", "authentication", "forbidden", "bad_request",
                      "rate_limited", "server_error", "other"})
FIELDS = ("http", "errors", "scope", "data")
DATA_BINS = frozenset({"minimal_shape", "unverified", "invalid"})


def http_bin(status: int) -> str:
    """Map HTTP metadata to source-owned bins, never infer a token grant."""
    if status == 200:
        return "ok"
    if status == 401:
        return "authentication"
    if status == 403:
        return "forbidden"
    if status == 400:
        return "bad_request"
    if status == 429:
        return "rate_limited"
    return "server_error" if 500 <= status <= 599 else "other"


def fetch(zone: str, token: str, window: tuple) -> tuple[str, dict]:
    """Make exactly one bounded query; HTTP error bodies stay in memory."""
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
        try:
            response = history.OPENER.open(request, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status = http_bin(response.code if isinstance(response, urllib.error.HTTPError)
                              else response.status)
            raw = response.read(history.MAX_BODY + 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise history.HistoryError("provider") from None
    history.need(len(raw) <= history.MAX_BODY, "provider")
    try:
        payload = json.loads(raw, object_pairs_hook=history.unique_object)
    except (ValueError, UnicodeError):
        raise history.HistoryError("schema") from None
    history.need(isinstance(payload, dict), "schema")
    return status, payload


def message_class(error: dict) -> str:
    """Recognize bounded anchored public templates; unknowns remain unknown."""
    message = error.get("message")
    if not isinstance(message, str) or len(message) > 2048:
        return "invalid"
    classes = {category for category, pattern in TEMPLATES
               if re.fullmatch(pattern, message) is not None}
    extensions = error.get("extensions")
    if isinstance(extensions, dict) and extensions.get("code") == "budget":
        classes.add("rate_or_resource")
    return next(iter(classes)) if len(classes) == 1 else "mixed" if classes else "unclassified"


def error_scope(error: dict) -> str:
    """Accept documented string-zero or integer-zero paths, never emit paths."""
    path = error.get("path")
    if path is None:
        return "unscoped"
    if not isinstance(path, list) or len(path) > 10:
        return "invalid"
    if len(path) < 4 or path[:2] != ["viewer", "zones"] \
            or not (type(path[2]) is int and path[2] == 0
                    or type(path[2]) is str and path[2] == "0"):
        return "unscoped"
    if path[3] in ("sendingErrorProbe", "emailSendingAdaptive"):
        return "sending"
    if path[3] in ("routingErrorProbe", "emailRoutingAdaptive"):
        return "routing"
    return "unscoped"


def errors_bin(value: object) -> tuple[str, str]:
    """Preserve contradictory errors rather than cherry-pick one category."""
    if value is None or value == []:
        return "no_errors", "none"
    if not isinstance(value, list) or not 0 < len(value) <= history.LIMIT \
            or not all(isinstance(error, dict) for error in value):
        return "invalid", "invalid"
    classes = {message_class(error) for error in value}
    scopes = {error_scope(error) for error in value}
    category = next(iter(classes)) if len(classes) == 1 else "mixed"
    scope = "both" if scopes == {"sending", "routing"} else \
            next(iter(scopes)) if len(scopes) == 1 else \
            "invalid" if "invalid" in scopes else "unscoped"
    return category, scope


def minimal_data(payload: dict) -> str:
    """Check selected metadata shape without returning even type names."""
    data = payload.get("data")
    viewer = data.get("viewer") if isinstance(data, dict) else None
    zones = viewer.get("zones") if isinstance(viewer, dict) else None
    if not isinstance(zones, list) or len(zones) != 1 or not isinstance(zones[0], dict):
        return "unverified"
    zone = zones[0]
    if set(zone) != {"sendingErrorProbe", "routingErrorProbe"}:
        return "invalid"
    for alias in ("sendingErrorProbe", "routingErrorProbe"):
        rows = zone[alias]
        if not isinstance(rows, list) or len(rows) > 1:
            return "invalid"
        if not all(isinstance(row, dict) and set(row) == {"__typename"}
                   and isinstance(row["__typename"], str) and len(row["__typename"]) <= 128
                   for row in rows):
            return "invalid"
    return "minimal_shape"


def run(confirm: str, original: str) -> dict[str, str]:
    """Use unchanged authenticated original-run provenance and time window."""
    history.need(confirm == CONFIRM, "confirmation")
    history.need(original == history.RUN and os.environ.get("GITHUB_REPOSITORY")
                 == history.REPOSITORY, "identity")
    window = history.historical_window(os.environ.get("GITHUB_TOKEN", ""))
    status, payload = fetch(os.environ.get("CF_ZONE_ID", ""),
                            os.environ.get("CF_OBSERVABILITY_TOKEN", ""), window)
    history.need("errors" in payload or "data" in payload, "schema")
    category, scope = errors_bin(payload.get("errors"))
    return {"http": status, "errors": category, "scope": scope,
            "data": minimal_data(payload) if category == "no_errors" else "unverified"}


def main() -> int:
    """Output only reviewed closed categories; never authorize mail operations."""
    try:
        result = run(sys.argv[1] if len(sys.argv) == 3 else "",
                     sys.argv[2] if len(sys.argv) == 3 else "")
        history.need(set(result) == set(FIELDS) and result["http"] in HTTP_BINS
                     and result["errors"] in CATEGORIES and result["scope"] in SCOPES
                     and result["data"] in DATA_BINS, "schema")
        print("worker_r2_history_error=CLASSIFIED delivery=UNVERIFIED " +
              " ".join(field + "=" + result[field] for field in FIELDS))
        return 0
    except history.HistoryError as error:
        reason = error.args[0] if error.args and error.args[0] in history.REASONS else "internal"
        print("worker_r2_history_error=UNVERIFIED reason=" + reason)
        return 1
    except Exception:
        print("worker_r2_history_error=UNVERIFIED reason=internal")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
