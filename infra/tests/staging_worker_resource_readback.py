"""Categorical staging Worker resource readback; never a containment attestation.

Five control-plane GETs bracket three representations with an expected stable
100%-serving deployment. No Mail traffic, mutation, discovery, or raw output.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.request import HTTPRedirectHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
from pin_staging_mail import ACCOUNT, API, LIMIT, SCRIPT, UUID, serving_deployment

CONFIRM = "READ_STAGING_WORKER_RESOURCE_OBSERVABILITY"
MISSING = object()
DEPLOYMENTS = f"workers/scripts/{SCRIPT}/deployments?per_page=1&page=1"
ENDPOINTS = (
    ("settings", f"workers/scripts/{SCRIPT}/settings"),
    ("script_settings", f"workers/scripts/{SCRIPT}/script-settings"),
    ("worker", f"workers/workers/{SCRIPT}"),
)
FIELDS = (
    "observability_shape", "logs_shape", "traces_shape", "issues_shape",
    "enabled", "sampling", "redact", "logs", "invocation", "persist",
    "logs_sampling", "logs_destinations_shape", "logs_destinations",
    "traces", "traces_sampling", "traces_destinations_shape",
    "traces_destinations", "issues", "logpush", "tails_shape", "tails",
)


class NoRedirect(HTTPRedirectHandler):
    """Reject redirects rather than leak credentials or add unreviewed GETs."""

    def redirect_request(self, request, response, code, message, headers, url):
        """Prevent automatic traversal outside the exact reviewed API paths."""
        return None


def fetch(account: str, token: str, path: str) -> dict:
    """Read one bounded successful provider object without raw error output."""
    request = Request(
        f"{API}/accounts/{account}/{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    with build_opener(NoRedirect()).open(request, timeout=15) as response:
        if response.getcode() != 200:
            raise ValueError("unavailable")
        raw = response.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("unavailable")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("unavailable")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("unavailable")
    return result


def field(value: object, key: str) -> object:
    """Preserve an absent child separately from JSON null."""
    return value.get(key, MISSING) if isinstance(value, dict) else MISSING


def shape(value: object) -> str:
    """Classify JSON kinds, checking Boolean before its numeric superclass."""
    if value is MISSING:
        return "missing"
    if value is None:
        return "null"
    kinds = ((dict, "object"), (bool, "boolean"), (int, "number"),
             (float, "number"), (str, "string"), (list, "array"))
    return next((label for kind, label in kinds if isinstance(value, kind)), "other")


def boolean(value: object) -> str:
    """Expose literal booleans and distinct missing/null categories only."""
    if value is MISSING:
        return "missing"
    if value is None:
        return "null"
    return "true" if value is True else "false" if value is False else "other"


def sampling(value: object) -> str:
    """Classify zero/one without conflating sampling with capture being off."""
    if value is MISSING:
        return "missing"
    if value is None:
        return "null"
    if type(value) not in (int, float):
        return "other"
    return "zero" if value == 0 else "one" if value == 1 else "other"


def collection_shape(value: object) -> str:
    """Use list terminology while retaining non-list JSON distinctions."""
    return "list" if isinstance(value, list) else shape(value)


def collection(value: object, destinations: bool = False) -> str:
    """Validate every member before categorizing exports or tail consumers.

    Destination strings other than exact Cloudflare are external, never printed.
    Tail entries require nonempty service and a string environment if supplied.
    Unknown fields are never emitted.
    """
    if value is MISSING:
        return "missing"
    if value is None:
        return "null"
    if not isinstance(value, list):
        return "malformed"
    if destinations:
        if not all(isinstance(x, str) and x.strip() for x in value):
            return "malformed"
        if not value:
            return "empty"
        return "cloudflare_only" if all(x == "cloudflare" for x in value) else "external"
    if not all(
        isinstance(x, dict) and isinstance(x.get("service"), str)
        and bool(x["service"].strip())
        and ("environment" not in x or isinstance(x["environment"], str))
        for x in value
    ):
        return "malformed"
    return "populated" if value else "empty"


def classify(settings: dict) -> dict[str, str]:
    """Produce closed reviewed categories; unknown keys never escape."""
    obs = field(settings, "observability")
    logs, traces, issues = (field(obs, key) for key in ("logs", "traces", "issues"))
    log_dest, trace_dest = field(logs, "destinations"), field(traces, "destinations")
    tails = field(settings, "tail_consumers")
    return {
        "observability_shape": shape(obs), "logs_shape": shape(logs),
        "traces_shape": shape(traces), "issues_shape": shape(issues),
        "enabled": boolean(field(obs, "enabled")),
        "sampling": sampling(field(obs, "head_sampling_rate")),
        "redact": boolean(field(obs, "redact_query_string")),
        "logs": boolean(field(logs, "enabled")),
        "invocation": boolean(field(logs, "invocation_logs")),
        "persist": boolean(field(logs, "persist")),
        "logs_sampling": sampling(field(logs, "head_sampling_rate")),
        "logs_destinations_shape": collection_shape(log_dest),
        "logs_destinations": collection(log_dest, True),
        "traces": boolean(field(traces, "enabled")),
        "traces_sampling": sampling(field(traces, "head_sampling_rate")),
        "traces_destinations_shape": collection_shape(trace_dest),
        "traces_destinations": collection(trace_dest, True),
        "issues": boolean(field(issues, "enabled")),
        "logpush": boolean(field(settings, "logpush")),
        "tails_shape": collection_shape(tails), "tails": collection(tails),
    }


def probe(account: str, token: str, expected: str) -> tuple[str, dict[str, dict[str, str]]]:
    """Discard categories on serving change; never infer capture safety."""
    first = serving_deployment(fetch(account, token, DEPLOYMENTS))
    if first is None:
        return "deployment_unverified", {}
    if first[1] != expected:
        return "version_mismatch", {}
    result = {}
    for label, path in ENDPOINTS:
        try:
            value = fetch(account, token, path)
            identity = {}
            if label == "worker":
                identity["worker_name"] = "match" if value.get("name") == SCRIPT else "mismatch"
                worker_id = value.get("id")
                identity["worker_id"] = "valid" if isinstance(worker_id, str) and worker_id.strip() else "invalid"
                if identity != {"worker_name": "match", "worker_id": "valid"}:
                    result[label] = {"read": "unavailable", **identity}
                    continue
            result[label] = {"read": "available", **identity, **classify(value)}
        except Exception:
            result[label] = {"read": "unavailable"}
    second = serving_deployment(fetch(account, token, DEPLOYMENTS))
    if first != second:
        return "deployment_changed", {}
    return ("stable100" if all(x["read"] == "available" for x in result.values())
            else "representation_unavailable"), result


def main() -> int:
    """Validate before networking; emit fixed bins and no containment pass."""
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    expected = os.environ.get("AMAIL_EXPECTED_WORKER_VERSION", "")
    confirm = os.environ.get("AMAIL_WORKER_RESOURCE_CONFIRM", "")
    if confirm != CONFIRM or not ACCOUNT.fullmatch(account) or not token or not UUID.fullmatch(expected):
        reason, result = "invalid_input", {}
    else:
        try:
            reason, result = probe(account, token, expected)
        except Exception:
            reason, result = "unavailable", {}
    print("staging_worker_resource_readback=" + ("stable100" if reason == "stable100" else "UNVERIFIED"))
    print("staging_worker_resource_reason=" + reason)
    for endpoint, _ in ENDPOINTS:
        values = result.get(endpoint, {})
        for name in ("read", "worker_name", "worker_id", *FIELDS):
            if name in values:
                print("staging_worker_resource_" + endpoint + "_" + name + "=" + values[name])
    return 0 if reason == "stable100" else 1


if __name__ == "__main__":
    raise SystemExit(main())
