"""Read provider permissions and role destination without exposing either secret.

This is a one-run, staging-only discriminator for the first role SMTP timeout.
It does not repair routing, send mail, or infer historical Cron execution.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/provider"))
sys.path.insert(0, str(ROOT / "workers/role-monitor"))
import ensure_role_forwarding as forwarding
import hosted_acceptance as hosted
import staging_route


RUN = "36603362864"
CONFIRM = "READ_FIRST_ROLE_TOKEN_PERMISSIONS"
ZONE = forwarding.ZONE
MAX_REPLY = forwarding.MAX_REPLY


class ProbeError(Exception):
    """Carry one fixed, public-safe provider outcome."""


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    """Never send the routing bearer to a redirected URL."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        """Reject all redirect targets, including same-origin redirects."""

        return None


_NO_REDIRECT = urllib.request.build_opener(RejectRedirect)


class Client:
    """Supply only bounded, non-redirecting GETs to the shared paginator."""

    def __init__(self, token: str):
        """Retain the exact deployed routing token in memory only."""

        self.token = token

    def request(self, method: str, path: str, body: object = None) -> dict:
        """Return a successful JSON envelope, or a fixed error category."""

        if method != "GET" or body is not None or not path.startswith((
            "/accounts/", "/zones/",
        )):
            raise ProbeError("invalid_request")
        request = urllib.request.Request(
            forwarding.API + path,
            headers={"Authorization": "Bearer " + self.token, "Accept": "application/json"},
            method="GET",
        )
        try:
            with _NO_REDIRECT.open(request, timeout=25) as response:
                status, raw = response.status, response.read(MAX_REPLY + 1)
        except urllib.error.HTTPError as error:
            if error.code == 403:
                raise ProbeError("forbidden") from None
            if error.code == 401:
                raise ProbeError("unauthorized") from None
            if 300 <= error.code < 400:
                raise ProbeError("redirect") from None
            raise ProbeError("unavailable") from None
        except (urllib.error.URLError, TimeoutError):
            raise ProbeError("unavailable") from None
        if status != 200 or len(raw) > MAX_REPLY:
            raise ProbeError("unavailable")
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise ProbeError("invalid_response") from None
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise ProbeError("invalid_response")
        return payload


def inventory(client: Client, path: str) -> tuple[list[dict], str]:
    """Require complete bounded pagination before treating a read as accessible."""

    try:
        return forwarding.pages(client, path), "accessible"
    except ProbeError as error:
        return [], str(error)
    except forwarding.ProvisionError:
        return [], "invalid_response"


def destination_state(addresses: list[dict], destination: str) -> str:
    """Classify exactly one provider-verified private destination."""

    matches = [item for item in addresses if item.get("email") == destination]
    if not matches:
        return "missing"
    if len(matches) != 1:
        return "duplicate"
    verified = matches[0].get("verified")
    if verified is None:
        return "pending"
    if isinstance(verified, str) and bool(verified):
        return "verified"
    return "invalid"


def rule_state(rules: list[dict], destination: str) -> str:
    """Check all four standard forwards without publishing their target."""

    try:
        present = forwarding.audit(rules, destination)
    except forwarding.ProvisionError:
        return "contract_mismatch"
    return "four_direct" if present == set(forwarding.ROLES) else "incomplete"


def route_state(rules: list[dict]) -> str:
    """Require that the disposable SMTP route stayed absent."""

    try:
        return "present" if any(staging_route.touches_alias(rule) for rule in rules) else "absent"
    except (AttributeError, TypeError, ValueError):
        return "invalid"


def version_state(account: str, token: str, expected: str) -> str:
    """Compare the current 100%-serving staging version to a private pin."""

    try:
        actual, _ = hosted.active_version(account, token)
        return "match" if actual == expected else "drift"
    except Exception:
        return "unavailable"


def main() -> int:
    """Check exact historical coordinates and print only fixed status labels."""

    if sys.argv[1:] != [CONFIRM, RUN]:
        print("role_token_probe=coordinates_invalid")
        return 1
    token = os.environ.get("CF_EMAIL_ROUTING_TOKEN", "")
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    zone = os.environ.get("CF_ZONE_ID", "")
    destination = os.environ.get("ROLE_FORWARD_DESTINATION", "")
    expected_version = os.environ.get("AMAIL_STAGING_ROLE_VERSION", "").lower()
    if (
        not token or not api_token or not re.fullmatch(r"[0-9a-f]{32}", account)
        or zone != ZONE or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", destination)
        or not hosted.valid_uuid(expected_version)
    ):
        print("role_token_probe=configuration_invalid")
        return 1
    client = Client(token)
    addresses, address_access = inventory(client, f"/accounts/{account}/email/routing/addresses")
    rules, rule_access = inventory(client, f"/zones/{zone}/email/routing/rules")
    destination_result = destination_state(addresses, destination) if address_access == "accessible" else "not_checked"
    rules_result = rule_state(rules, destination) if rule_access == "accessible" else "not_checked"
    route_result = route_state(rules) if rule_access == "accessible" else "not_checked"
    version_result = version_state(account, api_token, expected_version)
    print(f"role_token_addresses={address_access}")
    print(f"role_token_rules={rule_access}")
    print(f"role_token_destination={destination_result}")
    print(f"role_token_standard_rules={rules_result}")
    print(f"role_token_disposable_route={route_result}")
    print(f"role_token_worker_version={version_result}")
    good = (address_access, rule_access, destination_result, rules_result, route_result, version_result) == (
        "accessible", "accessible", "verified", "four_direct", "absent", "match",
    )
    print("role_token_probe=" + ("read_only_pass" if good else "inconclusive"))
    return 0 if good else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # A library exception may contain provider data; emit no traceback.
        print("role_token_probe=unexpected_failure")
        raise SystemExit(1) from None
