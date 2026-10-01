"""Hosted-only regressions for completing real owned storage without re-creation."""

from contextlib import ExitStack
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import resume_fresh_mail as resume
from fresh_bootstrap_contract import Epoch, Scope


class ResumeTests(unittest.TestCase):
    """Positive creation and current metadata, not an old failed run verdict, admit work."""

    def test_current_empty_and_exact_partial_schema_never_use_failed_reads_as_absence(self):
        """An exact six-migration prefix is continued; unknown schema/user population stops."""
        with sqlite3.connect(":memory:") as database:
            database.row_factory = sqlite3.Row
            reader = Mock()
            reader.query.side_effect = lambda sql: [dict(row) for row in database.execute(sql).fetchall()]
            self.assertEqual(resume.migration_prefix(reader), 0)
            database.execute("CREATE TABLE unknown_owner_data(value TEXT)")
            with self.assertRaisesRegex(ValueError, "fresh_resume_unrecorded_schema"):
                resume.migration_prefix(reader)
            database.execute("DROP TABLE unknown_owner_data")
            files = sorted(resume.MIGRATIONS.glob("*.sql"))[:6]
            for file in files:
                database.executescript(file.read_text(encoding="utf-8"))
            database.execute("CREATE TABLE d1_migrations(id INTEGER PRIMARY KEY,name TEXT)")
            database.executemany("INSERT INTO d1_migrations(name) VALUES(?)", [(file.name,) for file in files])
            self.assertEqual(resume.migration_prefix(reader), 6)
            read = reader.query.side_effect
            reader.query.side_effect = lambda sql: [{"n": 1}] if sql == 'SELECT COUNT(*) AS n FROM "addresses"' else read(sql)
            with self.assertRaisesRegex(ValueError, "fresh_resume_retained_state"):
                resume.migration_prefix(reader)
            reader.query.side_effect = ValueError("provider_read_failed")
            with self.assertRaisesRegex(ValueError, "provider_read_failed"):
                resume.migration_prefix(reader)

    def test_owned_current_scope_completes_paused_receipt_without_resource_create(self):
        """Current deployment bytes are distinct from retained original creation provenance."""
        creation = Epoch("a" * 40, "123", 42, "b" * 64, "1.98.1")
        current = Epoch("c" * 40, "456", 43, "d" * 64, "1.98.1")
        scope = Scope(creation, "00000000-0000-0000-0000-000000000002",
                      "2026-10-01T19:20:25Z", "2026-10-01T19:20:26Z")
        temp = ROOT / ".temp"
        temp.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp, prefix="resume-contract-") as folder, ExitStack() as stack:
            path = Path(folder)
            provider, s3 = Mock(account="a" * 32), Mock()
            graph = {"state": "paused"}
            stack.enter_context(patch.object(resume, "owned_scope", return_value=scope))
            stack.enter_context(patch.object(resume.bootstrap, "inspect_old_scope", return_value={"sink_present": False}))
            stack.enter_context(patch.object(resume.old, "Provider"))
            stack.enter_context(patch.object(resume.old, "r2_count", return_value=0))
            stack.enter_context(patch.object(resume, "migration_prefix", return_value=0))
            stack.enter_context(patch.object(resume, "render_configs", return_value={"api": path / "api", "maintenance": path / "maintenance"}))
            stack.enter_context(patch.object(resume.bootstrap, "sink_config", return_value=path / "sink"))
            migrate = stack.enter_context(patch.object(resume.bootstrap, "migrate_and_hold_new_scope"))
            stack.enter_context(patch.object(resume.bootstrap, "provision_trace_graph", return_value=("3" * 32, "4" * 32)))
            submits = stack.enter_context(patch.object(resume.bootstrap, "submit_once", return_value="00000000-0000-0000-0000-000000000005"))
            stack.enter_context(patch.object(resume, "verify_sink_reader"))
            stack.enter_context(patch.object(resume, "verify", return_value=graph))
            persist = stack.enter_context(patch.object(resume, "persist", return_value={"state": "paused"}))
            create = stack.enter_context(patch.object(resume.bootstrap, "create_scope"))
            self.assertEqual(resume.run(provider, s3, current, "123", path), {"state": "paused"})
            create.assert_not_called()
            provider.post.assert_not_called()
            migrate.assert_called_once()
            self.assertEqual([call.args[0] for call in submits.call_args_list], ["sink", "maintenance", "api"])
            self.assertEqual(persist.call_args.kwargs, {"deployment_epoch": current})
            records = [json.loads(line) for line in (path / "recovery/resume.jsonl").read_text().splitlines()]
            self.assertEqual(records[1]["creation_epoch"], asdict(creation))
            self.assertEqual(records[1]["deployment_epoch"], asdict(current))

    def test_incomplete_or_changed_owned_creation_does_not_bind_writer_scope(self):
        """A create intent or failed exact GET cannot become owned storage authority."""
        creation = Epoch("a" * 40, "123", 42, "b" * 64, "1.98.1")
        temp = ROOT / ".temp"
        temp.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp, prefix="resume-ownership-") as folder:
            controller = Path(folder) / "controller.jsonl"
            controller.write_text(json.dumps({"phase": "migrate", "state": "failed"}))
            scope = Scope(creation, "00000000-0000-0000-0000-000000000002",
                          "2026-10-01T19:20:25Z", "2026-10-01T19:20:26Z")
            provider = Mock()
            with patch.object(resume, "load", return_value=(creation, controller)), \
                    patch.object(resume, "reconcile_scope", return_value={"database": "UNKNOWN", "bucket": "CREATED_IDENTITY_OBSERVED"}):
                controller.with_suffix(".scope.jsonl").write_text(json.dumps({"event": "r2_submit_intent"}))
                with self.assertRaisesRegex(ValueError, "fresh_resume_complete_creation_required"):
                    resume.owned_scope(provider, "123", Path(folder))
                controller.with_suffix(".scope.jsonl").write_text(json.dumps({"event": "scope_readback_verified", "scope": asdict(scope)}))
                with self.assertRaisesRegex(ValueError, "fresh_resume_owned_store_readback_required"):
                    resume.owned_scope(provider, "123", Path(folder))
            provider.post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
