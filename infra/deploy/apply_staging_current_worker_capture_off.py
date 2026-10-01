"""Apply one guarded current-Worker PATCH, never the legacy settings operation.

Required hosted environment is documented in the alternative-operation runbook.
Provider objects stay in memory; only closed phase labels reach stdout.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
from urllib.request import Request, build_opener

from apply_staging_capture_off import (
    API, SCRIPT, VERSION, containment_bindings_match, effective_api_settings,
    relax_issues, safe_observability, source_policy, NoRedirect,
)
from pin_staging_mail import LIMIT, serving_deployment

CONFIRM = "APPLY_STAGING_CURRENT_WORKER_CAPTURE_OFF"
FREEZE = "FREEZE_STAGING_MAIL_DEPLOYS"
DEPLOYMENTS = "deployments?per_page=1&page=1"
PHASES = ("projection", "serving_pin", "patch", "readback", "unchanged_state")


def unique_object(pairs: list) -> dict:
    """Reject duplicate JSON keys instead of silently choosing a capture flag."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("provider_shape")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    """Nonfinite numbers are not JSON and cannot form provider evidence."""
    raise ValueError("provider_shape")


def request_result(request: Request) -> dict:
    """Read one bounded 200 success object without redirects or raw diagnostics."""
    with build_opener(NoRedirect()).open(request, timeout=15) as response:
        raw = response.read(LIMIT + 1)
        if response.status != 200 or len(raw) > LIMIT:
            raise ValueError("provider_shape")
    payload = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    if (not isinstance(payload, dict) or payload.get("success") is not True
            or not isinstance(payload.get("result"), dict)):
        raise ValueError("provider_shape")
    return payload["result"]


def fetch(account: str, token: str, suffix: str) -> dict:
    """Read only exact serving/version endpoints through the strict decoder."""
    if suffix not in (DEPLOYMENTS, f"versions/{VERSION}"):
        raise ValueError("endpoint")
    return request_result(Request(
        f"{API}/accounts/{account}/workers/scripts/{SCRIPT}/{suffix}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}))


def worker_readback(account: str, token: str) -> dict:
    """Read current exact-name Worker once through the strict response decoder."""
    return request_result(Request(
        f"{API}/accounts/{account}/workers/workers/{SCRIPT}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}))


def validate_write_policy(policy: dict) -> None:
    """Enforce PATCH input types independently from permissive GET readback.

    Optional response members may be null without contradicting capture-off,
    but omission and explicit null are not interchangeable in the write schema.
    Only traces.propagation_policy is a documented nullable request preference.
    """
    for section in (policy, policy["logs"], policy["traces"], policy["issues"]):
        for key in ("enabled", "redact_query_string", "invocation_logs", "persist"):
            if key in section and type(section[key]) is not bool:
                raise ValueError("projection")
        if "head_sampling_rate" in section:
            value = section["head_sampling_rate"]
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("projection")
        if "destinations" in section:
            value = section["destinations"]
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ValueError("projection")
    if policy["traces"].get("propagation_policy") not in (None, "authenticated", "accept"):
        raise ValueError("projection")


def projection(worker: dict, *, script: str = SCRIPT, reviewed: dict | None = None) -> dict:
    """Project six writable required fields; do not copy response-only fields.

    All capture mechanisms except the independent Issues switch must already be
    off. Preserve recognized optional preferences, rejecting unknown schema.
    Defaults retain the historical staging source policy. Another exact script
    requires its corresponding reviewed source observability object explicitly;
    this projection does not grant deployment or PATCH authorization. The caller
    must bracket the unchanged serving version and address PATCH by worker["id"].

    Example: ``projection(current, script="amail-mail-maintenance",
    reviewed=maintenance_config["observability"])``.
    """
    if (not isinstance(script, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,63}", script) is None
            or reviewed is None and script != SCRIPT
            or not effective_api_settings(relax_issues(worker), script)):
        raise ValueError("projection")
    identity = worker["id"]
    if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identity) is None:
        raise ValueError("projection")
    subdomain = worker.get("subdomain")
    if (not isinstance(subdomain, dict)
            or type(subdomain.get("enabled")) is not bool
            or type(subdomain.get("previews_enabled")) is not bool
            or set(subdomain) - {"enabled", "previews_enabled", "url", "preview_url_suffix"}):
        raise ValueError("projection")
    tags = worker.get("tags")
    if (not isinstance(tags, list) or len(tags) > 100
            or any(not isinstance(tag, str) or len(tag) > 256 for tag in tags)):
        raise ValueError("projection")
    policy = copy.deepcopy(worker["observability"])
    reviewed = source_policy() if reviewed is None else copy.deepcopy(reviewed)
    if not safe_observability(reviewed):
        raise ValueError("projection")
    validate_write_policy(reviewed)
    policy.update({key: value for key, value in reviewed.items()
                   if key not in ("logs", "traces", "issues")})
    for section in ("logs", "traces", "issues"):
        current = policy.get(section)
        policy[section] = {} if current is None else copy.deepcopy(current)
        policy[section].update(reviewed[section])
    if not safe_observability(policy):
        raise ValueError("projection")
    validate_write_policy(policy)
    return {"name": script, "logpush": False, "observability": policy,
            "subdomain": {key: subdomain[key] for key in ("enabled", "previews_enabled")},
            "tags": copy.deepcopy(tags), "tail_consumers": []}


def unaffected(worker: dict) -> dict:
    """Compare every unaffected response field privately, including preview data.

    Only documented observability and mutable update timestamps are excluded;
    newly added or removed unknown fields therefore fail closed after PATCH.
    """
    return {key: copy.deepcopy(value) for key, value in worker.items()
            if key not in ("observability", "updated_on", "modified_on")}


def patch_worker(account: str, token: str, identity: str, body: dict) -> dict:
    """Issue one PATCH addressed by validated readback ID, without retry/fallback."""
    return request_result(Request(
        f"{API}/accounts/{account}/workers/workers/{identity}", method="PATCH",
        data=json.dumps(body, separators=(",", ":"), allow_nan=False).encode(),
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json",
                 "Content-Type": "application/json"}))


def apply(account: str, token: str, expected: str, phases: dict) -> str:
    """Bracket one mutation with exact serving/bindings and separate GET evidence.

    No poll, rollback, code upload, Mail traffic, or acceptance from PATCH alone
    is available. Ambiguous writes require investigation, never a rerun.
    """
    if expected != VERSION:
        raise ValueError("serving_pin")
    phases["serving_pin"] = "checking_before"
    before = serving_deployment(fetch(account, token, DEPLOYMENTS))
    if before is None or before[1] != VERSION:
        raise ValueError("serving_pin")
    if not containment_bindings_match(fetch(account, token, f"versions/{VERSION}"), VERSION):
        raise ValueError("serving_pin")
    prior = worker_readback(account, token)
    phases["projection"] = "checking"
    body = projection(prior)
    snapshot = unaffected(prior)
    phases["projection"] = "ready"
    if serving_deployment(fetch(account, token, DEPLOYMENTS)) != before:
        raise ValueError("serving_pin")
    phases["serving_pin"] = "before_match"
    mode = "unchanged" if effective_api_settings(prior, SCRIPT) else "applied"
    if mode == "applied":
        phases["patch"] = "attempted"
        response = patch_worker(account, token, prior["id"], body)
        if response.get("id") != prior["id"] or response.get("name") != SCRIPT:
            raise ValueError("patch")
        phases["patch"] = "accepted"
    else:
        phases["patch"] = "not_needed"
    phases["readback"] = "checking"
    current = worker_readback(account, token)
    if not effective_api_settings(current, SCRIPT) or current.get("id") != prior["id"]:
        raise ValueError("readback")
    # Capture policy may be normalized by the provider but cannot drop preserved
    # optional preferences or redaction settings from the submitted object.
    if current.get("observability") != body["observability"]:
        raise ValueError("readback")
    phases["readback"] = "explicit_off"
    phases["unchanged_state"] = "checking"
    if unaffected(current) != snapshot:
        raise ValueError("unchanged_state")
    phases["unchanged_state"] = "match"
    phases["serving_pin"] = "checking_after"
    if (not containment_bindings_match(fetch(account, token, f"versions/{VERSION}"), VERSION)
            or serving_deployment(fetch(account, token, DEPLOYMENTS)) != before):
        raise ValueError("serving_pin")
    phases["serving_pin"] = "match"
    return mode


def main() -> int:
    """Accept only a first-attempt exact staging dispatch under an external freeze."""
    phases = dict.fromkeys(PHASES, "skipped")
    try:
        account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
        token = os.getenv("CLOUDFLARE_API_TOKEN", "")
        if (os.getenv("AMAIL_CURRENT_WORKER_CONFIRM") != CONFIRM
                or os.getenv("AMAIL_CURRENT_WORKER_FREEZE") != FREEZE
                or os.getenv("GITHUB_RUN_ATTEMPT") != "1"
                or os.getenv("GITHUB_EVENT_NAME") != "workflow_dispatch"
                or os.getenv("GITHUB_REF") != "refs/heads/codex/amail-v0.1.0"
                or not re.fullmatch(r"[0-9a-f]{40}", os.getenv("GITHUB_SHA", ""))
                or not re.fullmatch(r"[0-9a-f]{32}", account) or not token):
            raise ValueError("input")
        mode = apply(account, token, os.getenv("AMAIL_EXPECTED_WORKER_VERSION", ""), phases)
    except Exception:
        # Exception strings/chained transport errors may contain secrets or URLs.
        # A fixed aggregate plus completed/attempted phase bins is sufficient.
        print("staging_current_worker_capture_off=UNVERIFIED")
        print("staging_current_worker_capture_phases=" + " ".join(
            f"{key}:{phases[key]}" for key in PHASES))
        return 1
    print(f"staging_current_worker_capture_off={mode}")
    print("staging_current_worker_capture_phases=" + " ".join(
        f"{key}:{phases[key]}" for key in PHASES))
    print(f"staging_current_worker_capture_attestation=current-worker-v1 version={VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
