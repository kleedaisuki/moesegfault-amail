"""Manage only the exact staging Identity verification test route.

中文：仅管理预发布 Identity 验证测试的精确路由；冲突时拒绝接管。
English: Never take over an existing alias or reconcile unrelated routing rules.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tomllib
import urllib.error
import urllib.request


API = "https://api.cloudflare.com/client/v4"
ADDRESS = "amail-e2e@moesegfault.dev"
WORKER = "amail-identity-test-inbox-staging"
MAX_BODY = 262_144


def allowed_addresses() -> frozenset[str]:
    """Validate the local allowlist; this is not proof of deployed bindings."""

    with Path(__file__).with_name("wrangler.toml").open("rb") as stream:
        config = tomllib.load(stream)
    raw = config.get("vars", {}).get("TEST_RECIPIENTS", "")
    if not isinstance(raw, str):
        return frozenset()
    addresses = raw.split(",")
    if (
        not 1 <= len(addresses) <= 4
        or addresses[0] != ADDRESS
        or len(set(addresses)) != len(addresses)
        or any(not re.fullmatch(r"amail-e2e(?:-[a-z0-9-]{1,21})?@moesegfault\.dev", value)
               for value in addresses)
    ):
        return frozenset()
    return frozenset(addresses)


def call(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    """Return bounded JSON; never echo the bearer token or provider error text.

    中文：仅返回有界 JSON；绝不输出令牌或提供商原始错误文本。
    """

    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    request = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status, raw = response.status, response.read(MAX_BODY + 1)
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read(MAX_BODY + 1)
    except (urllib.error.URLError, TimeoutError):
        return 0, {}
    if len(raw) > MAX_BODY:
        return status, {}
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return status, {}
    return status, parsed if isinstance(parsed, dict) else {}


def list_rules(zone: str, token: str) -> list[dict]:
    """Inspect every page before creating or deleting a rule.

    中文：创建或删除前遍历所有页面，避免遗漏重复规则。
    """

    rules: list[dict] = []
    for page in range(1, 201):
        status, payload = call(
            "GET", f"/zones/{zone}/email/routing/rules?per_page=50&page={page}", token
        )
        batch = payload.get("result")
        if status != 200 or payload.get("success") is not True or not isinstance(batch, list):
            raise RuntimeError(f"routing read failed: HTTP{status}")
        rules.extend(item for item in batch if isinstance(item, dict))
        info = payload.get("result_info")
        total = info.get("total_pages") if isinstance(info, dict) else None
        if total is not None:
            if type(total) is not int or total < 1 or total > 200:
                raise RuntimeError("routing pagination metadata invalid")
            if page < total:
                continue
            return rules
        if len(batch) < 50:
            return rules
    raise RuntimeError("routing pagination exceeded safe bound")


def is_alias(rule: dict, address: str = ADDRESS) -> bool:
    """Detect any literal matcher on the dedicated alias.

    中文：识别专用别名上的任意精确匹配规则。
    """

    return any(
        isinstance(matcher, dict)
        and matcher.get("type") == "literal"
        and matcher.get("field") == "to"
        and str(matcher.get("value", "")).lower() == address
        for matcher in rule.get("matchers") or []
    )


def owned(rule: dict, address: str = ADDRESS) -> bool:
    """Require one enabled, API-owned action to this exact staging Worker.

    中文：只承认指向精确预发布 Worker 的已启用 API 管理规则。
    """

    return (
        rule.get("enabled") is True
        and rule.get("source") == "api"
        and rule.get("actions") == [{"type": "worker", "value": [WORKER]}]
        and rule.get("matchers")
        == [{"type": "literal", "field": "to", "value": address}]
        and isinstance(rule.get("id"), str)
    )


def reconcile(zone: str, token: str, action: str, address: str = ADDRESS) -> str:
    """Audit, add, or remove only our one non-conflicting rule.

    中文：审计、添加或删除一条不冲突的专有规则。
    """

    if address not in allowed_addresses():
        raise RuntimeError("test alias not in staging inbox allowlist")
    matches = [rule for rule in list_rules(zone, token) if is_alias(rule, address)]
    if len(matches) > 1 or matches and not owned(matches[0], address):
        raise RuntimeError("test alias routing conflict; no changes made")
    if action == "audit":
        return "enabled" if matches else "absent"
    if action == "apply":
        if matches:
            return "enabled"
        body = {
            "name": "amail staging Identity verification",
            "enabled": True,
            "source": "api",
            "matchers": [{"type": "literal", "field": "to", "value": address}],
            "actions": [{"type": "worker", "value": [WORKER]}],
        }
        status, payload = call("POST", f"/zones/{zone}/email/routing/rules", token, body)
        if status not in (200, 201) or payload.get("success") is not True:
            raise RuntimeError(f"routing create failed: HTTP{status}")
        readback = [rule for rule in list_rules(zone, token) if is_alias(rule, address)]
        if len(readback) != 1 or not owned(readback[0], address):
            raise RuntimeError("routing create readback failed")
        return "created"
    if not matches:
        return "absent"
    rule_id = matches[0]["id"]
    status, payload = call("DELETE", f"/zones/{zone}/email/routing/rules/{rule_id}", token)
    if status != 204 and (status != 200 or payload.get("success") is not True):
        raise RuntimeError(f"routing delete failed: HTTP{status}")
    if any(is_alias(rule, address) for rule in list_rules(zone, token)):
        raise RuntimeError("routing delete readback failed")
    return "removed"


def audit_all_absent(zone: str, token: str) -> str:
    """Require every locally configured exact route absent before Worker replacement."""

    addresses = allowed_addresses()
    if not addresses or ADDRESS not in addresses:
        raise RuntimeError("staging test alias allowlist unavailable")
    rules = list_rules(zone, token)
    if any(is_alias(rule, address) for address in addresses for rule in rules):
        raise RuntimeError("test alias route active; no changes made")
    return "absent"


def main() -> int:
    """Use the existing single zone-scoped routing token. / 复用现有单一域名路由令牌。"""

    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true")
    action.add_argument("--remove", action="store_true")
    action.add_argument("--all-absent", action="store_true", help="require every configured alias unrouted")
    parser.add_argument("--address", default=ADDRESS, help="exact configured staging Identity test alias")
    args = parser.parse_args()
    zone = os.environ.get("CLOUDFLARE_ZONE_ID", "")
    token = os.environ.get("CF_EMAIL_ROUTING_TOKEN", "")
    if len(zone) != 32 or not token:
        print("missing zone ID or routing token", file=sys.stderr)
        return 2
    desired = "apply" if args.apply else "remove" if args.remove else "audit"
    try:
        if args.all_absent:
            if args.address != ADDRESS:
                raise RuntimeError("--address cannot be combined with --all-absent")
            print(audit_all_absent(zone, token))
        else:
            print(reconcile(zone, token, desired, args.address))
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
