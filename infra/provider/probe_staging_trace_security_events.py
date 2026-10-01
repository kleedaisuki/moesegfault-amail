"""Classify only sampled Security Events near one failed staging trace canary.

This one-shot diagnostic cannot attribute an event to the canary without a Ray
ID. It never prints provider data, request identifiers, network locations, or
free-form rule descriptions. The single query is zone, host, and time scoped.

The completed workflow lane is retired; retain this module for synthetic safety
tests and historical evidence, not as a current provider-read runbook.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
import re
import sys
import urllib.error
import urllib.request


ENDPOINT = "https://api.cloudflare.com/client/v4/graphql"
RUN_ID = "36671177226"
CONFIRM = "READ_STAGING_TRACE_SECURITY_EVENTS_36671177226"
HOST = "mail-staging.moesegfault.dev"
START = "2026-09-30T04:58:42Z"
END = "2026-09-30T05:00:42Z"
LIMIT = 100  # A full page is ambiguous; at most 99 rows are accepted.
MAX_BODY = 65_536
MAX_COUNT = 99
REASONS = frozenset({
    "confirmation", "credential", "permission", "http", "transport", "size",
    "schema_unverified", "graphql_unverified", "scope_unverified",
    "truncated_unverified", "internal", "graphql_retention_unverified",
    "graphql_limit_unverified", "graphql_parse_unverified",
    "graphql_auth_unverified", "graphql_transient_unverified",
})
QUERY = """query TraceSecurityEvents($zoneTag: string, $start: Time, $end: Time, $host: string) {
  viewer {
    zones(filter: {zoneTag: $zoneTag}) {
      firewallEventsAdaptive(
        filter: {datetime_geq: $start, datetime_leq: $end, clientRequestHTTPHost: $host}
        limit: 100
        orderBy: [datetime_DESC]
      ) {
        datetime
        clientRequestHTTPHost
        action
        source
        description
      }
    }
  }
}"""

# Cloudflare documents these as security-event sources. Unknown strings never
# enter the output and are conservatively labeled "other".
SOURCES = frozenset({
    "unknown", "asn", "country", "ip", "iprange", "securitylevel",
    "zonelockdown", "waf", "firewallrules", "uablock", "ratelimit", "bic",
    "hot", "l7ddos", "validation", "botfight", "apishield",
    "botmanagement", "dlp", "firewallmanaged", "firewallcustom",
    "apishieldschemavalidation", "apishieldtokenvalidation",
    "apishieldsequencemitigation",
})
ACTIONS = frozenset({
    "allow", "block", "challenge", "js_challenge", "managed_challenge",
    "log", "skip", "bypass", "connection_close", "force_connection_close",
})
MITIGATIONS = frozenset({
    "block", "challenge", "js_challenge", "managed_challenge",
    "connection_close", "force_connection_close",
})
# Exact equality only. A future rule may be added after separate review.
DESCRIPTIONS = {
    "Bot Fight Mode": "bot_fight_mode",
    "Browser Integrity Check": "browser_integrity_check",
}


class Unverified(Exception):
    """Represent a safe fixed-code diagnostic failure."""


def _graphql_error_reason(errors: object) -> str:
    """Classify documented error phrases without exposing provider text.

    GraphQL can return HTTP 200 with an error array. Categories are diagnostic
    hints only: unknown or mixed messages remain unverified, and no category
    establishes whether the historical mail request reached the Worker.
    """

    if not isinstance(errors, list) or not 1 <= len(errors) <= 8:
        return "graphql_unverified"
    reasons = set()
    for item in errors:
        if not isinstance(item, dict):
            return "graphql_unverified"
        message = item.get("message")
        if not isinstance(message, str) or len(message) > 2048:
            return "graphql_unverified"
        message = message.casefold()
        if "cannot request data older than" in message:
            reasons.add("graphql_retention_unverified")
        elif "not authorized" in message or "unauthorized" in message or \
                "does not have access to the path" in message:
            reasons.add("graphql_auth_unverified")
        elif "unknown field" in message or "error parsing args" in message or \
                "query contains error" in message or \
                "scalar fields must have no selections" in message or \
                "object field must have selections" in message:
            reasons.add("graphql_parse_unverified")
        elif "limit must be positive" in message or \
                "query time range is too large" in message or \
                "number of fields can't be more than" in message:
            reasons.add("graphql_limit_unverified")
        elif "unable to execute query" in message or \
                "too many queries in progress" in message:
            reasons.add("graphql_transient_unverified")
        else:
            reasons.add("graphql_unverified")
    return reasons.pop() if len(reasons) == 1 else "graphql_unverified"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Prevent forwarding the bearer credential to any redirect destination."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        """Refuse redirects without retaining their location."""

        return None


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    """Reject duplicate JSON keys that could shadow GraphQL scope fields."""

    result = {}
    for key, value in pairs:
        if key in result:
            raise Unverified("schema_unverified")
        result[key] = value
    return result


def _utc(value: object) -> datetime:
    """Accept only exact UTC GraphQL timestamps, not local-time guesses."""

    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?Z", value
    ):
        raise Unverified("schema_unverified")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise Unverified("schema_unverified") from error
    if parsed.tzinfo != timezone.utc:
        raise Unverified("schema_unverified")
    return parsed


def _label(value: object, allowed: frozenset[str]) -> str:
    """Map provider-controlled literals to a closed, non-echoing vocabulary."""

    if not isinstance(value, str):
        raise Unverified("schema_unverified")
    normalized = value.lower()
    return normalized if normalized in allowed else "other"


def classify(payload: object) -> list[str]:
    """Fully validate one zone/page, then emit only bounded safe labels.

    Security Events are sampled. Zero events or a non-mitigating event never
    establishes absence of edge intervention on the historical request.
    """

    if not isinstance(payload, dict) or set(payload) not in ({"data"}, {"data", "errors"}):
        raise Unverified("schema_unverified")
    if payload.get("errors") is not None:
        raise Unverified(_graphql_error_reason(payload["errors"]))
    data = payload["data"]
    if not isinstance(data, dict) or set(data) != {"viewer"}:
        raise Unverified("schema_unverified")
    viewer = data["viewer"]
    if not isinstance(viewer, dict) or set(viewer) != {"zones"}:
        raise Unverified("schema_unverified")
    zones = viewer["zones"]
    if not isinstance(zones, list) or len(zones) != 1:
        raise Unverified("scope_unverified")
    zone = zones[0]
    if not isinstance(zone, dict) or set(zone) != {"firewallEventsAdaptive"}:
        raise Unverified("schema_unverified")
    rows = zone["firewallEventsAdaptive"]
    if not isinstance(rows, list):
        raise Unverified("schema_unverified")
    if len(rows) >= LIMIT:
        raise Unverified("truncated_unverified")

    start, end = _utc(START), _utc(END)
    counts: Counter[tuple[str, str, str]] = Counter()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "datetime", "clientRequestHTTPHost", "action", "source", "description"
        }:
            raise Unverified("schema_unverified")
        at = _utc(row["datetime"])
        if row["clientRequestHTTPHost"] != HOST or not (start <= at <= end):
            raise Unverified("scope_unverified")
        description = row["description"]
        if description is not None and not isinstance(description, str):
            raise Unverified("schema_unverified")
        action = _label(row["action"], ACTIONS)
        source = _label(row["source"], SOURCES)
        rule = DESCRIPTIONS.get(description, "other")
        counts[(action, source, rule)] += 1
    if sum(counts.values()) > MAX_COUNT:
        raise Unverified("truncated_unverified")

    total = len(rows)
    count_label = "0" if total == 0 else "1" if total == 1 else "2_to_9" if total < 10 else "10_plus"
    lines = [f"security_events_count={count_label}"]
    lines.extend(
        f"security_events_bucket=action:{action},source:{source},rule:{rule},count:{count}"
        for (action, source, rule), count in sorted(counts.items())
    )
    result = "sampled_edge_candidate" if any(
        action in MITIGATIONS for action, _, _ in counts
    ) else "no_sample_or_non_edge"
    lines.append(f"security_events_result={result}")
    return lines


def fetch(zone: str, token: str) -> object:
    """Send exactly one bounded POST without retries, redirects, or raw logs."""

    body = json.dumps({"query": QUERY, "variables": {
        "zoneTag": zone, "start": START, "end": END, "host": HOST,
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
        raise Unverified("schema_unverified") from error


def run(confirm: str, run_id: str, zone: str, token: str) -> list[str]:
    """Check one historical run and exact confirmation before network access."""

    if confirm != CONFIRM or run_id != RUN_ID:
        raise Unverified("confirmation")
    if not re.fullmatch(r"[a-f0-9]{32}", zone) or not token:
        raise Unverified("credential")
    return classify(fetch(zone, token))


def main() -> int:
    """Expose only fixed labels on stdout, including all failure paths."""

    try:
        lines = run(
            sys.argv[1] if len(sys.argv) == 3 else "",
            sys.argv[2] if len(sys.argv) == 3 else "",
            os.environ.get("CF_ZONE_ID", ""),
            os.environ.get("CLOUDFLARE_API_TOKEN", ""),
        )
    except Unverified as error:
        reason = error.args[0] if error.args and error.args[0] in REASONS else "internal"
        print(f"security_events_result=unverified reason={reason}")
        return 1
    except Exception:
        print("security_events_result=unverified reason=internal")
        return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
