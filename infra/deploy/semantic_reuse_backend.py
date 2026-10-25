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
FAILURES = frozenset({"semantic_reuse_policy_changed", "semantic_reuse_adapter_unverified",
    "semantic_reuse_migration_unreviewed", "semantic_reuse_migration_unverified",
    "semantic_reuse_retained_graph_changed", "semantic_reuse_secrets_missing",
    "schema_objects_unverified", "schema_object_drift", "schema_columns_unverified",
    "schema_indexes_unverified", "schema_index_columns_unverified",
    "schema_migration_provenance_unverified", "semantic_reuse_partial_unreviewed"}) | previous.prior.graph.FAILURES


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


def replace(realm: str, role: str) -> str:
    require_artifact("mail_api")
    filename = "wrangler.toml" if role == "api" else "wrangler-maintenance.toml"
    config = ROOT / "crates/mail-worker" / filename
    names = ["OPENROUTER_API_KEY", "CF_EMAIL_ROUTING_TOKEN", "BILLING_SERVICE_KEY"]
    if role == "api":
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
    data = tomllib.loads(config.read_text(encoding="utf-8"))
    reviewed = data if realm == "production" else data["env"]["staging"]
    bindings = (expected_bindings("queue-api", QUEUES[realm][0], realm=realm) if role == "api"
                else previous.prior.retained.maintenance.expected_bindings(realm, QUEUES[realm][0], active=True))
    provider = previous.FreshProvider(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"])
    previous.prior.readback.capture_off(provider, "amail-mail" + ("-maintenance" if role == "maintenance" else "")
                                       + ("-staging" if realm == "staging" else ""), version,
        expected_bindings=bindings, reviewed=reviewed["observability"],
        record=lambda state, **facts: previous.prior.journal(role + "_capture", state, **facts))
    return version


def run(realm: str, *, resume: bool = False) -> None:
    import sys
    sys.path.insert(0, str(ROOT / "infra/ci"))
    import mail_backend_artifact
    mail_backend_artifact.context(realm)
    require_artifact("mail_api")
    pins = dict(STAGING if realm == "staging" else PRODUCTION)
    if resume:
        if realm != "staging" or not mail_backend_artifact.ADMISSION.is_file():
            raise ValueError("semantic_reuse_partial_unreviewed")
        pins["amail-mail-staging"] = "75bbcb55-e6f5-42e3-b65b-acb6dbc990c9"
    before, policy = observe(realm, pins)
    database = DatabaseClient(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"], realm)
    schema(database, realm, 19 if resume else 18)
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
        value.update(original_partial_run=mail_backend_artifact.PARTIAL_RUN,
                     original_build_source=mail_backend_artifact.PARTIAL_SOURCE)
    with (ROOT / f".temp/semantic-reuse-{realm}.json").open("x", encoding="utf-8") as file:
        json.dump(value, file, sort_keys=True)
    print(f"semantic_reuse_backend={realm}_verified")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("realm", choices=("staging", "production"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    try:
        run(args.realm, resume=args.resume)
    except Exception as error:
        reason = str(error) if isinstance(error, ValueError) and str(error) in FAILURES else "unknown"
        print(f"semantic_reuse_backend=unverified reason={reason} class={type(error).__name__}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
