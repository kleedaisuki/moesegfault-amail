"""Roll out billing navigation codes with only schema 0020 and an API replacement.

The hosted workflow owns the existing realm writer lock and orders one checked
build, staging, its real native/browser journey, and optional production. Unknown
write outcomes stop at the recorded boundary. The one named completed-staging
continuation reuses its original producer and never repeats staging writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import tomllib
import traceback
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

import semantic_reuse_backend as retained
from direct_contact_health import DatabaseClient
from control_plane_trace import span
from mail_schema_contract import expected_schema, verify_schema
from pin_staging_mail import UUID
from worker_deploy_result import DeploymentFailure, submit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ci"))
import worker_artifact as artifact
import accepted_staging_artifact as accepted

ROOT = artifact.ROOT
SOURCE_RUN = "42070608438"
SOURCE_SHA = "43c14c9d7fe966957665e67a2e1b87cb256b37e3"
SOURCE_ARTIFACT = 13435962042
SOURCE_STAGING_RECEIPT = 13437177224
SOURCE_STAGING_API = "1dba790f-5564-4b3a-aafd-2b4f8d9b83c5"
ACCEPTANCE_RUN = "42073709631"
ACCEPTANCE_SHA = "2979c52a55306f9859ba30cec66248481ddac137"
ACCEPTANCE_STAGE_ARTIFACT = 13437945110
ACCEPTANCE_ARTIFACT = 13436979065
PHASE = "arguments"
FOLDER = ROOT / ".temp/ci/device-backend"
TREES = ("crates/mail-worker/build",)
ENTRIES = ("crates/mail-worker/entry/api.mjs", "crates/mail-worker/entry/maintenance.mjs",
           "crates/mail-worker/wrangler.toml", "crates/mail-worker/wrangler-maintenance.toml",
           "crates/mail-worker/migrations/0020_billing_device_navigation.sql")
PINS = {
    "staging": {"amail-mail-staging": "fb03a457-f771-41fe-a041-86b2491d1a6a",
                "amail-mail-maintenance-staging": "0ee61a70-4040-40fe-a117-48d41c92f2de",
                "amail-trace-sink-staging": "5e556087-9a75-40db-9eb5-869a4b56372e"},
    "production": {"amail-mail": "28bc6307-2c85-4a23-8b2c-77563197729a",
                   "amail-mail-maintenance": "57c4d494-ef44-4ee4-ba1a-400e2a29a65b",
                   "amail-trace-sink": "2bc63288-c987-49f9-bee6-8bc25b35a8be"},
}
FAILURES = frozenset({"device_backend_context_unverified", "device_backend_artifact_unverified",
    "device_backend_installed_bytes_changed", "device_backend_existing_build_refused",
    "device_backend_entry_changed", "device_backend_migration_unreviewed",
    "device_backend_migration_submit_unverified", "device_backend_retained_graph_changed",
    "device_backend_staging_acceptance_unverified", "device_backend_public_unverified",
    "device_backend_recovery_unreviewed", "device_backend_recovery_source_unverified",
    "device_backend_recovery_stage_read_only", "device_backend_recovery_stage_unverified",
    "accepted_source_required_gate_failed", "accepted_source_runtime_changed",
    "accepted_source_inventory_incomplete", "accepted_source_metadata_unavailable",
    "accepted_source_metadata_invalid", "accepted_source_revision_invalid",
    "device_backend_acceptance_source_unverified"}) | retained.FAILURES


def orchestration_identity() -> dict[str, Any]:
    return {**artifact.context(), "schema": "device-backend-artifact/v1"}


def recovery_source() -> dict[str, Any]:
    """Admit exactly the completed staging boundary, not an arbitrary older run."""
    current = orchestration_identity()
    expected_context = {"AMAIL_DEVICE_SOURCE_RUN": SOURCE_RUN, "GITHUB_REPOSITORY": accepted.REPO,
        "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_RUN_ATTEMPT": "1"}
    if (any(os.getenv(key) != value for key, value in expected_context.items())
            or os.getenv("AMAIL_DEVICE_ARTIFACT_ID", str(SOURCE_ARTIFACT)) != str(SOURCE_ARTIFACT)):
        raise ValueError("device_backend_recovery_unreviewed")
    run = accepted.github(f"runs/{SOURCE_RUN}")
    expected = {"id": int(SOURCE_RUN), "head_sha": SOURCE_SHA, "status": "completed",
        "conclusion": "failure", "event": "workflow_dispatch", "head_branch": "main",
        "path": ".github/workflows/ci.yml", "run_attempt": 1}
    if (any(type(run.get(key)) is not type(value) or run.get(key) != value for key, value in expected.items())
            or run.get("repository", {}).get("full_name") != accepted.REPO):
        raise ValueError("device_backend_recovery_source_unverified")
    accepted.successful_jobs(SOURCE_RUN, frozenset({"Device-code backend release / build", "Device-code backend release / staging"}))
    artifacts = accepted.rows(accepted.github(f"runs/{SOURCE_RUN}/artifacts?per_page=100"), "artifacts")
    for name, identifier in ((f"device-backend-{SOURCE_SHA}", SOURCE_ARTIFACT),
                             (f"device-backend-staging-{SOURCE_RUN}", SOURCE_STAGING_RECEIPT)):
        found = [row for row in artifacts if row.get("name") == name]
        if (len(found) != 1 or found[0].get("id") != identifier or found[0].get("expired") is not False
                or found[0].get("workflow_run", {}).get("head_sha") != SOURCE_SHA):
            raise ValueError("device_backend_recovery_source_unverified")
    accepted.runtime_closure(SOURCE_SHA, current["source_sha"])
    return {**current, "source_sha": SOURCE_SHA, "run_id": SOURCE_RUN, "run_attempt": 1}


def identity() -> dict[str, Any]:
    return recovery_source() if os.getenv("AMAIL_DEVICE_SOURCE_RUN") else orchestration_identity()


def source_admit() -> None:
    source = recovery_source()
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"artifact_id={SOURCE_ARTIFACT}\nstaging_receipt_id={SOURCE_STAGING_RECEIPT}\n"
                     f"source_run_id={source['run_id']}\nsource_sha={source['source_sha']}\n")


def acceptance_identity() -> dict[str, Any]:
    current = orchestration_identity()
    selected = os.getenv("AMAIL_DEVICE_ACCEPTANCE_RUN", "")
    if not selected:
        return {"source_sha": current["source_sha"], "run_id": current["run_id"], "run_attempt": 1}
    if selected != ACCEPTANCE_RUN or os.getenv("AMAIL_DEVICE_SOURCE_RUN") != SOURCE_RUN:
        raise ValueError("device_backend_acceptance_source_unverified")
    run = accepted.github(f"runs/{ACCEPTANCE_RUN}")
    expected = {"id": int(ACCEPTANCE_RUN), "head_sha": ACCEPTANCE_SHA, "status": "completed",
        "conclusion": "failure", "event": "workflow_dispatch", "head_branch": "main",
        "path": ".github/workflows/ci.yml", "run_attempt": 1}
    if (any(type(run.get(key)) is not type(value) or run.get(key) != value for key, value in expected.items())
            or run.get("repository", {}).get("full_name") != accepted.REPO):
        raise ValueError("device_backend_acceptance_source_unverified")
    accepted.successful_jobs(ACCEPTANCE_RUN, frozenset({"Device-code backend release / reuse", "Device-code backend release / journey"}))
    inventory = accepted.rows(accepted.github(f"runs/{ACCEPTANCE_RUN}/artifacts?per_page=100"), "artifacts")
    for name, identifier in ((f"device-backend-staging-{ACCEPTANCE_RUN}", ACCEPTANCE_STAGE_ARTIFACT),
                             (f"device-staging-acceptance-{ACCEPTANCE_RUN}", ACCEPTANCE_ARTIFACT)):
        found = [row for row in inventory if row.get("name") == name]
        if (len(found) != 1 or found[0].get("id") != identifier or found[0].get("expired") is not False
                or found[0].get("workflow_run", {}).get("head_sha") != ACCEPTANCE_SHA):
            raise ValueError("device_backend_acceptance_source_unverified")
    accepted.runtime_closure(ACCEPTANCE_SHA, current["source_sha"])
    return {"source_sha": ACCEPTANCE_SHA, "run_id": ACCEPTANCE_RUN, "run_attempt": 1,
            "artifact_id": ACCEPTANCE_ARTIFACT, "staging_artifact_id": ACCEPTANCE_STAGE_ARTIFACT}


def mark_phase(name: str) -> None:
    global PHASE
    PHASE = name


def failure_diagnostic(error: Exception) -> dict[str, Any]:
    """Keep machine codes and source locations, never exception prose or locals."""
    reason = str(error) if isinstance(error, ValueError) and re.fullmatch(r"[a-z][a-z0-9_]{0,127}", str(error)) else "unknown"
    result: dict[str, Any] = {"schema": "device-backend-diagnostic/v1", "reason": reason,
        "class": type(error).__name__, "phase": PHASE}
    for frame in traceback.extract_tb(error.__traceback__):
        path = Path(frame.filename).resolve()
        if path.is_relative_to(ROOT / "infra"):
            result["location"] = {"file": path.relative_to(ROOT).as_posix(), "function": frame.name, "line": frame.lineno}
    return result


def inspect_production() -> None:
    """Observe the production predecessor without artifacts or staging authority."""
    mark_phase("production_inspection_context")
    expected = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": accepted.REPO,
        "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_REF": "refs/heads/main",
        "AMAIL_DEVICE_CONFIRM": "INSPECT_DEVICE_BACKEND_PRODUCTION",
        "AMAIL_PRODUCTION_GRAPH_FREEZE": "FREEZE_PRODUCTION_GRAPH_WRITERS"}
    if any(os.getenv(key) != value for key, value in expected.items()):
        raise ValueError("device_backend_context_unverified")
    current = orchestration_identity()
    pins = dict(PINS["production"])
    mark_phase("production_graph_preflight")
    before, policy = retained.observe("production", pins)
    mark_phase("production_schema_preflight")
    schema(DatabaseClient(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"], "production"), "production", 19)
    mark_phase("production_graph_final_readback")
    final, _ = retained.observe("production", pins, policy)
    if final != before:
        raise ValueError("device_backend_retained_graph_changed")
    value = {"schema": "device-backend-production-inspection/v1", "source_sha": current["source_sha"],
        "run_id": current["run_id"], "run_attempt": 1, "migration": 19, "pins": pins, "graph": final["graph"],
        "policy_fingerprint": retained.previous.prior.digest(policy),
        "retained_fingerprint": retained.previous.prior.digest(final["retained"]), "writes": False}
    path = ROOT / ".temp/device-backend-production-inspection.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, sort_keys=True)


def hashes(base: Path) -> dict[str, str]:
    return artifact.files(base, trees=TREES, entries=ENTRIES)


def artifact_create() -> None:
    if os.getenv("AMAIL_DEVICE_SOURCE_RUN"):
        raise ValueError("device_backend_recovery_unreviewed")
    value = {**identity(), "files": hashes(ROOT)}
    FOLDER.mkdir(parents=True, exist_ok=False)
    for name in value["files"]:
        target = FOLDER / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    (FOLDER / "manifest.json").write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def metadata(path: Path) -> dict[str, Any]:
    if path.is_symlink() or path.stat().st_size > 262144:
        raise ValueError("device_backend_artifact_unverified")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("device_backend_artifact_unverified")
    return value


def artifact_verified() -> dict[str, str]:
    if FOLDER.is_symlink():
        raise ValueError("device_backend_artifact_unverified")
    value = metadata(FOLDER / "manifest.json")
    current, files = identity(), hashes(FOLDER)
    names = {path.relative_to(FOLDER).as_posix() for path in FOLDER.rglob("*") if path.is_file()}
    if (set(value) != set(current) | {"files"}
            or any(type(value.get(key)) is not type(item) or value.get(key) != item for key, item in current.items())
            or value["files"] != files or names != set(files) | {"manifest.json"}):
        raise ValueError("device_backend_artifact_unverified")
    return files


def require_artifact() -> None:
    if artifact_verified() != hashes(ROOT):
        raise ValueError("device_backend_installed_bytes_changed")


def artifact_restore() -> None:
    files = artifact_verified()
    if any((ROOT / name).exists() for name in TREES):
        raise ValueError("device_backend_existing_build_refused")
    for name in ENTRIES:
        path = ROOT / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != files[name]:
            raise ValueError("device_backend_entry_changed")
    for name in files:
        if name in ENTRIES:
            continue
        target = ROOT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FOLDER / name, target)
    require_artifact()


def context(realm: str) -> None:
    expected = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": retained.previous.prior.REPO,
                "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_RUN_ATTEMPT": "1",
                "GITHUB_REF": "refs/heads/main", "AMAIL_DEVICE_CONFIRM": "RUN_DEVICE_BACKEND_" + realm.upper()}
    if (realm not in PINS or any(os.getenv(key) != value for key, value in expected.items())
            or re.fullmatch(r"[1-9][0-9]{0,19}", os.getenv("AMAIL_DEVICE_ARTIFACT_ID", "")) is None
            or realm == "production" and os.getenv("AMAIL_PRODUCTION_GRAPH_FREEZE") != "FREEZE_PRODUCTION_GRAPH_WRITERS"):
        raise ValueError("device_backend_context_unverified")
    identity()


def journal(realm: str, phase: str, state: str, **facts: Any) -> None:
    path = ROOT / f".temp/device-backend-{realm}-partial.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"schema": "device-backend-partial/v1", "source_sha": os.environ["GITHUB_SHA"],
           "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": 1, "realm": realm,
           "phase": phase, "state": state, **facts}
    with path.open("a", encoding="utf-8") as file:
        path.chmod(0o600)
        file.write(json.dumps(row, sort_keys=True) + "\n")
        file.flush()
        os.fsync(file.fileno())


def schema(database: DatabaseClient, realm: str, count: int) -> None:
    complete = expected_schema()
    if len(complete.migrations) != 20 or complete.migrations[-1] != "0020_billing_device_navigation.sql":
        raise ValueError("device_backend_migration_unreviewed")
    verify_schema(lambda sql: database.query(sql)["results"], expected_schema(count, staging_auxiliary=realm == "staging"))


def public_readback(realm: str) -> None:
    origin = "https://mail" + ("-staging" if realm == "staging" else "") + ".moesegfault.dev"
    opener = build_opener(retained.previous.NoRedirect)
    for path in ("/health", "/billing/device"):
        with span("device.backend.public", "readback", realm=realm, component="mail_api",
                  endpoint="health" if path == "/health" else "billing.device.page") as facts:
            try:
                response = opener.open(Request(origin + path, headers={"User-Agent": "amail-device-backend-witness"}), timeout=20)
            except HTTPError as error:
                facts.http_status = error.code
                facts.reason = "device_backend_public_unverified"
                raise ValueError(facts.reason) from error
            with response:
                facts.http_status = response.status
                body = response.read(16385)
                if response.status != 200 or len(body) > 16384:
                    raise ValueError("device_backend_public_unverified")
                if path == "/health":
                    value = json.loads(body)
                    if value.get("status") != "ok" or value.get("api_version") != "2":
                        raise ValueError("device_backend_public_unverified")
                elif b"name=user_code" not in body or b"This step does not approve" not in body:
                    raise ValueError("device_backend_public_unverified")


def public_ready(realm: str) -> None:
    """Allow edge propagation through bounded reads, never a second deployment."""
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            public_readback(realm)
            return
        except (URLError, TimeoutError, ValueError):
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(5, remaining))
    raise ValueError("device_backend_public_unverified")


def staging_receipt() -> dict[str, Any]:
    receipt = metadata(ROOT / ".temp/device-backend-staging.json")
    producer = identity()
    expected = {"schema": "device-backend/v1", "realm": "staging", "migration": 20,
                "source_sha": producer["source_sha"], "run_id": producer["run_id"],
                "run_attempt": 1, "artifact_id": os.environ["AMAIL_DEVICE_ARTIFACT_ID"]}
    pins = PINS["staging"]
    version = receipt.get("api_version")
    if (not isinstance(version, str) or UUID.fullmatch(version) is None
            or os.getenv("AMAIL_DEVICE_SOURCE_RUN") and version != SOURCE_STAGING_API
            or receipt.get("cron_changed") is not False or receipt.get("secrets_changed") is not False
            or any(type(receipt.get(key)) is not type(value) or receipt.get(key) != value for key, value in expected.items())
            or receipt.get("maintenance_version") != pins["amail-mail-maintenance-staging"]
            or receipt.get("sink_version") != pins["amail-trace-sink-staging"]):
        raise ValueError("device_backend_staging_acceptance_unverified")
    return receipt


def staging_verification(receipt: dict[str, Any]) -> dict[str, Any]:
    current = orchestration_identity()
    return {"schema": "device-backend-staging-verification/v1",
            "source_sha": current["source_sha"], "run_id": current["run_id"], "run_attempt": 1,
            "producer_source_sha": receipt["source_sha"], "producer_run_id": receipt["run_id"],
            "artifact_id": receipt["artifact_id"], "api_version": receipt["api_version"],
            "retained_fingerprint": receipt["retained_fingerprint"]}


def verify_staging() -> None:
    """Read the already deployed source-owned staging boundary without replay."""
    context("staging")
    if not os.getenv("AMAIL_DEVICE_SOURCE_RUN"):
        raise ValueError("device_backend_recovery_unreviewed")
    require_artifact()
    receipt = staging_receipt()
    pins = dict(PINS["staging"])
    pins["amail-mail-staging"] = receipt["api_version"]
    before, policy = retained.observe("staging", pins)
    digest = retained.previous.prior.digest
    if (digest(before["graph"]) != digest(receipt["graph"]) or digest(before["retained"]) != receipt["retained_fingerprint"]
            or digest(policy) != receipt["policy_fingerprint"]):
        raise ValueError("device_backend_recovery_stage_unverified")
    schema(DatabaseClient(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"], "staging"), "staging", 20)
    public_ready("staging")
    final, _ = retained.observe("staging", pins, policy)
    if final != before:
        raise ValueError("device_backend_retained_graph_changed")
    with (ROOT / ".temp/device-backend-staging-verified.json").open("x", encoding="utf-8") as file:
        json.dump(staging_verification(receipt), file, sort_keys=True)


def staging_accepted() -> dict[str, Any]:
    receipt = staging_receipt()
    acceptance = metadata(Path(os.getenv("AMAIL_DEVICE_STAGING_ACCEPTANCE", str(ROOT / ".temp/device-staging-acceptance.json"))))
    authority = acceptance_identity()
    checks = {"schema": "device-staging-acceptance/v1", "source_sha": authority["source_sha"],
              "run_id": authority["run_id"], "run_attempt": "1", "backend_artifact_id": receipt["artifact_id"],
              "api_version": receipt["api_version"], "issuer": "https://identity-staging.moesegfault.dev",
              "client_id": "amail-cli-staging", "login": "persisted",
              "billing": "pending_handoff_then_cancelled", "cleanup": "complete"}
    if any(acceptance.get(key) != value for key, value in checks.items()):
        raise ValueError("device_backend_staging_acceptance_unverified")
    if os.getenv("AMAIL_DEVICE_SOURCE_RUN"):
        observed = metadata(ROOT / ".temp/device-backend-staging-verified.json")
        if observed != staging_verification(receipt):
            raise ValueError("device_backend_recovery_stage_unverified")
    return authority



def migrate(realm: str, database: DatabaseClient) -> None:
    require_artifact()
    journal(realm, "migration", "intent")
    command = ["wrangler", "d1", "migrations", "apply", "MAIL_DB", "--remote"]
    if realm == "staging":
        command.extend(["--env", "staging"])
    result = subprocess.run(command, cwd=ROOT / "crates/mail-worker", capture_output=True, text=True, timeout=600, check=False)
    journal(realm, "migration", "submit_returned", process_exit_code=result.returncode)
    if result.returncode:
        raise ValueError("device_backend_migration_submit_unverified")
    schema(database, realm, 20)
    journal(realm, "migration", "verified", migration=20)


def capture_api(version: str) -> None:
    account, token = os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"]
    provider = retained.previous.FreshProvider(account, token)
    readback = retained.previous.prior.readback
    readback.complete(provider, f"accounts/{account}/queues", "queue_id", 100)
    reviewed = tomllib.loads((ROOT / "crates/mail-worker/wrangler.toml").read_text(encoding="utf-8"))

    def record(state: str, **facts: Any) -> None:
        journal("production", "api_capture", state, **facts)

    readback.capture_off(provider, "amail-mail", version,
        expected_bindings=retained.expected_bindings("queue-api", retained.QUEUES["production"][0], realm="production"),
        reviewed=reviewed["observability"], record=record)


def replace_api(realm: str) -> str:
    require_artifact()
    journal(realm, "api", "intent")
    # Wrangler preserves existing secrets on deploy. Do not rotate/re-upload
    # application keys for a code-only replacement; plain vars remain source-owned.
    # https://developers.cloudflare.com/workers/wrangler/commands/workers/#deploy
    command = ["wrangler", "deploy", "--config", str(ROOT / "crates/mail-worker/wrangler.toml")]
    if realm == "staging":
        command.extend(["--env", "staging"])
    try:
        version = submit(command, realm, "mail_api", cwd=ROOT / "crates/mail-worker")
    except DeploymentFailure as error:
        journal(realm, "api", "submit_unverified", **({"version": error.version} if error.version else {}))
        raise
    journal(realm, "api", "version_captured", version=version)
    if realm == "production":
        capture_api(version)
    else:
        retained.pin_api(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"], version,
                         phase="queue-api", queue_id=retained.QUEUES[realm][0])
    journal(realm, "api", "capture_verified", version=version)
    return version


def deploy(realm: str) -> None:
    mark_phase(realm + "_deployment_context")
    context(realm)
    if realm == "staging" and os.getenv("AMAIL_DEVICE_SOURCE_RUN"):
        raise ValueError("device_backend_recovery_stage_read_only")
    mark_phase(realm + "_artifact_preflight")
    require_artifact()
    authority = None
    if realm == "production":
        mark_phase("production_staging_acceptance")
        authority = staging_accepted()
    pins = dict(PINS[realm])
    mark_phase(realm + "_graph_preflight")
    before, policy = retained.observe(realm, pins)
    mark_phase(realm + "_schema_preflight")
    database = DatabaseClient(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"], realm)
    schema(database, realm, 19)
    checkpoint = {"realm": realm, "source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
                  "pins": pins, "artifact_id": os.environ["AMAIL_DEVICE_ARTIFACT_ID"],
                  "policy_fingerprint": retained.previous.prior.digest(policy),
                  "retained_fingerprint": retained.previous.prior.digest(before["retained"])}
    with (ROOT / f".temp/device-backend-{realm}-predecessor.json").open("x", encoding="utf-8") as file:
        json.dump(checkpoint, file, sort_keys=True)
    mark_phase(realm + "_migration")
    migrate(realm, database)
    suffix = "-staging" if realm == "staging" else ""
    mark_phase(realm + "_api_submit")
    pins["amail-mail" + suffix] = replace_api(realm)
    mark_phase(realm + "_graph_after_submit")
    after, _ = retained.observe(realm, pins, policy)
    if after["retained"] != before["retained"]:
        raise ValueError("device_backend_retained_graph_changed")
    mark_phase(realm + "_schema_after_submit")
    schema(database, realm, 20)
    mark_phase(realm + "_public_readback")
    public_ready(realm)
    # Bracket the public request with the same exact serving/retained graph.
    mark_phase(realm + "_graph_final_readback")
    final, _ = retained.observe(realm, pins, policy)
    if final != after:
        raise ValueError("device_backend_retained_graph_changed")
    value = {"schema": "device-backend/v1", "realm": realm, "migration": 20,
             "source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": 1,
             "artifact_id": os.environ["AMAIL_DEVICE_ARTIFACT_ID"], "api_version": pins["amail-mail" + suffix],
             "maintenance_version": pins["amail-mail-maintenance" + suffix], "sink_version": pins["amail-trace-sink" + suffix],
             "policy_fingerprint": retained.previous.prior.digest(policy),
             "retained_fingerprint": retained.previous.prior.digest(final["retained"]),
             "graph": final["graph"], "cron_changed": False, "secrets_changed": False,
             "producer": {**identity(), "artifact_id": os.environ["AMAIL_DEVICE_ARTIFACT_ID"]}}
    if authority is not None:
        value["staging_acceptance"] = authority
    with (ROOT / f".temp/device-backend-{realm}.json").open("x", encoding="utf-8") as file:
        json.dump(value, file, sort_keys=True)
    journal(realm, "complete", "verified", api_version=value["api_version"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("artifact-create", "artifact-restore", "source-admit", "verify-staging", "inspect-production", "deploy"))
    parser.add_argument("realm", nargs="?", choices=("staging", "production"))
    args = parser.parse_args()
    mark_phase(args.mode.replace("-", "_"))
    try:
        if args.mode == "deploy":
            if args.realm is None:
                parser.error("deploy requires a realm")
            deploy(args.realm)
        else:
            {"artifact-create": artifact_create, "artifact-restore": artifact_restore,
             "source-admit": source_admit, "verify-staging": verify_staging,
             "inspect-production": inspect_production}[args.mode]()
    except Exception as error:
        diagnostic = failure_diagnostic(error)
        realm = args.realm or ("production" if args.mode == "inspect-production" else "artifact")
        path = ROOT / f".temp/device-backend-{realm}-diagnostic.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(diagnostic, sort_keys=True), encoding="utf-8")
        print(json.dumps({"event": "device_backend_unverified", **diagnostic}, sort_keys=True))
        return 1
    print("device_backend=verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
