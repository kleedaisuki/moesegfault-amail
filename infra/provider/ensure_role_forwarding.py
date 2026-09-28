"""Provision four reserved aliases without disclosing the private destination.

中文：只在显式 apply 阶段创建精确转发规则；任何现有冲突均拒绝接管。
English: Only an explicit apply creates exact forwarding rules; conflicts fail closed.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


API = "https://api.cloudflare.com/client/v4"
ZONE = "6edff81c6ed02f412e70868076411a5e"
ROLES = (
    "abuse@moesegfault.dev",
    "postmaster@moesegfault.dev",
    "abuse@mail.moesegfault.dev",
    "postmaster@mail.moesegfault.dev",
)
MAX_REPLY = 512_000
MAX_PAGES = 100


class ProvisionError(Exception):
    """Represent a safe, non-secret operational failure. / 表示可安全输出的失败。"""


@dataclass(frozen=True)
class Client:
    """Hold API credentials in memory, never in printed diagnostics. / 凭据只驻内存。"""

    token: str
    account: str

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return bounded Cloudflare JSON without echoing the request or response. / 有界读取。"""

        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{API}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                status = response.status
                raw = response.read(MAX_REPLY + 1)
        except urllib.error.HTTPError as error:
            status = error.code
            raw = error.read(MAX_REPLY + 1)
        except (urllib.error.URLError, TimeoutError):
            raise ProvisionError("Cloudflare API network failure") from None
        if len(raw) > MAX_REPLY:
            raise ProvisionError("Cloudflare API response too large")
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise ProvisionError(f"Cloudflare API invalid JSON (HTTP {status})") from None
        if not isinstance(payload, dict) or payload.get("success") is not True or status not in (200, 201):
            raise ProvisionError(f"Cloudflare API request rejected (HTTP {status})")
        return payload


def pages(client: Client, path: str) -> list[dict[str, Any]]:
    """Read every page before decisions; truncated inventories must fail closed. / 全页读取。"""

    items: list[dict[str, Any]] = []
    total_count: int | None = None
    for page in range(1, MAX_PAGES + 1):
        separator = "&" if "?" in path else "?"
        payload = client.request("GET", f"{path}{separator}per_page=50&page={page}")
        result = payload.get("result")
        info = payload.get("result_info")
        if not isinstance(result, list) or not isinstance(info, dict):
            raise ProvisionError("Cloudflare API inventory shape changed")
        if not all(isinstance(item, dict) for item in result):
            raise ProvisionError("Cloudflare API inventory item malformed")
        per_page = info.get("per_page")
        count = info.get("count")
        available = info.get("total_count")
        if (
            type(info.get("page")) is not int
            or info.get("page") != page
            or type(per_page) is not int
            or per_page != 50
            or type(count) is not int
            or count != len(result)
            or type(available) is not int
            or available < 0
            or available > MAX_PAGES * per_page
            or (total_count is not None and total_count != available)
        ):
            raise ProvisionError("Cloudflare API pagination invalid")
        total_count = available
        total_pages = max(1, (available + per_page - 1) // per_page)
        reported = info.get("total_pages")
        if reported is not None and (
            type(reported) is not int
            or (reported != total_pages and not (available == 0 and reported == 0))
        ):
            raise ProvisionError("Cloudflare API pagination drift")
        expected_count = min(per_page, max(0, available - (page - 1) * per_page))
        if page > total_pages or count != expected_count:
            raise ProvisionError("Cloudflare API inventory truncated or shifted")
        items.extend(result)
        if page == total_pages:
            return items
    raise ProvisionError("Cloudflare API pagination exceeded bound")


def destination_state(client: Client, destination: str) -> str:
    """Return missing, pending, or verified without revealing address. / 不泄露地址。"""

    addresses = pages(client, f"/accounts/{client.account}/email/routing/addresses")
    matches = [item for item in addresses if item.get("email") == destination]
    if len(matches) > 1:
        raise ProvisionError("Duplicate destination records")
    if not matches:
        return "missing"
    verified = matches[0].get("verified")
    if verified is None:
        return "pending"
    if isinstance(verified, str) and verified:
        return "verified"
    raise ProvisionError("Destination verification state malformed")


def matched_roles(rule: dict[str, Any]) -> set[str]:
    """Find exact reserved aliases in any rule, including multi-matcher rules. / 查找所有匹配。"""

    matchers = rule.get("matchers")
    if not isinstance(matchers, list):
        raise ProvisionError("Routing rule matcher shape changed")
    found: set[str] = set()
    for matcher in matchers:
        if not isinstance(matcher, dict):
            raise ProvisionError("Routing rule matcher item malformed")
        if matcher.get("type") != "literal" or matcher.get("field") != "to":
            continue
        value = matcher.get("value")
        if not isinstance(value, str):
            raise ProvisionError("Routing rule literal matcher malformed")
        canonical = value.casefold()
        if canonical in ROLES:
            found.add(canonical)
    return found


def expected_rule(rule: dict[str, Any], role: str, destination: str) -> bool:
    """Accept only the exact enabled, API-owned forward contract. / 精确规则契约。"""

    return (
        rule.get("enabled") is True
        and rule.get("source") == "api"
        and rule.get("matchers") == [{"type": "literal", "field": "to", "value": role}]
        and rule.get("actions") == [{"type": "forward", "value": [destination]}]
    )


def audit(rules: list[dict[str, Any]], destination: str) -> set[str]:
    """Reject all duplicate, disabled, or redirected roles before writing. / 先审计后写入。"""

    seen: set[str] = set()
    for rule in rules:
        for role in matched_roles(rule):
            if role in seen or not expected_rule(rule, role, destination):
                raise ProvisionError("Reserved alias has a conflicting or duplicate rule")
            seen.add(role)
    return seen


def rules(client: Client) -> list[dict[str, Any]]:
    """List zone rules across all pages. / 列出整个 zone 的规则。"""

    return pages(client, f"/zones/{ZONE}/email/routing/rules")


def create_rule(client: Client, role: str, destination: str) -> None:
    """Create one literal rule, then require exact readback. / 创建后精确读回。"""

    body = {
        "name": f"amail reserved {role}",
        "enabled": True,
        "source": "api",
        "matchers": [{"type": "literal", "field": "to", "value": role}],
        "actions": [{"type": "forward", "value": [destination]}],
    }
    try:
        client.request("POST", f"/zones/{ZONE}/email/routing/rules", body)
    except ProvisionError:
        # 网络超时等结果不确定时，读回而非重试 POST，以免产生重复路由。
        # On ambiguous POST outcomes, read back rather than retrying a non-idempotent write.
        if role not in audit(rules(client), destination):
            raise
    if role not in audit(rules(client), destination):
        raise ProvisionError("New routing rule missing on readback")


def execute(client: Client, phase: str, destination: str) -> str:
    """Run a single explicit lifecycle phase. / 执行显式生命周期阶段。"""

    state = destination_state(client, destination)
    if phase == "request-verification":
        if state == "missing":
            client.request("POST", f"/accounts/{client.account}/email/routing/addresses", {"email": destination})
            state = destination_state(client, destination)
            if state == "missing":
                raise ProvisionError("Destination creation missing on readback")
        if state == "verified":
            return "Destination already verified; no email action required."
        return "Destination verification pending; complete the private email action before apply."

    if state != "verified":
        raise ProvisionError("Destination is not verified; run request-verification first")
    current = rules(client)
    present = audit(current, destination)
    if phase == "audit":
        return f"Destination verified; exact reserved rules present: {len(present)}/{len(ROLES)}."
    if phase != "apply":
        raise ProvisionError("Unknown phase")

    for role in ROLES:
        if role not in present:
            # 再读一次以避免预检后外部变更；并发创建将由读回发现。
            # Re-read before each mutation to detect concurrent control-plane changes.
            present = audit(rules(client), destination)
            if role not in present:
                create_rule(client, role, destination)
    final = audit(rules(client), destination)
    if final != set(ROLES):
        raise ProvisionError("Reserved rule set incomplete after apply")
    return "Four exact forwarding rules read back successfully; private SMTP canary still required."


def main() -> int:
    """Load secrets only from environment and print non-sensitive status. / 仅从环境读密钥。"""

    phase = os.environ.get("ROLE_FORWARD_PHASE", "")
    destination = os.environ.get("ROLE_FORWARD_DESTINATION", "")
    token = os.environ.get("CF_EMAIL_ROUTING_TOKEN", "")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if phase not in ("request-verification", "audit", "apply"):
        print("Invalid phase", file=sys.stderr)
        return 2
    if not token or not re.fullmatch(r"[0-9a-f]{32}", account) or not destination or len(destination) > 254:
        print("Required secret or account configuration missing or invalid", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", destination):
        print("Private destination has invalid email syntax", file=sys.stderr)
        return 2
    domain = destination.rsplit("@", 1)[1].casefold()
    if domain == "moesegfault.dev" or domain.endswith(".moesegfault.dev"):
        print("Private destination must be external to avoid forwarding loops", file=sys.stderr)
        return 2
    try:
        print(execute(Client(token, account), phase, destination))
    except ProvisionError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        # Never let a library traceback include response bodies or secret-bearing URLs.
        # 不允许异常回溯泄露包含私有地址的 API 响应。
        print("Unexpected provisioning failure", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
