"""Complete the actually owned, still-empty first Mail scope without recreating it.

Only the actual migration-stop and observed-sink checkpoints are supported. Immutable
successful create/readback records establish storage ownership; current positive
schema and whole-bucket reads determine remaining migration work. No old run is
relabeled successful and no resource creation or ambiguous deploy replay exists.
"""

from dataclasses import asdict
import json
import os
from pathlib import Path
import sqlite3

from fresh_bootstrap_contract import Epoch, Scope
from fresh_bootstrap_recovery import load, load_sink_checkpoint
from fresh_bootstrap_scope import reconcile_scope, render_configs
from fresh_bootstrap_receipt import persist
from fresh_bootstrap_readback import held_empty, verify, verify_sink_reader, verify_sink_replacement
from mail_schema_contract import MIGRATIONS, SCHEMA_SQL, expected_schema, verify_schema
from production_bootstrap_contract import ProductionResources
from worker_deploy_result import DeploymentFailure
import fresh_mail_bootstrap as bootstrap
import inspect_held_production as old


def migration_prefix(reader) -> int:
    """Prove exact source schema and migration-default population before any DDL.

    Missing metadata is never inferred from a failed query. Recorded partial
    migrations are retained and only their unapplied successors may be applied.
    Any application object without provenance or retained user row refuses.
    """
    objects = reader.query(old.INITIAL_SCHEMA)
    if objects == []:
        return 0
    if {"type": "table", "name": "d1_migrations"} not in objects:
        raise ValueError("fresh_resume_unrecorded_schema")
    recorded = reader.query("SELECT name FROM d1_migrations ORDER BY id")
    complete = expected_schema()
    if recorded == []:
        if reader.query(SCHEMA_SQL) != []:
            raise ValueError("fresh_resume_unrecorded_schema")
        return 0
    if (not 1 <= len(recorded) <= len(complete.migrations)
            or recorded != [{"name": name} for name in complete.migrations[:len(recorded)]]):
        raise ValueError("fresh_resume_migration_prefix_unverified")
    contract = expected_schema(len(recorded))
    verify_schema(reader.query, contract)
    with sqlite3.connect(":memory:") as reference:
        for name in contract.migrations:
            reference.executescript((MIGRATIONS / name).read_text(encoding="utf-8"))
        for table in sorted(contract.columns):
            sql = f'SELECT COUNT(*) AS n FROM "{table}"'
            actual = reader.query(sql)
            if (actual != [{"n": reference.execute(sql).fetchone()[0]}]
                    or type(actual[0].get("n")) is not int):
                raise ValueError("fresh_resume_retained_state")
    if len(recorded) >= 6:
        old.held_state(reader.query(old.POLICY), reader.query(old.GATES),
                       reader.query("SELECT COUNT(*) AS n FROM send_requests"),
                       reader.query("SELECT COUNT(*) AS n FROM storage_reservations"), 0)
    return len(recorded)


def owned_scope(provider, prior_run: str, folder: Path) -> Scope:
    """Load original protected evidence and positively re-observe both created stores."""
    creation_epoch, controller = load(prior_run, folder / "prior")
    records = [json.loads(line) for line in controller.read_text(encoding="utf-8").splitlines()]
    if records[-1].get("phase") != "migrate" or records[-1].get("state") != "failed":
        raise ValueError("fresh_resume_migration_failure_required")
    scope_path = controller.with_suffix(".scope.jsonl")
    records = [json.loads(line) for line in scope_path.read_text(encoding="utf-8").splitlines()]
    if records[-1].get("event") != "scope_readback_verified":
        raise ValueError("fresh_resume_complete_creation_required")
    value = records[-1]["scope"]
    scope = Scope(creation_epoch, value["database"], value["database_created_at"], value["bucket_created_at"])
    observed = reconcile_scope(provider, creation_epoch, scope_path)
    if any(observed.get(name) != "CREATED_IDENTITY_OBSERVED" for name in ("database", "bucket")):
        raise ValueError("fresh_resume_owned_store_readback_required")
    provider._epoch, provider._scope = creation_epoch, scope
    return scope


def run(provider, s3, deployment_epoch: Epoch, prior_run: str, folder: Path) -> dict:
    """Reach a genuine paused-first v3 receipt using this run's tested deployment bytes.

    The caller already performs the unchanged protected full same-run admission.
    Root separately authorizes completing the positively created empty scope.
    A second invocation cannot replace this run's exclusive journal or retry writes.
    """
    recovery = folder / "recovery"
    recovery.mkdir(parents=True, exist_ok=True)
    journal = recovery / "resume.jsonl"
    phase = "ownership"
    creation_run = prior_run
    with journal.open("x", encoding="utf-8") as output:
        def record(state: str, **facts) -> None:
            """Flush closed stage facts before every potential write; no tool output."""
            value = {"schema": "mail-fresh-resume/v1", "phase": phase, "state": state,
                     "deployment_epoch": asdict(deployment_epoch), "creation_run": creation_run, **facts}
            output.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
            output.flush()
            os.fsync(output.fileno())

        try:
            checkpoint = load_sink_checkpoint(prior_run, folder / "checkpoint")
            if checkpoint is not None:
                creation_run, sink_epoch, sink_version, queue, dlq, replace_needed = checkpoint
            record("intent")
            scope = owned_scope(provider, creation_run, folder)
            if checkpoint is not None:
                observed = json.loads((folder / "checkpoint/resume.jsonl").read_text(encoding="utf-8").splitlines()[1])
                if observed["scope"] != asdict(scope) or observed["creation_epoch"] != asdict(scope.epoch):
                    raise ValueError("fresh_resume_checkpoint_scope_mismatch")
            old_scope = bootstrap.inspect_old_scope(provider, s3)
            if old_scope["sink_present"] != (checkpoint is not None):
                raise ValueError("fresh_resume_prior_deployment_requires_reconciliation")
            resources = ProductionResources(scope.database, scope.bucket, deployment_epoch.source_sha)
            reader = old.Provider(provider.account, provider.token, resources)
            if old.r2_count(s3, scope.bucket) != 0:
                raise ValueError("fresh_resume_bucket_population_unverified")
            prefix = migration_prefix(reader)
            if checkpoint is not None and prefix != len(expected_schema().migrations):
                raise ValueError("fresh_resume_completed_migration_required")
            record("observed", creation_epoch=asdict(scope.epoch), scope=asdict(scope), schema_prefix=prefix)
            configs = render_configs(scope, folder / "configs")
            configs["sink"] = bootstrap.sink_config(folder / "configs")
            provider.r2_empty = lambda bucket: old.r2_count(s3, bucket) == 0
            provider.forward_snapshot = bootstrap.forward_snapshot
            pins = {}
            retained = {}
            roles = ("sink", "maintenance", "api")
            if checkpoint is None:
                phase = "migrate"
                record("intent")
                if prefix < len(expected_schema().migrations):
                    bootstrap.migrate_and_hold_new_scope(provider, s3, scope, configs["api"])
                else:
                    held_empty(provider, f"accounts/{provider.account}", scope)
                record("observed")
                phase = "queues"
                record("intent")
                queue, dlq = bootstrap.provision_trace_graph(provider)
                record("observed", queue=queue, dlq=dlq)
            else:
                # Storage/DDL/queues stay retained. Replace only the legacy SDK
                # surface; an observed completed wrapper is read back, not resent.
                phase = "retained_sink"
                record("intent")
                held_empty(provider, f"accounts/{provider.account}", scope)
                if replace_needed:
                    verify_sink_replacement(scope, sink_version, queue, dlq, provider)
                else:
                    verify_sink_reader(scope, sink_version, queue, dlq, provider)
                    pins[bootstrap.SCRIPTS["sink"]] = sink_version
                    retained = {"source_epoch": asdict(sink_epoch), "version": sink_version}
                    roles = ("maintenance", "api")
                record("observed", source_epoch=asdict(sink_epoch), version=sink_version, queue=queue, dlq=dlq)
            for role in roles:
                replacing = role == "sink" and checkpoint is not None
                phase = "sink_replacement" if replacing else role
                record("intent", **({"previous_version": sink_version} if replacing else {}))
                version = bootstrap.submit_once(role, configs[role], scope)
                pins[bootstrap.SCRIPTS[role]] = version
                record("observed", version=version)
                if role == "sink":
                    phase = "sink_readback"
                    record("intent")
                    verify_sink_reader(scope, version, queue, dlq, provider)
                    record("observed")
            phase = "receipt"
            record("intent")
            graph = verify(scope, pins, queue, dlq, provider)
            value = persist(scope, graph, queue, dlq, folder / "receipt.json",
                            deployment_epoch=deployment_epoch, **({"retained_sink": retained} if retained else {}))
            record("observed")
            return value
        except Exception as error:
            facts = {"error_type": type(error).__name__}
            if isinstance(error, DeploymentFailure) and error.version is not None:
                facts["version"] = error.version
            record("failed", **facts)
            raise
