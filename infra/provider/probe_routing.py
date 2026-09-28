"""Check the Worker's routing token can read rules for reconciliation.

中文：只读检查用于定时路由规则校对的令牌权限，不输出地址或规则内容。
English: Check read access needed by cron reconciliation without logging addresses.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    """只验证读取权限；写入权限须由真实注册流程验证。 / Verify read access only."""

    zone = os.environ.get("CF_ZONE_ID", "")
    token = os.environ.get("CF_EMAIL_ROUTING_TOKEN", "")
    if len(zone) != 32 or not token:
        print("CF_ZONE_ID and CF_EMAIL_ROUTING_TOKEN are required", file=sys.stderr)
        return 2
    request = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/zones/{zone}/email/routing/rules?per_page=1",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        print(f"Email Routing Rules read probe failed with HTTP {error.code}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, ValueError):
        print("Email Routing Rules read probe failed to get a valid response", file=sys.stderr)
        return 1
    if payload.get("success") is not True or not isinstance(payload.get("result"), list):
        print("Email Routing Rules read probe returned an invalid result", file=sys.stderr)
        return 1
    print("Email Routing Rules read access is available; Write remains unverified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
