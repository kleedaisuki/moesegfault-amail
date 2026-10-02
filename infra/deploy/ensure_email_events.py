"""Idempotently provision Cloudflare Email Sending Queue resources via Wrangler.

通过 Wrangler 幂等配置 Cloudflare 邮件发送事件队列资源。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any

import ensure_trace_queues as queues

ZONE = "6edff81c6ed02f412e70868076411a5e"
EVENTS = (
    "message.delivered,message.deferred,message.bounced,"
    "message.failed,message.rejected,message.complained"
)


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Capture Wrangler output so provider errors cannot leak secret-bearing details. / 捕获 Wrangler 输出，避免供应商错误泄漏秘密细节。"""
    command = ["wrangler", "queues", *args]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if check and result.returncode:
        raise RuntimeError(f"wrangler queues operation failed: {' '.join(args[:2])}")
    return result


def objects(value: Any):
    """Traverse a CLI JSON envelope without assuming one Wrangler display shape. / 遍历 CLI JSON 外壳，不假定 Wrangler 只有一种显示格式。"""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def ensure_queue(name: str) -> None:
    """Create only after a successful complete catalog proves exact-name absence.

    An unavailable/auth-denied Wrangler info call is not evidence of absence.
    Reuse the bounded account Queue reader; never overwrite or purge queues.
    """
    rows = queues.inventory(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"])
    if queues.exact_queue(rows, name) is not None:
        return
    run("create", name)


def ensure_subscription(queue: str, name: str, domain: str) -> None:
    """Create one named, domain-scoped subscription, refusing ambiguous duplicates. / 创建唯一具名域名订阅，拒绝含糊的重复项。"""
    data = json.loads(run("subscription", "list", queue, "--json").stdout)
    matches = [item for item in objects(data) if item.get("name") == name]
    if len(matches) > 1:
        raise RuntimeError("duplicate lifecycle subscriptions require operator review")
    if matches:
        subscription = matches[0]
        source = subscription.get("source")
        if (
            not isinstance(source, dict) or source.get("type") != "email.sending"
            or source.get("domain") != domain or subscription.get("enabled") is not True
            or set(subscription.get("events", [])) != set(EVENTS.split(","))
        ):
            raise RuntimeError("lifecycle subscription drift requires operator review")
        return
    run(
        "subscription", "create", queue, "--name", name,
        "--source", "email.sending", "--events", EVENTS,
        "--zone-id", ZONE, "--domain", domain,
    )


def main() -> int:
    """Select only reviewed staging or production resources. / 仅选择已审查的预发布或生产资源。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=("staging", "production"), required=True)
    parser.add_argument("--phase", choices=("queues", "subscription"), required=True)
    args = parser.parse_args()
    if not os.getenv("CLOUDFLARE_ACCOUNT_ID") or not os.getenv("CLOUDFLARE_API_TOKEN"):
        print("missing Cloudflare deployment credentials", file=sys.stderr)
        return 2
    suffix = "-staging" if args.target == "staging" else ""
    queue = f"amail-sending-events{suffix}"
    dlq = f"amail-sending-events-dlq{suffix}"
    domain = f"mail{suffix}.moesegfault.dev"
    try:
        if args.phase == "queues":
            ensure_queue(dlq)
            ensure_queue(queue)
        else:
            ensure_subscription(queue, f"amail-sending-lifecycle{suffix}", domain)
    except (RuntimeError, ValueError, KeyError, OSError, subprocess.TimeoutExpired):
        print("email events provisioning failed: read_or_write_unverified", file=sys.stderr)
        return 1
    print(f"email events {args.phase} ready: {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
