"""Bracket exact staging email/Queue adapters without reading message payloads.

Immutable bindings come from reviewed TOML, not mutable settings. Complete Queue,
subscription and public-route inventories use existing bounded readers. No write,
HTTP probe, dequeue, replay or production selection is available.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "crates/mail-worker"))
sys.path.insert(0, str(ROOT / "infra/provider"))
import check_observability as capture
import check_trace_sink_isolation as isolation
import ensure_role_forwarding as forwarding
import ensure_trace_queues as queues
from check_mail_maintenance import config_realm, entry_surface_match, schedules_match
from ensure_email_events import EVENTS, ZONE
from pin_staging_mail import ACCOUNT, UUID, _bindings_match, serving_deployment

INGRESS = "amail-inbound-staging"
EVENTS_WORKER = "amail-events-staging"
QUEUE = "amail-sending-events-staging"
DLQ = "amail-sending-events-dlq-staging"
DOMAIN = "mail-staging.moesegfault.dev"


def source_configs() -> dict[str, dict]:
    """Require private capture-off source intent and exact staging dependencies."""
    selected = {}
    for folder, name, main in (("mail-ingress", INGRESS, "entry/email.mjs"),
                               ("mail-events", EVENTS_WORKER, "entry/queue.mjs")):
        path = ROOT / "workers" / folder / "wrangler.toml"
        with path.open("rb") as source:
            root = tomllib.load(source)
        value = config_realm(path, "staging")
        allowed = {"name", "workers_dev", "preview_urls", "vars", "services", "d1_databases",
                   "queues", "observability", "routes", "triggers", "logpush"}
        if (set(value) - allowed or root.get("main") != main or value.get("name") != name
                or value.get("workers_dev") is not False or value.get("preview_urls") is not False
                or value.get("routes", []) != [] or value.get("triggers", {"crons": []}) != {"crons": []}
                or value.get("logpush", False) is not False
                or not capture.capture_disabled(value.get("observability"))
                or value["observability"].get("logs", {}).get("invocation_logs") is not False
                or value["observability"].get("issues", {}).get("enabled") is not False):
            raise ValueError("adapter_source_unreviewed")
        selected[name] = value
    ingress, events = selected[INGRESS], selected[EVENTS_WORKER]
    api = config_realm(ROOT / "crates/mail-worker/wrangler.toml", "staging")
    if (ingress.get("services") != [{"binding": "MAIL_API", "service": "amail-mail-staging"}]
            or ingress.get("vars") != {"MAIL_API_ORIGIN": f"https://{DOMAIN}"}
            or events.get("d1_databases") != [{key: api["d1_databases"][0][key]
                                               for key in ("binding", "database_name", "database_id")}]
            or ingress.get("d1_databases") or ingress.get("queues") or events.get("services")
            or events.get("vars") != {"CF_ACCOUNT_ID": "07109e406d4e1ab7a0997dd399db6fd5",
                                       "CF_ZONE_ID": ZONE, "MAIL_DOMAIN": DOMAIN}
            or events.get("queues") != {"consumers": [{"queue": QUEUE, "max_batch_size": 10,
                "max_batch_timeout": 5, "max_retries": 5, "retry_delay": 120, "dead_letter_queue": DLQ}]}):
        raise ValueError("adapter_staging_resources_unreviewed")
    return selected


def expected_bindings(configs: dict[str, dict], script: str) -> dict:
    """Expose only ingress delegation/secret or lifecycle D1 plus exact vars."""
    value = configs[script]
    expected = {key: ("plain_text", text) for key, text in value["vars"].items()}
    if script == INGRESS:
        expected.update({"MAIL_API": ("service", value["services"][0]["service"]),
                         "INGRESS_SECRET": ("secret_text", None)})
    elif script == EVENTS_WORKER:
        expected["MAIL_DB"] = ("d1", value["d1_databases"][0]["database_id"])
    else:
        raise ValueError("adapter_script_unreviewed")
    return expected


def bindings_match(value: dict, version: str, expected: dict) -> bool:
    """Supplement the shared exact binding matcher with exact service target."""
    if not _bindings_match(value, version, expected):
        return False
    rows = value["resources"]["bindings"]
    rows = rows["result"] if isinstance(rows, dict) else rows
    return all(row.get("service") == expected[row["name"]][1]
               and row.get("entrypoint") is None and row.get("environment") in (None, "production")
               for row in rows if row.get("type") == "service")


def serving(account: str, token: str, pins: dict[str, str]) -> dict:
    """Select one exact 100-percent version and retain deployment identity."""
    result = {}
    for script, version in pins.items():
        pin = serving_deployment(capture.readback(account, token, script, "deployments?per_page=1&page=1"))
        if pin is None or pin[1] != version:
            raise ValueError("adapter_serving_unverified")
        result[script] = pin
    return result


def private_surfaces(account: str, token: str) -> None:
    """Exclude adapter workers.dev, previews, custom domains and all zone routes."""
    names = {INGRESS, EVENTS_WORKER}
    if any(row["service"] in names for row in isolation.worker_domains(account, token)):
        raise ValueError("adapter_public_surface_unverified")
    zones = isolation.inventory(token, f"/zones?account.id={account}&type=full,partial,secondary,internal")
    if not zones or len(zones) > 20:
        raise ValueError("adapter_zones_unverified")
    for zone in zones:
        if not isinstance(zone.get("account"), dict) or zone["account"].get("id") != account:
            raise ValueError("adapter_zones_unverified")
        payload = isolation.envelope(token, f"/zones/{zone['id']}/workers/routes")
        rows = payload.get("result")
        if (not isinstance(rows, list) or len(rows) > 1000 or payload.get("result_info") not in (None, {})
                or not all(isinstance(row, dict) and isinstance(row.get("id"), str)
                    and ACCOUNT.fullmatch(row["id"]) and isinstance(row.get("pattern"), str)
                    and (row.get("script") is None or isinstance(row["script"], str)) for row in rows)
                or len({row["id"] for row in rows}) != len(rows)
                or any(row.get("script") in names for row in rows)):
            raise ValueError("adapter_public_surface_unverified")


def lifecycle_snapshot(account: str, token: str) -> dict:
    """Require sole exact lifecycle consumer and one domain-scoped subscription.

    Queue consumer API milliseconds correspond to TOML batch timeout seconds.
    Subscription inventory is account-wide and page-complete: an extra delivery
    path for the staging domain or either selected queue is not silently adopted.
    https://developers.cloudflare.com/api/resources/queues/subresources/consumers/
    https://developers.cloudflare.com/api/resources/queues/subresources/subscriptions/methods/list/
    """
    catalog = queues.inventory(account, token)
    found = {name: queues.exact_queue(catalog, name) for name in (QUEUE, DLQ)}
    if any(row is None for row in found.values()):
        raise ValueError("adapter_queue_missing")
    details = {}
    for name, row in found.items():
        detail = queues.request(account, token, f"queues/{row['queue_id']}").get("result")
        if (not isinstance(detail, dict) or detail.get("queue_name") != name
                or detail.get("queue_id") != row["queue_id"]):
            raise ValueError("adapter_queue_unverified")
        for field in ("consumers", "producers"):
            items = detail.get(field)
            if (not isinstance(items, list) or type(detail.get(f"{field}_total_count")) is not int
                    or detail[f"{field}_total_count"] != len(items)):
                raise ValueError("adapter_queue_ownership_unverified")
        if detail["producers"] or (name == DLQ and detail["consumers"]):
            raise ValueError("adapter_queue_ownership_unverified")
        if name == QUEUE:
            consumers = detail["consumers"]
            if len(consumers) != 1 or not isinstance(consumers[0], dict):
                raise ValueError("adapter_consumer_unverified")
            consumer = consumers[0]
            settings = consumer.get("settings")
            if (consumer.get("type") != "worker" or consumer.get("script_name") != EVENTS_WORKER
                    or consumer.get("dead_letter_queue") != DLQ or not isinstance(settings, dict)
                    or any(type(settings.get(key)) is not int or settings[key] != value for key, value in
                           {"batch_size": 10, "max_wait_time_ms": 5000, "max_retries": 5, "retry_delay": 120}.items())
                    or settings.get("max_concurrency") is not None):
                raise ValueError("adapter_consumer_unverified")
        details[name] = {key: detail[key] for key in ("queue_id", "queue_name", "consumers", "producers")}
    subscriptions = forwarding.pages(forwarding.Client(token=token, account=account),
                                     f"/accounts/{account}/event_subscriptions/subscriptions")
    seen = set()
    related = []
    for row in subscriptions:
        identity, source, destination = row.get("id"), row.get("source"), row.get("destination")
        if (not isinstance(identity, str) or not 1 <= len(identity) <= 256 or identity in seen
                or not isinstance(source, dict) or not isinstance(destination, dict)):
            raise ValueError("adapter_subscription_unverified")
        seen.add(identity)
        if (source.get("type") == "email.sending" and source.get("domain") == DOMAIN
                or destination.get("queue_id") in {row["queue_id"] for row in found.values()}):
            related.append(row)
    if len(related) != 1:
        raise ValueError("adapter_subscription_unverified")
    subscription = related[0]
    if (subscription.get("name") != "amail-sending-lifecycle-staging" or subscription.get("enabled") is not True
            or subscription["source"] != {"type": "email.sending", "zone_id": ZONE, "domain": DOMAIN}
            or subscription["destination"] != {"type": "queues.queue", "queue_id": found[QUEUE]["queue_id"]}
            or not isinstance(subscription.get("events"), list)
            or sorted(subscription["events"]) != sorted(EVENTS.split(","))):
        raise ValueError("adapter_subscription_unverified")
    return {"queues": details, "subscription": subscription}


def verify(ingress_version: str, events_version: str) -> dict:
    """Bracket immutable adapters and non-versioned graph with exact serving pins."""
    configs = source_configs()
    account, token = os.getenv("CLOUDFLARE_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_API_TOKEN", "")
    pins = {INGRESS: ingress_version, EVENTS_WORKER: events_version}
    if (ACCOUNT.fullmatch(account) is None or not token
            or account != configs[EVENTS_WORKER]["vars"]["CF_ACCOUNT_ID"]
            or any(UUID.fullmatch(value) is None for value in pins.values())):
        raise ValueError("adapter_coordinates_unverified")
    before = serving(account, token, pins)
    first = lifecycle_snapshot(account, token)
    for script, version in pins.items():
        value = capture.readback(account, token, script, f"versions/{version}")
        if (not bindings_match(value, version, expected_bindings(configs, script))
                or not entry_surface_match(value, version, "email" if script == INGRESS else "queue")):
            raise ValueError("adapter_capabilities_unverified")
        settings = capture.readback(account, token, script, "settings")
        legacy = capture.readback(account, token, script, "script-settings")
        worker = capture.worker_readback(account, token, script)
        subdomain = capture.readback(account, token, script, "subdomain")
        if (not capture.effective_api_settings(worker, script, settings, legacy)
                or not isinstance(subdomain, dict) or subdomain.get("enabled") is not False
                or subdomain.get("previews_enabled") is not False
                or not schedules_match(capture.readback(account, token, script, "schedules"))):
            raise ValueError("adapter_capture_or_surface_unverified")
    private_surfaces(account, token)
    if lifecycle_snapshot(account, token) != first or serving(account, token, pins) != before:
        raise ValueError("adapter_graph_changed")
    return before


def main() -> int:
    """Print only a fixed result; provider bodies never reach public CI output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--ingress-version", default=os.getenv("AMAIL_EXPECTED_INGRESS_VERSION", ""))
    parser.add_argument("--events-version", default=os.getenv("AMAIL_EXPECTED_EVENTS_VERSION", ""))
    args = parser.parse_args()
    try:
        source_configs() if args.source_only else verify(args.ingress_version, args.events_version)
    except (ValueError, KeyError, TypeError, OSError, forwarding.ProvisionError):
        print("staging_adapters=UNVERIFIED")
        return 1
    print("staging_adapters=source_checked" if args.source_only else "staging_adapters=exact_selected_graph")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
