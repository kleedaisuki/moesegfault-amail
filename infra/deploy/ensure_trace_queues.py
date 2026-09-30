"""Provision bounded private trace queues, then attest exact producer/consumer ownership.

Only reviewed names are accepted. Existing drift is never overwritten or purged.
Provider bodies and credentials never reach output; failures use fixed labels.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "https://api.cloudflare.com/client/v4"
RETENTION = 86400
LIMIT = 262144


def request(account: str, token: str, path: str, body: dict | None = None):
    """Read a bounded API envelope; never include provider error text in failures."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    req = Request(f"{API}/accounts/{account}/{path}", headers=headers,
                  data=json.dumps(body).encode() if body is not None else None)
    try:
        with urlopen(req, timeout=20) as response:
            raw = response.read(LIMIT + 1)
        payload = json.loads(raw)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        raise ValueError("provider_unavailable") from error
    if len(raw) > LIMIT or not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("provider_unavailable")
    return payload


def inventory(account: str, token: str) -> list[dict]:
    """Require cursor-complete bounded queue inventory before deciding absence."""
    queues = []
    for page in range(1, 101):
        payload = request(account, token, f"queues?page={page}&per_page=100")
        rows, info = payload.get("result"), payload.get("result_info")
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError("inventory_shape")
        if not isinstance(info, dict) or info.get("page") != page:
            raise ValueError("inventory_shape")
        total = info.get("total_pages")
        if type(total) is not int or not 1 <= total <= 100:
            raise ValueError("inventory_shape")
        queues.extend(rows)
        if page == total:
            return queues
    raise ValueError("inventory_incomplete")


def exact_queue(rows: list[dict], name: str) -> dict | None:
    """Reject duplicate names or malformed resource IDs rather than choosing one."""
    matches = [row for row in rows if row.get("queue_name") == name]
    if len(matches) > 1:
        raise ValueError("queue_ambiguous")
    if not matches:
        return None
    row = matches[0]
    if not isinstance(row.get("queue_id"), str) or not re.fullmatch(r"[0-9a-f]{32}", row["queue_id"]):
        raise ValueError("queue_shape")
    return row


def bounded_queue(row: dict) -> bool:
    """Require explicit one-day retention and immediate, unpaused delivery."""
    settings = row.get("settings")
    return (isinstance(settings, dict) and type(settings.get("message_retention_period")) is int
            and settings["message_retention_period"] == RETENTION
            and settings.get("delivery_delay", 0) == 0
            and settings.get("delivery_paused", False) is False)


def reconcile(account: str, token: str, target: str, phase: str) -> None:
    """Create only absent resources; readback never mutates or consumes messages."""
    suffix = "-staging" if target == "staging" else ""
    rows = inventory(account, token)
    for name in (f"amail-trace-dlq{suffix}", f"amail-trace-events{suffix}"):
        row = exact_queue(rows, name)
        if row is None:
            if phase != "queues":
                raise ValueError("queue_missing")
            request(account, token, "queues", {"queue_name": name, "settings": {
                "message_retention_period": RETENTION, "delivery_delay": 0, "delivery_paused": False}})
        elif not bounded_queue(row):
            raise ValueError("queue_settings_drift")
        elif phase == "queues":
            key = "AMAIL_TRACE_DLQ_ID" if name.startswith("amail-trace-dlq") else "AMAIL_TRACE_QUEUE_ID"
            expected = os.getenv(key, "")
            if not re.fullmatch(r"[0-9a-f]{32}", expected) or row["queue_id"] != expected:
                raise ValueError("existing_queue_ownership_unverified")
    # Fresh readback proves create completion; a timed-out POST is not retried here.
    rows = inventory(account, token)
    for name in (f"amail-trace-dlq{suffix}", f"amail-trace-events{suffix}"):
        row = exact_queue(rows, name)
        if row is None or not bounded_queue(row):
            raise ValueError("queue_settings_drift")
        detail = request(account, token, f"queues/{row['queue_id']}").get("result")
        if (not isinstance(detail, dict) or not bounded_queue(detail)
                or detail.get("queue_id") != row["queue_id"] or detail.get("queue_name") != name):
            raise ValueError("queue_settings_drift")
        consumers, producers = detail.get("consumers"), detail.get("producers")
        if (not isinstance(consumers, list) or not isinstance(producers, list)
                or type(detail.get("consumers_total_count")) is not int
                or detail["consumers_total_count"] != len(consumers)
                or type(detail.get("producers_total_count")) is not int
                or detail["producers_total_count"] != len(producers)):
            raise ValueError("ownership_shape")
        if name.startswith("amail-trace-dlq"):
            if consumers or producers:
                raise ValueError("dlq_consumer_unreviewed")
            continue
        if phase == "queues" and not consumers and not producers:
            continue
        if len(consumers) != 1 or not isinstance(consumers[0], dict):
            raise ValueError("consumer_drift")
        consumer = consumers[0]
        settings = consumer.get("settings")
        if (consumer.get("type") != "worker" or consumer.get("script_name") != f"amail-trace-sink{suffix}"
                or consumer.get("dead_letter_queue") != f"amail-trace-dlq{suffix}"
                or not isinstance(settings, dict)
                or any(settings.get(key) != value for key, value in {
                    "batch_size": 10, "max_wait_time_ms": 1000, "max_retries": 3,
                    "retry_delay": 30, "max_concurrency": 2}.items())):
            raise ValueError("consumer_drift")
        if phase == "queues" and not producers:
            continue
        if (len(producers) != 1 or not isinstance(producers[0], dict)
                or producers[0].get("type") != "worker"
                or producers[0].get("script") != f"amail-mail{suffix}"):
            raise ValueError("producer_drift")


def main() -> int:
    """Expose fixed deployment phases; no arbitrary queue, URL, or message input."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, choices=("staging", "production"))
    parser.add_argument("--phase", required=True, choices=("queues", "readback"))
    args = parser.parse_args()
    account, token = os.getenv("CLOUDFLARE_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_API_TOKEN", "")
    if not re.fullmatch(r"[0-9a-f]{32}", account) or not token:
        print("trace_queue=credentials_missing", file=sys.stderr)
        return 2
    try:
        reconcile(account, token, args.target, args.phase)
    except ValueError as error:
        print(f"trace_queue={error}", file=sys.stderr)
        return 1
    print(f"trace_queue_{args.phase}=match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
