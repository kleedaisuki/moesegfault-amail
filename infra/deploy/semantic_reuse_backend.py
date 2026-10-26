"""Roll only the tested Mail API/maintenance forward; retain Cron and all user state."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
from typing import Any

import production_v031 as previous
import check_staging_adapters as adapters
from direct_contact_health import DatabaseClient
from mail_schema_contract import expected_schema, verify_schema
from pin_staging_mail import expected_bindings, run as pin_api
from tested_worker_artifact import require_artifact
from worker_deploy_result import DeploymentFailure, submit

ROOT = previous.ROOT
PRODUCTION = {"amail-mail": "dd3e7d96-fde0-4ed9-adb8-ff5fcc76270f",
              "amail-mail-maintenance": "45662e34-b008-42d7-a76b-ba77c09693d0",
              "amail-trace-sink": "2bc63288-c987-49f9-bee6-8bc25b35a8be"}
STAGING = {"amail-mail-staging": "d592cd2a-95a3-4c89-859a-18a191bd641a",
           "amail-mail-maintenance-staging": "c00d2f51-096d-4b83-8d49-e42e196b85ec",
           "amail-trace-sink-staging": "5e556087-9a75-40db-9eb5-869a4b56372e"}
QUEUES = {"production": (previous.prior.QUEUE, previous.prior.DLQ),
          "staging": ("fcee510036af42c189e28c0b6ff9508e", "f023f804b7bd4d8691fbfcb60416a001")}
COMPLETED_STAGING_RUN = "40204723478"
COMPLETED_STAGING_SOURCE = "6db9d5f8444b3c2e471e5c5a00e48af95930500e"
STAGING_EPOCHS = {
    COMPLETED_STAGING_RUN: {"source": COMPLETED_STAGING_SOURCE, "conclusion": "success",
        "job": "Deploy semantic reuse staging backend", "api": "75bbcb55-e6f5-42e3-b65b-acb6dbc990c9"},
    "40210732820": {"source": "2ade1c0ce8d994acd4e8401828a75a41e22f69a1", "conclusion": "failure",
        "job": "Semantic reuse staging admission", "api": "fb03a457-f771-41fe-a041-86b2491d1a6a"},
}
PRODUCTION_PARTIAL_RUN = "40272159207"
PRODUCTION_PARTIAL_SOURCE = "9109b803e17719f940e1fc5404478411ee53aa22"
PRODUCTION_PARTIAL_API = "28bc6307-2c85-4a23-8b2c-77563197729a"
FAILURES = frozenset({"semantic_reuse_policy_changed", "semantic_reuse_adapter_unverified",
    "semantic_reuse_migration_unreviewed", "semantic_reuse_migration_unverified",
    "semantic_reuse_retained_graph_changed", "semantic_reuse_secrets_missing",
    "schema_objects_unverified", "schema_object_drift", "schema_columns_unverified",
    "schema_indexes_unverified", "schema_index_columns_unverified",
    "schema_migration_provenance_unverified", "semantic_reuse_partial_unreviewed",
    "semantic_reuse_completed_origin_unverified", "semantic_reuse_ingress_restore_unreviewed"}) | previous.prior.graph.FAILURES


def select(realm: str, pins: dict[str, str]) -> None:
    suffix = "-staging" if realm == "staging" else ""
    os.environ.update(AMAIL_EXPECTED_WORKER_VERSION=pins["amail-mail" + suffix],
                      AMAIL_EXPECTED_MAINTENANCE_VERSION=pins["amail-mail-maintenance" + suffix],
                      AMAIL_EXPECTED_TRACE_SINK_VERSION=pins["amail-trace-sink" + suffix],
                      AMAIL_TRACE_QUEUE_ID=QUEUES[realm][0], AMAIL_TRACE_DLQ_ID=QUEUES[realm][1],
                      AMAIL_TRACE_TOPOLOGY="api-scheduled")


def observe(realm: str, pins: dict[str, str], policy: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    select(realm, pins)
    current = previous.prior.graph.global_policy() if realm == "production" else {}
    if policy is not None and current != policy:
        raise ValueError("semantic_reuse_policy_changed")
    graph = previous.prior.graph.verify(realm, "active", expected_policy=current if realm == "production" else None)
    account, token = os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"]
    lifecycle = adapters.lifecycle_snapshot(account, token, realm=realm, temporary=True)
    if realm == "production":
        retained = previous.legacy.adapter_snapshot(previous.FreshProvider(account, token), previous.EVENTS)
    else:
        versions = {}
        for script in ("amail-inbound-staging", "amail-events-staging"):
            value = previous.prior.graph.capture.readback(account, token, script, "deployments?per_page=1&page=1")
            pin = previous.prior.graph.serving_deployment(value)
            if pin is None:
                raise ValueError("semantic_reuse_adapter_unverified")
            versions[script] = pin[1]
        retained = adapters.verify(versions["amail-inbound-staging"], versions["amail-events-staging"])
    anchors = {"adapters": retained, "lifecycle": lifecycle,
               "forwards": previous.prior.graph.direct_forward_snapshot(realm, account, token)}
    return {"graph": graph, "retained": anchors}, current


def schema(database: DatabaseClient, realm: str, count: int) -> None:
    contract = expected_schema(count, staging_auxiliary=realm == "staging")
    complete = expected_schema()
    if len(complete.migrations) != 19 or not complete.migrations[-1].startswith("0019_"):
        raise ValueError("semantic_reuse_migration_unreviewed")
    verify_schema(lambda sql: database.query(sql)["results"], contract)


def capture_production(role: str, version: str) -> None:
    """Retain observed queue identities when normalizing immutable bindings."""
    filename = "wrangler.toml" if role == "api" else "wrangler-maintenance.toml"
    reviewed = tomllib.loads((ROOT / "crates/mail-worker" / filename).read_text(encoding="utf-8"))
    bindings = (expected_bindings("queue-api", QUEUES["production"][0], realm="production") if role == "api"
                else previous.prior.retained.maintenance.expected_bindings("production", QUEUES["production"][0], active=True))
    provider = previous.FreshProvider(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"])
    previous.prior.readback.complete(provider, f"accounts/{provider.account}/queues", "queue_id", 100)
    previous.prior.readback.capture_off(provider, "amail-mail" + ("-maintenance" if role == "maintenance" else ""), version,
        expected_bindings=bindings, reviewed=reviewed["observability"],
        record=lambda state, **facts: previous.prior.journal(role + "_capture", state, **facts))


def replace(realm: str, role: str, *, ingress_only: bool = False) -> str:
    require_artifact("mail_api")
    filename = "wrangler.toml" if role == "api" else "wrangler-maintenance.toml"
    config = ROOT / "crates/mail-worker" / filename
    if ingress_only and (realm != "staging" or role != "api"):
        raise ValueError("semantic_reuse_ingress_restore_unreviewed")
    names = ["INGRESS_SECRET"] if ingress_only else ["OPENROUTER_API_KEY", "CF_EMAIL_ROUTING_TOKEN", "BILLING_SERVICE_KEY"]
    if role == "api" and not ingress_only:
        names.append("INGRESS_SECRET")
    secrets = {name: os.getenv(name, "") for name in names}
    if not all(secrets.values()):
        raise ValueError("semantic_reuse_secrets_missing")
    previous.prior.journal(role, "intent")
    with tempfile.TemporaryDirectory(prefix="semantic-reuse-", dir=ROOT / ".temp") as folder:
        path = Path(folder) / "secrets.json"
        path.write_text(json.dumps(secrets), encoding="utf-8")
        path.chmod(0o600)
        command = ["wrangler", "deploy", "--config", str(config), "--secrets-file", str(path)]
        if realm == "staging":
            command.extend(["--env", "staging"])
        try:
            version = submit(command, realm, "mail_api", cwd=ROOT / "crates/mail-worker")
        except DeploymentFailure as error:
            if error.version:
                previous.prior.journal(role, "ambiguous_version_captured", version=error.version)
            raise
    previous.prior.journal(role, "version_captured", version=version)
    if realm == "staging":
        account, token = os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"]
        if role == "api":
            pin_api(account, token, version, phase="queue-api", queue_id=QUEUES[realm][0])
        else:
            previous.prior.retained.maintenance.verify(realm, "active", account, token, version, QUEUES[realm][0])
        return version
    capture_production(role, version)
    return version


def production_partial() -> dict[str, Any]:
    """Admit the fixed owned migration/API boundary, never an arbitrary replay."""
    import sys
    sys.path.insert(0, str(ROOT / "infra/ci"))
    import mail_backend_artifact as artifact
    if os.getenv("AMAIL_PRODUCTION_COMPLETED_RUN") != PRODUCTION_PARTIAL_RUN:
        raise ValueError("semantic_reuse_partial_unreviewed")
    metadata = artifact.accepted.github(f"runs/{PRODUCTION_PARTIAL_RUN}")
    expected = {"id": int(PRODUCTION_PARTIAL_RUN), "head_sha": PRODUCTION_PARTIAL_SOURCE,
        "status": "completed", "conclusion": "failure", "event": "workflow_dispatch",
        "head_branch": "main", "path": ".github/workflows/ci.yml", "run_attempt": 1}
    if (any(metadata.get(key) != value for key, value in expected.items())
            or metadata.get("repository", {}).get("full_name") != artifact.accepted.REPO):
        raise ValueError("semantic_reuse_partial_unreviewed")
    artifact.accepted.runtime_closure(PRODUCTION_PARTIAL_SOURCE, os.environ["GITHUB_SHA"])
    folder = ROOT / ".temp/ci/semantic-reuse-production-partial"
    checkpoint = artifact.metadata(folder / "semantic-reuse-predecessor.json")
    if (checkpoint.get("realm") != "production" or checkpoint.get("pins") != PRODUCTION
            or checkpoint.get("run_id") != PRODUCTION_PARTIAL_RUN
            or checkpoint.get("source_sha") != PRODUCTION_PARTIAL_SOURCE):
        raise ValueError("semantic_reuse_partial_unreviewed")
    path = folder / "production-upgrade-partial.jsonl"
    if path.is_symlink() or path.stat().st_size > 8192:
        raise ValueError("semantic_reuse_partial_unreviewed")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    identity = {"schema": "production-upgrade-partial/v1", "source_sha": PRODUCTION_PARTIAL_SOURCE,
                "run_id": PRODUCTION_PARTIAL_RUN, "run_attempt": 1}
    if rows != [{**identity, "phase": "migration", "state": "intent"},
                {**identity, "phase": "migration", "state": "observed"},
                {**identity, "phase": "api", "state": "intent"},
                {**identity, "phase": "api", "state": "version_captured", "version": PRODUCTION_PARTIAL_API}]:
        raise ValueError("semantic_reuse_partial_unreviewed")
    return checkpoint


def run(realm: str, *, resume: bool = False) -> None:
    import sys
    sys.path.insert(0, str(ROOT / "infra/ci"))
    import mail_backend_artifact
    mail_backend_artifact.context(realm)
    require_artifact("mail_api")
    pins = dict(STAGING if realm == "staging" else PRODUCTION)
    partial: dict[str, Any] | None = None
    if resume:
        if not mail_backend_artifact.ADMISSION.is_file():
            raise ValueError("semantic_reuse_partial_unreviewed")
        if realm == "production":
            partial = production_partial()
            pins["amail-mail"] = PRODUCTION_PARTIAL_API
        else:
            pins["amail-mail-staging"] = "75bbcb55-e6f5-42e3-b65b-acb6dbc990c9"
    before, policy = observe(realm, pins)
    if partial is not None and (previous.prior.digest(policy) != partial.get("policy_fingerprint")
            or previous.prior.digest(before["retained"]) != partial.get("retained_fingerprint")):
        raise ValueError("semantic_reuse_retained_graph_changed")
    database = DatabaseClient(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"], realm)
    schema(database, realm, 19 if resume else 18)
    if partial is not None:
        # observe() already checked immutable/effective API capture read-only.
        previous.prior.journal("api_capture", "read_only_verified", version=PRODUCTION_PARTIAL_API)
    checkpoint = {"realm": realm, "source_sha": os.environ["GITHUB_SHA"],
                  "run_id": os.environ["GITHUB_RUN_ID"], "pins": pins,
                  "policy_fingerprint": previous.prior.digest(policy),
                  "retained_fingerprint": previous.prior.digest(before["retained"])}
    with (ROOT / ".temp/semantic-reuse-predecessor.json").open("x", encoding="utf-8") as file:
        json.dump(checkpoint, file, sort_keys=True)
    if not resume:
        previous.prior.journal("migration", "intent")
        command = ["wrangler", "d1", "migrations", "apply", "MAIL_DB", "--remote"]
        if realm == "staging":
            command.extend(["--env", "staging"])
        result = subprocess.run(command, cwd=ROOT / "crates/mail-worker", capture_output=True, text=True, timeout=600, check=False)
        if result.returncode:
            raise ValueError("semantic_reuse_migration_unverified")
        previous.prior.journal("migration", "observed")
        schema(database, realm, 19)
    suffix = "-staging" if realm == "staging" else ""
    roles = (("maintenance", "amail-mail-maintenance"),) if resume else (("api", "amail-mail"), ("maintenance", "amail-mail-maintenance"))
    for role, name in roles:
        pins[name + suffix] = replace(realm, role)
        actual, _ = observe(realm, pins, policy)
        if actual["retained"] != before["retained"]:
            raise ValueError("semantic_reuse_retained_graph_changed")
    actual, _ = observe(realm, pins, policy)
    if actual["retained"] != before["retained"]:
        raise ValueError("semantic_reuse_retained_graph_changed")
    if realm == "production":
        previous.health_ready()
    value = {"schema": "semantic-index-reuse/v1", "realm": realm, "migration": 19,
             "source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
             "api_version": pins["amail-mail" + suffix],
             "maintenance_version": pins["amail-mail-maintenance" + suffix],
             "sink_version": pins["amail-trace-sink" + suffix],
             "policy_fingerprint": previous.prior.digest(policy),
             "retained_fingerprint": previous.prior.digest(actual["retained"]),
             "graph": actual["graph"], "cron_changed": False,
             "vectors": "retained; compatible Voyage vectors reused independently of consent generation"}
    if resume:
        value.update(original_partial_run=PRODUCTION_PARTIAL_RUN if realm == "production" else mail_backend_artifact.PARTIAL_RUN,
                     original_build_source=mail_backend_artifact.PARTIAL_SOURCE)
    with (ROOT / f".temp/semantic-reuse-{realm}.json").open("x", encoding="utf-8") as file:
        json.dump(value, file, sort_keys=True)
    print(f"semantic_reuse_backend={realm}_verified")


def verify_completed() -> None:
    """Read the one completed staging deployment; never repeat its mutations."""
    import sys
    sys.path.insert(0, str(ROOT / "infra/ci"))
    import mail_backend_artifact as artifact
    artifact.context("staging")
    artifact.original_identity()
    origin_run = os.environ.get("AMAIL_STAGING_COMPLETED_RUN", COMPLETED_STAGING_RUN)
    if origin_run not in STAGING_EPOCHS:
        raise ValueError("semantic_reuse_completed_origin_unverified")
    epoch = STAGING_EPOCHS[origin_run]
    metadata = artifact.accepted.github(f"runs/{origin_run}")
    if (metadata.get("status") != "completed" or metadata.get("conclusion") != epoch["conclusion"]
            or str(metadata.get("id")) != origin_run
            or metadata.get("head_sha") != epoch["source"]
            or metadata.get("head_branch") != artifact.BRANCH
            or metadata.get("repository", {}).get("full_name") != artifact.accepted.REPO
            or metadata.get("path") != ".github/workflows/ci.yml"
            or metadata.get("event") != "workflow_dispatch" or metadata.get("run_attempt") != 1):
        raise ValueError("semantic_reuse_completed_origin_unverified")
    artifact.accepted.successful_jobs(origin_run, frozenset({epoch["job"]}))
    artifact.accepted.runtime_closure(epoch["source"], os.environ["GITHUB_SHA"])
    origin = artifact.metadata(ROOT / ".temp/ci/semantic-reuse-completed/semantic-reuse-staging.json")
    pins = dict(STAGING)
    pins["amail-mail-staging"] = epoch["api"]
    pins["amail-mail-maintenance-staging"] = "0ee61a70-4040-40fe-a117-48d41c92f2de"
    if (origin.get("schema") != "semantic-index-reuse/v1" or origin.get("realm") != "staging"
            or origin.get("run_id") != origin_run or origin.get("source_sha") != epoch["source"]
            or origin.get("migration") != 19 or origin.get("cron_changed") is not False
            or any(origin.get(field) != pins[name] for field, name in
                (("api_version", "amail-mail-staging"), ("maintenance_version", "amail-mail-maintenance-staging"),
                 ("sink_version", "amail-trace-sink-staging")))):
        raise ValueError("semantic_reuse_completed_origin_unverified")
    current, policy = observe("staging", pins)
    database = DatabaseClient(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"], "staging")
    schema(database, "staging", 19)
    if (previous.prior.digest(current["retained"]) != origin["retained_fingerprint"]
            or previous.prior.digest(policy) != origin["policy_fingerprint"]):
        raise ValueError("semantic_reuse_retained_graph_changed")
    value = {**origin, "source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
             "graph": current["graph"], "completion_mode": "read_only",
             "original_deployment_run": origin_run,
             "original_deployment_source": epoch["source"]}
    with (ROOT / ".temp/semantic-reuse-staging.json").open("x", encoding="utf-8") as file:
        json.dump(value, file, sort_keys=True)
    print("semantic_reuse_backend=staging_verified read_only=true")


def restore_staging_ingress() -> None:
    """Correct one source-evidenced realm credential, without changing other secrets."""
    import sys
    sys.path.insert(0, str(ROOT / "infra/ci"))
    import mail_backend_artifact as artifact
    artifact.context("staging")
    if os.getenv("AMAIL_STAGING_INGRESS_RESTORE") != "true" or not artifact.ADMISSION.is_file():
        raise ValueError("semantic_reuse_ingress_restore_unreviewed")
    original = artifact.original_identity()
    if original["source_sha"] != artifact.PARTIAL_SOURCE or original["run_id"] != artifact.PARTIAL_RUN:
        raise ValueError("semantic_reuse_ingress_restore_unreviewed")
    require_artifact("mail_api")
    pins = dict(STAGING)
    pins["amail-mail-staging"] = "75bbcb55-e6f5-42e3-b65b-acb6dbc990c9"
    pins["amail-mail-maintenance-staging"] = "0ee61a70-4040-40fe-a117-48d41c92f2de"
    before, policy = observe("staging", pins)
    database = DatabaseClient(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"], "staging")
    schema(database, "staging", 19)
    checkpoint = {"schema": "semantic-reuse-ingress-restore/v1", "realm": "staging",
                  "source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
                  "credential_source": "INGRESS_SECRET_STAGING",
                  "old_api_version": pins["amail-mail-staging"],
                  "retained_fingerprint": previous.prior.digest(before["retained"])}
    (ROOT / ".temp/semantic-reuse-predecessor.json").write_text(json.dumps(checkpoint, sort_keys=True), encoding="utf-8")
    pins["amail-mail-staging"] = replace("staging", "api", ingress_only=True)
    actual, _ = observe("staging", pins, policy)
    if actual["retained"] != before["retained"]:
        raise ValueError("semantic_reuse_retained_graph_changed")
    repair = {**checkpoint, "new_api_version": pins["amail-mail-staging"],
              "maintenance_version": pins["amail-mail-maintenance-staging"],
              "sink_version": pins["amail-trace-sink-staging"], "other_secrets": "inherited unchanged"}
    (ROOT / ".temp/semantic-reuse-ingress-restore.json").write_text(json.dumps(repair, sort_keys=True), encoding="utf-8")
    value = {"schema": "semantic-index-reuse/v1", "realm": "staging", "migration": 19,
             "source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
             "api_version": pins["amail-mail-staging"], "maintenance_version": pins["amail-mail-maintenance-staging"],
             "sink_version": pins["amail-trace-sink-staging"], "cron_changed": False,
             "credential_source": "INGRESS_SECRET_STAGING", "configuration_repair": "staging ingress credential only",
             "original_build_run": artifact.PARTIAL_RUN, "original_build_source": artifact.PARTIAL_SOURCE,
             "policy_fingerprint": previous.prior.digest(policy),
             "retained_fingerprint": previous.prior.digest(actual["retained"]), "graph": actual["graph"]}
    with (ROOT / ".temp/semantic-reuse-staging.json").open("x", encoding="utf-8") as file:
        json.dump(value, file, sort_keys=True)
    print("semantic_reuse_backend=staging_ingress_credential_restored")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("realm", choices=("staging", "production"))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verify-completed", action="store_true")
    parser.add_argument("--restore-staging-ingress", action="store_true")
    args = parser.parse_args()
    try:
        if args.restore_staging_ingress:
            if args.realm != "staging" or args.resume or args.verify_completed:
                raise ValueError("semantic_reuse_ingress_restore_unreviewed")
            restore_staging_ingress()
        elif args.verify_completed:
            if args.realm != "staging" or args.resume:
                raise ValueError("semantic_reuse_completed_origin_unverified")
            verify_completed()
        else:
            run(args.realm, resume=args.resume)
    except Exception as error:
        reason = str(error) if isinstance(error, ValueError) and str(error) in FAILURES else "unknown"
        print(f"semantic_reuse_backend=unverified reason={reason} class={type(error).__name__}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
