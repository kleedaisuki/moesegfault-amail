"""Inspect only fixed type bins for one already-scoped historical audit GET.

    No field value, PATCH matching, historical outcome or containment acceptance
    is produced. Existing audit outcome policy remains untouched.
"""
from __future__ import annotations

import os
import re

from staging_settings_patch_audit import AuditReadError, LIMIT, read_audit_payload

CONFIRM = "READ_STAGING_CAPTURE_SETTINGS_AUDIT_SHAPE"
MISSING = object()
ENVELOPE_KEYS = {"success", "errors", "result", "result_info"}
ROW_KEYS = {"id", "account", "action", "actor", "raw", "resource", "zone"}
ACTION_KEYS = {"description", "result", "time", "type"}
RAW_KEYS = {"cf_ray_id", "method", "status_code", "uri", "user_agent"}
FIELDS = (
    "read", "envelope_shape", "envelope_keys", "success_shape", "errors_shape",
    "messages_shape", "result_shape", "result_info_shape", "result_info_keys",
    "count_shape", "count_format", "count_relation", "cursor_shape", "cursor_state",
    "rows_bound", "row_shape", "row_keys", "action_shape", "action_keys",
    "action_time_shape", "action_result_shape", "raw_shape", "raw_keys",
    "raw_method_shape", "raw_uri_shape", "raw_status_shape", "strict_envelope", "strict_count",
)


def shape(value: object) -> str:
    """Reduce a value to a closed presence/type bin, never its contents."""
    if value is MISSING:
        return "missing"
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) in (int, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "other"


def member(value: object, key: str) -> object:
    """Inspect only an explicitly declared field, not arbitrary response keys."""
    return value.get(key, MISSING) if isinstance(value, dict) else MISSING


def keys_bin(value: object, allowed: set[str]) -> str:
    """Report only whether unknown keys exist; never emit their names."""
    if not isinstance(value, dict):
        return "not_object"
    return "known_only" if set(value) <= allowed else "unknown"


def group(values: list[str]) -> str:
    """Aggregate closed bins across at most LIMIT rows without outputting counts."""
    bins = set(values)
    return "no_rows" if not bins else next(iter(bins)) if len(bins) == 1 else "mixed"


def count_shape(value: object) -> tuple[str, int | None]:
    """Recognize only bounded count representation; numeric value stays private."""
    if isinstance(value, str) and re.fullmatch(r"(?:0|[1-9][0-9]{0,2})", value):
        count = int(value)
        return ("canonical_string", count) if count <= LIMIT else ("out_of_bound", None)
    if type(value) in (int, float) and 0 <= value <= LIMIT and value == int(value):
        return "integer_number", int(value)
    return "unavailable" if value is MISSING or value is None else "malformed", None


def diagnose_payload(payload: object) -> tuple[str, dict]:
    """Emit bounded schema observations while rejecting incomplete page claims.

    The shape discriminator may recognize a bounded numeric count only to show
    why the unchanged outcome classifier requires a string. SHAPE_DIAGNOSED is
    neither audit coverage nor any permission to relax the original classifier.
    """
    result = dict.fromkeys(FIELDS, "skipped")
    result["read"] = "ok"
    result["envelope_shape"] = shape(payload)
    result["envelope_keys"] = keys_bin(payload, ENVELOPE_KEYS)
    for field, key in (("success_shape", "success"), ("errors_shape", "errors"),
                       ("messages_shape", "messages"), ("result_shape", "result"),
                       ("result_info_shape", "result_info")):
        result[field] = shape(member(payload, key))
    rows, info = member(payload, "result"), member(payload, "result_info")
    result["result_info_keys"] = keys_bin(info, {"count", "cursor"})
    count, cursor = member(info, "count"), member(info, "cursor")
    result["count_shape"], result["cursor_shape"] = shape(count), shape(cursor)
    result["count_format"], number = count_shape(count)
    result["cursor_state"] = ("empty_string" if cursor == "" else "nonempty_string") if isinstance(cursor, str) else "not_string"
    bounded = isinstance(rows, list) and len(rows) <= LIMIT
    result["rows_bound"] = "within" if bounded else "exceeded" if isinstance(rows, list) else "unavailable"
    result["count_relation"] = "match" if bounded and number == len(rows) else "mismatch" if bounded and number is not None else "unverified"
    result["strict_envelope"] = "match" if (
        isinstance(payload, dict) and result["envelope_keys"] == "known_only"
        and payload.get("success") is True
        and ("errors" not in payload or payload["errors"] == [])) else "mismatch"
    result["strict_count"] = "match" if result["count_format"] == "canonical_string" and result["count_relation"] == "match" else "mismatch"
    if bounded:
        result["row_shape"] = group([shape(row) for row in rows])
        result["row_keys"] = group([keys_bin(row, ROW_KEYS) for row in rows])
        for label, allowed in (("action", ACTION_KEYS), ("raw", RAW_KEYS)):
            values = [member(row, label) for row in rows]
            result[f"{label}_shape"] = group([shape(value) for value in values])
            result[f"{label}_keys"] = group([keys_bin(value, allowed) for value in values])
        for label, parent, key in (("action_time_shape", "action", "time"),
                                   ("action_result_shape", "action", "result"),
                                   ("raw_method_shape", "raw", "method"),
                                   ("raw_uri_shape", "raw", "uri"),
                                   ("raw_status_shape", "raw", "status_code")):
            result[label] = group([shape(member(member(row, parent), key)) for row in rows])
    safe_frame = (bounded and result["strict_envelope"] == "match"
                  and result["result_info_keys"] == "known_only"
                  and result["count_relation"] == "match" and cursor == ""
                  and all(result[key] in ("known_only", "no_rows")
                          for key in ("row_keys", "action_keys", "raw_keys")))
    return "SHAPE_DIAGNOSED" if safe_frame else "UNVERIFIED", result


def main() -> int:
    """Use only the fixed manual project context; output approved shape keys only."""
    account, token = os.getenv("CLOUDFLARE_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_API_TOKEN", "")
    status, result = "UNVERIFIED", dict.fromkeys(FIELDS, "skipped")
    result["read"] = "input_unverified"
    if (os.getenv("AMAIL_SETTINGS_AUDIT_SHAPE_CONFIRM") == CONFIRM
            and os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"
            and os.getenv("GITHUB_RUN_ATTEMPT") == "1"
            and os.getenv("GITHUB_REF") == "refs/heads/codex/amail-v0.1.0"
            and re.fullmatch(r"[0-9a-f]{40}", os.getenv("GITHUB_SHA", ""))
            and re.fullmatch(r"[0-9a-f]{32}", account) and token):
        try:
            status, result = diagnose_payload(read_audit_payload(account, token))
        except AuditReadError as error:
            result["read"] = error.category
        except (ValueError, TypeError, KeyError, OSError):
            result["read"] = "shape"
    print(f"staging_settings_audit_shape={status}")
    for field in FIELDS:
        print(f"staging_settings_audit_shape_{field}={result[field]}")
    return 0 if status == "SHAPE_DIAGNOSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
