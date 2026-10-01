"""Hosted synthetic first-bootstrap contracts; never access real providers."""

from dataclasses import replace
from contextlib import ExitStack
import hashlib
from pathlib import Path
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
        for failing in ("create_scope", "migrate_and_hold_new_scope", "submit_once", "verify"):
            with self.subTest(adapter=failing):
                self.recovery = self.folder / (failing + ".jsonl")
                self.receipt = self.folder / (failing + ".json")
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


if __name__ == "__main__":
    unittest.main()
