"""Onboard only the isolated temporary-mail staging domain through provider APIs.

Read-only by default. Run --apply inside the admitted staging writer after restoring
its checked artifact. Existing DNS is never overwritten or deleted; an uncertain
mutation is never retried. No production domain is accepted as an argument.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import hashlib
import os
from pathlib import Path
import re
import sys
from typing import Any, Literal, Protocol
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.cloudflare.com/client/v4"
ZONE = "6edff81c6ed02f412e70868076411a5e"
DOMAIN = "tmpaddr-staging.moesegfault.dev"
PREFIX = f"/zones/{ZONE}"
MAX_REPLY = 512_000
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/dns"))
from txt_record import txt_content


class ProvisionError(Exception):
    """A closed diagnostic code safe for public Actions logs."""


def endpoint_alias(path: str) -> str:
    """Project provider coordinates onto a closed, non-content diagnostic set."""
    endpoint = urllib.parse.urlsplit(path).path
    if endpoint == PREFIX + "/dns_records":
        return "dns_records"
    if endpoint == PREFIX + "/email/routing/dns":
        return "routing_dns"
    if endpoint == PREFIX + "/email/routing":
        return "routing_settings"
    sending = PREFIX + "/email/sending/subdomains"
    if endpoint == sending:
        return "sending_domains"
    if re.fullmatch(re.escape(sending) + r"/[0-9a-f]{32}/dns", endpoint):
        return "sending_dns"
    if re.fullmatch(re.escape(sending) + r"/[0-9a-f]{32}", endpoint):
        return "sending_domain"
    return "other"


class ProviderError(ProvisionError):
    def __init__(self, code: str, method: str, path: str, role: str, status: int = 0) -> None:
        self.details: dict[str, str | int] = {
            "code": code,
            "phase": endpoint_alias(path),
            "method": method if method in ("GET", "POST", "PATCH") else "other",
            "http": status if 100 <= status <= 599 else 0,
            "credential": role if role in ("deployment", "routing") else "other",
        }
        super().__init__(" ".join(f"{key}={value}" for key, value in self.details.items()))


class Provider(Protocol):
    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Client:
    token: str = field(repr=False)
    role: Literal["deployment", "routing"] = "deployment"

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        request = urllib.request.Request(
            API + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                status = response.status
                raw = response.read(MAX_REPLY + 1)
        except urllib.error.HTTPError as error:
            error.close()
            if error.code in (401, 403):
                raise ProviderError("permission_or_provider_rejection", method, path, self.role, error.code) from None
            code = "provider_rejected" if method == "GET" or error.code in (400, 404, 409, 422) else "mutation_unknown_inspect_before_retry"
            raise ProviderError(code, method, path, self.role, error.code) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ProviderError("read_unavailable" if method == "GET" else "mutation_unknown_inspect_before_retry", method, path, self.role) from None
        if len(raw) > MAX_REPLY:
            raise ProviderError("response_too_large", method, path, self.role, status)
        try:
            payload: Any = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise ProviderError("response_invalid", method, path, self.role, status) from None
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise ProviderError("provider_rejected", method, path, self.role, status)
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
    contents = [normalize_txt(str(row.get("content", ""))) for row in records if row.get("type") == "TXT"]
    spf = [content for content in contents if content.startswith("v=spf1")]
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


def normalize_txt(content: str) -> str:
    try:
        return txt_content(content)
    except ValueError:
        raise ProvisionError("dns_txt_presentation_invalid") from None


def normalized_record(value: dict[str, Any]) -> dict[str, Any]:
    name = str(value.get("name", "")).lower().rstrip(".")
    if name != DOMAIN and not name.endswith("." + DOMAIN):
        raise ProvisionError("dns_outside_staging")
    kind = value.get("type")
    content = value.get("content")
    if kind not in ("MX", "TXT", "CNAME") or not isinstance(content, str) or not content:
        raise ProvisionError("dns_requirement_invalid")
    content = content.lower().rstrip(".") if kind in ("MX", "CNAME") else normalize_txt(content)
    result: dict[str, Any] = {"name": name, "type": kind, "content": content}
    if kind == "MX":
        priority = value.get("priority")
        if type(priority) is not int or not 0 <= priority <= 65535:
            raise ProvisionError("dns_requirement_invalid")
        result["priority"] = priority
    return result


def record_role(record: dict[str, Any]) -> str:
    name = record["name"]
    if name == DOMAIN:
        return "domain"
    if name == "cf-bounce." + DOMAIN:
        return "return_path"
    if name == "_dmarc." + DOMAIN:
        return "dmarc"
    if name.endswith("._domainkey." + DOMAIN):
        return "dkim"
    return "other_scoped"


def txt_purpose(content: str) -> str:
    if content.startswith("v=spf1"):
        return "spf"
    if content.startswith("v=DMARC1"):
        return "dmarc"
    if content.startswith("v=DKIM1"):
        return "dkim"
    return "other"


def dns_conflict(record: dict[str, Any], current: list[dict[str, Any]]) -> bool:
    """RRsets admit multiple MX/TXT values, but CNAME and mail policies differ."""
    if record in current:
        return False
    if record["type"] == "CNAME":
        return bool(current)
    if any(row.get("type") == "CNAME" for row in current):
        return True
    if record["type"] != "TXT":
        return False
    same_type = [row for row in current if row.get("type") == "TXT"]
    purpose = txt_purpose(record["content"])
    if purpose in ("spf", "dmarc"):
        return any(txt_purpose(str(row.get("content", ""))) == purpose for row in same_type)
    # A selector lookup must not introduce a second, ambiguous DKIM key candidate.
    if purpose == "dkim" or record_role(record) == "dkim":
        return bool(same_type)
    return False


def requirement_facts(record: dict[str, Any], current: list[dict[str, Any]]) -> dict[str, Any]:
    """Only closed roles, record classes and comparisons enter public diagnostics."""
    existing = [normalized_record(row) for row in current if row.get("type") in ("MX", "TXT", "CNAME")]
    comparable = existing + [{"type": row.get("type")} for row in current if row.get("type") not in ("MX", "TXT", "CNAME")]
    known_types = {"A", "AAAA", "CAA", "CNAME", "MX", "NS", "SRV", "TXT"}
    facts: dict[str, Any] = {
        "role": record_role(record),
        "type": record["type"],
        "purpose": txt_purpose(record["content"]) if record["type"] == "TXT" else "not_txt",
        "exact_present": record in existing,
        "same_type_count": sum(row.get("type") == record["type"] for row in current),
        "existing_types": sorted({row["type"] if row.get("type") in known_types else "other" for row in current}),
        "existing_spf_count": sum(row.get("type") == "TXT" and txt_purpose(row["content"]) == "spf" for row in existing),
        "conflict": dns_conflict(record, comparable),
        "spf_merge_attempted": False,
    }
    if record["type"] == "TXT":
        texts = [row["content"] for row in existing if row.get("type") == "TXT"]
        wanted_hash = hashlib.sha256(record["content"].encode("utf-8")).digest()
        facts.update({
            "txt_content_equal": record["content"] in texts,
            "txt_sha256_equal": any(hashlib.sha256(content.encode("utf-8")).digest() == wanted_hash for content in texts),
            "txt_presentation_changed_count": sum(row.get("type") == "TXT" and normalize_txt(str(row.get("content", ""))) != row.get("content") for row in current),
        })
    return facts


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
        if requirement_facts(record, current)["conflict"]:
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


def inspection_failure(error: ProvisionError) -> dict[str, Any]:
    """A failed read is unknown, never an empty inventory or absent domain."""
    result: dict[str, Any] = {"state": "unknown"}
    if isinstance(error, ProviderError):
        result.update(error.details)
    else:
        result["code"] = str(error)
    return result


def inspect(dns: Provider, routing: Provider) -> dict[str, Any]:
    """Independent fixed-domain GET probes; no ensure/apply function is called."""
    report: dict[str, Any] = {"schema": "amail.tmpaddr-staging-inspection.v1", "domain": DOMAIN}
    try:
        records = dns_records(dns, DOMAIN)
        report["dns"] = {"state": "observed", "record_count": len(records), "routing_ready": routing_ready(records)}
    except ProvisionError as error:
        report["dns"] = inspection_failure(error)
    for key, client in (("deployment_routing_read", dns), ("routing_token_read", routing)):
        try:
            settings = client.request("GET", PREFIX + "/email/routing").get("result")
            if not isinstance(settings, dict):
                raise ProvisionError("routing_settings_invalid")
            # Read access proves neither subdomain readiness nor Write permission.
            report[key] = {"state": "observed", "write_permission": "unverified"}
        except ProvisionError as error:
            report[key] = inspection_failure(error)
    try:
        domains = inventory(dns, PREFIX + "/email/sending/subdomains")
        matches = [domain for domain in domains if domain.get("name") == DOMAIN]
        if len(matches) > 1:
            raise ProvisionError("sending_domain_ambiguous")
        report["sending"] = {"state": "observed", "present": bool(matches)}
        if matches:
            domain = sending_domain(dns, False)
            report["sending"].update({
                "enabled": True,
                "preview_disabled": domain.get("preview_enabled") is False,
                "partial_drop_disabled": domain.get("drop_suppressed_recipients") is False,
            })
            wanted = [normalized_record(row) for row in rows(dns.request("GET", f"{PREFIX}/email/sending/subdomains/{domain['tag']}/dns"))]
            if not wanted:
                raise ProvisionError("sending_dns_requirements_missing")
            present = 0
            facts: list[dict[str, Any]] = []
            for record in wanted:
                current = dns_records(dns, record["name"])
                existing = [normalized_record(row) for row in current if row.get("type") in ("MX", "TXT", "CNAME")]
                present += int(record in existing)
                facts.append(requirement_facts(record, current))
            report["sending_dns"] = {"state": "observed", "required_count": len(wanted), "present_count": present, "ready": present == len(wanted), "requirements": facts}
    except ProvisionError as error:
        report["sending_probe"] = inspection_failure(error)
    return report


def write_inspection(path: str, report: dict[str, Any]) -> None:
    output = Path(path).resolve()
    if not output.is_relative_to(ROOT / ".temp"):
        raise ProvisionError("inspection_output_outside_workspace_temp")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--inspect", action="store_true")
    parser.add_argument("--output", default=".temp/tmpaddr-staging-inspection.json")
    args = parser.parse_args()
    try:
        if args.apply:
            authorize_apply(dict(os.environ))
        token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
        routing_token = os.environ.get("CF_EMAIL_ROUTING_TOKEN", "")
        if not token or (args.inspect and not routing_token):
            raise ProvisionError("credentials_required")
        client = Client(token)
        routing = Client(routing_token, "routing")
        if args.inspect:
            report = inspect(client, routing)
            write_inspection(args.output, report)
            print(json.dumps(report, sort_keys=True))
            return 0
        # Domain onboarding is deployment configuration, not runtime rule management.
        ensure_routing(client, client, args.apply)
        ensure_sending(client, args.apply)
    except ProvisionError as error:
        print(f"tmpaddr_staging={error}", file=sys.stderr)
        return 1
    print("tmpaddr_staging=provider_config_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
