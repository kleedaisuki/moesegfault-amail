"""Pin the currently serving staging Mail Worker using read-only Cloudflare APIs.

This probe deliberately emits only fixed labels. It never prints settings, bindings,
tokens, account identifiers, or an unexpected version ID.
"""

from __future__ import annotations

import json
import argparse
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
PHASES = ("pre-queue", "queue-api")


def mail_resources(stage: dict) -> tuple[str, str]:
    """Require the sole reviewed Mail database and body bucket by binding name.

    Direct-only Mail cannot acquire a role database through config drift. Never
    use array position as a resource identity: duplicate, renamed or additional
    entries fail closed before provider access.
    """
    databases = stage.get("d1_databases")
    buckets = stage.get("r2_buckets")
    if (not isinstance(databases, list) or len(databases) != 1
            or not isinstance(databases[0], dict) or databases[0].get("binding") != "MAIL_DB"
            or not isinstance(buckets, list) or len(buckets) != 1
            or not isinstance(buckets[0], dict) or buckets[0].get("binding") != "MAIL_BODIES"):
        raise ValueError("mail_resources_unreviewed")
    database, bucket = databases[0].get("database_id"), buckets[0].get("bucket_name")
    if (not isinstance(database, str) or UUID.fullmatch(database) is None
            or not isinstance(bucket, str) or not bucket):
        raise ValueError("mail_resources_unreviewed")
    return database, bucket


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
    if suffix.startswith("versions/"):
        import ensure_trace_queues as queues
        resources = result.get("resources")
        bindings = resources.get("bindings") if isinstance(resources, dict) else None
        if isinstance(bindings, dict) and set(bindings) == {"result"}:
            bindings = bindings["result"]
        if isinstance(bindings, list) and any(isinstance(row, dict) and row.get("type") == "queue"
                                             and "queue_name" in row for row in bindings):
            queues.normalize_queue_bindings(result, queues.inventory(account, token))
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


def expected_bindings(phase: str = "pre-queue", queue_id: str = "", *, realm: str = "staging", predecessor: bool = False) -> dict[str, tuple[str, str | None]]:
    """Derive the exact direct-only Mail contract from reviewed realm config."""

    if phase not in PHASES:
        raise ValueError("pin_phase_unreviewed")

    if realm not in ("staging", "production"):
        raise ValueError("pin_realm_unreviewed")
    with CONFIG.open("rb") as source:
        config = tomllib.load(source)
        stage = config["env"]["staging"] if realm == "staging" else config
    database, bucket = mail_resources(stage)
    expected = {
        "MAIL_DB": ("d1", database),
        "MAIL_BODIES": ("r2_bucket", bucket),
        "EMAIL": ("send_email", None),
        "OPENROUTER_API_KEY": ("secret_text", None),
        "CF_EMAIL_ROUTING_TOKEN": ("secret_text", None),
        "INGRESS_SECRET": ("secret_text", None),
        **{name: ("plain_text", value) for name, value in stage["vars"].items()},
    }
    if realm in ("staging", "production"):
        if predecessor:
            for name in ("BILLING_BASE_URL", "BILLING_SUBSCRIBE_ORIGIN", "BILLING_RETURN_URL"):
                expected.pop(name, None)
        else:
            expected["BILLING_SERVICE_KEY"] = ("secret_text", None)
    if realm == "production":
        expected["OFFICIAL_EMAIL"] = ("send_email", None)
    if phase == "queue-api":
        if (ACCOUNT.fullmatch(queue_id) is None or stage.get("queues", {}).get("producers") != [
                {"binding": "TRACE_EVENTS", "queue": "amail-trace-events" + ("-staging" if realm == "staging" else "")}]):
            raise ValueError("queue_pin_unreviewed")
        expected["TRACE_EVENTS"] = ("queue", queue_id)
    return expected


def containment_predecessor_bindings() -> dict[str, tuple[str, str | None]]:
    """Return a fresh frozen c3f staging contract, independent of current TOML.

    Immutable source daaab1f79cd985030d8d502fd647e16757673052 and hosted
    operation 36761367007 established this exact 14-binding pre-write match.
    This is binding provenance only, never privacy acceptance or retry authority.
    See docs/held-staging-mail-promotion-2026-10-01.md. Do not add optional
    bindings or derive this historical policy from provider data/current config.
    """
    return {
        "MAIL_DB": ("d1", "74f35f95-42ce-482c-86e6-dffbdd35cbbe"),
        "ROLE_MONITOR": ("d1", "272e024c-453a-461b-bea0-c37a62c89d24"),
        "MAIL_BODIES": ("r2_bucket", "moesegfault-mail-raw-staging"),
        "EMAIL": ("send_email", None),
        "OPENROUTER_API_KEY": ("secret_text", None),
        "CF_EMAIL_ROUTING_TOKEN": ("secret_text", None),
        "INGRESS_SECRET": ("secret_text", None),
        "ADDRESS_DIAGNOSTICS": ("plain_text", "v1"),
        "IDENTITY_ISSUER": ("plain_text", "https://identity-staging.moesegfault.dev"),
        "OIDC_CLIENT_ID": ("plain_text", "amail-cli-staging"),
        "CF_ZONE_ID": ("plain_text", "6edff81c6ed02f412e70868076411a5e"),
        "MAIL_DOMAIN": ("plain_text", "mail-staging.moesegfault.dev"),
        "EMAIL_INGRESS_WORKER_NAME": ("plain_text", "amail-inbound-staging"),
        "OPENROUTER_EMBEDDING_MODEL": ("plain_text", "qwen/qwen3-embedding-8b"),
    }


CONTAINMENT_PREDECESSOR_VERSION = "c3f6401a-1e84-4f51-91df-ae77d90683e9"


def containment_bindings_match(version: dict, expected_version: str) -> bool:
    """Match only the fixed staging c3f predecessor; never fall back to it."""
    if expected_version != CONTAINMENT_PREDECESSOR_VERSION:
        return False
    return _bindings_match(version, expected_version, containment_predecessor_bindings())


def bindings_match(version: dict, expected_version: str, *, phase: str = "pre-queue",
                   queue_id: str = "", realm: str = "staging", predecessor: bool = False) -> bool:
    """Check the current direct-only contract, without historical fallback."""
    if predecessor and realm == "production" and expected_version != "50bd330d-2f9b-4102-8c8e-9bbaada927fe":
        return False
    expected = (expected_bindings() if phase == "pre-queue" and realm == "staging"
                else expected_bindings(phase, queue_id, realm=realm, predecessor=predecessor))
    return _bindings_match(version, expected_version, expected)


def _bindings_match(version: dict, expected_version: str,
                    expected: dict[str, tuple[str, str | None]]) -> bool:
    """Compare one selected contract with exact version, shape, names and targets."""
    resources = version.get("resources")
    if version.get("id") != expected_version or not isinstance(resources, dict):
        return False
    actual = resources.get("bindings")
    # Cloudflare's version API has used both a direct list and a wrapper with a
    # `result` list across generated SDK schemas. Never treat its `{}` example
    # as an empty binding set or fall back to unversioned /settings.
    if isinstance(actual, dict) and set(actual) == {"result"}:
        actual = actual["result"]
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
        if name == "OFFICIAL_EMAIL" and binding.get("allowed_sender_addresses") != ["mail@moesegfault.dev"]:
            return False
        if kind == "queue" and binding.get("queue_id", binding.get("id")) != value:
            return False
    return seen == set(expected)


def fetch_worker(account: str, token: str) -> dict:
    """Read the current exact-name resource through the shared bounded reader."""
    from check_observability import worker_readback
    return worker_readback(account, token, SCRIPT)


def run(account: str, token: str, expected: str, *, phase: str = "pre-queue",
        queue_id: str = "") -> str:
    """Check serving version twice around settings to detect concurrent rollout."""

    # Validate the selected contract before any provider access. Historical
    # settings-only callers retain the strict pre-Queue default unchanged.
    expected_bindings(phase, queue_id)

    # This function is also called in-process by guarded staging jobs, not only
    # by this file's __main__. The sibling module must be importable in both cases.
    module_dir = str(CONFIG.parent)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)
    from check_observability import effective_api_settings

    first = serving_deployment(fetch(account, token, "deployments?per_page=1&page=1"))
    if first is None:
        return "deployment_unverified"
    if first[1] != expected:
        return "version_mismatch"
    version = fetch(account, token, f"versions/{expected}")
    settings = fetch(account, token, "settings")
    script_settings = fetch(account, token, "script-settings")
    worker = fetch_worker(account, token)
    if not effective_api_settings(worker, SCRIPT, settings, script_settings):
        return "privacy_unverified"
    if not bindings_match(version, expected, phase=phase, queue_id=queue_id):
        return "bindings_mismatch"
    from check_mail_maintenance import api_config, entry_surface_match, schedules_match
    api_config("staging")
    if not entry_surface_match(version, expected, "fetch"):
        return "entry_surface_mismatch"
    if not schedules_match(fetch(account, token, "schedules")):
        return "schedule_mismatch"
    second = serving_deployment(fetch(account, token, "deployments?per_page=1&page=1"))
    return "match" if second == first else "deployment_changed"


def main() -> int:
    """Print one fixed result and fail closed without exposing Cloudflare data."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=PHASES, default="pre-queue")
    args = parser.parse_args()
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    expected = os.environ.get("AMAIL_EXPECTED_WORKER_VERSION", "")
    if not ACCOUNT.fullmatch(account) or not token or not UUID.fullmatch(expected):
        result = "invalid_input"
    else:
        try:
            result = run(account, token, expected, phase=args.phase,
                         queue_id=os.getenv("AMAIL_EXPECTED_TRACE_QUEUE_ID", ""))
        except (ValueError, KeyError, TypeError, OSError):
            result = "unavailable"
    print(f"staging_mail_serving_pin={result}")
    return 0 if result == "match" else 1


if __name__ == "__main__":
    raise SystemExit(main())
