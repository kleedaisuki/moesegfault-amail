"""Disable duplicate content previews and partial suppressed-recipient drops.

关闭重复内容预览和被抑制收件人的部分发送丢弃行为。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ZONE = "6edff81c6ed02f412e70868076411a5e"
DOMAINS = {
    "production": "mail.moesegfault.dev",
    "staging": "mail-staging.moesegfault.dev",
}


def call(path: str, token: str, method: str = "GET", body: dict | None = None) -> dict:
    """Return only parsed provider JSON, never echo raw error bodies or credentials. / 仅返回解析后的提供商 JSON，不回显原始错误正文或凭据。"""
    payload = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/zones/{ZONE}/email/sending/subdomains{path}",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.load(response)
    if not result.get("success"):
        raise ValueError("provider reported unsuccessful result")
    return result


def unique_domain(rows: list[dict], name: str) -> dict:
    """Require one exact configured sending subdomain, never a wildcard/apex match. / 只接受唯一精确配置的发信子域，不匹配通配符或根域。"""
    matches = [row for row in rows if row.get("name") == name and row.get("enabled") is True]
    if len(matches) != 1 or not isinstance(matches[0].get("tag"), str):
        raise ValueError("sending domain missing or ambiguous")
    return matches[0]


def main() -> int:
    """Set and verify metadata-only privacy flags on the chosen user domain. / 在指定用户域设置并核验仅含元数据的隐私选项。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=tuple(DOMAINS), required=True)
    args = parser.parse_args()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    if not token:
        print("sending_privacy=missing_credential", file=sys.stderr)
        return 2
    try:
        domain = unique_domain(call("", token)["result"], DOMAINS[args.target])
        tag = domain["tag"]
        call(f"/{tag}", token, "PATCH", {"preview_enabled": False, "drop_suppressed_recipients": False})
        after = call(f"/{tag}", token)["result"]
        if after.get("name") != DOMAINS[args.target] or after.get("preview_enabled") is not False or after.get("drop_suppressed_recipients") is not False:
            raise ValueError("privacy flags did not persist")
    except (KeyError, TypeError, ValueError, urllib.error.URLError):
        print("sending_privacy=not_verified", file=sys.stderr)
        return 1
    print(f"sending_privacy=verified target={args.target} preview=false drop_suppressed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
