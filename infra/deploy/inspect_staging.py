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
    """Reuse the graph's single non-content capability projection."""
    from check_mail_split_graph import role_capabilities as project
    return project(version)


def routing_diagnostic(account: str) -> dict:
    """Project matcher shapes from the existing zone reader, never route values."""
    import ensure_role_forwarding as forwarding
    token = os.getenv("CF_EMAIL_ROUTING_TOKEN", "")
    if not token:
        return {"available": False, "reason": "routing_credentials_unavailable"}
    try:
        rows = forwarding.rules(forwarding.Client(token=token, account=account))
    except (ValueError, KeyError, TypeError, OSError, forwarding.ProvisionError):
        return {"available": False, "reason": "routing_read_unverified"}
    shapes = {name: 0 for name in ("null", "missing", "list", "invalid")}
    for row in rows:
        key = ("invalid" if not isinstance(row, dict) else "missing" if "matchers" not in row
               else "null" if row["matchers"] is None else "list" if isinstance(row["matchers"], list) else "invalid")
        shapes[key] += 1
    return {"available": True, "rows": len(rows), "matchers": shapes}


def canary_diagnostic(account: str, token: str) -> dict:
    """Read existing grant/audit predicates only; never expose ownership values.

    The fixed UTC window identifies the failed grant request's observation, not
    authority to replace its slot or submit its lost private intent.
    """
    sys.path.insert(0, str(ROOT / "infra/operator"))
    from direct_contact_health import DatabaseClient, HealthError, one_row
    sql = """
    SELECT 1 AS gate_present,
      (SELECT COUNT(*)=1 FROM send_policy WHERE scope='global' AND owner_iss='*'
       AND owner_sub='*' AND state='held') AS global_held,
      COALESCE(canary_expires_at>unixepoch(),0) AS live,
      canary_used_by IS NULL AS unused,
      (length(case_ref)=30 AND case_ref GLOB 'staging-owned-*') AS case_prefix_owned,
      updated_at BETWEEN unixepoch('2026-10-02 22:37:00') AND unixepoch('2026-10-02 22:38:00') AS recent_failed_grant_window,
      COALESCE((SELECT canary_owner_iss IS g.canary_owner_iss AND canary_owner_sub IS g.canary_owner_sub
       AND canary_recipient_sha256 IS g.canary_recipient_sha256 AND canary_expires_at IS g.canary_expires_at
       AND canary_used_by IS g.canary_used_by AND actor IS g.actor AND case_ref IS g.case_ref
       AND changed_at IS g.updated_at FROM send_release_gate_audit ORDER BY id DESC LIMIT 1),0) AS audit_match_latest,
      MAX(0,MIN(900,COALESCE(canary_expires_at-unixepoch(),0))) AS expires_remaining_seconds
    FROM send_release_gates AS g WHERE id=1
    """
    flags = ("gate_present", "global_held", "live", "unused", "case_prefix_owned",
             "recent_failed_grant_window", "audit_match_latest")
    try:
        row = one_row(DatabaseClient(account, token, "staging").query(sql))
        remaining = row.get("expires_remaining_seconds")
        if (any(type(row.get(key)) is not int or row[key] not in (0, 1) for key in flags)
                or type(remaining) is not int or not 0 <= remaining <= 900):
            raise ValueError("canary_shape_unverified")
    except (ValueError, KeyError, TypeError, OSError, HealthError):
        return {"available": False, "reason": "canary_read_unverified"}
    return {"available": True, **{key: bool(row[key]) for key in flags},
            "expires_remaining_seconds": remaining}


def split_diagnostic(result: dict) -> dict:
    """Read the full observed active graph; diagnostics never confer ownership."""
    import check_mail_split_graph as graph
    scripts = result["scripts"]
    os.environ.update({"AMAIL_EXPECTED_WORKER_VERSION": scripts["amail-mail-staging"]["version"],
                       "AMAIL_EXPECTED_MAINTENANCE_VERSION": scripts["amail-mail-maintenance-staging"]["version"],
                       "AMAIL_EXPECTED_TRACE_SINK_VERSION": scripts["amail-trace-sink-staging"]["version"],
                       "AMAIL_TRACE_TOPOLOGY": "api-scheduled"})
    try:
        graph.verify("staging", "active", allow_v012_predecessor=True)
    except (ValueError, KeyError, TypeError, OSError) as error:
        return {"exact_graph": False, "reason": graph.failure_reason(error)}
    return {"exact_graph": True, "reason": "verified"}


def adapter_diagnostic(result: dict) -> dict:
    """Read existing exact adapter pins and report only safe structural facts."""
    import check_staging_adapters as adapters
    scripts = result["scripts"]
    outcome = {"exact_graph": True, "reason": "verified"}
    try:
        adapters.verify(scripts[adapters.INGRESS]["version"], scripts[adapters.EVENTS_WORKER]["version"])
    except (ValueError, KeyError, TypeError, OSError, adapters.forwarding.ProvisionError) as error:
        outcome = {"exact_graph": False, "reason": adapters.failure_reason(error)}
    try:
        outcome["facts"] = adapters.diagnostic_facts(os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
                                                      os.getenv("CLOUDFLARE_API_TOKEN", ""))
    except (ValueError, KeyError, TypeError, OSError, adapters.forwarding.ProvisionError):
        outcome["facts"] = {"read": "unverified"}
    return outcome


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
    result["routing_checks"] = routing_diagnostic(account)
    result["canary_checks"] = canary_diagnostic(account, token)
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
    if all(result["scripts"][name]["present"] for name in ("amail-inbound-staging", "amail-events-staging")):
        result["adapter_checks"] = adapter_diagnostic(result)
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
