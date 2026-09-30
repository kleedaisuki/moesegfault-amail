"""Classify one fixed historical staging settings PATCH audit window read-only.

No API mutation, cursor continuation, broader time window, raw record output or
containment attestation exists. Matching audit evidence is not helper attribution.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

API = "https://api.cloudflare.com/client/v4"
SINCE = "2026-09-30T16:16:00Z"
BEFORE = "2026-09-30T16:16:06Z"
CONFIRM = "READ_STAGING_CAPTURE_SETTINGS_PATCH_AUDIT"
LIMIT = 100
BYTE_LIMIT = 1_048_576
TIMEOUT = 15
FIELDS = ("read", "complete", "matches", "http", "action", "historical")
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
                  r"(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z")


class AuditReadError(ValueError):
    """Carry only a fixed local diagnostic category, never provider detail."""

    def __init__(self, category: str):
        """Keep all untrusted response/error text outside the output interface."""
        if category not in {"denied", "transport", "http_other", "shape", "oversized"}:
            category = "shape"
        self.category = category
        super().__init__(category)


class NoRedirect(HTTPRedirectHandler):
    """Prevent credential forwarding and never discover a replacement endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Reject all redirects without printing Location or provider detail."""
        return None


def read_audit_payload(account: str, token: str) -> object:
    """Read one bounded JSON value for fixed-endpoint classification or shape bins.

    This transport boundary does not assert a response schema. The historical
    outcome classifier retains its independent object/envelope/page policy.
    """
    if not re.fullmatch(r"[0-9a-f]{32}", account) or not token:
        raise AuditReadError("shape")
    query = urlencode({"since": SINCE, "before": BEFORE, "limit": LIMIT, "direction": "asc"})
    request = Request(f"{API}/accounts/{account}/logs/audit?{query}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, method="GET")
    try:
        with build_opener(NoRedirect()).open(request, timeout=TIMEOUT) as response:
            if response.status != 200:
                raise AuditReadError("http_other")
            raw = response.read(BYTE_LIMIT + 1)
    except HTTPError as error:
        raise AuditReadError("denied" if error.code in (401, 403) else "http_other") from None
    except (URLError, TimeoutError, OSError, HTTPException):
        raise AuditReadError("transport") from None
    if len(raw) > BYTE_LIMIT:
        raise AuditReadError("oversized")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise AuditReadError("shape") from None
    return payload


def read_audit(account: str, token: str) -> dict:
    """Preserve the outcome classifier's original required object response shape."""
    payload = read_audit_payload(account, token)
    if not isinstance(payload, dict):
        raise AuditReadError("shape")
    return payload


def in_window(value: object) -> bool:
    """Require a typed RFC3339 instant strictly inside the requested six seconds."""
    if not isinstance(value, str) or len(value) > 40 or not DATE.fullmatch(value):
        return False
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (datetime.fromisoformat(SINCE.replace("Z", "+00:00")) < instant
                < datetime.fromisoformat(BEFORE.replace("Z", "+00:00")))
    except ValueError:
        return False


def http_category(value: object) -> str | None:
    """Reduce typed status to a closed class without logging its numeric value."""
    if (type(value) not in (int, float) or not 100 <= value <= 599
            or value != int(value)):
        return None
    if value == 200:
        return "expected_success"
    if 200 <= value <= 299:
        return "other_success"
    if 400 <= value <= 499:
        return "client_error"
    if 500 <= value <= 599:
        return "server_error"
    return "other"


def valid_count(value: object, length: int) -> bool:
    """Accept canonical documented strings or the observed integer JSON shape.

    The count is only a consistency check on this bounded page. Booleans,
    floats, missing values and alternate string encodings cannot pass.
    """
    if type(value) is int:
        return 0 <= value <= LIMIT and value == length
    return (isinstance(value, str)
            and re.fullmatch(r"(?:0|[1-9][0-9]{0,2})", value) is not None
            and int(value) == length)


def classify(payload: dict, account: str) -> tuple[str, dict]:
    """Validate the bounded envelope/page and match only exact method/URI in memory.

    Count measures returned records, not a query total. Neither an omitted nor
    empty optional cursor documents exhaustion. A fully validated returned page
    may expose a positive observation, but never completeness or uniqueness
    beyond that page; the aggregate and exit status remain fail-closed.
    """
    result = {"read": "ok", "complete": "unverified", "matches": "unverified",
              "http": "unverified", "action": "unverified", "historical": "unresolved"}
    if (not isinstance(payload, dict) or set(payload) - {"success", "errors", "result", "result_info"}
            or payload.get("success") is not True
            or ("errors" in payload and payload["errors"] != [])):
        result["read"] = "shape"
        return "UNVERIFIED", result
    rows, info = payload.get("result"), payload.get("result_info")
    if (not isinstance(rows, list) or len(rows) > LIMIT or not isinstance(info, dict)
            or set(info) - {"count", "cursor"}
            or not valid_count(info.get("count"), len(rows))):
        result["read"] = "shape"
        return "UNVERIFIED", result
    if "cursor" in info and info["cursor"] != "":
        # Only the observed omitted representation and legacy empty-string
        # representation are inspected. Neither establishes exhaustion.
        return "UNVERIFIED", result
    target = f"/accounts/{account}/workers/scripts/amail-mail-staging/script-settings"
    matches = []
    for row in rows:
        if not isinstance(row, dict) or set(row) - {"id", "account", "action", "actor", "raw", "resource", "zone"}:
            return "UNVERIFIED", result
        raw, action = row.get("raw"), row.get("action")
        if (not isinstance(raw, dict) or set(raw) - {"cf_ray_id", "method", "status_code", "uri", "user_agent"}
                or not isinstance(raw.get("method"), str)
                or raw["method"] not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
                or not isinstance(raw.get("uri"), str) or not 0 < len(raw["uri"]) <= 4096
                or not isinstance(action, dict) or set(action) - {"description", "result", "time", "type"}
                or not in_window(action.get("time"))):
            return "UNVERIFIED", result
        if row.get("account") is not None and (
                not isinstance(row["account"], dict) or row["account"].get("id") != account):
            return "UNVERIFIED", result
        if raw["method"] != "PATCH" or raw["uri"] != target:
            continue
        http = http_category(raw.get("status_code"))
        if http is None or action.get("result") not in ("success", "failure"):
            return "UNVERIFIED", result
        matches.append((http, action["result"]))
    result["matches"] = "zero" if not matches else "one" if len(matches) == 1 else "multiple"
    if not matches:
        return "UNVERIFIED", result
    for index, field in ((0, "http"), (1, "action")):
        values = {value[index] for value in matches}
        result[field] = next(iter(values)) if len(values) == 1 else "mixed"
    if len(matches) != 1:
        return "UNVERIFIED", result
    if result["action"] == "failure":
        result["historical"] = "page_reported_failure"
    elif result["http"] in ("expected_success", "other_success"):
        result["historical"] = "page_reported_success"
    else:
        return "UNVERIFIED", result
    return "UNVERIFIED", result


def main() -> int:
    """Print only fixed categories for the exact first-attempt manual project job."""
    account, token = os.getenv("CLOUDFLARE_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_API_TOKEN", "")
    status = "UNVERIFIED"
    result = {"read": "input_unverified", "complete": "unverified", "matches": "unverified",
              "http": "unverified", "action": "unverified", "historical": "unresolved"}
    if (os.getenv("AMAIL_SETTINGS_AUDIT_CONFIRM") == CONFIRM
            and os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"
            and os.getenv("GITHUB_RUN_ATTEMPT") == "1"
            and os.getenv("GITHUB_REF") == "refs/heads/codex/amail-v0.1.0"
            and re.fullmatch(r"[0-9a-f]{40}", os.getenv("GITHUB_SHA", ""))
            and re.fullmatch(r"[0-9a-f]{32}", account) and token):
        try:
            status, result = classify(read_audit(account, token), account)
        except AuditReadError as error:
            result["read"] = error.category
        except (ValueError, TypeError, KeyError, OSError):
            result["read"] = "shape"
    print(f"staging_settings_patch_audit={status}")
    for field in FIELDS:
        print(f"staging_settings_patch_audit_{field}={result[field]}")
    # Optional cursor semantics do not prove query exhaustion. Even a positive
    # page observation must never make this job an acceptance/attestation gate.
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
