"""Probe read-only Cloudflare Queues capability without exposing secrets or resources.

只读探测 Cloudflare Queues 权限，不暴露秘密或资源明细。
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request


def main() -> int:
    """Report only HTTP status and a coarse capability outcome. / 仅报告 HTTP 状态与粗粒度权限结果。"""
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not account or not token:
        print("queues_probe=missing_credentials")
        return 2
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/queues?per_page=1"
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    except urllib.error.URLError:
        print("queues_probe=network_error")
        return 2
    print(f"queues_probe_http={status}")
    print("queues_probe=read_available" if status == 200 else "queues_probe=not_available")
    return 0 if status == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
