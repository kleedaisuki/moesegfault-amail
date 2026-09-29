"""Classify retained exception metadata in one historical staging window.

The provider response can contain private mail data. It is parsed in memory,
never persisted or echoed, and all output comes from a closed vocabulary.
This probe cannot attribute an exception to the address-add request.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid


API = "https://api.cloudflare.com/client/v4/accounts"
WORKER = "amail-mail-staging"
START_MS = 1790684672000
END_MS = 1790684741000
CONFIRM = "READ_FOURTH_STAGING_EXCEPTION_36567571204"
PAGE_LIMIT = 200
MAX_BODY = 262_144
MAX_ROWS = 200
REASONS = frozenset({
    "confirmation", "credential", "transport", "http", "permission", "size",
    "schema", "provider", "echo", "incomplete", "scope", "count",
})


class Unverified(Exception):
    """Represent a fixed reason without retaining provider exception text."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Prevent bearer credentials from following a provider redirect."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        """Deny every redirect, including same-origin redirects."""

        return None


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    """Reject duplicate keys that could subvert query echo validation."""

    result = {}
    for key, value in pairs:
        if key in result:
            raise Unverified("schema")
        result[key] = value
    return result


def query_body() -> dict:
    """Constrain a dry event view to one service and the E2E step interval."""

    return {
        "queryId": str(uuid.uuid4()),
        "timeframe": {"from": START_MS, "to": END_MS},
        "dry": True, "view": "events", "limit": PAGE_LIMIT,
        "parameters": {"datasets": [], "filterCombination": "and", "filters": [
            {"key": "$metadata.service", "operation": "eq", "type": "string", "value": WORKER},
        ]},
    }


def fetch(account: str, token: str, body: dict) -> object:
    """Make exactly one read-only no-redirect query with a bounded response."""

    request = urllib.request.Request(
        f"{API}/{account}/workers/observability/telemetry/query",
        data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            if response.status != 200:
                raise Unverified("http")
            raw = response.read(MAX_BODY + 1)
    except urllib.error.HTTPError as error:
        raise Unverified("permission" if error.code in (401, 403) else "http") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise Unverified("transport") from None
    if len(raw) > MAX_BODY:
        raise Unverified("size")
    try:
        return json.loads(raw, object_pairs_hook=unique_object)
    except (ValueError, UnicodeError):
        raise Unverified("schema") from None


def _error_kind(value: object) -> str:
    """Recognize only exact platform exception literals; ignore all details."""

    if value in ("RuntimeError: unreachable", "unreachable"):
        return "wasm_unreachable"
    if value in ("RuntimeError: memory access out of bounds", "memory access out of bounds"):
        return "wasm_memory_bounds"
    return "other_or_absent"


def classify(payload: object, body: dict) -> str:
    """Validate response scope/completeness before returning a fixed label."""

    if not isinstance(payload, dict) or payload.get("success") is not True or payload.get("errors") not in (None, []):
        raise Unverified("provider")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise Unverified("schema")
    run = result.get("run")
    if not isinstance(run, dict) or run.get("status") != "COMPLETED" or run.get("dry") is not True:
        raise Unverified("incomplete")
    if run.get("timeframe") != body["timeframe"]:
        raise Unverified("echo")
    query = run.get("query")
    parameters = query.get("parameters") if isinstance(query, dict) else None
    if not isinstance(parameters, dict) or parameters.get("datasets") != [] or parameters.get("filters") != body["parameters"]["filters"]:
        raise Unverified("echo")
    if parameters.get("filterCombination") not in ("and", "AND"):
        raise Unverified("echo")
    if parameters.get("view", "events") != "events" or any(parameters.get(key) for key in ("needle", "havings", "groupBys")):
        raise Unverified("echo")
    container = result.get("events")
    if not isinstance(container, dict):
        raise Unverified("schema")
    rows, count = container.get("events"), container.get("count")
    if not isinstance(rows, list) or type(count) is not int or count != len(rows) or count > MAX_ROWS:
        raise Unverified("count")
    if not rows:
        return "none_retained_not_absence_proof"

    candidates: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            raise Unverified("schema")
        meta = row.get("$metadata")
        if not isinstance(meta, dict) or meta.get("service") != WORKER:
            raise Unverified("scope")
        at = row.get("timestamp")
        if type(at) is not int or not START_MS <= at <= END_MS:
            raise Unverified("scope")
        workers = row.get("$workers")
        if not isinstance(workers, dict) or workers.get("scriptName") != WORKER:
            raise Unverified("scope")
        if meta.get("error") is not None or (isinstance(workers, dict) and workers.get("outcome") == "exception"):
            candidates.append(_error_kind(meta.get("error")))
    if not candidates:
        return "no_exception_record_not_absence_proof"
    if len(candidates) == 1:
        return "one_" + candidates[0] + "_not_attributed"
    return "multiple_exception_records_not_attributed"


def run(confirm: str, account: str, token: str) -> str:
    """Gate the one historical read on an exact confirmation and credential."""

    if confirm != CONFIRM:
        raise Unverified("confirmation")
    if not re.fullmatch(r"[a-f0-9]{32}", account) or not token:
        raise Unverified("credential")
    body = query_body()
    return classify(fetch(account, token, body), body)


def main() -> int:
    """Print one fixed label; suppress provider-supplied exceptions and data."""

    try:
        label = run(sys.argv[1] if len(sys.argv) == 2 else "", os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
                    os.environ.get("CF_OBSERVABILITY_TOKEN", ""))
    except Unverified as error:
        reason = error.args[0] if error.args and error.args[0] in REASONS else "internal"
        print(f"exception_result=UNVERIFIED reason={reason}")
        return 1
    except Exception:
        print("exception_result=UNVERIFIED reason=internal")
        return 1
    print(f"exception_result={label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
