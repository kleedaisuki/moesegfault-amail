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
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "https://api.cloudflare.com/client/v4"
RETENTION = 86400
LIMIT = 262144


def request(account: str, token: str, path: str, body: dict | None = None, *, method: str | None = None):
    """Read a bounded API envelope; never include provider error text in failures."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    req = Request(f"{API}/accounts/{account}/{path}", headers=headers,
                  data=json.dumps(body).encode() if body is not None else None, method=method)
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
    """Read the documented unfiltered SyncSinglePage endpoint with bounded completeness guards."""
    payload = request(account, token, "queues")
    if set(payload) - {"success", "errors", "messages", "result", "result_info"}:
        raise ValueError("inventory_incomplete")
    rows = payload.get("result")
    if not isinstance(rows, list) or len(rows) > 10000 or not all(isinstance(row, dict) for row in rows):
        raise ValueError("inventory_shape")
    info = payload.get("result_info")
    if info is not None:
        if not isinstance(info, dict):
            raise ValueError("inventory_shape")
        if set(info) - {"page", "count", "total_count", "total_pages", "per_page"}:
            raise ValueError("inventory_incomplete")
        for field, expected in (("page", 1), ("count", len(rows)), ("total_count", len(rows))):
            if field in info and (type(info[field]) is not int or info[field] != expected):
                raise ValueError("inventory_incomplete")
        if "total_pages" in info and (type(info["total_pages"]) is not int
                or info["total_pages"] not in ({0, 1} if not rows else {1})):
            raise ValueError("inventory_incomplete")
        if "per_page" in info and (type(info["per_page"]) is not int
                or not max(1, len(rows)) <= info["per_page"] <= 10000):
            raise ValueError("inventory_incomplete")
    ids: set[str] = set()
    names: set[str] = set()
    for row in rows:
        queue_id, name = row.get("queue_id"), row.get("queue_name")
        if (not isinstance(queue_id, str) or not re.fullmatch(r"[0-9a-f]{32}", queue_id)
                or not isinstance(name, str) or not 1 <= len(name) <= 255
                or queue_id in ids or name in names):
            raise ValueError("inventory_identity")
        ids.add(queue_id)
        names.add(name)
    return rows


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


def validate_detail(detail: object, name: str, queue_id: str, suffix: str, phase: str) -> None:
    """Require complete exact attachment ownership before mutating any peer resource."""
    if (not isinstance(detail, dict) or (phase != "recover" and not bounded_queue(detail))
            or detail.get("queue_id") != queue_id or detail.get("queue_name") != name):
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
        return
    if phase in ("queues", "recover") and not consumers and not producers:
        return
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
    if phase in ("queues", "recover") and not producers:
        return
    if (len(producers) != 1 or not isinstance(producers[0], dict)
            or producers[0].get("type") != "worker"
            or producers[0].get("script") != f"amail-mail{suffix}"):
        raise ValueError("producer_drift")


def record_creation(target: str, name: str, queue_id: str) -> None:
    """Preserve fresh identity before PATCH in a restricted Actions recovery artifact."""
    workspace = os.getenv("GITHUB_WORKSPACE")
    if not workspace:
        raise ValueError("recovery_workspace_missing")
    path = Path(workspace) / ".temp" / f"trace-queue-provision-{target}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    records = json.loads(path.read_text()) if path.exists() else []
    if not isinstance(records, list) or len(records) >= 2:
        raise ValueError("recovery_record_unverified")
    records.append({"target": target, "queue_name": name, "queue_id": queue_id})
    with path.open("w", encoding="utf-8") as destination:
        json.dump(records, destination)
    path.chmod(0o600)


def reconcile(account: str, token: str, target: str, phase: str) -> None:
    """Create only absent resources; readback never mutates or consumes messages."""
    suffix = "-staging" if target == "staging" else ""
    rows = inventory(account, token)
    names = (f"amail-trace-dlq{suffix}", f"amail-trace-events{suffix}")
    identities: dict[str, str] = {}
    # Validate every existing resource before any mutation, even when its peer is absent.
    for name in names:
        row = exact_queue(rows, name)
        if row is None:
            if phase == "readback":
                raise ValueError("queue_missing")
            continue
        if phase != "recover" and not bounded_queue(row):
            raise ValueError("queue_settings_drift")
        key = "AMAIL_TRACE_DLQ_ID" if name.startswith("amail-trace-dlq") else "AMAIL_TRACE_QUEUE_ID"
        expected = os.getenv(key, "")
        if not re.fullmatch(r"[0-9a-f]{32}", expected) or row["queue_id"] != expected:
            raise ValueError("existing_queue_ownership_unverified")
        identities[name] = expected
    if phase == "queues":
        for name, queue_id in identities.items():
            detail = request(account, token, f"queues/{queue_id}").get("result")
            validate_detail(detail, name, queue_id, suffix, phase)
    for name in names:
        if name in identities or phase != "queues":
            continue
        response = request(account, token, "queues", {"queue_name": name})
        result = response.get("result")
        created = exact_queue([result], name) if isinstance(result, dict) else None
        if created is None:
            raise ValueError("created_queue_unverified")
        identities[name] = created["queue_id"]
        record_creation(target, name, created["queue_id"])
        # The create API accepts only identity fields. Configure only this newly
        # returned ID; never edit settings of a preexisting resource.
        patched = request(account, token, f"queues/{created['queue_id']}", {"settings": {
            "message_retention_period": RETENTION, "delivery_delay": 0, "delivery_paused": False}},
            method="PATCH").get("result")
        if (not isinstance(patched, dict) or patched.get("queue_id") != created["queue_id"]
                or patched.get("queue_name") != name or not bounded_queue(patched)):
            raise ValueError("created_queue_settings_unverified")
    if not identities or len(set(identities.values())) != len(identities):
        raise ValueError("queue_identity_ambiguous")
    # Fresh readback must match the exact create response or reviewed existing identity.
    rows = inventory(account, token)
    for name in identities:
        row = exact_queue(rows, name)
        if row is None or (phase != "recover" and not bounded_queue(row)) or row["queue_id"] != identities[name]:
            raise ValueError("queue_settings_drift")
        detail = request(account, token, f"queues/{row['queue_id']}").get("result")
        validate_detail(detail, name, row["queue_id"], suffix, phase)
        if phase == "recover":
            print("trace_queue_recovery_retention=" + ("within_boundary" if bounded_queue(detail) else "not_ready"))
    output = os.getenv("GITHUB_OUTPUT")
    if phase == "queues" and output:
        # Non-secret resource IDs connect the authorized create step to this exact rollout.
        with open(output, "a", encoding="utf-8") as destination:
            destination.write(f"queue_id={identities[names[1]]}\ndlq_id={identities[names[0]]}\n")


def main() -> int:
    """Expose fixed deployment phases; no arbitrary queue, URL, or message input."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, choices=("staging", "production"))
    parser.add_argument("--phase", required=True, choices=("queues", "readback", "recover"))
    args = parser.parse_args()
    account, token = os.getenv("CLOUDFLARE_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_API_TOKEN", "")
    if not re.fullmatch(r"[0-9a-f]{32}", account) or not token:
        print("trace_queue=credentials_missing", file=sys.stderr)
        return 2
    try:
        if args.phase == "queues" and not os.getenv("GITHUB_WORKSPACE"):
            raise ValueError("recovery_workspace_missing")
        reconcile(account, token, args.target, args.phase)
    except ValueError as error:
        print(f"trace_queue={error}", file=sys.stderr)
        return 1
    print("trace_queue_recover=exact_inventory_only" if args.phase == "recover" else f"trace_queue_{args.phase}=match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
