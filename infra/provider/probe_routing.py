"""Diagnose the routing token without disclosing credentials or routing rules.

中文：先检查规则列表，再以 Cloudflare 官方令牌验证接口区分凭据失效与权限不足。
English: Check rule listing, then use official token verification to distinguish
an inactive token from a valid token lacking rule or zone authorization.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


API = "https://api.cloudflare.com/client/v4"
MAX_REPLY = 8192


def _request(path: str, token: str) -> tuple[int, dict]:
    """读取有界 JSON；只向调用方返回状态和结构。 / Read bounded JSON safely."""

    request = urllib.request.Request(
        f"{API}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.status
            raw = response.read(MAX_REPLY + 1)
    except urllib.error.HTTPError as error:
        status = error.code
        raw = error.read(MAX_REPLY + 1)
    except (urllib.error.URLError, TimeoutError):
        return 0, {}
    if len(raw) > MAX_REPLY:
        return status, {}
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return status, {}
    return status, payload if isinstance(payload, dict) else {}


def _codes(payload: dict) -> str:
    """只提取有界数字错误码。 / Extract only bounded numeric error codes."""

    errors = payload.get("errors")
    if not isinstance(errors, list):
        return "none"
    codes = [item.get("code") for item in errors[:3] if isinstance(item, dict)]
    return ",".join(str(code) for code in codes if type(code) is int and 0 <= code <= 999999) or "none"


def _verify(token: str, account: str) -> str:
    """核实用户或账户令牌状态；不输出令牌标识。 / Verify user or account token status."""

    paths = [("user", "/user/tokens/verify")]
    if len(account) == 32:
        paths.append(("account", f"/accounts/{account}/tokens/verify"))
    failures = []
    for kind, path in paths:
        status, payload = _request(path, token)
        result = payload.get("result")
        if status == 200 and payload.get("success") is True and isinstance(result, dict):
            state = result.get("status")
            if state in ("active", "disabled", "expired"):
                return f"{kind}:{state}"
        failures.append(f"{kind}:HTTP{status}:codes={_codes(payload)}")
    return "unconfirmed(" + ";".join(failures) + ")"


def main() -> int:
    """验证规则读取权限，失败时诊断凭据状态。 / Probe rule-read authorization."""

    zone = os.environ.get("CF_ZONE_ID", "")
    token = os.environ.get("CF_EMAIL_ROUTING_TOKEN", "")
    if len(zone) != 32 or not token:
        print("CF_ZONE_ID and CF_EMAIL_ROUTING_TOKEN are required", file=sys.stderr)
        return 2
    # Cloudflare requires per_page >= 5; one page is enough to test permission.
    # Cloudflare 要求 per_page >= 5；一页足以验证权限。
    status, payload = _request(f"/zones/{zone}/email/routing/rules?per_page=5", token)
    if status == 200 and payload.get("success") is True and isinstance(payload.get("result"), list):
        print("Email Routing Rules read access is available; Write remains unverified")
        return 0
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    verified = _verify(token, account)
    print(
        f"Email Routing Rules read probe failed: HTTP{status}, codes={_codes(payload)}, "
        f"token={verified}. Requires zone Email Routing Rules Read/Write for CF_ZONE_ID.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
