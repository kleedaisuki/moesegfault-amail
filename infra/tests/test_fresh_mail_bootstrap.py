"""Hosted synthetic first-bootstrap contracts; never access real providers."""

from dataclasses import asdict, replace
from contextlib import ExitStack
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
from fresh_bootstrap_contract import Epoch, Scope, ORIGINAL_DATABASE, STAGING_DATABASE, ORIGINAL_BUCKET
import fresh_mail_bootstrap as controller


def epoch() -> Epoch:
    """Use explicit original-run coordinates rather than inferred current artifacts."""
    return Epoch("a" * 40, "123456", 98765, "b" * 64, "1.94.0")


class FreshBootstrapCoordinatesTests(unittest.TestCase):
    """Resource names are source-owned; validated coordinates do not grant activation."""

    def test_names_are_fixed_source_run_derivations_and_preserve_original_storage(self):
        """Artifact metadata changes cannot allocate a second name within one source/run."""
        value = epoch()
        suffix = hashlib.sha256(("a" * 40 + ":123456").encode()).hexdigest()[:24]
        self.assertEqual(value.database_name, "moesegfault-mail-production-" + suffix)
        self.assertEqual(value.bucket_name, ORIGINAL_BUCKET + "-" + suffix)
        self.assertNotEqual(value.bucket_name, ORIGINAL_BUCKET)
        self.assertLessEqual(len(value.bucket_name), 63)
        self.assertEqual(replace(value, artifact_id=98766).key, value.key)
        self.assertEqual(replace(value, manifest_sha256="c" * 64).key, value.key)
        self.assertNotEqual(replace(value, run_id="123457").key, value.key)
        self.assertNotEqual(replace(value, source_sha="c" * 40).key, value.key)

    def test_original_and_staging_databases_cannot_be_fresh_scope(self):
        """Even well-formed existing UUIDs cannot substitute for new-storage proof."""
        for database in (ORIGINAL_DATABASE, STAGING_DATABASE, "invalid"):
            with self.subTest(database=database), self.assertRaises(ValueError):
                Scope(epoch(), database, "2026-10-01T00:00:00Z", "2026-10-01T00:00:01Z")
        scope = Scope(epoch(), "00000000-0000-0000-0000-000000000002",
                      "2026-10-01T00:00:00Z", "2026-10-01T00:00:01Z")
        self.assertEqual(scope.bucket, epoch().bucket_name)
        self.assertEqual(scope.database_name, epoch().database_name)

    def test_artifact_coordinates_reject_missing_wrong_types_and_floating_compiler(self):
        """Boolean IDs, malformed provenance and floating bundlers fail at the boundary."""
        bad = (("source_sha", "main"), ("run_id", "0"), ("run_id", 123456),
               ("artifact_id", True), ("artifact_id", 0), ("artifact_id", "98765"),
               ("manifest_sha256", "b" * 63), ("rust", "stable"),
               ("worker_build", "latest"))
        for field, value in bad:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                replace(epoch(), **{field: value})

    def test_creation_timestamps_require_valid_exact_utc_dates(self):
        """Age and loosely parsed strings are never a replacement for response binding."""
        for value in ("2026-02-30T00:00:00Z", "2026-10-01T00:00:00+00:00", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Scope(epoch(), "00000000-0000-0000-0000-000000000002",
                      value, "2026-10-01T00:00:00Z")


class FreshBootstrapMigrationTests(unittest.TestCase):
    """Migration submit retains typed diagnostics without replay or private output."""

    def setUp(self):
        """Use synthetic owned coordinates and patch every external boundary."""
        self.scope = Scope(epoch(), "00000000-0000-0000-0000-000000000002",
                           "2026-10-01T00:00:00Z", "2026-10-01T00:00:01Z")
        self.provider = Mock(account="a" * 32)
        self.s3 = Mock()
        self.config = ROOT / ".temp" / "synthetic-fresh-api.toml"
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.artifact = self.stack.enter_context(patch.object(controller, "require_artifact"))
        self.process = self.stack.enter_context(patch.object(controller.subprocess, "run"))
        self.held = self.stack.enter_context(patch.object(controller, "held_empty"))
        self.objects = self.stack.enter_context(patch.object(controller.old, "r2_count", return_value=0))
        self.output = io.StringIO()
        self.stack.enter_context(redirect_stdout(self.output))

    def test_supported_command_submits_once_then_preserves_held_empty_checks(self):
        """Pinned Wrangler skips confirmation in CI; no unsupported --yes is sent."""
        self.process.return_value = subprocess.CompletedProcess([], 0, "private-cli-output", "")
        controller.migrate_and_hold_new_scope(self.provider, self.s3, self.scope, self.config)
        self.artifact.assert_called_once_with("mail_api")
        self.process.assert_called_once_with(
            ["wrangler", "d1", "migrations", "apply", "MAIL_DB", "--remote", "--config", str(self.config)],
            cwd=controller.ROOT, capture_output=True, text=True, check=False, timeout=300)
        self.assertNotIn("--yes", self.process.call_args.args[0])
        self.held.assert_called_once_with(self.provider, "accounts/" + self.provider.account, self.scope)
        self.objects.assert_called_once_with(self.s3, self.scope.bucket)
        self.assertNotIn("private-cli-output", self.output.getvalue())
        end = json.loads(self.output.getvalue().splitlines()[-1])
        self.assertEqual((end["outcome"], end["process_exit_code"]), ("success", 0))

    def test_parser_failure_emits_only_fixed_category_exit_code_and_stage(self):
        """Unknown arguments and parser diagnostics never expose argument or secret prose."""
        cases = (("Unknown argument: secret-token", "cli_unknown_argument"),
                 ("Unknown arguments: secret-token", "cli_unknown_argument"),
                 ("Missing required argument: secret-token", "cli_parameter_parse"),
                 ("Not enough non-option arguments: secret-token", "cli_parameter_parse"),
                 ("Invalid values: secret-token", "cli_parameter_parse"),
                 ("Not enough arguments following: secret-token", "cli_parameter_parse"),
                 ("private-provider-body secret-token", "process_exit"))
        for diagnostic, reason in cases:
            with self.subTest(reason=reason, diagnostic=diagnostic):
                self.process.reset_mock()
                self.output.seek(0)
                self.output.truncate()
                self.process.return_value = subprocess.CompletedProcess(
                    [], 1, "private-stdout secret-token", diagnostic + " private-provider-body")
                with self.assertRaisesRegex(ValueError, "^fresh_migration_submit_unverified$"):
                    controller.migrate_and_hold_new_scope(self.provider, self.s3, self.scope, self.config)
                self.process.assert_called_once()
                self.held.assert_not_called()
                self.objects.assert_not_called()
                captured = self.output.getvalue()
                for private in ("secret-token", "private-stdout", "private-provider-body", diagnostic):
                    self.assertNotIn(private, captured)
                end = json.loads(captured.splitlines()[-1])
                self.assertEqual(end["reason"], reason)
                self.assertEqual(end["process_exit_code"], 1)
                self.assertEqual(end["operation"], "d1.migrations.apply")
                self.assertEqual(end["phase"], "migrate")
                self.assertEqual(end["outcome"], "failure")
                self.assertEqual(end["error_type"], "ValueError")

    def test_successful_cli_does_not_replace_held_and_empty_proofs(self):
        """A successful command still refuses failed held proof or populated storage."""
        self.process.return_value = subprocess.CompletedProcess([], 0, "", "")
        self.held.side_effect = ValueError("synthetic_held_unverified")
        with self.assertRaisesRegex(ValueError, "^synthetic_held_unverified$"):
            controller.migrate_and_hold_new_scope(self.provider, self.s3, self.scope, self.config)
        self.objects.assert_not_called()
        self.held.side_effect = None
        self.objects.return_value = 1
        with self.assertRaisesRegex(ValueError, "^fresh_bucket_population_unverified$"):
            controller.migrate_and_hold_new_scope(self.provider, self.s3, self.scope, self.config)
        self.assertEqual(self.process.call_count, 2, "each explicit invocation submits only once")

    def test_output_limit_stops_before_classification_or_held_readback(self):
        """Oversized output is never classified or emitted, even on a zero exit."""
        self.process.return_value = subprocess.CompletedProcess([], 0, "x" * 1_048_577, "")
        with self.assertRaisesRegex(ValueError, "^fresh_migration_submit_unverified$"):
            controller.migrate_and_hold_new_scope(self.provider, self.s3, self.scope, self.config)
        end = json.loads(self.output.getvalue().splitlines()[-1])
        self.assertEqual((end["reason"], end["process_exit_code"]), ("output_limit", 0))
        self.process.assert_called_once()
        self.held.assert_not_called()
        self.objects.assert_not_called()

    def test_timeout_retains_ambiguity_without_retry_or_secret_output(self):
        """A timed-out process is not evidence that no remote migration was applied."""
        self.process.side_effect = subprocess.TimeoutExpired(
            ["private-command"], 300, output="private-timeout-body", stderr="secret-token")
        with self.assertRaises(subprocess.TimeoutExpired):
            controller.migrate_and_hold_new_scope(self.provider, self.s3, self.scope, self.config)
        captured = self.output.getvalue()
        end = json.loads(captured.splitlines()[-1])
        self.assertEqual(end["reason"], "submit_timeout_ambiguous")
        self.assertNotIn("process_exit_code", end)
        for private in ("private-command", "private-timeout-body", "secret-token"):
            self.assertNotIn(private, captured)
        self.process.assert_called_once()
        self.held.assert_not_called()
        self.objects.assert_not_called()


class FreshBootstrapColdStoreTests(unittest.TestCase):
    """Regress the actual first old-scope query failure without provider access."""

    def test_missing_migration_table_requires_positive_empty_metadata_and_empty_r2(self):
        """Cold old D1 is retained; unknown schema, objects or failed reads never pass."""
        with sqlite3.connect(":memory:") as database, ExitStack() as stack:
            database.row_factory = sqlite3.Row
            with self.assertRaises(sqlite3.OperationalError):
                database.execute("SELECT name FROM d1_migrations ORDER BY id")
            provider = Mock(account="a" * 32, token="synthetic-private-token")
            reader = Mock(resources=replace(controller.old.configured_resources("a" * 40),
                                            database=ORIGINAL_DATABASE, bucket=ORIGINAL_BUCKET))
            queries = []

            def read(sql):
                """Use SQLite's genuine missing-table semantics, not an always-empty fake."""
                queries.append(sql)
                return [dict(row) for row in database.execute(sql).fetchall()]

            reader.query.side_effect = read
            s3 = Mock()
            empty = {"Name": ORIGINAL_BUCKET, "IsTruncated": False, "KeyCount": 0, "Contents": []}
            s3.list_objects_v2.return_value = empty
            stack.enter_context(patch.dict(controller.os.environ, {"GITHUB_SHA": "a" * 40}))
            original_reader = stack.enter_context(patch.object(controller.old, "Provider", return_value=reader))
            scripts = stack.enter_context(patch.object(controller.old, "script_inventory", return_value={}))
            routes = stack.enter_context(patch.object(controller.old, "unattached_route", return_value={}))
            stack.enter_context(patch.object(controller, "forward_snapshot", return_value={}))
            output = io.StringIO()
            stack.enter_context(redirect_stdout(output))

            result = controller.inspect_old_scope(provider, s3)
            self.assertEqual(result["original_stores"], "RETAINED")
            self.assertEqual(original_reader.call_args.args[2].database, ORIGINAL_DATABASE)
            self.assertEqual(original_reader.call_args.args[2].bucket, ORIGINAL_BUCKET)
            self.assertEqual(s3.list_objects_v2.call_args.kwargs["Bucket"], ORIGINAL_BUCKET)
            self.assertEqual(result["external_activation"], "NOT_GRANTED")
            self.assertEqual(queries, [controller.old.INITIAL_SCHEMA] * 2)
            self.assertEqual(scripts.call_count, 2)
            self.assertEqual(routes.call_count, 2)

            database.execute("CREATE TABLE private_unknown_schema(value TEXT)")
            with self.assertRaisesRegex(ValueError, "^bootstrap_unrecorded_schema$"):
                controller.inspect_old_scope(provider, s3)
            self.assertNotIn("private_unknown_schema", output.getvalue())
            database.execute("DROP TABLE private_unknown_schema")

            database.execute("CREATE TABLE d1_migrations(id INTEGER PRIMARY KEY,name TEXT)")
            database.execute("INSERT INTO d1_migrations(name) VALUES('0001_init.sql')")
            with self.assertRaisesRegex(ValueError, "^bootstrap_schema_prefix_unverified$"):
                controller.inspect_old_scope(provider, s3)
            database.execute("DROP TABLE d1_migrations")

            s3.list_objects_v2.return_value = {**empty, "KeyCount": 1,
                                              "Contents": [{"Key": "private-object", "Size": 1}]}
            with self.assertRaisesRegex(ValueError, "^bootstrap_retained_state_requires_reconciliation$"):
                controller.inspect_old_scope(provider, s3)
            s3.list_objects_v2.return_value = empty
            reader.query.side_effect = ValueError("production_provider_http_other")
            with self.assertRaisesRegex(ValueError, "^production_provider_http_other$"):
                controller.inspect_old_scope(provider, s3)
            s3.get_object.assert_not_called()
            s3.delete_object.assert_not_called()
            provider.post.assert_not_called()


class FreshBootstrapControllerTests(unittest.TestCase):
    """Independent adapter events prove one-attempt orchestration, not real deployment."""

    def setUp(self):
        """Keep isolated harness state under the repository's approved temporary root."""
        folder = ROOT / ".temp"
        folder.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="fresh-controller-test-", dir=folder)
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.recovery = self.folder / "recovery.jsonl"
        self.receipt = self.folder / "receipt.json"
        self.scope = Scope(epoch(), "00000000-0000-0000-0000-000000000002",
                           "2026-10-01T00:00:00Z", "2026-10-01T00:00:01Z")
        self.provider, self.s3 = Mock(), Mock()
        self.events, self.adapters = [], {}
        stack = ExitStack()
        self.addCleanup(stack.close)
        graph = {"pins": {}, "api_crons": [], "maintenance_crons": [], "topology": "api-scheduled"}
        results = {
            "verify_same_run_artifact": None, "inspect_old_scope": {},
            "verify_sink_reader": None, "sink_config": self.folder / "sink.toml",
            "create_scope": self.scope,
            "render_configs": {"api": self.folder / "api.toml", "maintenance": self.folder / "maintenance.toml"},
            "migrate_and_hold_new_scope": None,
            "provision_trace_graph": ("00000000-0000-0000-0000-000000000003",
                                      "00000000-0000-0000-0000-000000000004"),
            "submit_once": "00000000-0000-0000-0000-000000000005",
            "verify": graph, "persist": {"activation": "NOT_GRANTED"},
        }
        for name, result in results.items():
            def invoke(*args, _name=name, _result=result, **kwargs):
                """Record the invocation independently of the controller's own diagnostics."""
                self.events.append((_name, args, kwargs))
                return _result
            self.adapters[name] = stack.enter_context(patch.object(controller, name, side_effect=invoke))

    def bootstrap(self):
        """Create the settled controller entry point without provider capabilities."""
        return controller.Bootstrap(self.provider, self.s3, epoch(), self.recovery, self.receipt)

    def test_positive_path_checks_new_hold_and_readback_before_receipt(self):
        """Only the creator's returned scope proceeds, and no activation is requested."""
        self.assertEqual(self.bootstrap().run(), {"activation": "NOT_GRANTED"})
        names = [event[0] for event in self.events]
        self.assertLess(names.index("verify_same_run_artifact"), names.index("create_scope"))
        self.assertLess(names.index("inspect_old_scope"), names.index("create_scope"))
        self.assertLess(names.index("migrate_and_hold_new_scope"), names.index("submit_once"))
        self.assertLess(names.index("verify"), names.index("persist"))
        sink_readback = names.index("verify_sink_reader")
        submits = [i for i, name in enumerate(names) if name == "submit_once"]
        self.assertLess(submits[0], sink_readback)
        self.assertLess(sink_readback, submits[1])
        self.adapters["verify_same_run_artifact"].assert_called_once_with(epoch())
        self.adapters["inspect_old_scope"].assert_called_once_with(self.provider, self.s3)
        hold_args = self.adapters["migrate_and_hold_new_scope"].call_args.args
        self.assertEqual(hold_args[:3], (self.provider, self.s3, self.scope))
        self.assertEqual(hold_args[3], self.folder / "api.toml")
        self.assertEqual(self.adapters["submit_once"].call_count, 3)
        self.assertEqual([call.args[0] for call in self.adapters["submit_once"].call_args_list],
                         ["sink", "maintenance", "api"])
        self.adapters["create_scope"].assert_called_once()
        self.assertEqual(self.adapters["create_scope"].call_args.args[:2],
                         (self.provider, epoch()))
        self.adapters["provision_trace_graph"].assert_called_once_with(self.provider)
        for call in self.adapters["submit_once"].call_args_list:
            self.assertNotIn("activate", str(call))
        readback_args = self.adapters["verify"].call_args.args
        self.assertEqual(readback_args[0], self.scope)
        self.assertEqual(set(readback_args[1]),
                         {"amail-mail", "amail-mail-maintenance", "amail-trace-sink"})
        self.assertEqual(readback_args[-1], self.provider)
        self.adapters["persist"].assert_called_once()

    def test_failed_artifact_or_old_scope_precondition_forbids_allocation(self):
        """Retained owner state, failed inventory, routing or grant is not fresh absence."""
        cases = (("verify_same_run_artifact", "artifact_provenance_mismatch"),
                 ("inspect_old_scope", "production_retained_owner_state"),
                 ("inspect_old_scope", "production_inventory_incomplete"),
                 ("inspect_old_scope", "production_route_attached"),
                 ("inspect_old_scope", "bootstrap_grant_or_release_gate_unverified"))
        for name, reason in cases:
            with self.subTest(adapter=name, reason=reason):
                self.recovery = self.folder / (reason + ".jsonl")
                self.receipt = self.folder / (reason + ".json")
                adapter = self.adapters[name]
                old = adapter.side_effect
                adapter.side_effect = ValueError(reason)
                try:
                    with self.assertRaises(Exception):
                        self.bootstrap().run()
                    self.adapters["create_scope"].assert_not_called()
                    self.adapters["persist"].assert_not_called()
                finally:
                    adapter.side_effect = old

    def test_timeout_or_readback_failure_never_retries_or_emits_receipt(self):
        """Ambiguous writes retain failure; observation cannot turn them into success."""
        for failing in ("create_scope", "render_configs", "migrate_and_hold_new_scope",
                        "provision_trace_graph", "submit_once", "verify_sink_reader", "verify"):
            with self.subTest(adapter=failing):
                case = self.folder / failing
                case.mkdir()
                self.recovery = case / "controller.jsonl"
                self.receipt = case / "receipt.json"
                for adapter in self.adapters.values():
                    adapter.reset_mock()
                adapter = self.adapters[failing]
                old = adapter.side_effect
                adapter.side_effect = TimeoutError("synthetic timeout")
                try:
                    with self.assertRaises(Exception):
                        self.bootstrap().run()
                    self.assertEqual(adapter.call_count, 1)
                    self.adapters["persist"].assert_not_called()
                    self.assertFalse(self.receipt.exists())
                finally:
                    adapter.side_effect = old


    def record(self, phase, state, **facts):
        """Build the documented journal envelope, not controller-generated diagnostics."""
        return {"schema": "mail-fresh-controller/v1", "epoch": asdict(epoch()),
                "phase": phase, "state": state, **facts}

    def journal(self, records):
        """Persist only synthetic bounded intent evidence inside the test folder."""
        self.recovery.write_text("".join(json.dumps(row) + "\n" for row in records),
                                 encoding="utf-8")

    def valid_failed_sink_journal(self):
        """An ambiguous one-attempt sink submit occurs after owned creation and queues."""
        return [self.record("admission", "intent"), self.record("admission", "observed"),
                self.record("old_scope", "intent"), self.record("old_scope", "observed"),
                self.record("create_scope", "intent"),
                self.record("create_scope", "observed", scope=asdict(self.scope)),
                self.record("render", "intent"), self.record("render", "observed"),
                self.record("migrate", "intent"), self.record("migrate", "observed"),
                self.record("queues", "intent"),
                self.record("queues", "observed", queue="3" * 32, dlq="4" * 32),
                self.record("sink", "intent"),
                self.record("sink", "failed", error_type="DeploymentFailure",
                            version="00000000-0000-0000-0000-000000000005")]

    def test_failed_write_recovery_observes_owned_coordinates_without_replay(self):
        """Captured failure versions permit readback, never success receipts or writes."""
        self.journal(self.valid_failed_sink_journal())
        original = self.recovery.read_bytes()
        observed = {"id": "00000000-0000-0000-0000-000000000006",
                    "versions": [{"version_id": "00000000-0000-0000-0000-000000000005", "percentage": 100}]}
        with patch.object(controller, "reconcile_scope", return_value={"status": "observed"}) as reconcile, \
                patch.object(controller, "serving_deployment", return_value=observed):
            result = self.bootstrap().recover()
        reconcile.assert_called_once_with(self.provider, epoch(), self.recovery.with_suffix(".scope.jsonl"))
        self.provider.get.assert_called_once_with(
            "accounts/" + str(self.provider.account) + "/workers/scripts/amail-trace-sink/deployments?per_page=1&page=1")
        self.assertIs(result["may_replay_write"], False)
        self.assertEqual(result["activation"], "NOT_GRANTED")
        self.assertEqual(result["receipt"], "NOT_GRANTED")
        for name in ("create_scope", "migrate_and_hold_new_scope", "provision_trace_graph", "submit_once", "persist"):
            self.adapters[name].assert_not_called()
        self.assertFalse(self.receipt.exists())
        self.assertEqual(self.recovery.read_bytes(), original, "recovery must not append or rewrite intent")

    def test_forged_phase_or_scope_journal_is_rejected_before_provider_reads(self):
        """Well-typed fields cannot forge the phase protocol or creator-owned scope."""
        forged_scope = asdict(replace(self.scope, epoch=replace(epoch(), run_id="123457")))
        cases = [
            [self.record("admission", "intent"), self.record("api", "observed",
                version="00000000-0000-0000-0000-000000000005")],
            [self.record("admission", "intent"), self.record("admission", "observed"),
                self.record("old_scope", "intent"), self.record("old_scope", "observed"),
                self.record("create_scope", "intent"),
                self.record("create_scope", "observed", scope=forged_scope)],
            [self.record("admission", "intent"), self.record("create_scope", "intent"),
                self.record("create_scope", "observed", scope=asdict(self.scope)),
                self.record("sink", "failed", error_type="DeploymentFailure",
                            version="00000000-0000-0000-0000-000000000005")],
        ]
        for records in cases:
            with self.subTest(records=records):
                self.journal(records)
                self.provider.reset_mock()
                with patch.object(controller, "reconcile_scope") as reconcile:
                    with self.assertRaises(ValueError):
                        self.bootstrap().recover()
                    reconcile.assert_not_called()
                self.provider.get.assert_not_called()

    def test_timeout_without_version_still_observes_intended_script(self):
        """A missing Wrangler pin cannot hide a possible accepted remote deployment."""
        records = self.valid_failed_sink_journal()
        records[-1] = self.record("sink", "failed", error_type="TimeoutExpired")
        self.journal(records)
        with patch.object(controller, "reconcile_scope", return_value={"status": "unknown"}), \
                patch.object(controller, "serving_deployment", return_value=("d", "v")):
            result = self.bootstrap().recover()
        self.assertEqual(result["pins"]["amail-trace-sink"], {
            "captured_version": None, "serving": ("d", "v"), "observation": "OBSERVED"})
        self.provider.get.assert_called_once()
        self.assertFalse(result["may_replay_write"])
        self.adapters["persist"].assert_not_called()

    def test_failed_recovery_read_is_unknown_not_absence_or_replay(self):
        """Provider refusal does not erase an ambiguous submit or grant ownership."""
        self.journal(self.valid_failed_sink_journal())
        self.provider.get.side_effect = TimeoutError("private arbitrary prose")
        with patch.object(controller, "reconcile_scope", return_value={"status": "unknown"}):
            result = self.bootstrap().recover()
        self.assertIsNone(result["pins"]["amail-trace-sink"]["serving"])
        self.assertEqual(result["pins"]["amail-trace-sink"]["observation"], "UNVERIFIED")
        self.assertNotIn("private arbitrary prose", json.dumps(result))
        self.assertFalse(result["may_replay_write"])

    def test_initial_refusal_evidence_exists_without_artifact_or_provider(self):
        """Admission failure has a closed diagnostic trail before controller creation."""
        root = self.folder / "preflight-root"
        with patch.object(controller, "ROOT", root), patch.dict(controller.os.environ, {
                "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123456", "PRIVATE_TOKEN": "never-retained"}):
            controller.preflight("intent")
            controller.preflight("failed", "FileNotFoundError")
        rows = [json.loads(line) for line in (root / ".temp/fresh-bootstrap/recovery/preflight.jsonl")
                .read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["state"] for row in rows], ["intent", "failed"])
        self.assertEqual(rows[1]["error_type"], "FileNotFoundError")
        self.assertTrue(all(row["activation"] == "NOT_GRANTED" for row in rows))
        self.assertNotIn("never-retained", json.dumps(rows))
        self.provider.get.assert_not_called()

    def test_recovery_cli_refuses_wrong_context_before_loader_or_provider(self):
        """A local invocation or arbitrary job cannot admit a protected recovery."""
        with patch.dict(controller.os.environ, {}, clear=True), \
                patch.object(controller, "FreshProvider") as provider:
            with self.assertRaisesRegex(ValueError, "fresh_recovery_protected_context_required"):
                controller.recover_main("123456")
        provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()
