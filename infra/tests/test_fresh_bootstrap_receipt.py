"""Hosted synthetic v2 provenance/archive/storage tests; v1 policy stays unchanged."""

from copy import deepcopy
from dataclasses import asdict
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import fresh_bootstrap_receipt as record
from fresh_bootstrap_readback import VerifiedGraph, _OBSERVED
from mail_lifecycle_receipt import scripts
from test_fresh_bootstrap_readback import fixture_scope, VERSION, DEPLOYMENT, QUEUE, DLQ


def fixture():
    """An exact fresh storage receipt still explicitly denies activation and drain."""
    scope = fixture_scope()
    graph = {"pins": {name: {"version": VERSION, "deployment": DEPLOYMENT}
                      for name in scripts("production")},
             "api_crons": [], "maintenance_crons": [], "topology": "api-scheduled"}
    return {"schema": record.SCHEMA, "realm": "production", "state": "paused", "source_epoch": asdict(scope.epoch),
            "run_attempt": 1, "scope": {"database": scope.database, "database_name": scope.database_name,
                "database_created_at": scope.database_created_at, "bucket": scope.bucket, "bucket_created_at": scope.bucket_created_at},
            "creation": {"database": record.CREATION, "bucket": record.CREATION}, "graph": graph,
            "resources": {"database": scope.database, "bucket": scope.bucket, "queue": QUEUE, "dlq": DLQ},
            "sendHeld": True, "originalstores": {"database": record.ORIGINAL_DATABASE, "bucket": record.ORIGINAL_BUCKET, "retained": True},
            "source_adoption": "REQUIRED", "activation": "NOT_GRANTED", "old_work_end": "UNVERIFIED"}


def archive(value, name="receipt.json", extra=None):
    """Build bounded in-memory archives; no extraction or account access occurs."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zipped:
        zipped.writestr(name, value if isinstance(value, str) else json.dumps(value))
        if extra:
            zipped.writestr(extra, "unexpected")
    return stream.getvalue()


def origin_fixture():
    """Successful exact protected CI dispatch, not a PR/research/source gate run."""
    run = {"id": 123, "run_attempt": 1, "status": "completed", "conclusion": "success", "event": "workflow_dispatch",
           "head_branch": "main", "path": record.WORKFLOW, "head_sha": "c" * 40, "repository": {"full_name": record.REPO}}
    jobs = {"jobs": [{"name": record.JOB, "run_id": 123, "head_sha": run["head_sha"],
                      "status": "completed", "conclusion": "success"}], "total_count": 1}
    return run, jobs


class FreshReceiptTests(unittest.TestCase):
    """Self-authored success-looking JSON never replaces protected producer origin."""

    def test_resumed_v3_separates_positive_creation_from_current_deployment_source(self):
        """Old v2 stays closed; v3's current origin never renames the owned old scope."""
        value = fixture()
        creation = deepcopy(value["source_epoch"])
        value["schema"] = record.RESUMED_SCHEMA
        value["creation_epoch"] = creation
        value["source_epoch"] = {**creation, "source_sha": "d" * 40, "run_id": "456", "artifact_id": 43}
        self.assertEqual(record.validate(value), value)
        changed = deepcopy(value)
        changed["schema"] = record.SCHEMA
        with self.assertRaises(ValueError):
            record.validate(changed)
        changed = deepcopy(value)
        changed["creation_epoch"]["run_id"] = "789"
        with self.assertRaisesRegex(ValueError, "fresh_receipt_scope_mismatch"):
            record.validate(changed)

    def test_closed_first_paused_schema_rejects_every_missing_or_extra_field(self):
        """Stored claims are fixed, including adoption-required and old-work unknown."""
        value = fixture()
        self.assertEqual(record.validate(value), value)
        for key in value:
            changed = deepcopy(value)
            del changed[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                record.validate(changed)
        with self.assertRaises(ValueError):
            record.validate({**value, "drain_granted": True})

    def test_original_stores_active_schedule_and_grants_rejected(self):
        """Fresh isolated population is not universal external-work or activation proof."""
        for field, bad in (("state", "active"), ("sendHeld", False), ("activation", "GRANTED"),
                           ("source_adoption", "ADOPTED"), ("old_work_end", "COMPLETE"), ("run_attempt", True)):
            value = fixture()
            value[field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                record.validate(value)
        value = fixture()
        value["scope"]["database"] = record.ORIGINAL_DATABASE
        value["resources"]["database"] = record.ORIGINAL_DATABASE
        with self.assertRaises(ValueError):
            record.validate(value)
        value = fixture()
        value["graph"]["maintenance_crons"] = ["*/5 * * * *"]
        with self.assertRaises(ValueError):
            record.validate(value)

    def test_source_scope_compiler_and_queue_identity_are_closed(self):
        """No user-entered bucket name, substituted artifact or ambiguous queue set."""
        for section, key, bad in (("source_epoch", "artifact_id", True), ("source_epoch", "manifest_sha256", "wrong"),
                                   ("source_epoch", "worker_build", "latest"), ("scope", "bucket", record.ORIGINAL_BUCKET),
                                   ("scope", "database_created_at", "yesterday"), ("resources", "dlq", QUEUE)):
            value = fixture()
            value[section][key] = bad
            with self.subTest(section=section, key=key), self.assertRaises(ValueError):
                record.validate(value)

    def test_persistence_requires_exact_unchanged_success_witness_and_context(self):
        """No plain graph JSON is enough; writes are exclusive and scoped to .temp."""
        scope, value = fixture_scope(), fixture()
        temp = ROOT / ".temp"
        temp.mkdir(exist_ok=True)
        env = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_REPOSITORY": record.REPO,
               "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_JOB": "production-fresh-bootstrap",
               "GITHUB_WORKFLOW_REF": f"{record.REPO}/{record.WORKFLOW}@refs/heads/main",
               "GITHUB_RUN_ATTEMPT": "1", "GITHUB_RUN_ID": scope.epoch.run_id, "GITHUB_SHA": scope.epoch.source_sha}
        with tempfile.TemporaryDirectory(dir=temp, prefix="fresh-receipt-test-") as folder:
            path = Path(folder) / "receipt.json"
            with self.assertRaisesRegex(ValueError, "fresh_successful_readback_required"):
                record.persist(scope, value["graph"], QUEUE, DLQ, path)
            observed = VerifiedGraph(value["graph"], scope, QUEUE, DLQ, _witness=_OBSERVED)
            with patch.dict(os.environ, env, clear=True):
                self.assertEqual(record.persist(scope, observed, QUEUE, DLQ, path), value)
                with self.assertRaises(FileExistsError):
                    record.persist(scope, observed, QUEUE, DLQ, path)
                observed["api_crons"].append("*/5 * * * *")
                with self.assertRaisesRegex(ValueError, "fresh_graph_witness_changed"):
                    record.persist(scope, observed, QUEUE, DLQ, path)

    def test_origin_rejects_pr_rerun_wrong_workflow_repo_job_or_incomplete_inventory(self):
        """Protected first-attempt job identity is not inferred from correct-looking JSON."""
        run, jobs = origin_fixture()
        self.assertEqual(record.origin(run, jobs, "123"), run["head_sha"])
        for field, bad in (("head_branch", "feature"), ("event", "pull_request"), ("run_attempt", 2),
                           ("path", ".github/workflows/mail-lifecycle.yml"), ("conclusion", "failure"),
                           ("repository", {"full_name": "other/repo"})):
            changed = deepcopy(run)
            changed[field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                record.origin(changed, jobs, "123")
        for bad in ({"jobs": jobs["jobs"], "total_count": 2},
                    {"jobs": [{**jobs["jobs"][0], "name": "Infrastructure"}], "total_count": 1}):
            with self.assertRaises(ValueError):
                record.origin(run, bad, "123")

    def load_fixture(self, raw=None, value=None, artifacts=None):
        """Substitute only GitHub metadata transport; admission logic executes fully."""
        run, jobs = origin_fixture()
        artifact = {"name": "mail-fresh-bootstrap-123-1", "id": 789, "expired": False, "size_in_bytes": 4096}
        responses = [run, jobs, artifacts or {"artifacts": [artifact], "total_count": 1}, raw or archive(value or fixture())]
        with patch.object(record, "github", side_effect=responses) as transport:
            receipt = record.load("123")
            self.assertEqual(transport.call_args.args[0], "artifacts/789/zip")
            return receipt

    def test_loader_preserves_original_artifact_source_and_immutable_record(self):
        """Receipt artifact ID and tested module artifact ID are distinct coordinates."""
        receipt = self.load_fixture()
        self.assertEqual(receipt.artifact_id, 789)
        self.assertEqual(receipt.value["source_epoch"]["artifact_id"], 456)
        changed = receipt.value
        changed["sendHeld"] = False
        self.assertTrue(receipt.value["sendHeld"])

    def test_archive_wrong_member_extra_duplicate_keys_and_source_mismatch_rejected(self):
        """No path traversal, multiple members or duplicate-key overwrite admission."""
        duplicate = json.dumps(fixture()).replace('"sendHeld": true', '"sendHeld": false, "sendHeld": true')
        for raw in (archive(fixture(), "../receipt.json"), archive(fixture(), extra="other.json"), archive(duplicate)):
            with self.subTest(archive_bytes=len(raw)), self.assertRaises(ValueError):
                self.load_fixture(raw=raw)
        value = fixture()
        value["source_epoch"]["source_sha"] = "f" * 40
        # Scope names must remain epoch-derived as well, so this already fails closed.
        with self.assertRaises(ValueError):
            self.load_fixture(value=value)

    def test_archive_duplicate_name_expired_and_incomplete_artifacts_rejected(self):
        """Download original immutable ID only after a bounded complete unique list."""
        row = {"name": "mail-fresh-bootstrap-123-1", "id": 789, "expired": False, "size_in_bytes": 4096}
        for value in ({"artifacts": [row, row], "total_count": 2},
                      {"artifacts": [{**row, "expired": True}], "total_count": 1},
                      {"artifacts": [row], "total_count": 2}):
            with self.assertRaises(ValueError):
                self.load_fixture(artifacts=value)


if __name__ == "__main__":
    unittest.main()
