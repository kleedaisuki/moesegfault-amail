"""Classify retained events for one failed Worker-created R2 probe, without writes.

The run/attempt and source revision are fixed. Provider message identifiers,
addresses, subjects, rule identifiers, and JSON are held only in memory.
Adaptive event absence is always inconclusive, never a delivery-negative claim.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys
import urllib.error
import urllib.request

from staging_worker_created_r2 import (BRANCH, FIRST, JOB_NAME, PROBE_STEP_NAME,
                                       REPOSITORY, SENDER, TEMPLATE, github_json,
                                       marker, parse_time)


RUN = "36751791789"
ATTEMPT = "1"
SHA = "15b50a5d1102873a81ff6628d491966852c2b76c"
CONFIRM = "READ_WORKER_R2_DELIVERY_HISTORY_36751791789"
WORKFLOW = ".github/workflows/staging-worker-r2-capability.yml"
API = "https://api.cloudflare.com/client/v4/graphql"
LIMIT = 100
MAX_BODY = 131_072
QUERY = """query WorkerR2DeliveryHistory($zoneTag: string!, $start: Time!, $end: Time!) {
  viewer {
    zones(filter: {zoneTag: $zoneTag}) {
      emailSendingAdaptive(filter: {datetime_geq: $start, datetime_leq: $end}, limit: 100, orderBy: [datetime_ASC]) {
        datetime from to subject messageId status errorCause isLastEvent
      }
      emailRoutingAdaptive(filter: {datetime_geq: $start, datetime_leq: $end}, limit: 100, orderBy: [datetime_ASC]) {
        datetime from to subject messageId status action ruleMatched
      }
    }
  }
}"""
SENDING_FIELDS = frozenset({"datetime", "from", "to", "subject", "messageId",
                            "status", "errorCause", "isLastEvent"})
ROUTING_FIELDS = frozenset({"datetime", "from", "to", "subject", "messageId",
                            "status", "action", "ruleMatched"})
RESULTS = frozenset({
    "sending_routing_unknown_address_observed",
    "sending_progress_observed_routing_unverified",
    "sending_failure_observed_routing_unverified",
    "sending_event_observed_status_unverified",
    "routing_correlated_observed_worker_unverified",
    "routing_id_unjoined",
    "historical_events_inconclusive",
})
REASONS = frozenset({"confirmation", "identity", "provenance", "credential",
                     "provider", "schema", "limit", "scope", "ambiguous"})


class HistoryError(Exception):
    """Carry only a fixed source-owned diagnostic category."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse bearer forwarding to every redirected URL."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        """Return no follow-up request for a 30x response."""

        return None


OPENER = urllib.request.build_opener(NoRedirect())


def need(condition: bool, reason: str) -> None:
    """Reject unverified evidence without interpolating private values."""

    if not condition:
        raise HistoryError(reason)


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    """Reject duplicate JSON fields that could change GraphQL meaning."""

    result = {}
    for key, value in pairs:
        need(key not in result, "schema")
        result[key] = value
    return result


def historical_window(token: str) -> tuple[datetime, datetime]:
    """Bind the exact reviewed failed probe step to a fixed-width UTC query."""

    need(bool(token), "credential")
    base = f"/repos/{REPOSITORY}/actions/runs/{RUN}/attempts/{ATTEMPT}"
    try:
        run = github_json(base, token)
        jobs = github_json(base + "/jobs?per_page=100", token)
    except Exception:
        raise HistoryError("provenance") from None
    need(run.get("id") == int(RUN) and run.get("run_attempt") == 1
         and run.get("event") == "workflow_dispatch" and run.get("status") == "completed"
         and run.get("conclusion") == "failure" and run.get("head_sha") == SHA
         and run.get("head_branch") == BRANCH
         and run.get("path") in (WORKFLOW, WORKFLOW + "@refs/heads/" + BRANCH),
         "provenance")
    entries = jobs.get("jobs")
    need(type(jobs.get("total_count")) is int and jobs["total_count"] <= 100
         and isinstance(entries, list) and len(entries) == jobs["total_count"],
         "provenance")
    matches = [job for job in entries if isinstance(job, dict)
               and job.get("name") == JOB_NAME]
    need(len(matches) == 1, "provenance")
    job = matches[0]
    need(job.get("run_id") == int(RUN) and job.get("head_sha") == SHA
         and job.get("status") == "completed" and job.get("conclusion") == "failure"
         and isinstance(job.get("steps"), list), "provenance")
    steps = [step for step in job["steps"] if isinstance(step, dict)
             and step.get("name") == PROBE_STEP_NAME]
    need(len(steps) == 1 and steps[0].get("status") == "completed"
         and steps[0].get("conclusion") == "failure", "provenance")
    try:
        run_start = parse_time(run.get("created_at"))
        run_end = parse_time(run.get("updated_at"))
        job_start = parse_time(job.get("started_at"))
        job_end = parse_time(job.get("completed_at"))
        step_start = parse_time(steps[0].get("started_at"))
        step_end = parse_time(steps[0].get("completed_at"))
    except Exception:
        raise HistoryError("provenance") from None
    need(run_start <= job_start <= step_start <= step_end <= job_end <= run_end + timedelta(minutes=2)
         and timedelta(0) < step_end - step_start <= timedelta(minutes=20)
         and -timedelta(minutes=2) <= datetime.now(timezone.utc) - run_start
         <= timedelta(days=31),
         "provenance")
    return step_start - timedelta(minutes=2), step_end + timedelta(minutes=10)


def utc(value: object) -> datetime:
    """Parse only bounded UTC event timestamps."""

    need(isinstance(value, str) and len(value) <= 32
         and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z", value)
         is not None, "schema")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HistoryError("schema") from None


def fetch(zone: str, token: str, window: tuple[datetime, datetime]) -> dict:
    """Issue one bounded, no-redirect GraphQL read without request logging."""

    need(re.fullmatch(r"[0-9a-f]{32}", zone) is not None and bool(token),
         "credential")
    body = json.dumps({"query": QUERY, "variables": {
        "zoneTag": zone,
        "start": window[0].isoformat(timespec="seconds").replace("+00:00", "Z"),
        "end": window[1].isoformat(timespec="seconds").replace("+00:00", "Z"),
    }}, separators=(",", ":")).encode()
    request = urllib.request.Request(API, data=body, method="POST", headers={
        "Authorization": "Bearer " + token, "Accept": "application/json",
        "Content-Type": "application/json",
    })
    try:
        with OPENER.open(request, timeout=20) as response:
            need(response.status == 200, "provider")
            raw = response.read(MAX_BODY + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        raise HistoryError("provider") from None
    need(len(raw) <= MAX_BODY, "provider")
    try:
        result = json.loads(raw, object_pairs_hook=unique_object)
    except (ValueError, UnicodeError):
        raise HistoryError("schema") from None
    need(isinstance(result, dict), "schema")
    return result


def events(payload: dict) -> tuple[list[dict], list[dict]]:
    """Reject GraphQL errors and full pages before examining event contents."""

    need(set(payload) in ({"data"}, {"data", "errors"})
         and payload.get("errors") is None, "schema")
    data = payload.get("data")
    viewer = data.get("viewer") if isinstance(data, dict) else None
    zones = viewer.get("zones") if isinstance(viewer, dict) else None
    need(isinstance(data, dict) and set(data) == {"viewer"}
         and isinstance(viewer, dict) and set(viewer) == {"zones"}, "schema")
    need(isinstance(zones, list) and len(zones) == 1
         and isinstance(zones[0], dict), "schema")
    zone = zones[0]
    need(set(zone) == {"emailSendingAdaptive", "emailRoutingAdaptive"},
         "schema")
    sending, routing = zone["emailSendingAdaptive"], zone["emailRoutingAdaptive"]
    need(isinstance(sending, list) and isinstance(routing, list), "schema")
    need(len(sending) < LIMIT and len(routing) < LIMIT, "limit")
    return sending, routing


def scoped(rows: list[dict], fields: frozenset[str],
           window: tuple[datetime, datetime]) -> list[dict]:
    """Keep exact synthetic event candidates while validating every row."""

    selected = []
    subject = TEMPLATE + marker(RUN, ATTEMPT)
    for row in rows:
        need(isinstance(row, dict) and set(row) == fields, "schema")
        at = utc(row["datetime"])
        need(window[0] <= at <= window[1], "scope")
        need(all(isinstance(row[field], str) and len(row[field]) <= 512
                 for field in ("from", "to", "subject", "status")), "schema")
        need(row["messageId"] is None or isinstance(row["messageId"], str)
             and len(row["messageId"]) <= 256, "schema")
        if row["from"].lower() == SENDER and row["to"].lower() == FIRST \
                and row["subject"] == subject:
            selected.append(row)
    return selected


def classify(payload: dict, window: tuple[datetime, datetime]) -> tuple[str, str, str]:
    """Return a fixed observation, never a negative inference from no rows."""

    sending, routing = events(payload)
    sends = scoped(sending, SENDING_FIELDS, window)
    routes = scoped(routing, ROUTING_FIELDS, window)
    send_count = "zero" if not sends else "one" if len(sends) == 1 else "multiple"
    route_count = "zero" if not routes else "one" if len(routes) == 1 else "multiple"
    if not sends:
        return "historical_events_inconclusive", send_count, route_count
    ids = {row["messageId"] for row in sends}
    if len(ids) != 1 or None in ids or "" in ids:
        return "historical_events_inconclusive", send_count, route_count
    need(all((row["errorCause"] is None or isinstance(row["errorCause"], str)
              and len(row["errorCause"]) <= 128)
             and type(row["isLastEvent"]) is int
             and row["isLastEvent"] in (0, 1) for row in sends), "schema")
    finals = [row for row in sends if row["isLastEvent"] == 1]
    if len(finals) > 1 or (len(sends) > 1 and len(finals) != 1):
        return "historical_events_inconclusive", send_count, route_count
    latest = finals[0] if finals else sends[0]
    if finals and any(utc(row["datetime"]) > utc(latest["datetime"]) for row in sends):
        return "historical_events_inconclusive", send_count, route_count
    need(all((row["action"] is None or isinstance(row["action"], str)
              and len(row["action"]) <= 128)
             and (row["ruleMatched"] is None or isinstance(row["ruleMatched"], str)
                  and len(row["ruleMatched"]) <= 128) for row in routes), "schema")
    if routes:
        route_ids = {row["messageId"] for row in routes}
        if len(route_ids) == 1 and route_ids == ids:
            if (latest["status"] == "deliveryFailed"
                    and latest["errorCause"] == "routing_unknown_address"):
                return "historical_events_inconclusive", send_count, route_count
            return "routing_correlated_observed_worker_unverified", send_count, route_count
        return "routing_id_unjoined", send_count, route_count
    if latest["isLastEvent"] == 1 and latest["status"] == "deliveryFailed" \
            and latest["errorCause"] == "routing_unknown_address":
        return "sending_routing_unknown_address_observed", send_count, route_count
    if latest["status"] in ("sent", "delivered"):
        return "sending_progress_observed_routing_unverified", send_count, route_count
    if latest["isLastEvent"] == 1 and latest["status"] in ("deliveryFailed", "rejected", "failed"):
        return "sending_failure_observed_routing_unverified", send_count, route_count
    return "sending_event_observed_status_unverified", send_count, route_count


def run(confirm: str, run: str, zone: str, analytics: str,
        github: str) -> tuple[str, str, str]:
    """Gate one historical query on immutable run identity and confirmation."""

    need(confirm == CONFIRM, "confirmation")
    need(run == RUN and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY,
         "identity")
    window = historical_window(github)
    return classify(fetch(zone, analytics, window), window)


def main() -> int:
    """Print only fixed category and bounded cardinality, suppressing errors."""

    try:
        result, sends, routes = run(
            sys.argv[1] if len(sys.argv) == 3 else "",
            sys.argv[2] if len(sys.argv) == 3 else "",
            os.environ.get("CF_ZONE_ID", ""),
            os.environ.get("CF_OBSERVABILITY_TOKEN", ""),
            os.environ.get("GITHUB_TOKEN", ""),
        )
        need(result in RESULTS, "schema")
        print(f"worker_r2_history={result} sending={sends} routing={routes}")
        return 0
    except HistoryError as error:
        reason = error.args[0] if error.args and error.args[0] in REASONS else "internal"
        print(f"worker_r2_history=UNVERIFIED reason={reason}")
        return 1
    except Exception:
        print("worker_r2_history=UNVERIFIED reason=internal")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
