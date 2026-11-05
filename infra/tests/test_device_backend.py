"""Incremental Mail API rollout: exact bytes, schema 0020, retained graph and consent."""
from __future__ import annotations

from contextlib import ExitStack, closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import device_backend as deploy

SOURCE = "a" * 40
VERSION = "11111111-1111-4111-8111-111111111111"
IDENTITY: dict[str, Any] = {"schema": "worker-native-artifact/v1", "source_sha": SOURCE,
    "run_id": "123", "run_attempt": 1, "rust": "1.98.1", "worker_build": "0.8.5"}
ENV = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "kleedaisuki/moesegfault-amail",
       "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
       "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": SOURCE,
       "AMAIL_DEVICE_ARTIFACT_ID": "456", "AMAIL_DEVICE_CONFIRM": "RUN_DEVICE_BACKEND_STAGING",
       "CLOUDFLARE_ACCOUNT_ID": "synthetic-account", "CLOUDFLARE_API_TOKEN": "synthetic-token"}


class DeviceBackendTests(unittest.TestCase):
    def test_same_run_artifact_restores_only_generated_bytes_and_detects_changes(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder, ExitStack() as stack:
            root = Path(folder)
            package = root / ".temp/ci/device-backend"
            stack.enter_context(patch.object(deploy, "ROOT", root))
            stack.enter_context(patch.object(deploy, "FOLDER", package))
            stack.enter_context(patch.object(deploy.artifact, "context", return_value=IDENTITY))
            for name in (*deploy.ENTRIES, "crates/mail-worker/build/index.js", "crates/mail-worker/build/worker/shim.mjs"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("synthetic public input", encoding="utf-8")
            deploy.artifact_create()
            shutil.rmtree(root / deploy.TREES[0])
            deploy.artifact_restore()
            deploy.require_artifact()
            (root / deploy.ENTRIES[-1]).write_text("changed migration", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "device_backend_installed_bytes_changed"):
                deploy.require_artifact()
            with patch.object(deploy.artifact, "context", return_value={**IDENTITY, "run_id": "124"}):
                with self.assertRaisesRegex(ValueError, "device_backend_artifact_unverified"):
                    deploy.artifact_verified()

    def test_context_requires_the_explicit_realm_writer_and_first_main_attempt(self) -> None:
        with patch.dict(os.environ, ENV, clear=True), patch.object(deploy.artifact, "context", return_value=IDENTITY):
            deploy.context("staging")
            for change in ({"GITHUB_RUN_ATTEMPT": "2"}, {"GITHUB_REF": "refs/heads/unreviewed"},
                           {"AMAIL_DEVICE_CONFIRM": "RUN_DEVICE_BACKEND_PRODUCTION"}, {"AMAIL_DEVICE_ARTIFACT_ID": ""}):
                with patch.dict(os.environ, change):
                    with self.assertRaisesRegex(ValueError, "device_backend_context_unverified"):
                        deploy.context("staging")
            with patch.dict(os.environ, {"AMAIL_DEVICE_CONFIRM": "RUN_DEVICE_BACKEND_PRODUCTION"}):
                with self.assertRaisesRegex(ValueError, "device_backend_context_unverified"):
                    deploy.context("production")
                with patch.dict(os.environ, {"AMAIL_PRODUCTION_GRAPH_FREEZE": "FREEZE_PRODUCTION_GRAPH_WRITERS"}):
                    deploy.context("production")

    def test_schema_19_to_20_is_additive_and_preserves_existing_billing_session(self) -> None:
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.row_factory = sqlite3.Row
            migrations = sorted((ROOT / "crates/mail-worker/migrations").glob("*.sql"))
            for file in migrations[:19]:
                connection.executescript(file.read_text(encoding="utf-8"))
            connection.executescript("CREATE TABLE d1_migrations(id INTEGER PRIMARY KEY,name TEXT,applied_at TEXT);")
            connection.executemany("INSERT INTO d1_migrations(name) VALUES(?)", [(file.name,) for file in migrations[:19]])
            connection.execute("INSERT INTO billing_sessions(id,owner_iss,owner_sub,action,requested_plan,created_at,expires_at) VALUES('intent','issuer','subject','subscribe','plus',1,2)")
            database = Mock()
            database.query.side_effect = lambda sql: {"results": [dict(row) for row in connection.execute(sql)]}
            deploy.schema(database, "production", 19)
            connection.executescript(migrations[19].read_text(encoding="utf-8"))
            connection.execute("INSERT INTO d1_migrations(name) VALUES(?)", (migrations[19].name,))
            deploy.schema(database, "production", 20)
            self.assertEqual(tuple(connection.execute("SELECT id,state,user_code FROM billing_sessions").fetchone()), ("intent", "pending", None))

    def test_staging_rollout_has_only_one_migration_and_one_api_submit_without_secret_updates(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder, ExitStack() as stack:
            root = Path(folder)
            (root / ".temp").mkdir()
            stack.enter_context(patch.object(deploy, "ROOT", root))
            stack.enter_context(patch.dict(os.environ, ENV, clear=True))
            stack.enter_context(patch.object(deploy.artifact, "context", return_value=IDENTITY))
            check = stack.enter_context(patch.object(deploy, "require_artifact"))
            observed = {"retained": {"adapters": "unchanged"}, "graph": {"cadence": "unchanged"}}
            observe = stack.enter_context(patch.object(deploy.retained, "observe", return_value=(observed, {})))
            stack.enter_context(patch.object(deploy, "DatabaseClient"))
            schema = stack.enter_context(patch.object(deploy, "schema"))
            migration = stack.enter_context(patch.object(deploy.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)))
            submit = stack.enter_context(patch.object(deploy, "submit", return_value=VERSION))
            pin = stack.enter_context(patch.object(deploy.retained, "pin_api"))
            stack.enter_context(patch.object(deploy, "public_ready"))
            deploy.deploy("staging")
            self.assertEqual(check.call_count, 3)
            self.assertEqual([call.args[2] for call in schema.call_args_list], [19, 20, 20])
            self.assertEqual(migration.call_args.args[0], ["wrangler", "d1", "migrations", "apply", "MAIL_DB", "--remote", "--env", "staging"])
            submit.assert_called_once()
            command = submit.call_args.args[0]
            self.assertNotIn("--secrets-file", command)
            self.assertEqual(command, ["wrangler", "deploy", "--config", str(root / "crates/mail-worker/wrangler.toml"), "--env", "staging"])
            pin.assert_called_once()
            pins = observe.call_args_list[-1].args[1]
            self.assertEqual(pins["amail-mail-staging"], VERSION)
            self.assertEqual(pins["amail-mail-maintenance-staging"], deploy.PINS["staging"]["amail-mail-maintenance-staging"])
            receipt = json.loads((root / ".temp/device-backend-staging.json").read_text(encoding="utf-8"))
            self.assertFalse(receipt["cron_changed"])
            self.assertFalse(receipt["secrets_changed"])
            self.assertEqual(receipt["migration"], 20)
            with self.assertRaises(FileExistsError):
                deploy.deploy("staging")
            submit.assert_called_once()

    def test_production_capture_uses_same_provider_catalog_and_own_journal(self) -> None:
        provider = Mock(account="synthetic-account", token="synthetic-token")
        with patch.dict(os.environ, ENV, clear=True), ExitStack() as stack:
            stack.enter_context(patch.object(deploy.retained.previous, "FreshProvider", return_value=provider))
            inventory = stack.enter_context(patch.object(deploy.retained.previous.prior.readback, "complete"))
            capture = stack.enter_context(patch.object(deploy.retained.previous.prior.readback, "capture_off"))
            journal = stack.enter_context(patch.object(deploy, "journal"))
            deploy.capture_api(VERSION)
            inventory.assert_called_once_with(provider, "accounts/synthetic-account/queues", "queue_id", 100)
            self.assertIs(capture.call_args.args[0], provider)
            self.assertEqual(capture.call_args.args[1:3], ("amail-mail", VERSION))
            capture.call_args.kwargs["record"]("unchanged", version=VERSION)
            journal.assert_called_once_with("production", "api_capture", "unchanged", version=VERSION)

    def test_public_propagation_retries_only_the_readback(self) -> None:
        with patch.object(deploy, "public_readback", side_effect=[URLError("synthetic"), None]) as read, \
             patch.object(deploy.time, "sleep") as sleep, patch.object(deploy, "submit") as submit:
            deploy.public_ready("staging")
            self.assertEqual(read.call_count, 2)
            sleep.assert_called_once()
            submit.assert_not_called()

    def test_ambiguous_api_submit_keeps_version_and_never_retries(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder, ExitStack() as stack:
            root = Path(folder)
            stack.enter_context(patch.object(deploy, "ROOT", root))
            stack.enter_context(patch.dict(os.environ, ENV, clear=True))
            stack.enter_context(patch.object(deploy, "require_artifact"))
            submit = stack.enter_context(patch.object(deploy, "submit", side_effect=deploy.DeploymentFailure("process_exit", VERSION)))
            pin = stack.enter_context(patch.object(deploy.retained, "pin_api"))
            with self.assertRaises(deploy.DeploymentFailure):
                deploy.replace_api("staging")
            submit.assert_called_once()
            pin.assert_not_called()
            rows = [json.loads(line) for line in (root / ".temp/device-backend-staging-partial.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[-1]["state"], "submit_unverified")
            self.assertEqual(rows[-1]["version"], VERSION)

    def test_production_requires_same_run_successful_staging_journey(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder, ExitStack() as stack:
            root = Path(folder)
            (root / ".temp").mkdir()
            stack.enter_context(patch.object(deploy, "ROOT", root))
            stack.enter_context(patch.dict(os.environ, ENV, clear=True))
            receipt: dict[str, Any] = {"schema": "device-backend/v1", "realm": "staging", "migration": 20,
                "source_sha": SOURCE, "run_id": "123", "run_attempt": 1, "artifact_id": "456", "api_version": VERSION,
                "maintenance_version": deploy.PINS["staging"]["amail-mail-maintenance-staging"],
                "sink_version": deploy.PINS["staging"]["amail-trace-sink-staging"], "cron_changed": False, "secrets_changed": False}
            acceptance: dict[str, Any] = {"schema": "device-staging-acceptance/v1", "source_sha": SOURCE,
                "run_id": "123", "run_attempt": "1", "backend_artifact_id": "456", "api_version": VERSION,
                "issuer": "https://identity-staging.moesegfault.dev", "client_id": "amail-cli-staging",
                "login": "persisted", "billing": "pending_handoff_then_cancelled", "cleanup": "complete"}
            (root / ".temp/device-backend-staging.json").write_text(json.dumps(receipt), encoding="utf-8")
            path = root / ".temp/device-staging-acceptance.json"
            path.write_text(json.dumps(acceptance), encoding="utf-8")
            deploy.staging_accepted()
            for change in ({"cleanup": "incomplete"}, {"api_version": "other"}, {"run_id": "124"}, {"billing": "pending"}):
                path.write_text(json.dumps({**acceptance, **change}), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "device_backend_staging_acceptance_unverified"):
                    deploy.staging_accepted()


if __name__ == "__main__":
    unittest.main()
