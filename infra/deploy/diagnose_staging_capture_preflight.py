"""Diagnose fixed staging capture-correction preflight phases using only GETs.

No PATCH, Mail request, log query, arbitrary URL/path, or settings attestation is
available. A diagnosed preflight is not capture-off or privacy acceptance.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).parent))
from apply_staging_capture_off import (
    SCRIPT, VERSION, bindings_match, effective_api_settings, fetch,
    relax_issues, serving_deployment, source_policy, unaffected, worker_readback,
)
from pin_staging_mail import expected_bindings
from check_observability import legacy_noncontradictory

CONFIRM = "READ_STAGING_CAPTURE_SETTINGS_PREFLIGHT"
DEPLOYMENTS = "deployments?per_page=1&page=1"
FIELDS = (
    "source", "serving", "version_read", "bindings", "binding_cause",
    "settings_read", "script_settings_read", "worker_read",
    "worker_normalized", "settings_normalized", "script_settings_normalized",
    "worker_policy", "settings_policy", "script_settings_policy",
    "unaffected_projection", "serving_after", "preflight",
)


def failure_category(error: Exception) -> str:
    """Classify only reviewed exception types/status ranges, never error text."""
    cause = error.__cause__ if isinstance(error.__cause__, Exception) else error
    if isinstance(cause, HTTPError):
        if cause.code in (401, 403):
            return "http_denied"
        if cause.code == 404:
            return "http_not_found"
        if type(cause.code) is int and 500 <= cause.code <= 599:
            return "http_5xx"
        return "http_error"
    if isinstance(cause, TimeoutError):
        return "timeout"
    if isinstance(cause, (URLError, OSError)):
        return "transport"
    return "provider_unverified"


def binding_cause(value: dict) -> str:
    """Refine a failed shared binding predicate into a fixed private shape cause.

    This diagnostic does not authorize a binding set. The shared exact validator
    remains the sole match predicate; no binding name, value or count is output.
    """
    if value.get("id") != VERSION:
        return "version_identity"
    resources = value.get("resources")
    if not isinstance(resources, dict):
        return "resources_shape"
    actual = resources.get("bindings")
    if isinstance(actual, dict) and set(actual) == {"result"}:
        actual = actual["result"]
    if not isinstance(actual, list):
        return "bindings_shape"
    expected = expected_bindings()
    if len(actual) != len(expected):
        return "bindings_count"
    seen = set()
    for entry in actual:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            return "binding_shape"
        name = entry["name"]
        if name in seen:
            return "binding_duplicate"
        if name not in expected:
            return "binding_names"
        seen.add(name)
        kind, value = expected[name]
        if entry.get("type") != kind:
            return "binding_type"
        resource_key = {"d1": "database_id", "r2_bucket": "bucket_name",
                        "plain_text": "text"}.get(kind)
        if resource_key and entry.get(resource_key) != value:
            return {"d1": "d1_resource", "r2_bucket": "r2_resource",
                    "plain_text": "plain_text_resource"}[kind]
        if kind == "send_email" and entry.get("destination_address") is not None:
            return "email_restriction"
    return "unclassified_mismatch"


def diagnose(account: str, token: str, expected: str) -> tuple[str, dict]:
    """Run a six-GET fixed preflight discriminator, never the mutating helper.

    Settings phases may still be inspected after a binding mismatch to resolve
    the complete bounded preflight in one run. A failed read is not retried. Once
    an initial serving pin is valid, the final GET always brackets attempted
    reads; collected phases are discarded on an observed deployment change.
    """
    result = dict.fromkeys(FIELDS, "skipped")
    if expected != VERSION:
        return "input_unverified", result
    try:
        source_policy()
        result["source"] = "match"
    except (ValueError, KeyError, TypeError, OSError):
        result["source"] = "unverified"
        return "source_unverified", result
    try:
        before = serving_deployment(fetch(account, token, DEPLOYMENTS))
    except (ValueError, KeyError, TypeError, OSError) as error:
        result["serving"] = failure_category(error)
        return "incomplete", result
    if before is None or before[1] != expected:
        result["serving"] = "unverified"
        return "serving_unverified", result
    result["serving"] = "match"
    complete = True
    try:
        version = fetch(account, token, f"versions/{VERSION}")
        result["version_read"] = "ok"
        if bindings_match(version, VERSION):
            result["bindings"] = result["binding_cause"] = "match"
        else:
            result["bindings"] = "mismatch"
            result["binding_cause"] = binding_cause(version)
    except (ValueError, KeyError, TypeError, OSError) as error:
        result["version_read"] = failure_category(error)
        complete = False
    values = {}
    for label, reader in (
        ("settings", lambda: fetch(account, token, "settings")),
        ("script_settings", lambda: fetch(account, token, "script-settings")),
        ("worker", lambda: worker_readback(account, token)),
    ):
        try:
            values[label] = reader()
            result[f"{label}_read"] = "ok"
        except (ValueError, KeyError, TypeError, OSError) as error:
            result[f"{label}_read"] = failure_category(error)
            complete = False
    for label, value in values.items():
        try:
            normalized = relax_issues(value)
            result[f"{label}_normalized"] = "ok"
            matched = (effective_api_settings(normalized, SCRIPT) if label == "worker"
                       else legacy_noncontradictory(normalized))
            result[f"{label}_policy"] = "match" if matched else "mismatch"
        except (ValueError, KeyError, TypeError, OSError):
            result[f"{label}_normalized"] = "unverified"
    if len(values) == 3:
        try:
            tuple(unaffected(values[label]) for label in ("worker", "settings", "script_settings"))
            result["unaffected_projection"] = "match"
        except (ValueError, KeyError, TypeError, OSError):
            result["unaffected_projection"] = "unverified"
    try:
        after = serving_deployment(fetch(account, token, DEPLOYMENTS))
    except (ValueError, KeyError, TypeError, OSError) as error:
        result["serving_after"] = failure_category(error)
        return "incomplete", result
    if before != after:
        discarded = dict.fromkeys(FIELDS, "discarded")
        discarded["serving_after"] = "changed"
        return "deployment_changed", discarded
    result["serving_after"] = "match"
    required = ("source", "serving", "bindings", "worker_policy",
                "settings_policy", "script_settings_policy", "unaffected_projection")
    result["preflight"] = "pass" if all(result[key] == "match" for key in required) else "blocked"
    if not complete:
        result["preflight"] = "unavailable"
    return "diagnosed" if complete else "incomplete", result


def main() -> int:
    """Accept only a fixed first-attempt manual project diagnostic with exact pin."""
    empty = dict.fromkeys(FIELDS, "skipped")
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    expected = os.getenv("AMAIL_EXPECTED_WORKER_VERSION", "")
    if (os.getenv("AMAIL_CAPTURE_PREFLIGHT_CONFIRM") != CONFIRM
            or expected != VERSION or os.getenv("GITHUB_RUN_ATTEMPT") != "1"
            or os.getenv("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or os.getenv("GITHUB_REF") != "refs/heads/codex/amail-v0.1.0"
            or not re.fullmatch(r"[0-9a-f]{40}", os.getenv("GITHUB_SHA", ""))
            or not re.fullmatch(r"[0-9a-f]{32}", account) or not token):
        status, result = "input_unverified", empty
    else:
        try:
            status, result = diagnose(account, token, expected)
        except (ValueError, KeyError, TypeError, OSError):
            status, result = "incomplete", empty
    print(f"staging_capture_preflight_diagnostic={status}")
    for field in FIELDS:
        print(f"staging_capture_preflight_{field}={result[field]}")
    return 0 if status == "diagnosed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
