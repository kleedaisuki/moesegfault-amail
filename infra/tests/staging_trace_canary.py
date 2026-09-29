"""Inspect retained staging mail logs without displaying or storing raw records.

This is an explicitly invoked, staging-only deployed canary. It performs no mail
or routing mutation. The operator supplies an already authenticated, isolated
AMAIL_HOME under the repository's ignored .temp directory and an Observability
token through environment variables; no credential or log row is an argument.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid


ROOT = Path(__file__).resolve().parents[2]
WORKER = "amail-mail-staging"
API = "https://mail-staging.moesegfault.dev"
OBS_API = "https://api.cloudflare.com/client/v4/accounts"
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
HEX16 = re.compile(r"[0-9a-f]{16}\Z")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
MAX_PAGE = 200
MAX_EVENTS = 1600
EVENT_KEYS = frozenset({
    "schema_version", "service", "operation", "phase", "trace_id", "span_id",
    "parent_span_id", "request_id", "outcome", "error_code",
    "http_status_class", "duration_ms_bucket", "request_bytes_bucket",
    "response_bytes_bucket", "provider_http_status", "provider_error_code",
})
EVENT_SERVICES = frozenset({"mail_api", "mail_cli"})
EVENT_PHASES = frozenset({
    "request_exit", "operation_exit", "d1_read", "d1_write", "r2_write", "provider_send",
    "routing_list", "routing_create",
})
EVENT_OUTCOMES = frozenset({"success", "client_error", "server_error", "phase_failure"})
EVENT_OPERATIONS = frozenset({
    "health", "inbound", "addresses_list", "addresses_add", "addresses_delete",
    "messages_list", "messages_search", "search_poll", "messages_send",
    "messages_get", "messages_archive", "messages_mark", "messages_delete",
    "telemetry_upload", "unknown",
})
EVENT_ERRORS = frozenset({
    "invalid_request", "unauthorized", "forbidden", "not_found", "conflict",
    "rate_limited", "service_unavailable", "other_client", "other_server",
    "dependency_failure",
})


class CanaryError(Exception):
    """A fixed stage code, never raw provider, HTTP, CLI, or SQLite text."""


def need(condition: bool, code: str) -> None:
    """Stop on ambiguous evidence instead of silently turning it into a pass."""

    if not condition:
        raise CanaryError(code)


def under_temp(path: Path) -> Path:
    """Keep the authorized CLI state and executable inside the workspace."""

    resolved = path.resolve(strict=True)
    need(resolved.is_relative_to((ROOT / ".temp").resolve()), "path_not_under_temp")
    return resolved


def request_json(account: str, token: str, endpoint: str, body: dict) -> dict:
    """Perform one bounded Cloudflare query without exposing an error body."""

    url = f"{OBS_API}/{account}/workers/observability/telemetry/{endpoint}"
    request = Request(
        url,
        data=json.dumps(body, separators=(",", ":")).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read(2_000_001)
    except HTTPError as error:
        if error.code == 403:
            raise CanaryError("observability_permission_denied") from None
        raise CanaryError("observability_http_unavailable") from None
    except (URLError, TimeoutError):
        raise CanaryError("observability_network_unavailable") from None
    need(len(raw) <= 2_000_000, "observability_response_too_large")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise CanaryError("observability_response_malformed") from None
    need(isinstance(payload, dict) and payload.get("success") is True
         and ("errors" not in payload or payload["errors"] == []),
         "observability_query_failed")
    return payload


def preflight(account: str, obs_token: str, deploy_token: str) -> None:
    """Require deployed privacy settings and a verified service filter key."""

    sys.path.insert(0, str(ROOT / "crates" / "mail-worker"))
    from check_observability import verify  # pylint: disable=import-outside-toplevel

    try:
        safe = verify("staging", account, deploy_token)
    except ValueError:
        safe = False
    need(safe, "deployed_privacy_settings_unverified")
    payload = request_json(account, obs_token, "keys", {"limit": 1000})
    result = payload.get("result")
    # The keys endpoint is a paginated list, not a query-run envelope.
    need(isinstance(result, list), "observability_keys_malformed")
    need(any(isinstance(row, dict) and row.get("key") == "$metadata.service"
             and row.get("type") == "string" for row in result),
         "service_filter_key_unverified")


def journal_max(home: Path) -> int:
    """Read only the integer watermark from the local redacted journal."""

    path = home / "telemetry.sqlite3"
    if not path.is_file():
        return 0
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5) as conn:
        return int(conn.execute("SELECT COALESCE(MAX(id),0) FROM events").fetchone()[0])


def journal_new(home: Path, watermark: int) -> tuple[str, str, str]:
    """Find exactly one CLI list event and retain only its safe correlation IDs."""

    path = home / "telemetry.sqlite3"
    need(path.is_file(), "cli_journal_missing")
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5) as conn:
        rows = conn.execute(
            "SELECT status,trace_id,span_id,correlation_id FROM events "
            "WHERE id>? AND operation='addresses.list' ORDER BY id", (watermark,),
        ).fetchall()
    need(len(rows) == 1 and rows[0][0] == 200, "cli_list_not_correlatable")
    _, trace_id, span_id, request_id = rows[0]
    need(isinstance(trace_id, str) and HEX32.fullmatch(trace_id) is not None,
         "cli_trace_id_invalid")
    need(isinstance(span_id, str) and HEX16.fullmatch(span_id) is not None,
         "cli_span_id_invalid")
    need(isinstance(request_id, str) and UUID.fullmatch(request_id) is not None,
         "cli_request_id_invalid")
    return trace_id, span_id, request_id


def rejected_url_failure(status: int, request_id: object) -> str | None:
    """Classify only reviewed status/header facts; never expose response data."""

    if status == 403:
        return "rejected_url_status_forbidden"
    if status == 404:
        return "rejected_url_status_not_found"
    if 500 <= status <= 599:
        return "rejected_url_status_server_error"
    if status != 401:
        return "rejected_url_status_other"
    if request_id is None:
        return "rejected_url_header_absent"
    if not isinstance(request_id, str) or UUID.fullmatch(request_id) is None:
        return "rejected_url_header_malformed"
    return None


def run_probes(cli: Path, home: Path) -> tuple[int, int, tuple[str, str, str], str, tuple[str, str]]:
    """Exercise an ordinary CLI read and one anonymous rejected synthetic URL."""

    # Do not inherit Cloudflare API capabilities into the native mail process.
    inherited = (
        "PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SYSTEMROOT",
        "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL", "XDG_RUNTIME_DIR",
        "DBUS_SESSION_BUS_ADDRESS",
    )
    environment = {key: os.environ[key] for key in inherited if key in os.environ}
    environment.update({
        "AMAIL_HOME": str(home),
        "AMAIL_API_BASE": API,
        "AMAIL_ISSUER": "https://identity-staging.moesegfault.dev",
        "AMAIL_CLIENT_ID": "amail-cli-staging",
        "AMAIL_REDIRECT_URI": "http://127.0.0.1/callback",
    })
    before = journal_max(home)
    start = int(time.time() * 1000) - 2_000
    result = subprocess.run(
        [str(cli), "address", "list"], env=environment,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=30, check=False,
    )
    need(result.returncode == 0, "cli_address_list_failed")
    ids = journal_new(home, before)
    marker = uuid.uuid4().hex
    path_marker = f"amail_path_canary_{marker}"
    query_marker = f"amail_query_canary_{marker}"
    # Use a protected read route so URL denial is not confounded with unknown-path handling.
    request = Request(f"{API}/v1/messages/{path_marker}?probe={query_marker}", method="GET")
    try:
        with urlopen(request, timeout=15) as response:
            status = response.status
            denied_id = response.headers.get("x-amail-request-id")
    except HTTPError as error:
        status = error.code
        denied_id = error.headers.get("x-amail-request-id")
    except (URLError, TimeoutError):
        raise CanaryError("rejected_url_network_unavailable") from None
    failure = rejected_url_failure(status, denied_id)
    if failure is not None:
        raise CanaryError(failure)
    end = int(time.time() * 1000) + 2_000
    return start, end, ids, denied_id, (path_marker, query_marker)


def expected_service_filter(value: object) -> bool:
    """Recognize only the one exact service filter, allowing its optional tag."""

    return isinstance(value, dict) and value.get("key") == "$metadata.service" \
        and value.get("operation") in ("eq", "=") \
        and value.get("type") == "string" and value.get("value") == WORKER \
        and set(value).issubset({"key", "operation", "type", "value", "kind"}) \
        and value.get("kind", "filter") == "filter"


QUERY_SHAPE_FIELDS = (
    "run_status", "dry", "timeframe", "view", "datasets",
    "filter_combination", "service_filter", "narrowing", "events_container",
)


def shape_match(container: object, key: str, expected: object) -> str:
    """Classify one echoed field without returning its provider-supplied value."""

    if not isinstance(container, dict) or key not in container:
        return "unavailable"
    return "match" if container[key] == expected else "mismatch"


def query_shape(result: object, start: int, end: int) -> dict[str, str]:
    """Reduce a query response to fixed, non-sensitive echo/view categories.

    Cloudflare does not echo the top-level requested view in the documented run.
    An unexpected legacy parameters.view is reported only as a contradiction.
    The required result.events container verifies the requested result shape.
    """

    run = result.get("run") if isinstance(result, dict) else None
    query = run.get("query") if isinstance(run, dict) else None
    parameters = query.get("parameters") if isinstance(query, dict) else None
    timeframe = run.get("timeframe") if isinstance(run, dict) else None
    filters = parameters.get("filters") if isinstance(parameters, dict) else None
    status = run.get("status") if isinstance(run, dict) else None
    dry = run.get("dry") if isinstance(run, dict) else None
    if not isinstance(result, dict):
        events_container = "unavailable"
    elif "events" not in result:
        events_container = "absent"
    else:
        events_container = "present" if isinstance(result["events"], dict) else "invalid"
    return {
        "run_status": ("completed" if status == "COMPLETED" else "started"
                       if status == "STARTED" else "unavailable" if status is None else "other"),
        "dry": "true" if dry is True else "false" if dry is False else "unavailable",
        "timeframe": ("unavailable" if not isinstance(timeframe, dict)
                      else "match" if timeframe.get("from") == start
                      and timeframe.get("to") == end else "mismatch"),
        "view": shape_match(parameters, "view", "events"),
        "datasets": shape_match(parameters, "datasets", []),
        "filter_combination": ("unavailable" if not isinstance(parameters, dict)
                               or "filterCombination" not in parameters
                               else "match" if parameters["filterCombination"] in ("and", "AND")
                               else "mismatch"),
        "service_filter": ("unavailable" if not isinstance(filters, list)
                           else "match" if len(filters) == 1
                           and expected_service_filter(filters[0]) else "mismatch"),
        "narrowing": ("unavailable" if not isinstance(parameters, dict)
                      else "match" if all(not parameters.get(key)
                                          for key in ("needle", "havings", "groupBys"))
                      else "mismatch"),
        "events_container": events_container,
    }


def query_echo_matches(run: dict, start: int, end: int) -> bool:
    """Require documented scope echoes; reject a contradictory legacy view."""

    shape = query_shape({"run": run}, start, end)
    return shape["view"] != "mismatch" and all(shape[key] == "match" for key in (
        "timeframe", "datasets", "filter_combination", "service_filter", "narrowing",
    ))


def query_page(account: str, token: str, start: int, end: int, cursor: str | None,
               shape_reporter: Callable[[dict[str, str]], None] | None = None) -> dict:
    """Read one dry retained-event page, rejecting absent or unfinished views."""

    body: dict = {
        "queryId": str(uuid.uuid4()), "timeframe": {"from": start, "to": end},
        "dry": True, "limit": MAX_PAGE, "view": "events",
        "parameters": {"datasets": [], "filterCombination": "and", "filters": [{
            "key": "$metadata.service", "operation": "eq", "type": "string", "value": WORKER,
        }]},
    }
    if cursor:
        body["offset"] = cursor
        body["offsetDirection"] = "next"
    result = request_json(account, token, "query", body).get("result")
    if shape_reporter is not None:
        shape_reporter(query_shape(result, start, end))
    need(isinstance(result, dict), "observability_result_malformed")
    run = result.get("run")
    need(isinstance(run, dict), "observability_run_malformed")
    status = run.get("status")
    need(status == "COMPLETED",
         "observability_query_incomplete" if status == "STARTED"
         else "observability_query_status_unverified")
    need(run.get("dry") is True, "observability_query_echo_unverified")
    need(query_echo_matches(run, start, end), "observability_query_echo_unverified")
    # The API schema marks result.events optional even for the events view.
    # Missing is not equivalent to a completed zero-event container.
    need("events" in result, "observability_events_view_absent")
    need(isinstance(result["events"], dict), "observability_events_malformed")
    events = result["events"]
    need(isinstance(events.get("events"), list), "observability_events_malformed")
    need(type(events.get("count")) is int and events["count"] >= 0,
         "observability_count_malformed")
    return events


def retained_events(account: str, token: str, start: int, end: int,
                    shape_reporter: Callable[[dict[str, str]], None] | None = None) -> list[dict]:
    """Fetch a complete bounded window or fail; truncated data is no privacy proof."""

    records: list[dict] = []
    cursor: str | None = None
    total_count: int | None = None
    seen_ids: set[str] = set()
    while True:
        page = query_page(account, token, start, end, cursor, shape_reporter)
        batch = page["events"]
        need(len(batch) <= MAX_PAGE, "observability_events_malformed")
        need(all(isinstance(item, dict) for item in batch), "observability_events_malformed")
        count = page.get("count")
        need(type(count) is int and count >= len(records) + len(batch),
             "observability_count_malformed")
        if total_count is None:
            total_count = count
        need(count == total_count, "observability_count_malformed")
        # A paginated result cannot prove completeness when rows repeat or
        # lack stable cursor IDs, even if its reported total eventually matches.
        if cursor is not None or count > len(batch):
            ids = [item.get("$metadata", {}).get("id")
                   if isinstance(item.get("$metadata"), dict) else None
                   for item in batch]
            need(all(isinstance(item_id, str) and item_id for item_id in ids),
                 "observability_cursor_missing")
            need(not any(item_id in seen_ids for item_id in ids)
                 and len(set(ids)) == len(ids), "observability_cursor_stalled")
            seen_ids.update(ids)
        records.extend(batch)
        need(len(records) <= MAX_EVENTS, "observability_window_too_busy")
        if len(records) == total_count:
            return records
        need(len(batch) == MAX_PAGE, "observability_page_incomplete")
        metadata = batch[-1].get("$metadata")
        need(isinstance(metadata, dict) and isinstance(metadata.get("id"), str),
             "observability_cursor_missing")
        next_cursor = metadata["id"]
        need(next_cursor != cursor, "observability_cursor_stalled")
        cursor = next_cursor


def embedded_events(value: object, depth: int = 0) -> list[dict]:
    """Decode only an exact event or a single reviewed transport wrapper."""

    if depth > 5:
        return []
    if isinstance(value, dict):
        if value.get("schema_version") == 1:
            return [value]
        if set(value) == {"message"}:
            return embedded_events(value["message"], depth + 1)
        return []
    if isinstance(value, list):
        return embedded_events(value[0], depth + 1) if len(value) == 1 else []
    if isinstance(value, str) and len(value) <= 4096 and value.lstrip().startswith(("{", "[")):
        try:
            return embedded_events(json.loads(value), depth + 1)
        except ValueError:
            return []
    return []


def empty_log_payload(value: object) -> bool:
    """Treat only absent or structurally empty log fields as non-evidence."""

    return value is None or value == "" or value == {} or value == []


def allowlisted_event(event: dict) -> bool:
    """Reject arbitrary application-event attributes and malformed identifiers."""

    if (not set(event).issubset(EVENT_KEYS)
            or event.get("schema_version") != 1
            or not isinstance(event.get("service"), str)
            or event["service"] not in EVENT_SERVICES
            or not isinstance(event.get("phase"), str)
            or event["phase"] not in EVENT_PHASES
            or not isinstance(event.get("operation"), str)
            or event["operation"] not in EVENT_OPERATIONS
            or not isinstance(event.get("outcome"), str)
            or event["outcome"] not in EVENT_OUTCOMES):
        return False
    if event.get("error_code") is not None and (
            not isinstance(event["error_code"], str)
            or event["error_code"] not in EVENT_ERRORS):
        return False
    if event.get("http_status_class") is not None and event["http_status_class"] not in range(6):
        return False
    for key in ("duration_ms_bucket", "request_bytes_bucket", "response_bytes_bucket"):
        value = event.get(key)
        if value is not None and (type(value) is not int or value < 0 or value > 1 << 30):
            return False
    status = event.get("provider_http_status")
    if status is not None and (type(status) is not int or not 100 <= status <= 599):
        return False
    code = event.get("provider_error_code")
    if code is not None and (type(code) is not int or not 0 <= code <= 0xFFFFFFFF):
        return False
    trace = event.get("trace_id")
    span = event.get("span_id")
    parent = event.get("parent_span_id")
    request_id = event.get("request_id")
    if not isinstance(trace, str) or HEX32.fullmatch(trace) is None:
        return False
    if span is not None and (not isinstance(span, str) or HEX16.fullmatch(span) is None):
        return False
    if parent is not None and (not isinstance(parent, str) or HEX16.fullmatch(parent) is None):
        return False
    if request_id is not None and (not isinstance(request_id, str)
                                   or UUID.fullmatch(request_id) is None):
        return False
    return True


def assess(records: list[dict], ids: tuple[str, str, str], denied_id: str,
           markers: tuple[str, str]) -> None:
    """Prove marker absence and CLI→API parentage from a complete retained window."""

    trace_id, cli_span, request_id = ids
    need(records, "retained_window_empty")
    safe_events: list[dict] = []
    denied_seen = False
    for record in records:
        raw = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        need(not any(marker in raw for marker in markers), "synthetic_url_marker_retained")
        metadata = record.get("$metadata")
        need(isinstance(metadata, dict) and metadata.get("service") == WORKER,
             "service_filter_not_enforced")
        source = record.get("source")
        message = metadata.get("message")
        source_events = embedded_events(source)
        message_events = embedded_events(message)
        recognized = source_events or message_events
        # Cloudflare's event type is optional. A missing or unknown classifier
        # cannot turn arbitrary retained text into an application-schema pass.
        # No platform payload type is exempt until a separate live review.
        need(empty_log_payload(source) or bool(source_events),
             "unreviewed_retained_payload")
        need(empty_log_payload(message) or bool(message_events),
             "unreviewed_retained_payload")
        need(all(allowlisted_event(event) for event in source_events + message_events),
             "application_event_schema_unallowlisted")
        safe_events.extend(recognized)
    for event in safe_events:
        if event.get("request_id") == denied_id and event.get("phase") == "request_exit":
            denied_seen = (event.get("http_status_class") == 4
                           and event.get("parent_span_id") is None)
    roots = [event for event in safe_events if event.get("service") == "mail_api"
             and event.get("phase") == "request_exit"
             and event.get("operation") == "addresses_list"
             and event.get("request_id") == request_id]
    need(len(roots) == 1, "cli_api_root_missing_or_duplicate")
    root = roots[0]
    need(root.get("trace_id") == trace_id and root.get("parent_span_id") == cli_span
         and isinstance(root.get("span_id"), str)
         and HEX16.fullmatch(root["span_id"]) is not None
         and root["span_id"] != cli_span
         and root.get("http_status_class") == 2,
         "cli_api_parentage_invalid")
    need(denied_seen, "rejected_request_event_missing")
    # Cloudflare may retain exceptional platform records; do not call every
    # unrelated platform field safe merely because the two markers are absent.


def main() -> int:
    """Run only after an explicit staging confirmation and fixed preflight."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", choices=["RUN_STAGING_TRACE_CANARY"], required=True)
    parser.add_argument("--amail", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    args = parser.parse_args()
    try:
        account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        obs_token = os.environ.get("CF_OBSERVABILITY_TOKEN", "")
        deploy_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
        need(HEX32.fullmatch(account) is not None, "account_id_missing_or_invalid")
        need(bool(obs_token and deploy_token), "observability_or_deploy_token_missing")
        cli = under_temp(args.amail)
        home = under_temp(args.home)
        need(cli.is_file() and home.is_dir(), "cli_or_home_missing")
        preflight(account, obs_token, deploy_token)
        start, end, ids, denied_id, markers = run_probes(cli, home)
        time.sleep(20)  # Allow Workers Logs indexing; absence remains fail-closed.
        records = retained_events(account, obs_token, start, end)
        assess(records, ids, denied_id, markers)
    except (CanaryError, OSError, sqlite3.Error, subprocess.TimeoutExpired,
            TypeError, ValueError, RecursionError) as error:
        label = error.args[0] if isinstance(error, CanaryError) else "local_probe_unavailable"
        print(f"staging_trace_canary: UNVERIFIED ({label})")
        return 1
    print("staging_trace_canary: retained_marker_absence_and_cli_api_parentage_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
