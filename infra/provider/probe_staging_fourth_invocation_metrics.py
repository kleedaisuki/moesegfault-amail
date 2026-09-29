"""Read only bounded Workers invocation aggregates for the fourth staging 500.

This is deliberately not an event-log reader: the query selects only a fixed
Worker, UTC window, invocation status and aggregate request/error counters.
Provider payloads and exception messages are never written to stdout/stderr.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
import sys
import urllib.error
import urllib.request


ENDPOINT = "https://api.cloudflare.com/client/v4/graphql"
WORKER = "amail-mail-staging"
START = "2026-09-29T12:24:32Z"
END = "2026-09-29T12:25:41Z"
CONFIRM = "READ_FOURTH_STAGING_INVOCATION_METRICS_36567571204"
LIMIT = 100
MAX_BODY = 65_536
MAX_COUNT = 10_000
STATUSES = frozenset({
    "success", "scriptThrewException", "exceededResources", "internalError",
    "clientDisconnected",
})
REASONS = frozenset({
    "schema", "graphql", "account", "limit", "empty", "scope", "status",
    "duplicate", "count", "http", "permission", "transport", "size",
    "confirmation", "credential",
})
QUERY = """query FourthStagingInvocationMetrics($accountTag: string, $datetimeStart: string, $datetimeEnd: string, $scriptName: string) {
  viewer {
    accounts(filter: {accountTag: $accountTag}) {
      workersInvocationsAdaptive(limit: 100, filter: {
        scriptName: $scriptName,
        datetime_geq: $datetimeStart,
        datetime_leq: $datetimeEnd
      }) {
        dimensions { datetime scriptName status }
        sum { requests errors }
      }
    }
  }
}"""


class Unverified(Exception):
    """Represent a fixed, non-provider failure classification."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward the analytics bearer to a redirect target."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        """Refuse all redirects, even to another Cloudflare URL."""

        return None


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    """Reject duplicate JSON keys before they can change response meaning."""

    result = {}
    for key, value in pairs:
        if key in result:
            raise Unverified("schema")
        result[key] = value
    return result


def _utc(value: object) -> datetime:
    """Accept only a UTC timestamp with exact Z suffix."""

    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?Z", value):
        raise Unverified("schema")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise Unverified("schema") from error
    if parsed.tzinfo != timezone.utc:
        raise Unverified("schema")
    return parsed


def classify(payload: object) -> list[tuple[str, int, int]]:
    """Validate the entire selected GraphQL shape and aggregate safe buckets.

    A returned row equal to the query limit is ambiguous: there may be more
    rows. Empty or mixed-status windows also cannot identify the failed add.
    """

    if not isinstance(payload, dict) or set(payload) not in ({"data"}, {"data", "errors"}):
        raise Unverified("schema")
    if payload.get("errors") is not None:
        raise Unverified("graphql")
    data = payload["data"]
    if not isinstance(data, dict) or set(data) != {"viewer"}:
        raise Unverified("schema")
    viewer = data["viewer"]
    if not isinstance(viewer, dict) or set(viewer) != {"accounts"}:
        raise Unverified("schema")
    accounts = viewer["accounts"]
    if not isinstance(accounts, list) or len(accounts) != 1:
        raise Unverified("account")
    account = accounts[0]
    if not isinstance(account, dict) or set(account) != {"workersInvocationsAdaptive"}:
        raise Unverified("schema")
    rows = account["workersInvocationsAdaptive"]
    if not isinstance(rows, list) or len(rows) >= LIMIT:
        raise Unverified("limit")
    if not rows:
        raise Unverified("empty")

    start, end = _utc(START), _utc(END)
    buckets: dict[str, list[int]] = {}
    seen: set[tuple[datetime, str]] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"dimensions", "sum"}:
            raise Unverified("schema")
        dimensions, sums = row["dimensions"], row["sum"]
        if not isinstance(dimensions, dict) or set(dimensions) != {"datetime", "scriptName", "status"}:
            raise Unverified("schema")
        if not isinstance(sums, dict) or set(sums) != {"requests", "errors"}:
            raise Unverified("schema")
        at, status = _utc(dimensions["datetime"]), dimensions["status"]
        if dimensions["scriptName"] != WORKER or at < start or at > end:
            raise Unverified("scope")
        if not isinstance(status, str) or status not in STATUSES:
            raise Unverified("status")
        if (at, status) in seen:
            raise Unverified("duplicate")
        seen.add((at, status))
        requests, errors = sums["requests"], sums["errors"]
        if type(requests) is not int or type(errors) is not int or not (0 <= errors <= requests <= MAX_COUNT):
            raise Unverified("count")
        counts = buckets.setdefault(status, [0, 0])
        counts[0] += requests
        counts[1] += errors
        if counts[0] > MAX_COUNT or counts[1] > MAX_COUNT:
            raise Unverified("count")
    return [(status, *buckets[status]) for status in sorted(buckets)]


def fetch(account: str, token: str) -> object:
    """POST a single no-retry GraphQL query; retain its bounded body in memory."""

    body = json.dumps({"query": QUERY, "variables": {
        "accountTag": account, "datetimeStart": START, "datetimeEnd": END,
        "scriptName": WORKER,
    }}, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(ENDPOINT, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/json",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            if response.status != 200:
                raise Unverified("http")
            raw = response.read(MAX_BODY + 1)
    except urllib.error.HTTPError as error:
        raise Unverified("permission" if error.code in (401, 403) else "http") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise Unverified("transport") from error
    if len(raw) > MAX_BODY:
        raise Unverified("size")
    try:
        return json.loads(raw, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError) as error:
        raise Unverified("schema") from error


def run(confirm: str, account: str, token: str) -> list[str]:
    """Return fixed-key lines only; caller prints them after full validation."""

    if confirm != CONFIRM:
        raise Unverified("confirmation")
    if not re.fullmatch(r"[a-f0-9]{32}", account) or not token:
        raise Unverified("credential")
    buckets = classify(fetch(account, token))
    lines = [f"metrics_status={status} requests={requests} errors={errors}"
             for status, requests, errors in buckets]
    if len(buckets) != 1:
        lines.append("metrics_result=UNVERIFIED reason=mixed")
    elif buckets[0][0] == "success":
        lines.append("metrics_result=success_only_http_unknown")
    else:
        lines.append("metrics_result=aggregate_only_not_request_attributed")
    return lines


def main() -> int:
    """Expose a closed safe diagnostic without provider text or tracebacks."""

    try:
        lines = run(sys.argv[1] if len(sys.argv) == 2 else "", os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
                    os.environ.get("CF_OBSERVABILITY_TOKEN", ""))
    except Unverified as error:
        reason = error.args[0] if error.args and error.args[0] in REASONS else "internal"
        print(f"metrics_result=UNVERIFIED reason={reason}")
        return 1
    except Exception:
        print("metrics_result=UNVERIFIED reason=internal")
        return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
