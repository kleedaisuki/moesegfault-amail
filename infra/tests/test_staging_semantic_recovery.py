"""The named continuation inspects schema before its sole maintenance write."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Any
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import staging_semantic_recovery as recovery


class RecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        (ROOT / ".temp").mkdir(exist_ok=True)

    def database(self) -> tuple[sqlite3.Connection, Mock]:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        self.addCleanup(connection.close)
        names = []
        for path in sorted(recovery.schema.MIGRATIONS.glob("*.sql")):
            connection.executescript(path.read_text(encoding="utf-8"))
            names.append(path.name)
        auxiliary = (ROOT / "infra/deploy/staging-acceptance-migrations/0001_quota_escrow.sql").read_text(encoding="utf-8")
        connection.executescript(auxiliary)
        connection.executescript(auxiliary.replace("staging_acceptance_", "staging_d1_probe_"))
        connection.execute("CREATE TABLE d1_migrations(id INTEGER PRIMARY KEY,name TEXT)")
        connection.executemany("INSERT INTO d1_migrations(name) VALUES(?)", [(name,) for name in names])
        database = Mock()
        database.query.side_effect = lambda sql: {"results": recovery.schema.rows(connection, sql)}
        return connection, database

    def test_exact_schema_is_verified_without_content_reads(self) -> None:
        _, database = self.database()
        facts = recovery.schema_facts(database)
        self.assertTrue(facts["verified"])
        self.assertEqual(facts["reason"], "verified")
        self.assertEqual(facts["expected_migration_count"], 18)
        self.assertEqual(facts["expected_object_count"], 163)
        for call in database.query.call_args_list:
            self.assertNotIn("SELECT * FROM messages", call.args[0])

    def test_schema_drift_reports_names_not_ddl_or_message_values(self) -> None:
        connection, database = self.database()
        connection.execute("DROP TRIGGER embedding_claim_consent")
        facts = recovery.schema_facts(database)
        self.assertFalse(facts["verified"])
        self.assertEqual(facts["reason"], "schema_objects_unverified")
        self.assertEqual(facts["missing_objects"], ["embedding_claim_consent"])
        self.assertNotIn("CREATE TABLE", json.dumps(facts))
        self.assertNotIn("owner_sub", json.dumps(facts))

    def test_inspection_never_calls_a_deployment(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder:
            path = Path(folder) / "inspection.json"
            with patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "synthetic", "CLOUDFLARE_API_TOKEN": "synthetic",
                                         "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123"}), \
                 patch.object(recovery, "context"), patch.object(recovery, "witness"), \
                 patch.object(recovery, "paused_graph"), patch.object(recovery, "DatabaseClient"), \
                 patch.object(recovery, "schema_facts", return_value={"verified": False, "reason": "schema_object_drift"}), \
                 patch.object(recovery, "INSPECTION", path), \
                 patch.object(recovery.rollout, "deploy_maintenance") as deploy:
                recovery.run("inspect")
                deploy.assert_not_called()
                self.assertFalse(json.loads(path.read_text())["schema_facts"]["verified"])

    def test_recovery_stops_on_schema_drift_before_first_write(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder:
            with patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "synthetic", "CLOUDFLARE_API_TOKEN": "synthetic",
                                         "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123"}), \
                 patch.object(recovery, "context"), patch.object(recovery, "witness"), \
                 patch.object(recovery, "paused_graph"), patch.object(recovery, "DatabaseClient"), \
                 patch.object(recovery, "schema_facts", return_value={"verified": False}), \
                 patch.object(recovery, "INSPECTION", Path(folder) / "inspection.json"), \
                 patch.object(recovery.rollout, "deploy_maintenance") as deploy:
                with self.assertRaisesRegex(ValueError, "staging_semantic_recovery_schema_unverified"):
                    recovery.run("recover")
                deploy.assert_not_called()

    def test_recovery_does_not_repeat_original_writes_or_wait(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder:
            with patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "synthetic", "CLOUDFLARE_API_TOKEN": "synthetic",
                                         "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123"}), \
                 patch.object(recovery, "context"), patch.object(recovery, "witness"), \
                 patch.object(recovery, "paused_graph"), patch.object(recovery, "DatabaseClient"), \
                 patch.object(recovery, "schema_facts", return_value={"verified": True}), \
                 patch.object(recovery, "INSPECTION", Path(folder) / "inspection.json"), \
                 patch.object(recovery, "RECEIPT", Path(folder) / "recovery.json"), \
                 patch.object(recovery.rollout, "deploy_maintenance", return_value="new-active") as deploy, \
                 patch.object(recovery.rollout.graph, "verify") as graph:
                recovery.run("recover")
                deploy.assert_called_once_with(True)
                graph.assert_called_once_with("staging", "active")


if __name__ == "__main__":
    unittest.main()
