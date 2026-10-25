"""Inspect or finish only the admitted v0.3.1 paused staging transition.

The original attempt installed its API/sink, applied 0018 and completed the old
scheduled-cohort boundary. A continuation never repeats those writes or treats
the failed overall run as a successful deployment.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
import accepted_staging_artifact as accepted
import mail_schema_contract as schema
import staging_rollout as rollout
from direct_contact_health import DatabaseClient

ORIGIN_RUN = "40188956353"
ORIGIN_SHA = "f262e8e433ffeabb7d67d0fc26c363be7e4133f8"
API = "d592cd2a-95a3-4c89-859a-18a191bd641a"
PAUSED = "e42df778-c8a8-4975-abdd-83cb73dad372"
SINK = "5e556087-9a75-40db-9eb5-869a4b56372e"
QUEUE = "fcee510036af42c189e28c0b6ff9508e"
DLQ = "f023f804b7bd4d8691fbfcb60416a001"
RECEIPT = ROOT / ".temp/staging-semantic-recovery.json"
INSPECTION = ROOT / ".temp/staging-semantic-inspection.json"
JOURNEY_ADMISSION = ROOT / ".temp/staging-semantic-journey-admission.json"
JOURNEY_RUNTIME = ROOT / ".temp/staging-semantic-runtime.json"
SCHEMA_ERRORS = frozenset({
    "schema_objects_unverified", "schema_object_drift", "schema_columns_unverified",
    "schema_indexes_unverified", "schema_index_columns_unverified",
    "schema_migration_provenance_unverified", "schema_sql_unverified",
    "schema_rows_unverified", "schema_duplicate_unverified",
})


def context(mode: str) -> None:
    confirmation = {"inspect": "INSPECT_STAGING_SEMANTIC_V031",
                    "recover": "RUN_STAGING_SEMANTIC_RECOVERY_V031",
                    "journey": "RUN_STAGING_SEMANTIC_V031"}
    expected = {
        "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "kleedaisuki/moesegfault-amail",
        "GITHUB_REF": "refs/heads/codex/v0.3.1-semantic-consent",
        "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_RUN_ATTEMPT": "1",
        "AMAIL_SOURCE_RUN": ORIGIN_RUN, "AMAIL_STAGING_ENVIRONMENT": "staging",
        "AMAIL_STAGING_CONFIRM": confirmation.get(mode, ""),
    }
    if mode not in confirmation or any(os.getenv(key) != value for key, value in expected.items()):
        raise ValueError("staging_semantic_recovery_context_unverified")
    if accepted.producer(ORIGIN_RUN)["source_sha"] != ORIGIN_SHA:
        raise ValueError("staging_semantic_recovery_origin_unverified")
    accepted.runtime_closure(ORIGIN_SHA, os.environ["GITHUB_SHA"])


def select(maintenance: str) -> None:
    os.environ.update({
        "AMAIL_EXPECTED_WORKER_VERSION": API,
        "AMAIL_EXPECTED_MAINTENANCE_VERSION": maintenance,
        "AMAIL_EXPECTED_TRACE_SINK_VERSION": SINK,
        "AMAIL_TRACE_QUEUE_ID": QUEUE, "AMAIL_TRACE_DLQ_ID": DLQ,
        "AMAIL_TRACE_TOPOLOGY": "api-scheduled",
    })


def paused_graph() -> None:
    select(PAUSED)
    rollout.graph.verify("staging", "paused")


def witness() -> None:
    value = json.loads(rollout.WITNESS.read_text(encoding="utf-8"))
    if (value.get("schema") != "staging-semantic-cutover/v1"
            or value.get("source_sha") != ORIGIN_SHA or value.get("run_id") != ORIGIN_RUN
            or value.get("api_version") != API or value.get("paused_maintenance_version") != PAUSED
            or value.get("old_usage_model") != "standard"
            or type(value.get("observed_monotonic_seconds")) not in (int, float)
            or value["observed_monotonic_seconds"] < rollout.WINDOW_SECONDS
            or value.get("pin_samples", 0) < 2
            or value.get("old_http_drain") != "NOT_CLAIMED"):
        raise ValueError("staging_semantic_recovery_origin_unverified")


def schema_facts(database: DatabaseClient) -> dict[str, Any]:
    """Return source-owned object/column names, never DDL values or mailbox data."""
    contract = schema.expected_schema()
    cached: dict[str, list[dict[str, Any]]] = {}

    def read(sql: str) -> list[dict[str, Any]]:
        if sql not in cached:
            rows = database.query(sql).get("results")
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("schema_rows_unverified")
            cached[sql] = rows
        return cached[sql]

    reason = "verified"
    try:
        schema.verify_schema(read, contract)
    except ValueError as error:
        reason = str(error) if str(error) in SCHEMA_ERRORS else "schema_unverified"
    actual = {row.get("name"): row for row in cached.get(schema.SCHEMA_SQL, [])
              if isinstance(row.get("name"), str)}
    known = set(actual) & set(contract.objects)
    drift = []
    for name in sorted(known):
        kind, table, tokens = contract.objects[name]
        row = actual[name]
        if row.get("type") != kind or row.get("tbl_name") != table or schema.sql_tokens(row.get("sql", "")) != tokens:
            drift.append(name)
    columns = {}
    for name, expected in contract.columns.items():
        observed = cached.get(schema.pragma("table_xinfo", name))
        if observed is not None and observed != expected:
            source_names = {row["name"] for row in expected}
            observed_names = {row.get("name") for row in observed}
            columns[name] = {"missing": sorted(source_names - observed_names),
                             "unknown_count": len(observed_names - source_names),
                             "metadata_drift": observed_names == source_names}
    return {"verified": reason == "verified", "reason": reason,
            "expected_object_count": len(contract.objects), "observed_object_count": len(actual),
            "missing_objects": sorted(set(contract.objects) - set(actual)),
            "unknown_object_count": len(set(actual) - set(contract.objects)),
            "unknown_objects": sorted(name for name in set(actual) - set(contract.objects)
                                      if len(name) <= 128 and schema.IDENTIFIER.fullmatch(name)),
            "drift_objects": drift, "column_drift": columns,
            "expected_migration_count": len(contract.migrations)}


def run(mode: str) -> None:
    context(mode)
    witness()
    paused_graph()
    database = DatabaseClient(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"], "staging")
    facts = schema_facts(database)
    value = {"schema": "staging-semantic-inspection/v1", "source_run_id": ORIGIN_RUN,
             "source_sha": ORIGIN_SHA, "run_id": os.environ["GITHUB_RUN_ID"],
             "checkout_sha": os.environ["GITHUB_SHA"], "api_version": API,
             "maintenance_version": PAUSED, "sink_version": SINK, "schema_facts": facts}
    INSPECTION.parent.mkdir(parents=True, exist_ok=True)
    INSPECTION.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    if mode == "inspect":
        print(json.dumps({"event": "staging_semantic_schema_inspected", **facts}, sort_keys=True))
        return
    if not facts["verified"]:
        raise ValueError("staging_semantic_recovery_schema_unverified")
    # Only this reviewed continuation may borrow the normal maintenance submit
    # primitive; its artifact retains the original producer's immutable manifest.
    os.environ["AMAIL_STAGING_DEPLOY_CONFIRM"] = "RUN_STAGING_V031"
    version = rollout.deploy_maintenance(True)
    select(version)
    rollout.graph.verify("staging", "active")
    value.update({"schema": "staging-semantic-recovery/v1", "maintenance_version": version,
                  "old_http_drain": "NOT_CLAIMED", "origin_boundary_reused": True})
    RECEIPT.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def admit_journey(recovery_run: str) -> None:
    """Select only a successful named maintenance continuation's safe receipt."""
    context("journey")
    metadata = accepted.run_metadata(recovery_run)
    if metadata.get("conclusion") != "success":
        raise ValueError("staging_semantic_recovery_not_completed")
    accepted.successful_jobs(recovery_run, frozenset({"Inspect or finish the named paused semantic staging transition"}))
    artifact_id = accepted.unique_artifact(recovery_run, metadata["head_sha"], f"staging-semantic-recovery-{recovery_run}")
    JOURNEY_ADMISSION.parent.mkdir(parents=True, exist_ok=True)
    JOURNEY_ADMISSION.write_text(json.dumps({"recovery_run": recovery_run,
                                           "recovery_sha": metadata["head_sha"],
                                           "checkout_sha": os.environ["GITHUB_SHA"]}), encoding="utf-8")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"recovery_artifact_id={artifact_id}\n")


def journey_ready() -> None:
    """Check actual active pins before the single new semantic user journey."""
    context("journey")
    admission = json.loads(JOURNEY_ADMISSION.read_text(encoding="utf-8"))
    value = json.loads(RECEIPT.read_text(encoding="utf-8"))
    if (admission.get("checkout_sha") != os.environ["GITHUB_SHA"]
            or value.get("schema") != "staging-semantic-recovery/v1"
            or value.get("source_run_id") != ORIGIN_RUN or value.get("source_sha") != ORIGIN_SHA
            or value.get("run_id") != admission.get("recovery_run")
            or value.get("checkout_sha") != admission.get("recovery_sha")
            or value.get("api_version") != API or value.get("sink_version") != SINK
            or not isinstance(value.get("maintenance_version"), str)
            or rollout.graph.UUID.fullmatch(value["maintenance_version"]) is None
            or value.get("schema_facts", {}).get("verified") is not True):
        raise ValueError("staging_semantic_recovery_receipt_unverified")
    accepted.runtime_closure(value["checkout_sha"], os.environ["GITHUB_SHA"])
    select(value["maintenance_version"])
    rollout.graph.verify("staging", "active")
    JOURNEY_RUNTIME.write_text(json.dumps({"schema": "staging-semantic-acceptance/v1",
        "source_run_id": ORIGIN_RUN, "source_sha": ORIGIN_SHA,
        "run_id": os.environ["GITHUB_RUN_ID"], "checkout_sha": os.environ["GITHUB_SHA"],
        "api_version": API, "maintenance_version": value["maintenance_version"], "sink_version": SINK}), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect", "recover", "admit-journey", "journey"))
    parser.add_argument("--recovery-run", default="")
    args = parser.parse_args()
    mode = args.mode
    try:
        if mode == "admit-journey":
            admit_journey(args.recovery_run)
        elif mode == "journey":
            journey_ready()
        else:
            run(mode)
    except Exception as error:
        reason = "unverified"
        if isinstance(error, FileNotFoundError):
            reason = "required_artifact_missing"
        elif isinstance(error, ValueError) and str(error) in SCHEMA_ERRORS | rollout.FAILURES:
            reason = str(error)
        print(f"staging_semantic_recovery={reason}")
        return 1
    print(f"staging_semantic_recovery={mode}_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
