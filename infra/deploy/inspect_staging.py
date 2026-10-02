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


def role_capabilities(version: dict) -> dict:
    """Project capability facts without secret values, destination addresses or mail."""
    resources = version.get("resources", {})
    bindings = resources.get("bindings")
    if isinstance(bindings, dict) and set(bindings) == {"result"}:
        bindings = bindings["result"]
    handlers = resources.get("script", {}).get("handlers")
    if (not isinstance(bindings, list) or not all(isinstance(row, dict) for row in bindings)
            or not isinstance(handlers, list) or any(item not in ("fetch", "scheduled", "email", "queue") for item in handlers)):
        raise ValueError("staging_role_metadata_unverified")
    return {
        "handlers": handlers,
        "mail_database_bound": any(row.get("type") == "d1" and row.get("database_id") == "74f35f95-42ce-482c-86e6-dffbdd35cbbe" for row in bindings),
        "mail_service_bound": any(row.get("type") == "service" and row.get("service") in
                                  ("amail-mail-staging", "amail-mail-maintenance-staging") for row in bindings),
        "mail_body_bucket_bound": any(row.get("type") == "r2_bucket" and row.get("bucket_name") == "moesegfault-mail-raw-staging" for row in bindings),
        "mail_trace_queue_bound": any(row.get("type") == "queue" and
                                       (row.get("queue_id") == os.getenv("AMAIL_TRACE_QUEUE_ID", "")
                                        or row.get("queue_name") == "amail-trace-events-staging") for row in bindings),
    }


def split_diagnostic(result: dict) -> dict:
    """Read the full observed active graph; diagnostics never confer ownership."""
    import check_mail_split_graph as graph
    scripts = result["scripts"]
    os.environ.update({"AMAIL_EXPECTED_WORKER_VERSION": scripts["amail-mail-staging"]["version"],
                       "AMAIL_EXPECTED_MAINTENANCE_VERSION": scripts["amail-mail-maintenance-staging"]["version"],
                       "AMAIL_EXPECTED_TRACE_SINK_VERSION": scripts["amail-trace-sink-staging"]["version"],
                       "AMAIL_TRACE_TOPOLOGY": "api-scheduled"})
    try:
        graph.verify("staging", "active")
    except (ValueError, KeyError, TypeError, OSError) as error:
        return {"exact_graph": False, "reason": graph.failure_reason(error)}
    return {"exact_graph": True, "reason": "verified"}


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
    catalog = queues.inventory(account, token)
    trace_ids = {}
    for name in ("amail-trace-events-staging", "amail-trace-dlq-staging"):
        row = queues.exact_queue(catalog, name)
        if row is not None:
            trace_ids[name] = row["queue_id"]
    # Observed IDs support read-only diagnostics, not resource adoption authority.
    if len(trace_ids) == 2:
        os.environ["AMAIL_TRACE_QUEUE_ID"] = trace_ids["amail-trace-events-staging"]
        os.environ["AMAIL_TRACE_DLQ_ID"] = trace_ids["amail-trace-dlq-staging"]
    result = {"schema": "staging-predecessor/v1", "source_sha": os.getenv("GITHUB_SHA", ""),
              "run_id": os.getenv("GITHUB_RUN_ID", ""), "scripts": {}, "queues": {},
              "legacy_role_present": "amail-role-monitor-staging" in present}
    if result["legacy_role_present"]:
        script = "amail-role-monitor-staging"
        before = serving_deployment(capture.readback(account, token, script, "deployments?per_page=1&page=1"))
        if before is None:
            raise ValueError("staging_role_metadata_unverified")
        facts = role_capabilities(capture.readback(account, token, script, f"versions/{before[1]}"))
        schedules = capture.readback(account, token, script, "schedules").get("schedules")
        if not isinstance(schedules, list) or any(not isinstance(row, dict) or not isinstance(row.get("cron"), str) for row in schedules):
            raise ValueError("staging_role_metadata_unverified")
        facts["crons"] = [row["cron"] for row in schedules]
        if serving_deployment(capture.readback(account, token, script, "deployments?per_page=1&page=1")) != before:
            raise ValueError("staging_role_metadata_unverified")
        result["legacy_role_capabilities"] = facts
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
            import check_trace_sink_isolation as sink
            # A sink-only legacy preparation is not the final two-producer graph.
            topology = "api-scheduled" if "amail-mail-maintenance-staging" in present else "api-only"
            os.environ["AMAIL_TRACE_TOPOLOGY"] = topology
            result["sink_checks"] = {
                "topology_checked": topology,
                "immutable_capabilities": sink.version_isolated(version, before[1]),
                "retained_settings": all(capture.safe_settings(value, sink=True) for value in (settings, script_settings)),
                "private_surfaces": sink.surfaces_private(account, token, script, capture.readback),
                "queue_trigger": sink.queue_trigger_exact(account, token, "staging", script),
            }
            private = capture.verify("staging", account, token, sink=True)
        if serving_deployment(capture.readback(account, token, script, "deployments?per_page=1&page=1")) != before:
            raise ValueError("staging_serving_changed")
        result["scripts"][script] = {"present": True, "deployment": before[0], "version": before[1],
                                     "handlers": handlers, "crons": [row["cron"] for row in rows],
                                     "usage_model": resources.get("script_runtime", {}).get("usage_model"),
                                     "capture_off": private}
        if script == "amail-trace-sink-staging":
            # Sanitized sink logs intentionally remain enabled. Safety of that
            # private retention is not a claim that provider capture is disabled.
            result["scripts"][script]["capture_off"] = capture.capture_disabled(worker.get("observability"))
            result["scripts"][script]["privacy_safe"] = private
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
    if all(result["scripts"][name]["present"] for name in
           ("amail-mail-staging", "amail-mail-maintenance-staging", "amail-trace-sink-staging")):
        result["split_checks"] = split_diagnostic(result)
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
