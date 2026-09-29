"""Inspect a staging routing token's configured zone Write grant without mutation.

Only token verification and token-detail GETs are used. Run this on GitHub-hosted
infrastructure with the existing routing secret and a separate API Tokens Read
credential; never print either credential or returned token metadata.
"""

from __future__ import annotations

import os
import re
import sys

from probe_routing import _codes, _request


TAG = re.compile(r"[0-9a-fA-F]{32}\Z")
WRITE_NAMES = frozenset(("Email Routing Rules Write", "Email Routing Rules Edit"))


def _covers(resources: object, account: str, zone: str) -> bool | None:
    """Check documented zone selectors; unknown resource shapes stay inconclusive."""

    if not isinstance(resources, dict):
        return None
    direct = (f"com.cloudflare.api.account.zone.{zone}", "com.cloudflare.api.account.zone.*")
    for key in direct:
        if key in resources:
            return resources[key] == "*" if isinstance(resources[key], str) else None
    nested = resources.get(f"com.cloudflare.api.account.{account}")
    if isinstance(nested, dict):
        value = nested.get("com.cloudflare.api.account.zone.*")
        return value == "*" if value is not None else False
    if nested is not None:
        return None
    return False


def _write_policy(result: dict, account: str, zone: str) -> str:
    """Classify a complete policy list, honoring explicit deny before allow."""

    policies = result.get("policies")
    if not isinstance(policies, list):
        return "unknown"
    allow = False
    unknown = False
    for policy in policies:
        if not isinstance(policy, dict):
            unknown = True
            continue
        groups = policy.get("permission_groups")
        if not isinstance(groups, list):
            unknown = True
            continue
        names = [group.get("name") for group in groups if isinstance(group, dict)]
        if any(not isinstance(group, dict) for group in groups):
            unknown = True
        if not any(name in WRITE_NAMES for name in names):
            # A permission ID without a returned name cannot be interpreted safely.
            if any(name is None for name in names):
                unknown = True
            continue
        covers = _covers(policy.get("resources"), account, zone)
        if covers is None:
            unknown = True
            continue
        if not covers:
            continue
        if policy.get("effect") == "deny":
            return "explicit_deny"
        if policy.get("effect") == "allow":
            allow = True
        else:
            unknown = True
    if unknown:
        return "unknown"
    return "configured_grant" if allow else "no_grant"


def _verify(token: str, account: str) -> tuple[str, str]:
    """Return the opaque token ID only in memory, never in the diagnostic."""

    for kind, path in (
        ("user", "/user/tokens/verify"),
        ("account", f"/accounts/{account}/tokens/verify"),
    ):
        status, payload = _request(path, token)
        result = payload.get("result")
        if status == 200 and payload.get("success") is True and isinstance(result, dict):
            token_id = result.get("id")
            state = result.get("status")
            if isinstance(token_id, str) and TAG.fullmatch(token_id) and state == "active":
                return kind, token_id
            if state in ("disabled", "expired"):
                return state, ""
    return "unconfirmed", ""


def main() -> int:
    """Print a fixed, redacted policy outcome; never assert effective API access."""

    zone = os.environ.get("CF_ZONE_ID", "")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    routing = os.environ.get("CF_EMAIL_ROUTING_TOKEN", "")
    reader = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not TAG.fullmatch(zone) or not TAG.fullmatch(account) or not routing or not reader:
        print("routing_write_check=invalid_input", file=sys.stderr)
        return 2
    kind, token_id = _verify(routing, account)
    if not token_id:
        print(f"routing_write_check=unavailable verify={kind}")
        return 1
    path = (f"/user/tokens/{token_id}" if kind == "user"
            else f"/accounts/{account}/tokens/{token_id}")
    status, payload = _request(path, reader)
    result = payload.get("result")
    if status != 200 or payload.get("success") is not True or not isinstance(result, dict):
        print(f"routing_write_check=unavailable detail_http={status} codes={_codes(payload)}")
        return 1
    if result.get("id") != token_id:
        print("routing_write_check=unavailable detail_mismatch")
        return 1
    if result.get("status") != "active":
        print("routing_write_check=unavailable detail_inactive")
        return 1
    outcome = _write_policy(result, account, zone)
    print(f"routing_write_check={outcome} scope=configured_policy_only")
    return 0 if outcome in ("configured_grant", "no_grant", "explicit_deny") else 1


if __name__ == "__main__":
    raise SystemExit(main())
