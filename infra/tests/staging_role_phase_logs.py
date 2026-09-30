"""Classify one historical role Cron phase from bounded, retained application logs.

The query is read-only and exact-run scoped. Provider records, request IDs,
private destinations, and unreviewed log payloads never reach stdout.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid


RUN = "36603362864"
CONFIRM = "READ_FIRST_ROLE_PHASE_LOGS"
SHA = "337925fe45a12d7a9a17d0441c278e76357713d9"
VERSION = "cc4c263c-387c-4ce1-99e7-f911b88bd91a"
SERVICE = "amail-role-monitor-staging"
START = 1790701988000  # 2026-09-29 17:13:08 UTC, exact failed job start.
END = 1790703041000  # 2026-09-29 17:30:41 UTC, exact failed job end.
API = "https://api.cloudflare.com/client/v4"
GITHUB = "https://api.github.com/repos/kleedaisuki/moesegfault-amail/actions/runs/"
MAX_REPLY = 1_000_000
MAX_PAGE = 200
MAX_ROWS = 1600
REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{8,128}\Z")
DIGEST = re.compile(r"role alert digest accepted groups=([1-5])\Z")
HEALTHY = re.compile(r"role monitor healthy pending=(0|[1-9][0-9]{0,3})\Z")
PHASES = {
    "role monitor phase=destination failed": "destination",
    "role monitor phase=routes failed": "routes",
    "role monitor phase=lease failed": "lease",
    "role monitor phase=digest failed": "digest",
    "role monitor health check failed": "health_failed",
}


class ProbeError(Exception):
    """A closed, public-safe diagnostic code, never provider text."""


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    """Prevent bearer forwarding, including to same-origin redirects."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        """Reject every redirect without inspecting its URL."""

        return None


OPENER = urllib.request.build_opener(RejectRedirect)


def need(condition: bool, code: str) -> None:
    """Fail closed when evidence cannot support a historical claim."""

    if not condition:
        raise ProbeError(code)


def read_json(url: str, token: str, body: dict | None = None) -> dict:
    """Read a bounded JSON envelope without redirects or diagnostic bodies."""

    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url, headers=headers, method="POST" if body is not None else "GET",
        data=json.dumps(body, separators=(",", ":")).encode() if body is not None else None,
    )
    try:
        with OPENER.open(request, timeout=25) as response:
            status, raw = response.status, response.read(MAX_REPLY + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        raise ProbeError("provider_unavailable") from None
    need(status == 200 and len(raw) <= MAX_REPLY, "provider_unavailable")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ProbeError("provider_schema_unverified") from None
    need(isinstance(value, dict), "provider_schema_unverified")
    return value


def historical_run(token: str) -> None:
    """Bind this read to the exact failed run and its reviewed source revision."""

    run = read_json(GITHUB + RUN, token)
    need(run.get("id") == int(RUN) and run.get("head_sha") == SHA
         and run.get("conclusion") == "failure" and run.get("status") == "completed"
         and run.get("event") == "workflow_dispatch"
         and run.get("head_branch") == "codex/amail-v0.1.0"
         and isinstance(run.get("path"), str)
         and run["path"].split("@", 1)[0] == ".github/workflows/ci.yml",
         "historical_run_unverified")


def exact_filter(value: object) -> bool:
    """Accept only the single exact indexed service filter echo."""

    return isinstance(value, dict) and set(value).issubset({
        "key", "operation", "type", "value", "kind",
    }) and value.get("key") == "$metadata.service" \
        and value.get("operation") in ("eq", "=") \
        and value.get("type") == "string" and value.get("value") == SERVICE \
        and value.get("kind", "filter") == "filter"


def query_page(account: str, token: str, cursor: str | None) -> dict:
    """Require Cloudflare's completed dry query and exact scope echo."""

    body = {
        "queryId": str(uuid.uuid4()), "timeframe": {"from": START, "to": END},
        "dry": True, "limit": MAX_PAGE, "view": "events",
        "parameters": {"datasets": [], "filterCombination": "and", "filters": [{
            "key": "$metadata.service", "operation": "eq", "type": "string", "value": SERVICE,
        }]},
    }
    if cursor is not None:
        body.update({"offset": cursor, "offsetDirection": "next"})
    envelope = read_json(
        f"{API}/accounts/{account}/workers/observability/telemetry/query", token, body,
    )
    need(envelope.get("success") is True and envelope.get("errors", []) == [],
         "query_unverified")
    result = envelope.get("result")
    need(isinstance(result, dict), "query_schema_unverified")
    run = result.get("run")
    need(isinstance(run, dict) and run.get("status") == "COMPLETED"
         and run.get("dry") is True and run.get("timeframe") == body["timeframe"],
         "query_incomplete_or_echo_unverified")
    query = run.get("query")
    parameters = query.get("parameters") if isinstance(query, dict) else None
    need(isinstance(parameters, dict) and parameters.get("datasets") == []
         and parameters.get("filterCombination") in ("and", "AND")
         and isinstance(parameters.get("filters"), list)
         and len(parameters["filters"]) == 1 and exact_filter(parameters["filters"][0])
         and parameters.get("view", "events") == "events"
         and not any(parameters.get(key) for key in ("needle", "havings", "groupBys")),
         "query_incomplete_or_echo_unverified")
    view = result.get("events")
    need(isinstance(view, dict) and type(view.get("count")) is int
         and view["count"] >= 0 and isinstance(view.get("events"), list),
         "events_view_unverified")
    return view


def retained_events(account: str, token: str) -> list[dict]:
    """Fetch every row or reject incomplete, unstable, or oversized pagination."""

    rows: list[dict] = []
    cursor = None
    seen: set[str] = set()
    total = None
    while True:
        view = query_page(account, token, cursor)
        batch = view["events"]
        count = view["count"]
        need(len(batch) <= MAX_PAGE and all(isinstance(row, dict) for row in batch)
             and count >= len(rows) + len(batch), "events_page_unverified")
        if total is None:
            total = count
        need(count == total, "events_count_shifted")
        if cursor is not None or count > len(batch):
            ids = [row.get("$metadata", {}).get("id")
                   if isinstance(row.get("$metadata"), dict) else None for row in batch]
            need(all(isinstance(value, str) and value for value in ids)
                 and len(ids) == len(set(ids)) and not (set(ids) & seen),
                 "events_cursor_unverified")
            seen.update(ids)
        rows.extend(batch)
        need(len(rows) <= MAX_ROWS, "events_window_too_busy")
        if len(rows) == total:
            return rows
        need(len(batch) == MAX_PAGE, "events_page_incomplete")
        metadata = batch[-1].get("$metadata")
        need(isinstance(metadata, dict) and isinstance(metadata.get("id"), str)
             and metadata["id"] != cursor, "events_cursor_unverified")
        cursor = metadata["id"]


def text_payload(value: object, depth: int = 0) -> str | None:
    """Unwrap only Cloudflare's documented single-message console wrapper."""

    if depth > 3:
        return None
    if isinstance(value, str):
        return value if len(value) <= 128 else None
    if isinstance(value, dict) and set(value) == {"message"}:
        return text_payload(value["message"], depth + 1)
    if isinstance(value, list) and len(value) == 1:
        return text_payload(value[0], depth + 1)
    return None


def classify(records: list[dict]) -> str:
    """Correlate exact reviewed scheduled labels by opaque request ID in memory."""

    invocations: dict[str, set[str]] = {}
    for record in records:
        metadata = record.get("$metadata")
        need(isinstance(metadata, dict) and metadata.get("service") == SERVICE,
             "service_scope_unverified")
        need(type(record.get("timestamp")) is int
             and START <= record["timestamp"] <= END
             and metadata.get("truncated") is not True,
             "event_window_or_integrity_unverified")
        worker = record.get("$workers")
        need(isinstance(worker, dict), "worker_envelope_unverified")
        need(worker.get("scriptName") == SERVICE, "worker_scope_unverified")
        need(worker.get("truncated") is not True, "event_window_or_integrity_unverified")
        trigger = worker.get("eventType")
        if trigger not in ("scheduled", "cron"):
            # Email Handler logs can contain a random arrival reference.
            need(trigger == "email", "trigger_unverified")
            continue
        version = worker.get("scriptVersion")
        need(isinstance(version, dict) and version.get("id") == VERSION,
             "historical_version_unverified")
        request_id = metadata.get("requestId") or worker.get("requestId")
        need(isinstance(request_id, str) and REQUEST_ID.fullmatch(request_id) is not None
             and (not metadata.get("requestId") or not worker.get("requestId")
                  or metadata["requestId"] == worker["requestId"]),
             "invocation_id_unverified")
        source = text_payload(record.get("source"))
        message = text_payload(metadata.get("message"))
        need(record.get("source") in (None, "", {}, []) or source is not None,
             "scheduled_payload_unreviewed")
        need(metadata.get("message") in (None, "", {}, []) or message is not None,
             "scheduled_payload_unreviewed")
        need(source is None or message is None or source == message,
             "log_echo_disagrees")
        payload = source or message
        need(payload is not None, "scheduled_payload_unreviewed")
        digest = DIGEST.fullmatch(payload)
        phase = ("digest_accepted" if digest else "healthy" if HEALTHY.fullmatch(payload)
                 else PHASES.get(payload))
        need(phase is not None, "scheduled_payload_unreviewed")
        invocations.setdefault(request_id, set()).add(phase)
    if not invocations:
        return "no_reviewed_invocation"
    digest_ids = [key for key, labels in invocations.items() if "digest_accepted" in labels]
    need(len(digest_ids) <= 1, "digest_invocation_ambiguous")
    if not digest_ids:
        return "digest_not_observed"
    labels = invocations[digest_ids[0]]
    failures = labels & {"digest", "destination", "routes", "lease"}
    # A failed phase cannot reach the final healthy log; flush_alerts cannot
    # both log its final accepted digest and return a digest-phase failure.
    # Such records indicate provider/correlation ambiguity, not a root cause.
    need(len(failures) <= 1 and not (failures and "healthy" in labels)
         and "digest" not in labels
         and not ({"healthy", "health_failed"} <= labels),
         "invocation_phase_ambiguous")
    if failures:
        return "same_invocation_" + next(iter(failures)) + "_failed"
    if "healthy" in labels:
        return "same_invocation_healthy"
    # No failure label does not prove the historical run completed: missing
    # retained rows, sampled events, or unexpected Cron timing remain possible.
    return "digest_only_inconclusive"


def main() -> int:
    """Print only a fixed phase label after all run, query, and privacy gates."""

    if sys.argv[1:] != [CONFIRM, RUN]:
        print("role_phase_logs=coordinates_invalid")
        return 1
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    obs = os.environ.get("CF_OBSERVABILITY_TOKEN", "")
    github = os.environ.get("GITHUB_TOKEN", "")
    if re.fullmatch(r"[0-9a-f]{32}", account) is None or not obs or not github:
        print("role_phase_logs=configuration_invalid")
        return 1
    try:
        historical_run(github)
        state = classify(retained_events(account, obs))
    except ProbeError as error:
        print(f"role_phase_logs=UNVERIFIED ({error})")
        return 1
    except Exception:
        # A future transport/schema change must not expose provider objects in
        # a Python traceback on a public Actions log.
        print("role_phase_logs=UNVERIFIED (unexpected_failure)")
        return 1
    print("role_phase_logs=" + state)
    return 0 if state.startswith("same_invocation_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
