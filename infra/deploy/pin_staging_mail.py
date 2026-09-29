"""Pin the currently serving staging Mail Worker using read-only Cloudflare APIs.

This probe deliberately emits only fixed labels. It never prints settings, bindings,
tokens, account identifiers, or an unexpected version ID.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SCRIPT = "amail-mail-staging"
UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
ACCOUNT = re.compile(r"[0-9a-f]{32}\Z")
CONFIG = Path(__file__).resolve().parents[2] / "crates/mail-worker/wrangler.toml"
API = "https://api.cloudflare.com/client/v4"
LIMIT = 262_144


def fetch(account: str, token: str, suffix: str) -> dict:
    """Read one bounded Cloudflare response without exposing its body on failure."""

    url = f"{API}/accounts/{account}/workers/scripts/{SCRIPT}/{suffix}"
    request = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read(LIMIT + 1)
    except (HTTPError, URLError, TimeoutError) as error:
        raise ValueError("api_unavailable") from error
    if len(raw) > LIMIT:
        raise ValueError("api_unavailable")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError("api_unavailable") from error
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("api_unavailable")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("api_unavailable")
    return result


def serving_deployment(result: dict) -> tuple[str, str] | None:
    """Use the first active deployment, rejecting split traffic or missing IDs."""

    deployments = result.get("deployments")
    if not isinstance(deployments, list) or not deployments:
        return None
    latest = deployments[0]
    if not isinstance(latest, dict) or latest.get("strategy") != "percentage":
        return None
    deployment_id = latest.get("id")
    if not isinstance(deployment_id, str) or not UUID.fullmatch(deployment_id):
        return None
    versions = latest.get("versions")
    if not isinstance(versions, list) or len(versions) != 1:
        return None
    version = versions[0]
    if not isinstance(version, dict) or type(version.get("percentage")) not in (int, float):
        return None
    version_id = version.get("version_id")
    if version.get("percentage") != 100 or not isinstance(version_id, str) or not UUID.fullmatch(version_id):
        return None
    return deployment_id, version_id


def expected_bindings() -> dict[str, tuple[str, str | None]]:
    """Derive staging resource values from reviewed config, not copied IDs."""

    with CONFIG.open("rb") as source:
        stage = tomllib.load(source)["env"]["staging"]
    return {
        "MAIL_DB": ("d1", stage["d1_databases"][0]["database_id"]),
        "ROLE_MONITOR": ("d1", stage["d1_databases"][1]["database_id"]),
        "MAIL_BODIES": ("r2_bucket", stage["r2_buckets"][0]["bucket_name"]),
        "EMAIL": ("send_email", None),
        "OPENROUTER_API_KEY": ("secret_text", None),
        "CF_EMAIL_ROUTING_TOKEN": ("secret_text", None),
        "INGRESS_SECRET": ("secret_text", None),
        **{name: ("plain_text", value) for name, value in stage["vars"].items()},
    }


def bindings_match(version: dict, expected_version: str) -> bool:
    """Check exact resource bindings on the identified serving version."""

    resources = version.get("resources")
    if version.get("id") != expected_version or not isinstance(resources, dict):
        return False
    actual = resources.get("bindings")
    expected = expected_bindings()
    if not isinstance(actual, list) or len(actual) != len(expected):
        return False
    seen: set[str] = set()
    for binding in actual:
        if not isinstance(binding, dict):
            return False
        name = binding.get("name")
        if not isinstance(name, str) or name in seen or name not in expected:
            return False
        seen.add(name)
        kind, value = expected[name]
        if binding.get("type") != kind:
            return False
        if kind == "d1" and binding.get("database_id") != value:
            return False
        if kind == "r2_bucket" and binding.get("bucket_name") != value:
            return False
        if kind == "plain_text" and binding.get("text") != value:
            return False
        if kind == "send_email" and binding.get("destination_address") is not None:
            return False
    return seen == set(expected)


def run(account: str, token: str, expected: str) -> str:
    """Check serving version twice around settings to detect concurrent rollout."""

    from check_observability import safe_settings  # Imported after test path setup.

    first = serving_deployment(fetch(account, token, "deployments?per_page=1&page=1"))
    if first is None:
        return "deployment_unverified"
    if first[1] != expected:
        return "version_mismatch"
    version = fetch(account, token, f"versions/{expected}")
    settings = fetch(account, token, "settings")
    script_settings = fetch(account, token, "script-settings")
    if not safe_settings(settings) or not safe_settings(script_settings):
        return "privacy_unverified"
    if not bindings_match(version, expected):
        return "bindings_mismatch"
    second = serving_deployment(fetch(account, token, "deployments?per_page=1&page=1"))
    return "match" if second == first else "deployment_changed"


def main() -> int:
    """Print one fixed result and fail closed without exposing Cloudflare data."""

    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    expected = os.environ.get("AMAIL_EXPECTED_WORKER_VERSION", "")
    if not ACCOUNT.fullmatch(account) or not token or not UUID.fullmatch(expected):
        result = "invalid_input"
    else:
        try:
            result = run(account, token, expected)
        except (ValueError, KeyError, TypeError, OSError):
            result = "unavailable"
    print(f"staging_mail_serving_pin={result}")
    return 0 if result == "match" else 1


if __name__ == "__main__":
    sys.path.insert(0, str(CONFIG.parent))
    raise SystemExit(main())
