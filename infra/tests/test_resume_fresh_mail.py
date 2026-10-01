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
from fresh_bootstrap_recovery import Checkpoint


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
            stack.enter_context(patch.object(resume, "load_sink_checkpoint", return_value=None))
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

    def test_observed_sink_checkpoint_authorizes_only_changed_source_sink_replacement(self):
        """Retain stores/DDL/queues, verify old version, then replace the unsafe SDK surface once."""
        creation = Epoch("a" * 40, "123", 42, "b" * 64, "1.98.1")
        sink = Epoch("c" * 40, "456", 43, "d" * 64, "1.98.1")
        current = Epoch("e" * 40, "789", 44, "f" * 64, "1.98.1")
        version = "c56c8062-ef7f-48ed-b91f-91394b03cd69"
        scope = Scope(creation, "d9be9bb4-5a73-4223-85d6-b04763e6f03b",
                      "2026-10-01T19:20:25Z", "2026-10-01T19:20:26Z")
        temp = ROOT / ".temp"
        temp.mkdir(exist_ok=True)
        for failure in (None, "partial_schema", "changed_sink", "retained_wrapper"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory(
                    dir=temp, prefix="resume-sink-") as folder, ExitStack() as stack:
                path = Path(folder)
                (path / "checkpoint").mkdir()
                (path / "checkpoint/resume.jsonl").write_text(
                    "{}\n" + json.dumps({"scope": asdict(scope), "creation_epoch": asdict(creation)}), encoding="utf-8")
                provider, s3 = Mock(account="a" * 32), Mock()
                stack.enter_context(patch.object(resume, "load_sink_checkpoint",
                                                return_value=Checkpoint("123", sink, sink, {"sink": version}, "3" * 32, "4" * 32,
                                                                        failure != "retained_wrapper")))
                owned = stack.enter_context(patch.object(resume, "owned_scope", return_value=scope))
                stack.enter_context(patch.object(resume.bootstrap, "inspect_old_scope", return_value={"sink_present": True}))
                stack.enter_context(patch.object(resume.old, "Provider"))
                stack.enter_context(patch.object(resume.old, "r2_count", return_value=0))
                prefix = len(resume.expected_schema().migrations) - (failure == "partial_schema")
                stack.enter_context(patch.object(resume, "migration_prefix", return_value=prefix))
                stack.enter_context(patch.object(resume, "render_configs", return_value={"api": path / "api", "maintenance": path / "maintenance"}))
                stack.enter_context(patch.object(resume.bootstrap, "sink_config", return_value=path / "sink"))
                migrate = stack.enter_context(patch.object(resume.bootstrap, "migrate_and_hold_new_scope"))
                queues = stack.enter_context(patch.object(resume.bootstrap, "provision_trace_graph"))
                submits = stack.enter_context(patch.object(resume.bootstrap, "submit_once", return_value="00000000-0000-0000-0000-000000000005"))
                stack.enter_context(patch.object(resume, "held_empty"))
                read = stack.enter_context(patch.object(resume, "verify_sink_reader"))
                previous = stack.enter_context(patch.object(resume, "verify_sink_replacement"))
                graph = stack.enter_context(patch.object(resume, "verify", return_value={"state": "paused"}))
                persist = stack.enter_context(patch.object(resume, "persist", return_value={"state": "paused"}))
                if failure == "changed_sink":
                    previous.side_effect = ValueError("fresh_serving_unverified")
                if failure in ("partial_schema", "changed_sink"):
                    with self.assertRaises(ValueError):
                        resume.run(provider, s3, current, "456", path)
                    submits.assert_not_called()
                    persist.assert_not_called()
                else:
                    self.assertEqual(resume.run(provider, s3, current, "456", path), {"state": "paused"})
                    if failure == "retained_wrapper":
                        previous.assert_not_called()
                        new_version = version
                        roles = ["maintenance", "api"]
                        provenance = {"retained_sink": {"source_epoch": asdict(sink), "version": version}}
                    else:
                        previous.assert_called_once_with(scope, version, "3" * 32, "4" * 32, provider)
                        new_version, roles, provenance = submits.return_value, ["sink", "maintenance", "api"], {}
                    read.assert_called_once_with(scope, new_version, "3" * 32, "4" * 32, provider)
                    self.assertEqual([call.args[0] for call in submits.call_args_list], roles)
                    self.assertEqual(graph.call_args.args[1]["amail-trace-sink"], new_version)
                    self.assertEqual(persist.call_args.kwargs, {"deployment_epoch": current, **provenance})
                    records = [json.loads(line) for line in (path / "recovery/resume.jsonl").read_text().splitlines()]
                    self.assertTrue(all(row["creation_run"] == "123" for row in records))
                    self.assertFalse(any(row["phase"] in ("migrate", "queues", "sink") for row in records))
                    intents = [row for row in records if row["phase"] == "sink_replacement" and row["state"] == "intent"]
                    self.assertEqual(len(intents), 0 if failure == "retained_wrapper" else 1)
                    if intents:
                        self.assertEqual(intents[0]["previous_version"], version)
                owned.assert_called_once_with(provider, "123", path)
                migrate.assert_not_called()
                queues.assert_not_called()
                provider.post.assert_not_called()

    def test_completed_workers_are_observed_and_corrected_without_deployment_replay(self):
        """The actual receipt-readback failure retains all versions and both source epochs."""
        creation = Epoch("a" * 40, "123", 42, "b" * 64, "1.98.1")
        sink = Epoch("c" * 40, "456", 43, "d" * 64, "1.98.1")
        deployed = Epoch("e" * 40, "789", 44, "f" * 64, "1.98.1")
        current = Epoch("1" * 40, "987", 45, "2" * 64, "1.98.1")
        pins = {"sink": "d372b6f0-42ed-4536-b7ee-15273b50d6a3",
                "maintenance": "d1f2946b-4001-4a82-bb75-3c30441b25a8",
                "api": "a2eba957-43e1-4ba1-af67-44d368f03b6f"}
        scope = Scope(creation, "d9be9bb4-5a73-4223-85d6-b04763e6f03b",
                      "2026-10-01T19:20:25Z", "2026-10-01T19:20:26Z")
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp", prefix="resume-completed-") as folder, ExitStack() as stack:
            path = Path(folder)
            (path / "checkpoint").mkdir()
            (path / "checkpoint/resume.jsonl").write_text(
                "{}\n" + json.dumps({"scope": asdict(scope), "creation_epoch": asdict(creation)}), encoding="utf-8")
            provider, s3 = Mock(account="a" * 32), Mock()
            stack.enter_context(patch.object(resume, "load_sink_checkpoint", return_value=
                Checkpoint("123", Epoch("3" * 40, "654", 46, "4" * 64, "1.98.1"), sink,
                           pins, "3" * 32, "4" * 32, False,
                           {"sink": sink, "maintenance": deployed, "api": deployed})))
            stack.enter_context(patch.object(resume, "owned_scope", return_value=scope))
            inventory = stack.enter_context(patch.object(resume.bootstrap, "inspect_old_scope", return_value={"sink_present": True}))
            stack.enter_context(patch.object(resume.old, "Provider"))
            stack.enter_context(patch.object(resume.old, "r2_count", return_value=0))
            stack.enter_context(patch.object(resume, "migration_prefix", return_value=len(resume.expected_schema().migrations)))
            for name in ("serving", "queue_graph", "surfaces"):
                stack.enter_context(patch.object(resume.readback, name))
            stack.enter_context(patch.object(resume, "held_empty"))
            # This caller test retains paused live versions while source now desires active maintenance.
            stack.enter_context(patch.object(resume.readback.maintenance, "expected_bindings", return_value={}))
            correction = stack.enter_context(patch.object(resume.readback, "capture_off", return_value="applied"))
            stack.enter_context(patch.object(resume, "verify", return_value={"state": "paused"}))
            persist = stack.enter_context(patch.object(resume, "persist", return_value={"state": "paused"}))
            renderer = stack.enter_context(patch.object(resume, "render_configs"))
            submit = stack.enter_context(patch.object(resume.bootstrap, "submit_once"))
            migrate = stack.enter_context(patch.object(resume.bootstrap, "migrate_and_hold_new_scope"))
            queues = stack.enter_context(patch.object(resume.bootstrap, "provision_trace_graph"))
            self.assertEqual(resume.run(provider, s3, current, "789", path), {"state": "paused"})
            for unused in (renderer, submit, migrate, queues):
                unused.assert_not_called()
            inventory.assert_called_once_with(provider, s3, owned_scripts=frozenset({"amail-mail", "amail-mail-maintenance"}))
            self.assertEqual([call.args[1] for call in correction.call_args_list], ["amail-mail-maintenance", "amail-mail"])
            retained = persist.call_args.kwargs["retained_workers"]
            self.assertEqual(retained["amail-trace-sink"], {"source_epoch": asdict(sink), "version": pins["sink"]})
            self.assertEqual(retained["amail-mail"], {"source_epoch": asdict(deployed), "version": pins["api"]})
            self.assertEqual(persist.call_args.kwargs["deployment_epoch"], current)

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
