"""Manage only the disposable staging role-monitor canary route. / 只管理可撤销的预发布角色监控金丝雀路由。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


ALIAS = "amail-role-e2e@moesegfault.dev"
WORKER = "amail-role-monitor-staging"
NAME = "amail staging role monitor"
API = "https://api.cloudflare.com/client/v4"
MAX_BODY = 262_144


def call(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    """Read a bounded provider response without printing its contents. / 有界读取供应商响应且不打印其内容。"""

    request = urllib.request.Request(
        API + path,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        method=method,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            status, raw = response.status, response.read(MAX_BODY + 1)
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read(MAX_BODY + 1)
    except (urllib.error.URLError, TimeoutError):
        return 0, {}
    if len(raw) > MAX_BODY:
        return status, {}
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return status, {}
    return status, data if isinstance(data, dict) else {}


def rules(zone: str, token: str) -> list[dict]:
    """Read every rule page and fail on inventory drift. / 读取所有规则页，库存漂移时失败。"""

    found: list[dict] = []
    total: int | None = None
    for page in range(1, 101):
        status, data = call("GET", f"/zones/{zone}/email/routing/rules?per_page=50&page={page}", token)
        batch = data.get("result")
        info = data.get("result_info")
        if status != 200 or data.get("success") is not True or not isinstance(batch, list) or not isinstance(info, dict):
            raise RuntimeError("staging route inventory unavailable")
        available = info.get("total_count")
        if type(available) is not int or not 0 <= available <= 5000 or (total is not None and total != available):
            raise RuntimeError("staging route inventory count drift")
        pages = max(1, (available + 49) // 50)
        if (info.get("page"), info.get("per_page"), info.get("count"), info.get("total_pages")) != (
            page, 50, len(batch), pages
        ) or len(batch) != min(50, max(0, available - (page - 1) * 50)):
            raise RuntimeError("staging route inventory pagination drift")
        if not all(isinstance(item, dict) for item in batch):
            raise RuntimeError("staging route inventory malformed")
        total = available
        found.extend(batch)
        if page == pages:
            return found
    raise RuntimeError("staging route inventory too large")


def touches_alias(rule: dict) -> bool:
    """Detect any literal matcher for our canary, even under a conflict. / 检测所有涉及金丝雀的精确匹配器。"""

    return any(
        isinstance(matcher, dict)
        and matcher.get("type") == "literal"
        and matcher.get("field") == "to"
        and str(matcher.get("value", "")).casefold() == ALIAS
        for matcher in rule.get("matchers") or []
    )


def owned(rule: dict) -> bool:
    """Require one exact, API-owned Worker action; never take over other rules. / 只承认一条精确的 API 管理 Worker 规则。"""

    return (
        rule.get("name") == NAME
        and rule.get("enabled") is True
        and rule.get("source") == "api"
        and isinstance(rule.get("id"), str)
        and rule.get("matchers") == [{"type": "literal", "field": "to", "value": ALIAS}]
        and rule.get("actions") == [{"type": "worker", "value": [WORKER]}]
    )


def reconcile(zone: str, token: str, action: str) -> str:
    """Audit or explicitly mutate only the dedicated canary rule. / 审计或显式更改唯一专用金丝雀规则。"""

    if action not in ("audit", "apply", "remove"):
        raise ValueError("unknown staging role route action")
    matches = [item for item in rules(zone, token) if touches_alias(item)]
    if len(matches) > 1 or (matches and not owned(matches[0])):
        raise RuntimeError("staging role alias conflict; no changes made")
    if action == "audit":
        return "enabled" if matches else "absent"
    if action == "apply":
        if matches:
            return "enabled"
        body = {
            "name": NAME,
            "enabled": True,
            "source": "api",
            "matchers": [{"type": "literal", "field": "to", "value": ALIAS}],
            "actions": [{"type": "worker", "value": [WORKER]}],
        }
        status, data = call("POST", f"/zones/{zone}/email/routing/rules", token, body)
        if status not in (200, 201) or data.get("success") is not True:
            raise RuntimeError("staging role route creation failed")
        readback = [item for item in rules(zone, token) if touches_alias(item)]
        if len(readback) != 1 or not owned(readback[0]):
            raise RuntimeError("staging role route readback failed")
        return "created"
    if not matches:
        return "absent"
    status, data = call("DELETE", f"/zones/{zone}/email/routing/rules/{matches[0]['id']}", token)
    if status != 204 and (status != 200 or data.get("success") is not True):
        raise RuntimeError("staging role route removal failed")
    if any(touches_alias(item) for item in rules(zone, token)):
        raise RuntimeError("staging role route removal readback failed")
    return "removed"


def main() -> int:
    """Load one existing routing token from the environment. / 从环境读取现有唯一的路由令牌。"""

    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--apply", action="store_true")
    selection.add_argument("--remove", action="store_true")
    args = parser.parse_args()
    zone = os.environ.get("CF_ZONE_ID", "")
    token = os.environ.get("CF_EMAIL_ROUTING_TOKEN", "")
    if len(zone) != 32 or not token:
        print("staging route audit needs zone ID and routing token", file=sys.stderr)
        return 2
    action = "apply" if args.apply else "remove" if args.remove else "audit"
    try:
        print(reconcile(zone, token, action))
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
