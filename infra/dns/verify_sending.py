"""Verify mail-subdomain sending DNS against Cloudflare's live requirements.

中文：只读取 Cloudflare 生成的记录与权威 DNS；不创建、修改或删除记录。
English: Read provider-generated records and authoritative DNS only; never mutate DNS.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import dns.flags
import dns.exception
import dns.message
import dns.query
import dns.rcode
import dns.resolver
import dns.rdatatype

ZONE = "moesegfault.dev"
DOMAINS = {"mail.moesegfault.dev", "mail-staging.moesegfault.dev"}
DOMAIN = os.environ.get("MAIL_SENDING_DOMAIN", "mail.moesegfault.dev").lower().rstrip(".")
API = "https://api.cloudflare.com/client/v4"


@dataclass(frozen=True)
class Record:
    """表示不含 TTL 与文本引号差异的 MX/TXT 记录。 / Represent comparable MX/TXT records."""

    name: str
    type: str
    content: str
    priority: int | None = None


def api_get(path: str, token: str) -> Any:
    """读取 Cloudflare API，权限或结构错误时拒绝继续。 / Fetch API data and fail closed."""

    request = urllib.request.Request(
        API + path,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(
            f"Cloudflare API returned HTTP {error.code} for {path}; "
            "check token Email Sending Read permission"
        ) from error
    if payload.get("success") is not True or not isinstance(payload.get("result"), list):
        raise RuntimeError(f"Cloudflare API returned an invalid result for {path}")
    return payload["result"]


def fqdn(name: str) -> str:
    """仅接受邮件子域下的相对或绝对名称。 / Accept only mail-scoped DNS names."""

    name = name.lower().rstrip(".")
    if not name.endswith("." + ZONE):
        name += "." + ZONE
    if name != DOMAIN and not name.endswith("." + DOMAIN):
        raise ValueError(f"Provider requested an out-of-scope DNS name: {name}")
    return name


def normalize(record: dict[str, Any]) -> Record:
    """标准化提供商的 MX/TXT 记录以便比较。 / Normalize provider records for DNS comparison."""

    kind = record["type"].upper()
    if kind not in {"MX", "TXT"}:
        raise ValueError(f"Unexpected Email Sending record type: {kind}")
    content = record["content"].strip()
    if kind == "MX":
        content = content.lower().rstrip(".")
    elif content.startswith('"') and content.endswith('"'):
        content = content[1:-1]
    priority = int(record["priority"]) if kind == "MX" else None
    return Record(fqdn(record["name"]), kind, content, priority)


def expected_records(zone_id: str, token: str) -> set[Record]:
    """仅选择已启用的目标发送子域。 / Select the exact enabled sending subdomain."""

    prefix = f"/zones/{zone_id}/email/sending/subdomains"
    matches = [
        item for item in api_get(prefix, token)
        if item.get("name", "").lower().rstrip(".") == DOMAIN and item.get("enabled") is True
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("tag"), str):
        raise RuntimeError(f"Expected exactly one enabled Email Sending subdomain: {DOMAIN}")
    generated = api_get(f"{prefix}/{matches[0]['tag']}/dns", token)
    records = {normalize(item) for item in generated}
    if not records:
        raise RuntimeError("Cloudflare returned no required Email Sending DNS records")
    return records


def nameserver_addresses() -> dict[str, list[str]]:
    """解析区域委派的权威服务器地址。 / Resolve delegated authoritative nameservers."""

    nameservers = [str(answer.target).rstrip(".") for answer in dns.resolver.resolve(ZONE, "NS")]
    if not nameservers:
        raise RuntimeError("The zone has no delegated authoritative nameservers")
    addresses: dict[str, list[str]] = {}
    for server in nameservers:
        ips = []
        for kind in ("A", "AAAA"):
            try:
                ips.extend(str(answer) for answer in dns.resolver.resolve(server, kind))
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
                continue
        if not ips:
            raise RuntimeError(f"Could not resolve authoritative nameserver {server}")
        addresses[server] = ips
    return addresses


def authoritative_records(address: str, wanted: set[Record]) -> set[Record]:
    """直接查询一台权威服务器并解码 RDATA。 / Query one authoritative server directly."""

    actual: set[Record] = set()
    for name, kind in sorted({(item.name, item.type) for item in wanted}):
        query = dns.message.make_query(name, kind)
        response = dns.query.udp(query, address, timeout=5)
        if response.flags & dns.flags.TC:
            response = dns.query.tcp(query, address, timeout=5)
        if not response.flags & dns.flags.AA or response.rcode() != dns.rcode.NOERROR:
            raise RuntimeError(f"Non-authoritative or unsuccessful DNS answer for {name} {kind}")
        for rrset in response.answer:
            if str(rrset.name).lower().rstrip(".") != name or dns.rdatatype.to_text(rrset.rdtype) != kind:
                continue
            for item in rrset:
                if kind == "MX":
                    actual.add(Record(name, kind, str(item.exchange).lower().rstrip("."), int(item.preference)))
                else:
                    actual.add(Record(name, kind, b"".join(item.strings).decode("utf-8")))
    return actual


def verify(zone_id: str, token: str, retries: int = 6, delay: int = 10) -> None:
    """等待传播，要求所有权威服务器均提供所需记录。 / Retry until every server agrees."""

    wanted = expected_records(zone_id, token)
    servers = nameserver_addresses()
    last_errors: list[str] = []
    for attempt in range(retries):
        last_errors = []
        for server, addresses in servers.items():
            try:
                # 中文：优先 IPv4，避免 CI 容器没有 IPv6 路由；仍检查每个权威服务器。
                # English: Prefer IPv4 for CI reachability while checking every authoritative server.
                records = authoritative_records(next((ip for ip in addresses if ":" not in ip), addresses[0]), wanted)
                missing = wanted - records
                if missing:
                    kinds = ", ".join(sorted({f"{item.name} {item.type}" for item in missing}))
                    last_errors.append(f"{server}: missing {kinds}")
            except (OSError, dns.exception.DNSException, RuntimeError) as error:
                last_errors.append(f"{server}: {error}")
        if not last_errors:
            print(f"Verified {len(wanted)} provider-required mail sending records on {len(servers)} authoritative DNS servers")
            return
        if attempt + 1 < retries:
            time.sleep(delay)
    raise RuntimeError("Email Sending DNS is not ready: " + "; ".join(last_errors))


def main() -> int:
    """验证环境并运行只读生产 DNS 门禁。 / Run the read-only production DNS gate."""

    zone_id = os.environ.get("CF_ZONE_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if DOMAIN not in DOMAINS:
        print("MAIL_SENDING_DOMAIN must be an explicitly approved mail domain", file=sys.stderr)
        return 2
    if len(zone_id) != 32 or any(char not in "0123456789abcdef" for char in zone_id.lower()):
        print("CF_ZONE_ID must be the 32-character Cloudflare zone ID", file=sys.stderr)
        return 2
    if not token:
        print("CLOUDFLARE_API_TOKEN is required", file=sys.stderr)
        return 2
    try:
        verify(zone_id, token)
    except (RuntimeError, ValueError, KeyError, UnicodeDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
