"""Fixed eight-type schema discriminator, never runtime or release evidence.

Usage: set AMAIL_SCHEMA_CONFIRM=READ_CRON_METRICS_SCHEMA and privately supply
CF_OBSERVABILITY_TOKEN; run python infra/provider/probe_cron_metrics_schema.py.
"""
import json
import os
import re
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ENDPOINT = "https://api.cloudflare.com/client/v4/graphql"
CONFIRM = "READ_CRON_METRICS_SCHEMA"
MAX_BODY, MAX_FIELDS = 262_144, 500
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
# Exact names are hypotheses until authenticated readback; no discovery/fallback.
TYPES = {
    "adaptive_dimensions": ("AccountWorkersInvocationsAdaptiveDimensions", "fields", "scriptName scriptVersion type eventType status datetime"),
    "adaptive_filter": ("AccountWorkersInvocationsAdaptiveFilter_InputObject", "inputFields", "scriptName scriptVersion type eventType datetime_geq datetime_lt"),
    "adaptive_quantiles": ("AccountWorkersInvocationsAdaptiveQuantiles", "fields", "cpuTimeP99 wallTimeP99 memoryUsageBytesP99"),
    "scheduled": ("AccountWorkersInvocationsScheduled", "fields", "cpuTimeUs cron datetime scheduledDatetime scriptName status scriptVersion wallTimeUs wallTimeMs memoryUsageBytes"),
    "scheduled_filter": ("AccountWorkersInvocationsScheduledFilter_InputObject", "inputFields", "scriptName cron scriptVersion datetime_geq datetime_lt"),
    "d1_dimensions": ("AccountD1AnalyticsAdaptiveGroupsDimensions", "fields", "databaseId datetime"),
    "d1_filter": ("AccountD1AnalyticsAdaptiveGroupsFilter_InputObject", "inputFields", "databaseId datetime_geq datetime_lt"),
    "d1_sum": ("AccountD1AnalyticsAdaptiveGroupsSum", "fields", "readQueries writeQueries rowsRead rowsWritten"),
}
# __Type cannot filter members by name; only these eight types are requested.
QUERY = "query CronMetricsSchema {\n" + "\n".join(
    f'{alias}: __type(name: "{name}") {{ name kind {member} {{ name }} }}'
    for alias, (name, member, _selected) in TYPES.items()) + "\n}"
REASONS = frozenset({"confirmation", "credential", "http", "permission", "size", "schema", "graphql"})


class Unverified(Exception):
    """Carry only a closed non-provider failure category."""


class NoRedirect(HTTPRedirectHandler):
    """Reject traversal rather than forward the bearer."""

    def redirect_request(self, request, response, code, message, headers, url):
        """Refuse every redirect, including same-origin redirects."""
        return None


def unique_object(pairs):
    """Reject duplicate JSON keys before they overwrite response meaning."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise Unverified("schema")
        result[key] = value
    return result


def reject_constant(_value):
    """Reject nonstandard JSON constants without retaining their text."""
    raise Unverified("schema")


def classify(payload):
    """Return fixed membership bins only after validating all eight aliases."""
    if not isinstance(payload, dict) or set(payload) not in ({"data"}, {"data", "errors"}):
        raise Unverified("schema")
    if payload.get("errors") not in (None, []):
        raise Unverified("graphql")
    data = payload.get("data")
    if not isinstance(data, dict) or set(data) != set(TYPES):
        raise Unverified("schema")
    lines = []
    for alias, (name, member, selected) in TYPES.items():
        value, fields = data[alias], set()
        if value is not None:
            kind = "INPUT_OBJECT" if member == "inputFields" else "OBJECT"
            if (not isinstance(value, dict) or set(value) != {"name", "kind", member}
                    or value["name"] != name or value["kind"] != kind
                    or not isinstance(value[member], list) or len(value[member]) > MAX_FIELDS):
                raise Unverified("schema")
            for item in value[member]:
                if (not isinstance(item, dict) or set(item) != {"name"}
                        or not isinstance(item["name"], str) or not NAME.fullmatch(item["name"])
                        or item["name"] in fields):
                    raise Unverified("schema")
                fields.add(item["name"])
        lines.extend(f"schema_{alias}_{key}=" + ("unavailable" if value is None else
                     "present" if key in fields else "absent") for key in selected.split())
    return lines + ["schema_result=classified_only", "cron_resource_admission=UNVERIFIED",
                    "runtime_measurement=not_performed", "issues_privacy_gate=unchanged"]


def fetch(token):
    """Send one fixed bounded no-retry GraphQL query, with no resource variable."""
    request = Request(ENDPOINT, data=json.dumps({"query": QUERY}).encode(), method="POST",
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            if response.getcode() != 200:
                raise Unverified("http")
            raw = response.read(MAX_BODY + 1)
    except HTTPError as error:
        raise Unverified("permission" if error.code in (401, 403) else "http") from None
    if len(raw) > MAX_BODY:
        raise Unverified("size")
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)


def run(confirm, token):
    """Reject unconfirmed or invalid credentials before any network access."""
    if confirm != CONFIRM:
        raise Unverified("confirmation")
    if not token or len(token) > 4096 or any(ord(char) < 33 or ord(char) > 126 for char in token):
        raise Unverified("credential")
    return classify(fetch(token))


def main():
    """Suppress all provider bodies, dynamic reasons and exception tracebacks."""
    try:
        lines = run(os.getenv("AMAIL_SCHEMA_CONFIRM", ""), os.getenv("CF_OBSERVABILITY_TOKEN", ""))
    except Exception as error:
        reason = error.args[0] if isinstance(error, Unverified) and error.args else None
        reason = reason if isinstance(reason, str) and reason in REASONS else "internal"
        print(f"schema_result=UNVERIFIED reason={reason}")
        return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
