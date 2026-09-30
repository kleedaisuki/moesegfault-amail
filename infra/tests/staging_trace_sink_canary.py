"""Attest one bounded CLI/API trace window after the Queue-only sink migration.

No raw event, marker, application ID or provider exception is printed or stored.
The sink window is cursor/count-complete; this is not lossless global tracing or
an inspection of pending Queue/DLQ envelopes. Settings and serving versions are
pinned both before traffic and after retained readback.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

import staging_trace_canary as legacy

SINK = "amail-trace-sink-staging"
CONFIRM = "RUN_STAGING_TRACE_SINK_CANARY"
SUCCESS = "staging_trace_sink_canary: bounded_retained_privacy_and_parentage_verified"
RETRY_SECONDS = (125, 60)


def settings_module():
    """Load the reviewed source/sink effective-settings checker without test code."""
    sys.path.insert(0, str(legacy.ROOT / "crates/mail-worker"))
    import check_observability
    return check_observability


def require_pins(account: str, token: str, source_version: str, sink_version: str) -> None:
    """Reject missing, split or changed versions; never expose readback bodies."""
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location("trace_pin", legacy.ROOT / "infra/deploy/pin_staging_mail.py")
    pin = module_from_spec(spec)
    spec.loader.exec_module(pin)
    reader = settings_module()
    for service, expected in ((legacy.WORKER, source_version), (SINK, sink_version)):
        legacy.need(legacy.UUID.fullmatch(expected) is not None, "sink_serving_pin_invalid")
        try:
            active = pin.serving_deployment(reader.readback(account, token, service, "deployments"))
        except ValueError:
            active = None
        legacy.need(active is not None and active[1] == expected, "sink_serving_pin_unverified")


def preflight(account: str, obs: str, deploy: str, source_version: str, sink_version: str) -> None:
    """Require effective source-off/sink-on policies before native login or traffic."""
    reader = settings_module()
    try:
        safe = reader.verify("staging", account, deploy) and reader.verify("staging", account, deploy, sink=True)
    except (ValueError, TypeError):
        safe = False
    legacy.need(safe, "sink_privacy_settings_unverified")
    require_pins(account, deploy, source_version, sink_version)
    payload = legacy.request_json(account, obs, "keys", {"limit": 1000})
    rows = payload.get("result")
    legacy.need(isinstance(rows, list) and any(isinstance(row, dict)
                and row.get("key") == "$metadata.service" and row.get("type") == "string"
                for row in rows), "service_filter_key_unverified")


def probe(cli: Path, home: Path):
    """Run one CLI read, then one anonymous POST with four synthetic marker carriers."""
    from staging_trace_http_compare import BIN, reqwest_environment
    # Reuse CLI-only environment/journal contracts, not legacy's denial request.
    from staging_identity_cdp import browser_environment
    environment = browser_environment()
    environment.update({"AMAIL_HOME": str(home), "AMAIL_API_BASE": legacy.API,
                        "AMAIL_ISSUER": "https://identity-staging.moesegfault.dev",
                        "AMAIL_CLIENT_ID": "amail-cli-staging",
                        "AMAIL_REDIRECT_URI": "http://127.0.0.1/callback"})
    watermark = legacy.journal_max(home)
    start = int(time.time() * 1000) - 2000
    result = subprocess.run([str(cli), "address", "list"], env=environment,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=30, check=False)
    legacy.need(result.returncode == 0, "cli_address_list_failed")
    ids = legacy.journal_new(home, watermark)
    suffix = uuid.uuid4().hex
    markers = tuple(f"amail_{carrier}_canary_{suffix}" for carrier in ("path", "query", "body", "header"))
    target = f"{legacy.API}/v1/messages/{markers[0]}?probe={markers[1]}"
    legacy.need(BIN.is_file(), "rejected_url_helper_missing")
    result = subprocess.run([str(BIN), "--sink-private-id"], input=(target + "\n").encode("ascii"),
                            env=reqwest_environment(), stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=35, check=False)
    match = re.fullmatch(rb"staging_http_compare: private_id=([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\r?\n",
                         result.stdout) if len(result.stdout) <= 96 else None
    legacy.need(result.returncode == 0 and match is not None, "rejected_url_contract_failed")
    return start, int(time.time() * 1000) + 2000, ids, match.group(1).decode("ascii"), markers


DIAGNOSTIC_CODES = frozenset({
    "routing_reconciliation_failed", "outbound_reconciliation_failed",
    "semantic_index_retry_failed", "storage_ledger_reconciliation_failed",
    "deleted_message_cleanup_failed", "orphan_object_cleanup_failed",
    "search_job_cleanup_failed", "abuse_data_cleanup_failed",
    "address_reconciliation_batch_full", "non_enabled_committed_routing_rule",
    "non_enabled_provisioning_routing_rule", "semantic_document_quarantined",
    "semantic_provider_cooldown", "storage_ledger_state_deferred",
})


def canonical_uuid(value: object) -> bool:
    """Match the producer's canonical lower-case UUIDv4 domain."""
    return isinstance(value, str) and legacy.UUID.fullmatch(value) is not None and uuid.UUID(value).version == 4


def safe_event(event: dict) -> bool:
    """Mirror the strict typed wire domain, not merely JSON parseability."""
    if not canonical_uuid(event.get("event_id")) or type(event.get("schema_version")) is not int:
        return False
    if not canonical_uuid(event.get("request_id")) and event.get("request_id") is not None:
        return False
    for key, width in (("trace_id", 32), ("span_id", 16), ("parent_span_id", 16)):
        value = event.get(key)
        if key == "trace_id" or value is not None:
            if not isinstance(value, str) or not re.fullmatch(f"[0-9a-f]{{{width}}}", value) or int(value, 16) == 0:
                return False
    for key, maximum in (("duration_ms_bucket", 1 << 22), ("request_bytes_bucket", 1 << 32),
                         ("response_bytes_bucket", 1 << 32)):
        value = event.get(key)
        if (key == "duration_ms_bucket" or value is not None) and (
                type(value) is not int or not 0 <= value <= maximum or (value and value & (value - 1))):
            return False
    status = event.get("http_status_class")
    if status is not None and (type(status) is not int or not 0 <= status <= 5):
        return False
    stripped = {key: value for key, value in event.items() if key != "event_id"}
    if event.get("phase") == "maintenance":
        return set(stripped).issubset(legacy.EVENT_KEYS | {"diagnostic_code"}) and (
            event.get("schema_version") == 1 and event.get("service") == "mail_api"
            and event.get("operation") == "maintenance" and event.get("span_id") is not None
            and event.get("request_id") is not None and event.get("parent_span_id") is None
            and event.get("outcome") == "phase_failure" and event.get("error_code") == "dependency_failure"
            and event.get("diagnostic_code") in DIAGNOSTIC_CODES
            and all(event.get(key) is None for key in ("http_status_class", "request_bytes_bucket",
                        "response_bytes_bucket", "provider_http_status", "provider_error_code")))
    return legacy.allowlisted_event(stripped)


def assess(records: list[dict], ids: tuple[str, str, str], denied_id: str,
           markers: tuple[str, ...]) -> None:
    """Scan whole retained records, deduplicate at-least-once copies, and prove two roots."""
    legacy.need(bool(records), "retained_window_empty")
    legacy.retained_record_ids(records)
    unique: dict[str, dict] = {}
    for record in records:
        legacy.need(not any(marker in json.dumps(record, ensure_ascii=False) for marker in markers),
                    "synthetic_marker_retained")
        metadata = record.get("$metadata")
        workers = record.get("$workers")
        legacy.need(isinstance(record.get("dataset"), str) and bool(record["dataset"])
                    and "source" in record, "sink_record_shape_unverified")
        legacy.need(isinstance(metadata, dict) and metadata.get("service") == SINK,
                    "service_filter_not_enforced")
        legacy.need(isinstance(workers, dict) and workers.get("truncated") is False,
                    "sink_record_truncated_or_unverified")
        source, message = record.get("source"), metadata.get("message")
        left, right = legacy.embedded_events(source), legacy.embedded_events(message)
        legacy.need((legacy.empty_log_payload(source) or bool(left))
                    and (legacy.empty_log_payload(message) or bool(right)), "unreviewed_retained_payload")
        legacy.need(bool(left or right) and (not left or not right or left == right),
                    "application_event_representations_conflict")
        for event in left or right:
            legacy.need(safe_event(event), "application_event_schema_unallowlisted")
            event_id = event["event_id"]
            legacy.need(event_id not in unique or unique[event_id] == event, "sink_duplicate_event_conflict")
            unique[event_id] = event
    events = list(unique.values())
    trace_id, cli_span, request_id = ids
    roots = [event for event in events if event.get("request_id") == request_id
             and event.get("phase") == "request_exit" and event.get("operation") == "addresses_list"]
    legacy.need(len(roots) == 1, "cli_api_root_missing_or_duplicate")
    root = roots[0]
    legacy.need(root.get("service") == "mail_api" and root.get("trace_id") == trace_id
                and root.get("parent_span_id") == cli_span and root.get("span_id") != cli_span
                and isinstance(root.get("span_id"), str) and legacy.HEX16.fullmatch(root["span_id"])
                and root.get("http_status_class") == 2 and root.get("outcome") == "success",
                "cli_api_parentage_invalid")
    denied = [event for event in events if event.get("request_id") == denied_id]
    legacy.need(bool(denied), "rejected_request_event_missing")
    legacy.need(len(denied) == 1, "rejected_request_event_duplicate")
    event = denied[0]
    suffix = markers[0].removeprefix("amail_path_canary_")
    legacy.need(event.get("service") == "mail_api" and event.get("phase") == "request_exit"
                and event.get("parent_span_id") is None and event.get("trace_id") not in (trace_id, suffix)
                and event.get("http_status_class") == 4 and event.get("error_code") == "unauthorized"
                and event.get("outcome") == "client_error", "rejected_request_event_invalid")


def execute(cli: Path, home: Path, source_version: str, sink_version: str) -> None:
    """One bounded traffic window; late readback never repeats traffic or widens scope."""
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    obs, deploy = os.environ.get("CF_OBSERVABILITY_TOKEN", ""), os.environ.get("CLOUDFLARE_API_TOKEN", "")
    legacy.need(legacy.HEX32.fullmatch(account) is not None and bool(obs and deploy), "sink_capability_missing")
    preflight(account, obs, deploy, source_version, sink_version)
    cli, home = legacy.under_temp(cli), legacy.under_temp(home)
    start, end, ids, denied, markers = probe(cli, home)
    # Queue consumption/indexing is asynchronous. Expand only the original upper
    # bound once, immediately after probes, to include bounded consumer delay.
    end += 120_000
    previous_ids: set[str] = set()
    for index, delay in enumerate(RETRY_SECONDS):
        time.sleep(delay)
        records = legacy.retained_events(account, obs, start, end, service=SINK)
        current_ids = legacy.retained_record_ids(records)
        legacy.need(previous_ids <= current_ids, "observability_record_ids_regressed")
        previous_ids = current_ids
        try:
            assess(records, ids, denied, markers)
        except legacy.CanaryError as error:
            if index == 0 and error.args[0] in ("retained_window_empty", "cli_api_root_missing_or_duplicate",
                                               "rejected_request_event_missing"):
                continue
            raise
        break
    source = legacy.retained_events(account, obs, start, end)
    legacy.need(not source, "source_retained_records_present")
    preflight(account, obs, deploy, source_version, sink_version)


def main() -> int:
    """Emit a fixed result only; raw exceptions and query data remain process-private."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", choices=[CONFIRM], required=True)
    parser.add_argument("--amail", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--sink-version", required=True)
    args = parser.parse_args()
    try:
        execute(args.amail, args.home, args.source_version, args.sink_version)
    except legacy.CanaryError as error:
        print(f"staging_trace_sink_canary: UNVERIFIED ({error.args[0]})")
        return 1
    except Exception:
        print("staging_trace_sink_canary: UNVERIFIED (local_probe_unavailable)")
        return 1
    print(SUCCESS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
