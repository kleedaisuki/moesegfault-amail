"""Protected first-production held bootstrap; no activation, retry or deletion.

The only executable writer creates a source/run-owned storage epoch after exact
same-run source admission and complete old-scope preconditions. It installs the
reader before producers, uses migration defaults to hold sending, and persists
a paused observation only after exact readback. Unknown external old work is
not relabelled as drained. Recovery observes owned coordinates without replay.
"""

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
sys.path.insert(0, str(ROOT / "crates/mail-worker"))
from fresh_bootstrap_contract import Epoch, Scope, REPO
from fresh_bootstrap_scope import FreshProvider, create_scope, render_configs, reconcile_scope
from fresh_bootstrap_readback import verify, verify_sink_reader, held_empty
from fresh_bootstrap_receipt import persist
from tested_worker_artifact import require_artifact
from worker_deploy_result import submit, DeploymentFailure
from control_plane_trace import span
from pin_staging_mail import UUID, serving_deployment
import worker_artifact
from native_fixture import api
from inbox_worker_artifact import REQUIRED, rows
import inspect_held_production as old
import ensure_trace_queues as queues
from check_production_role_graph import forward_snapshot
from mail_schema_contract import expected_schema, MIGRATIONS

CONFIRM = "RUN_FRESH_HELD_PRODUCTION_BOOTSTRAP"
SCRIPTS = {"sink": "amail-trace-sink", "maintenance": "amail-mail-maintenance", "api": "amail-mail"}
PHASES = ("admission", "old_scope", "create_scope", "render", "migrate", "queues", "sink",
          "sink_readback", "maintenance", "api", "readback", "receipt")


def verify_same_run_artifact(epoch: Epoch) -> None:
    """Require genuine completed full source jobs and the fixed original artifact.

    The enclosing workflow is still running; only required source jobs may have
    completed. A caller flag, a green producer alone, an ancestor or an attempt
    rerun cannot substitute for all source gates and immutable artifact identity.
    """
    if (os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("GITHUB_REPOSITORY") != REPO
            or os.getenv("GITHUB_REF") != "refs/heads/main" or os.getenv("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or os.getenv("GITHUB_RUN_ATTEMPT") != "1" or os.getenv("GITHUB_JOB") != "production-fresh-bootstrap"
            or os.getenv("GITHUB_SHA") != epoch.source_sha or os.getenv("GITHUB_RUN_ID") != epoch.run_id
            or os.getenv("AMAIL_PRODUCTION_BOOTSTRAP_CONFIRM") != CONFIRM
            or os.getenv("AMAIL_PRODUCTION_GRAPH_FREEZE") != "FREEZE_PRODUCTION_GRAPH_WRITERS"
            or os.getenv("AMAIL_PRODUCTION_ENVIRONMENT") != "production"
            or os.getenv("GITHUB_WORKFLOW_REF") != f"{REPO}/.github/workflows/ci.yml@refs/heads/main"):
        raise ValueError("fresh_protected_context_unverified")
    require_artifact("mail_api")
    manifest = worker_artifact.FOLDER / "manifest.json"
    identity = worker_artifact.context()
    if (hashlib.sha256(manifest.read_bytes()).hexdigest() != epoch.manifest_sha256
            or identity["rust"] != epoch.rust or identity["worker_build"] != epoch.worker_build):
        raise ValueError("fresh_original_artifact_changed")
    run = api(f"runs/{epoch.run_id}")
    if (not isinstance(run, dict) or type(run.get("id")) is not int or str(run["id"]) != epoch.run_id
            or type(run.get("run_attempt")) is not int or run["run_attempt"] != 1
            or run.get("head_sha") != epoch.source_sha or run.get("head_branch") != "main"
            or run.get("event") != "workflow_dispatch" or run.get("path") != ".github/workflows/ci.yml"
            or not isinstance(run.get("repository"), dict) or run["repository"].get("full_name") != REPO):
        raise ValueError("fresh_run_identity_unverified")
    listing = rows(api(f"runs/{epoch.run_id}/attempts/1/jobs?per_page=100"), "jobs")
    for name in REQUIRED:
        selected = [row for row in listing if row.get("name") == name]
        if (len(selected) != 1 or selected[0].get("status") != "completed"
                or selected[0].get("conclusion") != "success"):
            raise ValueError("fresh_full_source_checks_required")
    artifacts = rows(api(f"runs/{epoch.run_id}/artifacts?per_page=100"), "artifacts")
    selected = [row for row in artifacts if row.get("name") == f"worker-native-modules-{epoch.source_sha}"]
    if (len(selected) != 1 or type(selected[0].get("id")) is not int
            or selected[0]["id"] != epoch.artifact_id or selected[0].get("expired") is not False):
        raise ValueError("fresh_fixed_artifact_id_required")


def inspect_old_scope(provider, s3) -> dict:
    """Keep original stores untouched and reject existing-user abandonment.

    Current complete absence/held facts are bracketed; no failed read is empty.
    Source-owned owner-state tables must have migration-only population. Identity
    account storage is a different product and is neither queried nor migrated.
    Routing/sending history remains unknown, so this lane never activates work.
    """
    resources = old.configured_resources(os.environ["GITHUB_SHA"])
    reader = old.Provider(provider.account, provider.token, resources)
    zone = os.getenv("CLOUDFLARE_ZONE_ID", "")
    first_forward = forward_snapshot(provider.account)
    snapshots = []
    for _ in range(2):
        snapshot = old.collect(reader, zone, old.r2_count(s3, resources.bucket), allow_uninitialized=True)
        if snapshot["schema_prefix"] == 0:
            snapshots.append(snapshot)  # Positive metadata absence, never a failed table read.
            continue
        contract = expected_schema(snapshot["schema_prefix"])
        with sqlite3.connect(":memory:") as reference:
            for name in contract.migrations:
                reference.executescript((MIGRATIONS / name).read_text(encoding="utf-8"))
            for table in sorted(contract.columns):
                if table in {"send_policy_audit", "send_release_gate_audit"}:
                    continue  # Aggregate operator audit history is not abandoned user state.
                sql = f'SELECT COUNT(*) AS n FROM "{table}"'
                wanted = reference.execute(sql).fetchone()[0]
                actual = reader.query(sql)
                if actual != [{"n": wanted}] or type(actual[0].get("n")) is not int:
                    raise ValueError("production_retained_owner_state")
        snapshots.append(snapshot)
    if (old.stable_digest(snapshots[0]) != old.stable_digest(snapshots[1])
            or first_forward != forward_snapshot(provider.account)):
        raise ValueError("production_inventory_drift")
    return {"snapshot_sha256": old.stable_digest(snapshots[0]), "old_work_end": "UNVERIFIED",
            "original_stores": "RETAINED", "external_activation": "NOT_GRANTED",
            "sink_present": SCRIPTS["sink"] in snapshots[0]["scripts"]}


def migrate_and_hold_new_scope(provider, s3, scope: Scope, config: Path) -> None:
    """Submit source migrations once on new scope, then prove default-held state.

    Migration 0006 inserts held policy and zero grants. No redundant UPDATE is
    performed (its audit trigger would destroy the migration-only witness).
    An ambiguous migration result stops; recovery cannot run migrations again.
    Official workers-sdk tag wrangler@4.142.0, packages/wrangler/src:
    d1/migrations/apply.ts and index.ts globalFlags have no --yes; dialogs.ts
    confirm() already accepts its default in CI/non-interactive execution.
    CLI output is inspected only for fixed diagnostic categories, never emitted.
    """
    require_artifact("mail_api")
    with span("d1.migrations.apply", "migrate", realm="production", component="fresh_bootstrap") as facts:
        try:
            result = subprocess.run(["wrangler", "d1", "migrations", "apply", "MAIL_DB", "--remote",
                                     "--config", str(config)], cwd=ROOT,
                                    capture_output=True, text=True, check=False, timeout=300)
        except subprocess.TimeoutExpired:
            facts.reason = "submit_timeout_ambiguous"
            raise
        except OSError:
            facts.reason = "process_unavailable"
            raise
        facts.process_exit_code = result.returncode
        if len(result.stdout) + len(result.stderr) > 1_048_576:
            facts.reason = "output_limit"
            raise ValueError("fresh_migration_submit_unverified")
        if result.returncode:
            output = result.stdout + "\n" + result.stderr
            facts.reason = "process_exit"
            if re.search(r"\bUnknown arguments?:", output):
                facts.reason = "cli_unknown_argument"
            elif re.search(r"\b(?:Not enough non-option arguments|Missing required arguments?|"
                           r"Invalid values|Not enough arguments following):", output):
                facts.reason = "cli_parameter_parse"
            raise ValueError("fresh_migration_submit_unverified")
    held_empty(provider, f"accounts/{provider.account}", scope)
    if old.r2_count(s3, scope.bucket) != 0:
        raise ValueError("fresh_bucket_population_unverified")


def provision_trace_graph(provider) -> tuple[str, str]:
    """Reuse reviewed bounded Queue provisioning; never edit existing settings."""
    queues.reconcile(provider.account, provider.token, "production", "queues", "api-only")
    listing = queues.inventory(provider.account, provider.token)
    main = queues.exact_queue(listing, "amail-trace-events")
    dlq = queues.exact_queue(listing, "amail-trace-dlq")
    if main is None or dlq is None or main["queue_id"] == dlq["queue_id"]:
        raise ValueError("fresh_queue_identity_unverified")
    os.environ["AMAIL_TRACE_QUEUE_ID"] = main["queue_id"]
    os.environ["AMAIL_TRACE_DLQ_ID"] = dlq["queue_id"]
    return main["queue_id"], dlq["queue_id"]


def sink_config(folder: Path) -> Path:
    """Render the exact source sink with absolute entry and independent Issues off."""
    source = ROOT / "workers/trace-sink/wrangler.toml"
    text = source.read_text(encoding="utf-8")
    if text.count('main = "entry/queue.mjs"') != 1:
        raise ValueError("fresh_sink_entry_unreviewed")
    text = text.replace('main = "entry/queue.mjs"',
                        f'main = "{(source.parent / "entry/queue.mjs").as_posix()}"', 1)
    if "[observability.issues]" not in text.split("[env.staging]", 1)[0]:
        text = text.replace("[env.staging]", "[observability.issues]\nenabled = false\n\n[env.staging]", 1)
    target = folder / "sink.toml"
    with target.open("x", encoding="utf-8") as output:
        output.write(text)
    return target


def submit_once(role: str, config: Path, scope: Scope | None = None) -> str:
    """Deploy one same-artifact role; secrets are private and always removed."""
    if role not in SCRIPTS or (role != "sink" and not isinstance(scope, Scope)):
        raise ValueError("fresh_deploy_role_unreviewed")
    component = "trace_sink" if role == "sink" else "mail_api"
    require_artifact(component)
    command = ["wrangler", "deploy", "--config", str(config)]
    secret_path = None
    try:
        if role != "sink":
            names = ["OPENROUTER_API_KEY", "CF_EMAIL_ROUTING_TOKEN"]
            if role == "api":
                names.append("INGRESS_SECRET")
            secrets = {name: os.getenv(name, "") for name in names}
            if not all(secrets.values()):
                raise ValueError("fresh_project_secrets_missing")
            descriptor, name = tempfile.mkstemp(prefix="fresh-mail-secrets-", suffix=".json", dir=ROOT / ".temp")
            secret_path = Path(name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                secret_path.chmod(0o600)
                json.dump(secrets, output)
            command.extend(["--secrets-file", str(secret_path)])
        return submit(command, "production", component, cwd=ROOT)
    finally:
        if secret_path is not None:
            secret_path.unlink(missing_ok=True)


class Bootstrap:
    """One controlled paused graph writer with an append-only recovery journal."""

    def __init__(self, provider, s3, epoch: Epoch, recovery_path: Path, receipt_path: Path):
        """Caller coordinates never substitute for the protected admission or creator."""
        self.provider, self.s3, self.epoch = provider, s3, epoch
        self.recovery_path, self.receipt_path = Path(recovery_path), Path(receipt_path)
        self.phase, self.scope, self.pins = "admission", None, {}

    def _record(self, phase: str, state: str, **facts) -> None:
        """Flush owned aggregate intent before every potential write; no raw outputs."""
        value = {"schema": "mail-fresh-controller/v1", "epoch": asdict(self.epoch),
                 "phase": phase, "state": state, **facts}
        with self.recovery_path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
            output.flush()
            os.fsync(output.fileno())

    def run(self) -> dict:
        """Reach initial held receipt or stop with immutable owned recovery evidence."""
        self.recovery_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.recovery_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        self._record("admission", "intent")
        try:
            verify_same_run_artifact(self.epoch)
            self._record("admission", "observed")
            self.phase = "old_scope"
            self._record(self.phase, "intent")
            inspect_old_scope(self.provider, self.s3)
            self._record(self.phase, "observed")
            self.phase = "create_scope"
            self._record(self.phase, "intent")
            self.scope = create_scope(self.provider, self.epoch, self.recovery_path.with_suffix(".scope.jsonl"))
            self._record(self.phase, "observed", scope=asdict(self.scope))
            self.phase = "render"
            self._record(self.phase, "intent")
            folder = self.recovery_path.parent / "configs"
            folder.mkdir(exist_ok=False)
            configs = render_configs(self.scope, folder)
            configs["sink"] = sink_config(folder)
            self._record(self.phase, "observed")
            self.phase = "migrate"
            self._record(self.phase, "intent")
            migrate_and_hold_new_scope(self.provider, self.s3, self.scope, configs["api"])
            self._record(self.phase, "observed")
            self.phase = "queues"
            self._record(self.phase, "intent")
            queue, dlq = provision_trace_graph(self.provider)
            self._record(self.phase, "observed", queue=queue, dlq=dlq)
            self.provider.r2_empty = lambda bucket: old.r2_count(self.s3, bucket) == 0
            self.provider.forward_snapshot = forward_snapshot
            for role in ("sink", "maintenance", "api"):
                self.phase = role
                self._record(role, "intent")
                version = submit_once(role, configs[role], self.scope)
                self.pins[SCRIPTS[role]] = version
                self._record(role, "observed", version=version)
                if role == "sink":
                    self.phase = "sink_readback"
                    self._record(self.phase, "intent")
                    verify_sink_reader(self.scope, version, queue, dlq, self.provider)
                    self._record(self.phase, "observed")
            self.phase = "readback"
            self._record(self.phase, "intent")
            graph = verify(self.scope, self.pins, queue, dlq, self.provider)
            self._record(self.phase, "observed")
            self.phase = "receipt"
            self._record(self.phase, "intent")
            value = persist(self.scope, graph, queue, dlq, self.receipt_path)
            self._record(self.phase, "observed")
            return value
        except Exception as error:
            facts = {"error_type": type(error).__name__}
            if isinstance(error, DeploymentFailure) and error.version is not None:
                facts["version"] = error.version
            self._record(self.phase, "failed", **facts)
            raise

    def recover(self) -> dict:
        """Read owned intended coordinates once; never re-create/deploy/rollback.

        Recovery does not mint a success receipt, and an observed resource does
        not retroactively turn an ambiguous create into positive ownership.
        """
        if self.recovery_path.is_symlink() or self.recovery_path.stat().st_size > 65536:
            raise ValueError("fresh_recovery_journal_unverified")
        from mail_lifecycle_receipt import unique_object
        records = [json.loads(line, object_pairs_hook=unique_object)
                   for line in self.recovery_path.read_text(encoding="utf-8").splitlines()]
        if not records or len(records) > 32:
            raise ValueError("fresh_recovery_journal_unverified")
        basic = {"schema", "epoch", "phase", "state"}
        sequence = [(phase, state) for phase in PHASES for state in ("intent", "observed")]
        for index, row in enumerate(records):
            if (not isinstance(row, dict)
                    or row.get("schema") != "mail-fresh-controller/v1" or row.get("epoch") != asdict(self.epoch)
                    or row.get("phase") not in PHASES or row.get("state") not in {"intent", "observed", "failed"}):
                raise ValueError("fresh_recovery_journal_unverified")
            event = (row["phase"], row["state"])
            if row["state"] == "failed":
                if (index != len(records) - 1 or index == 0
                        or index >= len(sequence)
                        or (row["phase"], "observed") != sequence[index]):
                    raise ValueError("fresh_recovery_journal_unverified")
                expected = basic | {"error_type"} | ({"version"} if "version" in row else set())
                if (not isinstance(row["error_type"], str)
                        or re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,63}", row["error_type"]) is None
                        or "version" in row and row["phase"] not in SCRIPTS):
                    raise ValueError("fresh_recovery_journal_unverified")
            else:
                if index >= len(sequence) or event != sequence[index]:
                    raise ValueError("fresh_recovery_journal_unverified")
                extras = {"create_scope": {"scope"}, "queues": {"queue", "dlq"},
                          **{role: {"version"} for role in SCRIPTS}}
                expected = basic | (extras.get(row["phase"], set()) if row["state"] == "observed" else set())
            if set(row) != expected:
                raise ValueError("fresh_recovery_journal_unverified")
            if "version" in row and (not isinstance(row["version"], str) or not UUID.fullmatch(row["version"])):
                raise ValueError("fresh_recovery_journal_unverified")
            if "scope" in row:
                scope = row["scope"]
                if (not isinstance(scope, dict) or set(scope) != {"epoch", "database", "database_created_at", "bucket_created_at"}
                        or scope["epoch"] != asdict(self.epoch)):
                    raise ValueError("fresh_recovery_journal_unverified")
                Scope(self.epoch, scope["database"], scope["database_created_at"], scope["bucket_created_at"])
            if "queue" in row and (any(not isinstance(row[key], str) or re.fullmatch(r"[0-9a-f]{32}", row[key]) is None
                                       for key in ("queue", "dlq")) or row["queue"] == row["dlq"]):
                raise ValueError("fresh_recovery_journal_unverified")
        if records[0] != {"schema": "mail-fresh-controller/v1", "epoch": asdict(self.epoch),
                          "phase": "admission", "state": "intent"}:
            raise ValueError("fresh_recovery_journal_unverified")
        result = {"may_replay_write": False, "activation": "NOT_GRANTED", "receipt": "NOT_GRANTED", "pins": {}}
        if any(row["phase"] == "create_scope" and row["state"] == "intent" for row in records):
            result["scope"] = reconcile_scope(self.provider, self.epoch, self.recovery_path.with_suffix(".scope.jsonl"))
        for role, script in SCRIPTS.items():
            versions = [row["version"] for row in records if row["phase"] == role and "version" in row]
            if any(row["phase"] == role and row["state"] == "intent" for row in records):
                if len(versions) > 1:
                    raise ValueError("fresh_recovery_journal_unverified")
                try:
                    current = self.provider.get(f"accounts/{self.provider.account}/workers/scripts/{script}/deployments?per_page=1&page=1")
                    serving = serving_deployment(current)
                except Exception:
                    serving = None  # Failed reads never become resource absence.
                result["pins"][script] = {"captured_version": versions[0] if versions else None,
                                          "serving": serving,
                                          "observation": "OBSERVED" if serving is not None else "UNVERIFIED"}
        return result


def recover_main(run_id: str) -> int:
    """Admit immutable prior protected intent before one read-only observation.

    This separate operational lane has no build, secret mutation, migration,
    deploy, create, successful receipt or activation code path.
    """
    if (os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("GITHUB_REPOSITORY") != REPO
            or os.getenv("GITHUB_REF") != "refs/heads/main"
            or os.getenv("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or os.getenv("GITHUB_RUN_ATTEMPT") != "1"
            or os.getenv("GITHUB_JOB") != "recover"
            or os.getenv("GITHUB_WORKFLOW_REF") != f"{REPO}/.github/workflows/fresh-mail-bootstrap-recovery.yml@refs/heads/main"
            or os.getenv("AMAIL_BOOTSTRAP_RECOVERY_CONFIRM") != "OBSERVE_FRESH_BOOTSTRAP_NO_REPLAY"):
        raise ValueError("fresh_recovery_protected_context_required")
    from fresh_bootstrap_recovery import load
    folder = ROOT / ".temp/fresh-bootstrap-recovery" / run_id
    epoch, path = load(run_id, folder)
    provider = FreshProvider(os.getenv("CLOUDFLARE_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_API_TOKEN", ""))
    value = Bootstrap(provider, None, epoch, path, folder / "receipt.json").recover()
    with (folder / "observation.json").open("x", encoding="utf-8") as output:
        json.dump(value, output, sort_keys=True, allow_nan=False)
        output.write("\n")
    print("fresh_bootstrap_recovery=observed replay=NOT_GRANTED receipt=NOT_GRANTED")
    return 0


def preflight(state: str, error_type: str | None = None) -> None:
    """Retain bounded initial admission/refusal even when no controller can start.

    This diagnostic record is not a receipt, creation witness or recovery grant.
    Source/run metadata is accepted only in the established syntactic namespace;
    provider bodies, exception prose, private destinations and secrets are absent.
    """
    if state not in {"intent", "admitted", "failed"} or (
            error_type is not None and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,63}", error_type) is None):
        raise ValueError("fresh_preflight_record_unreviewed")
    sha, run = os.getenv("GITHUB_SHA", ""), os.getenv("GITHUB_RUN_ID", "")
    value = {"schema": "mail-fresh-preflight/v1", "state": state,
             "source_sha": sha if re.fullmatch(r"[0-9a-f]{40}", sha) else "UNVERIFIED",
             "run_id": run if re.fullmatch(r"[1-9][0-9]{0,19}", run) else "UNVERIFIED",
             "activation": "NOT_GRANTED", "replay": "NOT_GRANTED"}
    if error_type is not None:
        value["error_type"] = error_type
    path = ROOT / ".temp/fresh-bootstrap/recovery/preflight.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if state == "intent" else "a", encoding="utf-8") as output:
        output.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
        output.flush()
        os.fsync(output.fileno())


def main() -> int:
    """Expose only first held bootstrap; no active, legacy adoption or replay CLI."""
    writer_started = False
    try:
        import argparse
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--recover-run", help="Observe one immutable prior protected bootstrap without replay")
        arguments = parser.parse_args()
        if arguments.recover_run is not None:
            return recover_main(arguments.recover_run)
        preflight("intent")
        writer_started = True
        manifest = worker_artifact.FOLDER / "manifest.json"
        identity = worker_artifact.context()
        epoch = Epoch(identity["source_sha"], identity["run_id"], int(os.environ["AMAIL_WORKER_ARTIFACT_ID"]),
                      hashlib.sha256(manifest.read_bytes()).hexdigest(), identity["rust"])
        verify_same_run_artifact(epoch)  # Credentials/SDK creation occurs only after admission.
        preflight("admitted")
        required = ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCESS_KEY_ID",
                    "CLOUDFLARE_SECRET_ACCESS_KEY", "CF_EMAIL_ROUTING_TOKEN", "OPENROUTER_API_KEY",
                    "INGRESS_SECRET", "ROLE_FORWARD_DESTINATION")
        if not all(os.getenv(name, "") for name in required):
            raise ValueError("fresh_project_capabilities_missing")
        provider = FreshProvider(os.getenv("CLOUDFLARE_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_API_TOKEN", ""))
        import boto3
        from botocore.config import Config
        access, secret = os.getenv("CLOUDFLARE_ACCESS_KEY_ID", ""), os.getenv("CLOUDFLARE_SECRET_ACCESS_KEY", "")
        if not access or not secret:
            raise ValueError("fresh_r2_capability_missing")
        s3 = boto3.client("s3", endpoint_url=f"https://{provider.account}.r2.cloudflarestorage.com",
                          aws_access_key_id=access, aws_secret_access_key=secret, region_name="auto",
                          config=Config(connect_timeout=15, read_timeout=30, retries={"max_attempts": 0}))
        folder = ROOT / ".temp/fresh-bootstrap"
        prior_run = os.getenv("AMAIL_FRESH_BOOTSTRAP_RUN_ID", "")
        if prior_run:
            from resume_fresh_mail import run
            run(provider, s3, epoch, prior_run, folder)
        else:
            Bootstrap(provider, s3, epoch, folder / "recovery/controller.jsonl", folder / "receipt.json").run()
        print("fresh_production_bootstrap=paused_receipt activation=NOT_GRANTED source_adoption=REQUIRED")
        return 0
    except Exception as error:
        if writer_started:
            preflight("failed", type(error).__name__)
        print(f"fresh_production_bootstrap=UNVERIFIED error_type={type(error).__name__} "
              f"reason={old.failure_reason(error)} replay=NOT_GRANTED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
