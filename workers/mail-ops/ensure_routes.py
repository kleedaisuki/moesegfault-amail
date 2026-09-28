"""Audit or provision literal system-role Email Routing rules.

中文：只管理四个精确运营地址；默认只读，显式 --apply 后仍拒绝接管冲突规则。
English: Own only exact role addresses; default to read-only and never take over conflicts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


API = "https://api.cloudflare.com/client/v4"
MAX_REPLY = 262_144


def request(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    """Return bounded JSON without exposing API errors or address inventories in logs.

    中文：有界读取 JSON，不在日志中暴露 API 错误详情或邮箱库存。
    """

    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    req = urllib.request.Request(
        f"{API}{path}", data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            status, raw = response.status, response.read(MAX_REPLY + 1)
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read(MAX_REPLY + 1)
    except (urllib.error.URLError, TimeoutError):
        return 0, {}
    if len(raw) > MAX_REPLY:
        return status, {}
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return status, {}
    return status, parsed if isinstance(parsed, dict) else {}


def roles(target: str) -> tuple[str, list[str]]:
    """Keep staging entirely off the production apex. / 预发布绝不占用生产根域名。"""

    if target == "staging":
        return "amail-ops-staging", [
            "abuse@mail-staging.moesegfault.dev",
            "postmaster@mail-staging.moesegfault.dev",
        ]
    return "amail-ops", [
        "abuse@moesegfault.dev", "postmaster@moesegfault.dev",
        "abuse@mail.moesegfault.dev", "postmaster@mail.moesegfault.dev",
    ]


def list_rules(zone: str, token: str) -> list[dict]:
    """Read every page before mutation so duplicate/conflicting rules are visible.

    中文：修改前遍历全部页，避免遗漏重复或冲突规则。
    """

    rules: list[dict] = []
    for page in range(1, 201):
        status, payload = request(
            "GET", f"/zones/{zone}/email/routing/rules?per_page=50&page={page}", token
        )
        batch = payload.get("result")
        if status != 200 or payload.get("success") is not True or not isinstance(batch, list):
            raise RuntimeError(f"routing read failed: HTTP{status}")
        rules.extend(item for item in batch if isinstance(item, dict))
        info = payload.get("result_info") or {}
        total_pages = info.get("total_pages") if isinstance(info, dict) else None
        if len(batch) < 50 or isinstance(total_pages, int) and page >= total_pages:
            return rules
    raise RuntimeError("routing pagination exceeded safe bound")


def address_of(rule: dict) -> str | None:
    """Extract only exact literal recipient matchers. / 仅解析精确收件人规则。"""

    for matcher in rule.get("matchers") or []:
        if isinstance(matcher, dict) and matcher.get("type") == "literal" and matcher.get("field") == "to":
            value = matcher.get("value")
            if isinstance(value, str):
                return value.lower()
    return None


def matches(rule: dict, worker: str, address: str) -> bool:
    """Require one enabled Worker action to our exact deployed script.

    中文：仅认可唯一已启用且指向指定 Worker 的操作。
    """

    actions = rule.get("actions")
    return (
        rule.get("enabled") is True
        and address_of(rule) == address
        and isinstance(actions, list)
        and len(actions) == 1
        and actions[0] == {"type": "worker", "value": [worker]}
    )


def audit(zone: str, token: str, worker: str, addresses: list[str]) -> list[str]:
    """Fail closed on any existing rule we do not own exactly.

    中文：已有规则只要不完全符合预期就拒绝接管。
    """

    existing = list_rules(zone, token)
    missing: list[str] = []
    for address in addresses:
        found = [rule for rule in existing if address_of(rule) == address]
        if not found:
            missing.append(address)
        elif len(found) != 1 or not matches(found[0], worker, address):
            raise RuntimeError(f"conflicting or disabled operator route: {address}")
    return missing


def main() -> int:
    """Run a safe dry-run or explicitly create missing role routes.

    中文：执行只读审计，或显式创建缺失的角色路由。
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("production", "staging"), required=True)
    parser.add_argument("--apply", action="store_true", help="Create missing rules after Worker/Access validation")
    args = parser.parse_args()
    zone = os.environ.get("CF_ZONE_ID", "")
    token = os.environ.get("CF_EMAIL_ROUTING_TOKEN", "")
    if len(zone) != 32 or not token:
        print("CF_ZONE_ID and CF_EMAIL_ROUTING_TOKEN are required", file=sys.stderr)
        return 2
    worker, addresses = roles(args.target)
    try:
        missing = audit(zone, token, worker, addresses)
        if not args.apply:
            print(f"Operator routes: {len(addresses) - len(missing)} ready, {len(missing)} missing; dry-run only")
            return 0 if not missing else 1
        for address in missing:
            body = {
                "name": f"amail operator {address}", "enabled": True, "source": "api",
                "actions": [{"type": "worker", "value": [worker]}],
                "matchers": [{"type": "literal", "field": "to", "value": address}],
            }
            status, payload = request("POST", f"/zones/{zone}/email/routing/rules", token, body)
            if status not in (200, 201) or payload.get("success") is not True:
                raise RuntimeError(f"operator route creation failed: HTTP{status}")
        if audit(zone, token, worker, addresses):
            raise RuntimeError("operator route read-back was incomplete")
        print(f"Operator routes: {len(addresses)} ready; no user mailbox slots consumed")
        return 0
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
