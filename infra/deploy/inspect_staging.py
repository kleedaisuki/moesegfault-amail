"""Read the fixed staging rollout predecessor; never mutate a provider resource.

The small public artifact contains infrastructure pins and capability facts only.
It is a snapshot, not deployment authority or proof that scheduled work drained.
Missing resources require a successful bounded inventory, never a failed GET.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "crates/mail-worker"))
import check_observability as capture
import ensure_trace_queues as queues
from check_production_role_graph import role
from check_staging import check
from pin_staging_mail import ACCOUNT, serving_deployment

SCRIPTS = ("amail-mail-staging", "amail-mail-maintenance-staging", "amail-inbound-staging",
           "amail-events-staging", "amail-trace-sink-staging")


def inspect() -> dict:
    """Bracket reviewed serving pins and explicitly project non-content facts."""
    check()
    account, token = os.getenv("CLOUDFLARE_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_API_TOKEN", "")
    if ACCOUNT.fullmatch(account) is None or not token:
        raise ValueError("staging_credentials_unverified")
    inventory = role.api_get(f"/accounts/{account}/workers/scripts", token)
    if (not isinstance(inventory, list) or len(inventory) > 10000
            or not all(isinstance(row, dict) and isinstance(row.get("id"), str) for row in inventory)
            or len({row["id"] for row in inventory}) != len(inventory)):
        raise ValueError("staging_inventory_unverified")
    present = {row["id"] for row in inventory}
    result = {"schema": "staging-predecessor/v1", "source_sha": os.getenv("GITHUB_SHA", ""),
              "run_id": os.getenv("GITHUB_RUN_ID", ""), "scripts": {}, "queues": {}}
    for script in SCRIPTS:
        if script not in present:
            result["scripts"][script] = {"present": False}
            continue
        before = serving_deployment(capture.readback(account, token, script, "deployments?per_page=1&page=1"))
        if before is None:
            raise ValueError("staging_serving_unverified")
        version = capture.readback(account, token, script, f"versions/{before[1]}")
        resources = version.get("resources", {})
        handlers = resources.get("script", {}).get("handlers")
        if not isinstance(handlers, list) or any(item not in ("fetch", "scheduled", "email", "queue") for item in handlers):
            raise ValueError("staging_handlers_unverified")
        schedules = capture.readback(account, token, script, "schedules")
        rows = schedules.get("schedules")
        if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get("cron"), str) for row in rows):
            raise ValueError("staging_schedules_unverified")
        settings = capture.readback(account, token, script, "settings")
        script_settings = capture.readback(account, token, script, "script-settings")
        worker = capture.worker_readback(account, token, script)
        private = capture.effective_api_settings(worker, script, settings, script_settings)
        if script == "amail-trace-sink-staging":
            os.environ["AMAIL_EXPECTED_TRACE_SINK_VERSION"] = before[1]
            private = capture.verify("staging", account, token, sink=True)
        if serving_deployment(capture.readback(account, token, script, "deployments?per_page=1&page=1")) != before:
            raise ValueError("staging_serving_changed")
        result["scripts"][script] = {"present": True, "deployment": before[0], "version": before[1],
                                     "handlers": handlers, "crons": [row["cron"] for row in rows],
                                     "usage_model": resources.get("script_runtime", {}).get("usage_model"),
                                     "capture_off": private}
    inventory = queues.inventory(account, token)
    for name in ("amail-trace-events-staging", "amail-trace-dlq-staging"):
        row = queues.exact_queue(inventory, name)
        if row is None:
            result["queues"][name] = {"present": False}
            continue
        detail = queues.request(account, token, f"queues/{row['queue_id']}").get("result")
        producers = detail.get("producers") if isinstance(detail, dict) else None
        if not isinstance(producers, list):
            raise ValueError("staging_queue_unverified")
        scripts = [item.get("script") for item in producers]
        if any(not isinstance(script, str) or script not in SCRIPTS for script in scripts):
            raise ValueError("staging_producer_unreviewed")
        result["queues"][name] = {"present": True, "queue_id": row["queue_id"],
                                  "bounded_retention": queues.bounded_queue(detail), "producers": scripts}
    return result


def main() -> int:
    """Persist only explicitly projected facts; provider prose never enters logs."""
    try:
        result = inspect()
        path = ROOT / ".temp/staging-predecessor.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except (ValueError, KeyError, TypeError, OSError):
        print("staging_predecessor=UNVERIFIED")
        return 1
    print("staging_predecessor=observed drain=UNVERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
