"""Reject an accidentally public or cross-environment verification Worker.

中文：拒绝意外公开或跨环境复用的验证码 Worker 配置。
English: This is a source admission check; live Cloudflare state needs separate verification.
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


EXPECTED_BUCKET = "amail-identity-test-inbox-staging"
EXPECTED_WORKER = "amail-identity-test-inbox-staging"
PRIMARY_ADDRESS = "amail-e2e@moesegfault.dev"
API = "https://api.cloudflare.com/client/v4"
MAX_REPLY = 65_536


def recipients(config: dict) -> frozenset[str] | None:
    """Accept a small explicit apex-only test allowlist including the legacy alias."""

    values = config.get("vars")
    raw = values.get("TEST_RECIPIENTS") if isinstance(values, dict) else None
    if not isinstance(raw, str) or set(values) != {"TEST_RECIPIENTS"}:
        return None
    parts = raw.split(",")
    if not 1 <= len(parts) <= 4 or len(parts) != len(set(parts)):
        return None
    if parts[0] != PRIMARY_ADDRESS:
        return None
    for address in parts:
        if not re.fullmatch(r"amail-e2e(?:-[a-z0-9-]{1,21})?@moesegfault\.dev", address):
            return None
    return frozenset(parts)


def valid(config: dict) -> bool:
    """Require one private R2 binding and no HTTP publication surface.

    中文：要求唯一私有 R2 绑定，且没有 HTTP 发布入口。
    """

    return (
        config.get("name") == EXPECTED_WORKER
        and config.get("main") == "build/worker/shim.mjs"
        and config.get("workers_dev") is False
        and config.get("preview_urls") is False
        and "routes" not in config
        and "route" not in config
        and "env" not in config
        and "triggers" not in config
        and config.get("r2_buckets")
        == [{"binding": "PRIVATE_INBOX", "bucket_name": EXPECTED_BUCKET}]
        and recipients(config) is not None
        and config.get("observability") == {"enabled": False}
    )


def fetch_json(path: str, token: str) -> tuple[int, dict]:
    """Read bounded Cloudflare JSON without printing credentials or domain names.

    中文：有界读取 Cloudflare JSON，不打印凭据或域名。
    """

    request = urllib.request.Request(
        f"{API}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status, raw = response.status, response.read(MAX_REPLY + 1)
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read(MAX_REPLY + 1)
    except (urllib.error.URLError, TimeoutError):
        return 0, {}
    if len(raw) > MAX_REPLY:
        return status, {}
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return status, {}
    return status, payload if isinstance(payload, dict) else {}


def private_bucket(account: str, token: str) -> None:
    """Require private R2 URLs and bounded verification-object retention.

    中文：必须关闭 R2 公开入口，并保证验证码对象有界保留。
    """

    if len(account) != 32 or any(char not in "0123456789abcdefABCDEF" for char in account) or not token:
        raise RuntimeError("missing or invalid R2 read credentials")
    base = f"/accounts/{account}/r2/buckets/{EXPECTED_BUCKET}/domains"
    status, managed = fetch_json(f"{base}/managed", token)
    if status != 200 or managed.get("success") is not True or not isinstance(managed.get("result"), dict):
        raise RuntimeError(f"R2 managed-domain read failed: HTTP{status}")
    if managed["result"].get("enabled") is not False:
        raise RuntimeError("R2 managed public domain is enabled or unknown")
    status, custom = fetch_json(f"{base}/custom", token)
    if status != 200 or custom.get("success") is not True or not isinstance(custom.get("result"), dict):
        raise RuntimeError(f"R2 custom-domain read failed: HTTP{status}")
    if custom["result"].get("domains") != []:
        raise RuntimeError("R2 custom domains are present or unknown")
    status, lifecycle = fetch_json(
        f"/accounts/{account}/r2/buckets/{EXPECTED_BUCKET}/lifecycle", token
    )
    if status != 200 or lifecycle.get("success") is not True or not isinstance(lifecycle.get("result"), dict):
        raise RuntimeError(f"R2 lifecycle read failed: HTTP{status}")
    rules = lifecycle["result"].get("rules")
    if not isinstance(rules, list):
        raise RuntimeError("R2 lifecycle rules are missing or unknown")
    matches = [rule for rule in rules if isinstance(rule, dict) and rule.get("id") == "amail-test-expire"]
    if len(matches) != 1:
        raise RuntimeError("R2 verification expiry rule is missing or duplicated")
    rule = matches[0]
    condition = rule.get("deleteObjectsTransition")
    condition = condition.get("condition") if isinstance(condition, dict) else None
    age = condition.get("maxAge") if isinstance(condition, dict) else None
    if (
        rule.get("enabled") is not True
        or rule.get("conditions") != {"prefix": "verification/"}
        or not isinstance(condition, dict)
        or condition.get("type") != "Age"
        or type(age) is not int
        or not 0 < age <= 86_400
    ):
        raise RuntimeError("R2 verification expiry rule is disabled or too long")


def main() -> int:
    """Check source, optionally verify live R2 privacy, without mutation.

    中文：检查源码并可选核验线上 R2 私密性，不修改 Cloudflare。
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="also verify private R2 domain state")
    args = parser.parse_args()
    path = Path(__file__).with_name("wrangler.toml")
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    if not valid(config):
        print("staging test inbox config is not isolated", file=sys.stderr)
        return 1
    if args.live:
        try:
            private_bucket(
                os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
                os.environ.get("CLOUDFLARE_API_TOKEN", ""),
            )
        except RuntimeError as error:
            print(str(error), file=sys.stderr)
            return 1
    print("staging test inbox config isolated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
