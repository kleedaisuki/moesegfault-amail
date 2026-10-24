"""Onboard only the isolated temporary-mail staging domain through provider APIs.

Read-only by default. Run --apply inside the admitted staging writer after restoring
its checked artifact. Existing DNS is never overwritten or deleted; an uncertain
mutation is never retried. No production domain is accepted as an argument.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
import re
import sys
from typing import Any, Protocol
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.cloudflare.com/client/v4"
ZONE = "6edff81c6ed02f412e70868076411a5e"
DOMAIN = "tmpaddr-staging.moesegfault.dev"
PREFIX = f"/zones/{ZONE}"
MAX_REPLY = 512_000


class ProvisionError(Exception):
    """A closed diagnostic code safe for public Actions logs."""


class Provider(Protocol):
    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Client:
    token: str

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        request = urllib.request.Request(
            API + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                raw = response.read(MAX_REPLY + 1)
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise ProvisionError("permission_or_provider_rejection") from None
            code = "provider_rejected" if method == "GET" or error.code in (400, 404, 409, 422) else "mutation_unknown_inspect_before_retry"
            raise ProvisionError(code) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ProvisionError("read_unavailable" if method == "GET" else "mutation_unknown_inspect_before_retry") from None
        if len(raw) > MAX_REPLY:
            raise ProvisionError("response_too_large")
        try:
            payload: Any = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise ProvisionError("response_invalid") from None
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise ProvisionError("provider_rejected")
        return payload


def rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result")
    if not isinstance(result, list) or not all(isinstance(row, dict) for row in result):
        raise ProvisionError("inventory_invalid")
    return result


def inventory(client: Provider, path: str) -> list[dict[str, Any]]:
    """Require a complete inventory before treating a domain/record as absent."""
    result: list[dict[str, Any]] = []
    for page in range(1, 101):
        separator = "&" if "?" in path else "?"
        payload = client.request("GET", f"{path}{separator}per_page=50&page={page}")
        batch = rows(payload)
        info = payload.get("result_info")
        if not isinstance(info, dict):
            # Sending subdomain lists are bounded by the documented 30-domain cap.
            if path.endswith("/email/sending/subdomains") and page == 1 and len(batch) <= 30:
                return batch
            raise ProvisionError("inventory_pagination_invalid")
        if info.get("page") != page or info.get("count") != len(batch):
            raise ProvisionError("inventory_pagination_invalid")
        total = info.get("total_count")
        if type(total) is not int or total < len(result) + len(batch):
            raise ProvisionError("inventory_pagination_invalid")
        result.extend(batch)
        if len(result) == total:
            return result
        if not batch:
            raise ProvisionError("inventory_incomplete")
    raise ProvisionError("inventory_incomplete")


def dns_records(client: Provider, name: str) -> list[dict[str, Any]]:
    if name != DOMAIN and not name.endswith("." + DOMAIN):
        raise ProvisionError("dns_outside_staging")
    query = urllib.parse.urlencode({"name": name})
    result = inventory(client, f"{PREFIX}/dns_records?{query}")
    if any(str(row.get("name", "")).lower().rstrip(".") != name for row in result):
        raise ProvisionError("dns_filter_mismatch")
    return result


def routing_ready(records: list[dict[str, Any]]) -> bool:
    mx = [row for row in records if row.get("type") == "MX"]
    if any(not str(row.get("content", "")).lower().rstrip(".").endswith(".mx.cloudflare.net") for row in mx):
        raise ProvisionError("routing_existing_mx_conflict")
    spf = [str(row.get("content", "")).strip('"') for row in records if row.get("type") == "TXT" and str(row.get("content", "")).strip('"').startswith("v=spf1")]
    if len(spf) > 1 or any("include:_spf.mx.cloudflare.net" not in value.split() for value in spf):
        raise ProvisionError("routing_existing_spf_conflict")
    return bool(mx and spf)


def ensure_routing(dns: Provider, routing: Provider, apply: bool) -> None:
    before = dns_records(dns, DOMAIN)
    if routing_ready(before):
        return
    if not apply:
        raise ProvisionError("routing_onboarding_required")
    # Cloudflare owns the MX/SPF values; never synthesize them from another domain.
    payload = routing.request("POST", f"{PREFIX}/email/routing/dns", {"name": DOMAIN})
    result = payload.get("result")
    if not isinstance(result, dict) or result.get("name") != DOMAIN or result.get("enabled") is not True:
        raise ProvisionError("routing_submit_not_verified")
    if not routing_ready(dns_records(dns, DOMAIN)):
        raise ProvisionError("routing_dns_not_ready")


def sending_domain(client: Provider, apply: bool) -> dict[str, Any]:
    path = f"{PREFIX}/email/sending/subdomains"
    matches = [row for row in inventory(client, path) if row.get("name") == DOMAIN]
    if len(matches) > 1:
        raise ProvisionError("sending_domain_ambiguous")
    if not matches or matches[0].get("enabled") is not True:
        if not apply:
            raise ProvisionError("sending_onboarding_required")
        value = client.request("POST", path, {"name": DOMAIN}).get("result")
    else:
        value = matches[0]
    if not isinstance(value, dict) or value.get("name") != DOMAIN or value.get("enabled") is not True or not re.fullmatch(r"[0-9a-f]{32}", str(value.get("tag", ""))):
        raise ProvisionError("sending_domain_not_verified")
    return value


def normalized_record(value: dict[str, Any]) -> dict[str, Any]:
    name = str(value.get("name", "")).lower().rstrip(".")
    if name != DOMAIN and not name.endswith("." + DOMAIN):
        raise ProvisionError("dns_outside_staging")
    kind = value.get("type")
    content = value.get("content")
    if kind not in ("MX", "TXT", "CNAME") or not isinstance(content, str) or not content:
        raise ProvisionError("dns_requirement_invalid")
    content = content.lower().rstrip(".") if kind in ("MX", "CNAME") else content.strip('"')
    result: dict[str, Any] = {"name": name, "type": kind, "content": content}
    if kind == "MX":
        priority = value.get("priority")
        if type(priority) is not int or not 0 <= priority <= 65535:
            raise ProvisionError("dns_requirement_invalid")
        result["priority"] = priority
    return result


def ensure_sending(client: Provider, apply: bool) -> None:
    domain = sending_domain(client, apply)
    path = f"{PREFIX}/email/sending/subdomains/{domain['tag']}"
    if domain.get("preview_enabled") is not False or domain.get("drop_suppressed_recipients") is not False:
        if not apply:
            raise ProvisionError("sending_privacy_required")
        client.request("PATCH", path, {"preview_enabled": False, "drop_suppressed_recipients": False})
    wanted = [normalized_record(row) for row in rows(client.request("GET", path + "/dns"))]
    if not wanted:
        raise ProvisionError("sending_dns_requirements_missing")
    for record in wanted:
        current = dns_records(client, record["name"])
        existing = [normalized_record(row) for row in current if row.get("type") in ("MX", "TXT", "CNAME")]
        if record in existing:
            continue
        if any((row["type"] == record["type"] and row not in wanted) or row["type"] == "CNAME" or record["type"] == "CNAME" for row in existing) or (record["type"] == "CNAME" and current):
            raise ProvisionError("sending_existing_dns_conflict")
        if not apply:
            raise ProvisionError("sending_dns_required")
        client.request("POST", f"{PREFIX}/dns_records", {**record, "ttl": 1, "proxied": False})
        after = [normalized_record(row) for row in dns_records(client, record["name"]) if row.get("type") in ("MX", "TXT", "CNAME")]
        if record not in after:
            raise ProvisionError("sending_dns_not_verified")
    after = client.request("GET", path).get("result")
    if not isinstance(after, dict) or after.get("name") != DOMAIN or after.get("enabled") is not True or after.get("preview_enabled") is not False or after.get("drop_suppressed_recipients") is not False:
        raise ProvisionError("sending_privacy_not_verified")


def authorize_apply(environment: dict[str, str]) -> None:
    required = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF": "refs/heads/codex/v0.3.0-multitenant",
        "AMAIL_STAGING_CONFIRM": "RUN_STAGING_V030",
        "AMAIL_STAGING_ENVIRONMENT": "staging",
        "GITHUB_RUN_ATTEMPT": "1",
    }
    if any(environment.get(key) != value for key, value in required.items()):
        raise ProvisionError("staging_writer_required")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        if args.apply:
            authorize_apply(dict(os.environ))
        token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
        routing_token = os.environ.get("CF_EMAIL_ROUTING_TOKEN", "")
        if not token or not routing_token:
            raise ProvisionError("credentials_required")
        client = Client(token)
        ensure_routing(client, Client(routing_token), args.apply)
        ensure_sending(client, args.apply)
    except ProvisionError as error:
        print(f"tmpaddr_staging={error}", file=sys.stderr)
        return 1
    print("tmpaddr_staging=provider_config_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
