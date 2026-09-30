"""Correct only the reviewed staging API's non-versioned capture settings.

The one-shot boundary preserves serving code/bindings and never provisions a
Queue. A successful settings attestation is not a retained-record privacy pass.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
import tomllib
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).parent))
from pin_staging_mail import API, CONFIG, LIMIT, SCRIPT, bindings_match, serving_deployment
sys.path.insert(0, str(CONFIG.parent))
from check_observability import effective_api_settings, safe_observability

VERSION = "c3f6401a-1e84-4f51-91df-ae77d90683e9"
CONFIRM = "APPLY_STAGING_API_CAPTURE_OFF_SETTINGS"
POLICY = {
    "enabled": False, "head_sampling_rate": 1.0, "redact_query_string": True,
    "logs": {"enabled": False, "invocation_logs": False},
    "traces": {"enabled": False}, "issues": {"enabled": False},
}


class NoRedirect(HTTPRedirectHandler):
    """Never forward the deployment credential to a redirected endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Reject every redirect, including same-host redirects, without output."""
        return None


def source_policy() -> dict:
    """Extract only the exact reviewed object, never bindings or runtime source."""
    with CONFIG.open("rb") as source:
        stage = tomllib.load(source)["env"]["staging"]
    value = stage.get("observability")
    if stage.get("name") != SCRIPT or not safe_observability(value) or value != POLICY:
        raise ValueError("source_unverified")
    return copy.deepcopy(value)


def request_result(request: Request) -> dict:
    """Read one bounded provider object with no redirects, retries or raw errors."""
    try:
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            raw = response.read(LIMIT + 1)
            if response.status != 200 or len(raw) > LIMIT:
                raise ValueError("api_unverified")
        payload = json.loads(raw)
    except (HTTPError, URLError, TimeoutError, ValueError, UnicodeDecodeError) as error:
        raise ValueError("api_unverified") from error
    if (not isinstance(payload, dict) or payload.get("success") is not True
            or not isinstance(payload.get("result"), dict)):
        raise ValueError("api_unverified")
    return payload["result"]


def fetch(account: str, token: str, suffix: str) -> dict:
    """Read only fixed reviewed script resources; callers do not accept a URL."""
    return request_result(Request(
        f"{API}/accounts/{account}/workers/scripts/{SCRIPT}/{suffix}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}))


def worker_readback(account: str, token: str) -> dict:
    """Read the exact current Worker resource, never listing or preview settings."""
    return request_result(Request(
        f"{API}/accounts/{account}/workers/workers/{SCRIPT}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}))


def relax_issues(value: dict) -> dict:
    """Check the pre-correction boundary without asserting Issues is already off.

    Only the independent Issues switch may be absent, null, or enabled. All
    other positive capture/export premises must already pass the shared gate.
    This local synthetic normalization is never returned as provider evidence.
    """
    result = copy.deepcopy(value)
    obs = result.get("observability")
    if obs is None:
        return result
    if not isinstance(obs, dict):
        raise ValueError("preflight_unverified")
    issues = obs.get("issues")
    if issues is not None:
        if (not isinstance(issues, dict) or set(issues) - {"enabled"}
                or (issues.get("enabled") is not None
                    and type(issues["enabled"]) is not bool)):
            raise ValueError("preflight_unverified")
    obs["issues"] = {"enabled": False}
    return result


def unaffected(value: dict) -> tuple:
    """Keep typed non-observability settings privately with absence distinctions."""
    tags = value.get("tags")
    if tags is not None and not (
            isinstance(tags, list) and len(tags) <= 100
            and all(isinstance(tag, str) and len(tag) <= 256 for tag in tags)):
        raise ValueError("preflight_unverified")
    return tuple((key, key in value, copy.deepcopy(value.get(key))) for key in
                 ("tags", "logpush", "tail_consumers", "streaming_tail_consumers"))


def settings(account: str, token: str) -> tuple[dict, dict, dict]:
    """Read exact Worker identity and both legacy settings, never preview config."""
    legacy = fetch(account, token, "settings")
    nonversioned = fetch(account, token, "script-settings")
    worker = worker_readback(account, token)
    return worker, legacy, nonversioned


def patch_policy(account: str, token: str, policy: dict) -> None:
    """Issue exactly one bounded JSON script-level PATCH; do not retry ambiguity."""
    request = Request(
        f"{API}/accounts/{account}/workers/scripts/{SCRIPT}/script-settings",
        data=json.dumps({"observability": policy}, separators=(",", ":")).encode(),
        method="PATCH", headers={"Authorization": f"Bearer {token}",
                                  "Accept": "application/json",
                                  "Content-Type": "application/json"},
    )
    request_result(request)


def apply(account: str, token: str, expected: str) -> str:
    """Apply or positively reconcile this one-shot capture correction.

    The returned mode is fixed. No marker is emitted here; the CLI does so only
    after the entire guarded transaction succeeds. Settings are non-versioned,
    so the operator freeze is still required despite deployment brackets.
    """
    if expected != VERSION:
        raise ValueError("input_unverified")
    policy = source_policy()
    before = serving_deployment(fetch(account, token, "deployments?per_page=1&page=1"))
    if before is None or before[1] != expected:
        raise ValueError("deployment_unverified")
    version = fetch(account, token, f"versions/{expected}")
    if not bindings_match(version, expected):
        raise ValueError("bindings_unverified")
    prior = settings(account, token)
    if not effective_api_settings(relax_issues(prior[0]), SCRIPT,
                                  relax_issues(prior[1]), relax_issues(prior[2])):
        raise ValueError("preflight_unverified")
    projections = tuple(unaffected(x) for x in prior)
    if serving_deployment(fetch(account, token, "deployments?per_page=1&page=1")) != before:
        raise ValueError("deployment_changed")
    mode = "unchanged" if effective_api_settings(prior[0], SCRIPT, *prior[1:]) else "applied"
    if mode == "applied":
        patch_policy(account, token, policy)
    current = settings(account, token)
    if (not effective_api_settings(current[0], SCRIPT, *current[1:])
            or current[0]["id"] != prior[0]["id"]):
        raise ValueError("readback_unverified")
    if tuple(unaffected(x) for x in current) != projections:
        raise ValueError("unaffected_changed")
    if not bindings_match(fetch(account, token, f"versions/{expected}"), expected):
        raise ValueError("bindings_unverified")
    if serving_deployment(fetch(account, token, "deployments?per_page=1&page=1")) != before:
        raise ValueError("deployment_changed")
    return mode


def main() -> int:
    """Accept only the exact first-attempt hosted staging settings dispatch."""
    try:
        account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
        token = os.getenv("CLOUDFLARE_API_TOKEN", "")
        expected = os.getenv("AMAIL_EXPECTED_WORKER_VERSION", "")
        if (os.getenv("AMAIL_CONTAINMENT_CONFIRM") != CONFIRM
                or os.getenv("GITHUB_RUN_ATTEMPT") != "1"
                or os.getenv("GITHUB_EVENT_NAME") != "workflow_dispatch"
                or os.getenv("GITHUB_REF") != "refs/heads/codex/amail-v0.1.0"
                or not re.fullmatch(r"[0-9a-f]{40}", os.getenv("GITHUB_SHA", ""))
                or not re.fullmatch(r"[0-9a-f]{32}", account) or not token):
            raise ValueError("input_unverified")
        mode = apply(account, token, expected)
    except (ValueError, KeyError, TypeError, OSError):
        print("staging_api_capture_off=UNVERIFIED")
        return 1
    print(f"staging_api_capture_off={mode}")
    print(f"staging_api_capture_off_attestation=settings-v1 version={VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
