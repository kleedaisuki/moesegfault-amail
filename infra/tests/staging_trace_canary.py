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
    "response_bytes_bucket",
})
EVENT_SERVICES = frozenset({"mail_api", "mail_cli"})
EVENT_PHASES = frozenset({
    "request_exit", "operation_exit", "d1_read", "d1_write", "r2_write", "provider_send",
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
    need(isinstance(payload, dict) and payload.get("success") is True, "observability_query_failed")
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


def run_probes(cli: Path, home: Path) -> tuple[int, int, tuple[str, str, str], str, tuple[str, str]]:
    """Exercise an ordinary CLI read and one anonymous rejected synthetic URL."""

    environment = dict(os.environ)
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
    request = Request(f"{API}/{path_marker}?probe={query_marker}", method="GET")
    try:
        with urlopen(request, timeout=15) as response:
            status = response.status
            denied_id = response.headers.get("x-amail-request-id")
    except HTTPError as error:
        status = error.code
        denied_id = error.headers.get("x-amail-request-id")
    except (URLError, TimeoutError):
        raise CanaryError("rejected_url_network_unavailable") from None
    need(status == 401 and isinstance(denied_id, str)
         and UUID.fullmatch(denied_id) is not None, "rejected_url_contract_failed")
    end = int(time.time() * 1000) + 2_000
    return start, end, ids, denied_id, (path_marker, query_marker)


def query_page(account: str, token: str, start: int, end: int, cursor: str | None) -> dict:
    """Read one dry, service-filtered retained-event page; never save a query."""

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
    need(isinstance(result, dict) and isinstance(result.get("events"), dict),
         "observability_events_malformed")
    events = result["events"]
    need(isinstance(events.get("events"), list), "observability_events_malformed")
    return events


def retained_events(account: str, token: str, start: int, end: int) -> list[dict]:
    """Fetch a complete bounded window or fail; truncated data is no privacy proof."""

    records: list[dict] = []
    cursor: str | None = None
    while True:
        page = query_page(account, token, start, end, cursor)
        batch = page["events"]
        need(all(isinstance(item, dict) for item in batch), "observability_events_malformed")
        records.extend(batch)
        need(len(records) <= MAX_EVENTS, "observability_window_too_busy")
        count = page.get("count")
        need(isinstance(count, int) and count >= len(records), "observability_count_malformed")
        if len(records) == count:
            return records
        need(len(batch) == MAX_PAGE, "observability_page_incomplete")
        metadata = batch[-1].get("$metadata")
        need(isinstance(metadata, dict) and isinstance(metadata.get("id"), str),
             "observability_cursor_missing")
        next_cursor = metadata["id"]
        need(next_cursor != cursor, "observability_cursor_stalled")
        cursor = next_cursor


def embedded_events(value: object) -> list[dict]:
    """Decode Cloudflare's string or structured console source without printing it."""

    if isinstance(value, dict):
        found = [value] if value.get("schema_version") == 1 else []
        for child in value.values():
            found.extend(embedded_events(child))
        return found
    if isinstance(value, list):
        return [event for child in value for event in embedded_events(child)]
    if isinstance(value, str) and len(value) <= 4096 and value.lstrip().startswith(("{", "[")):
        try:
            return embedded_events(json.loads(value))
        except ValueError:
            return []
    return []


def allowlisted_event(event: dict) -> bool:
    """Reject arbitrary application-event attributes and malformed identifiers."""

    if (not set(event).issubset(EVENT_KEYS)
            or event.get("schema_version") != 1
            or event.get("service") not in EVENT_SERVICES
            or event.get("phase") not in EVENT_PHASES
            or event.get("operation") not in EVENT_OPERATIONS
            or event.get("outcome") not in EVENT_OUTCOMES):
        return False
    if event.get("error_code") is not None and event["error_code"] not in EVENT_ERRORS:
        return False
    if event.get("http_status_class") is not None and event["http_status_class"] not in range(6):
        return False
    for key in ("duration_ms_bucket", "request_bytes_bucket", "response_bytes_bucket"):
        value = event.get(key)
        if value is not None and (type(value) is not int or value < 0 or value > 1 << 30):
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
        source_events = embedded_events(record.get("source"))
        safe_events.extend(source_events or embedded_events(metadata.get("message")))
    need(all(allowlisted_event(event) for event in safe_events),
         "application_event_schema_unallowlisted")
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
    except (CanaryError, OSError, sqlite3.Error, subprocess.TimeoutExpired) as error:
        label = error.args[0] if isinstance(error, CanaryError) else "local_probe_unavailable"
        print(f"staging_trace_canary: UNVERIFIED ({label})")
        return 1
    print("staging_trace_canary: retained_marker_absence_and_cli_api_parentage_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
