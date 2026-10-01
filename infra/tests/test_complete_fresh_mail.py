"""Hosted synthetic online completion contracts; no real provider or send operations."""

from contextlib import ExitStack
from contextlib import redirect_stdout
from dataclasses import asdict
import json
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import complete_fresh_mail as online
from fresh_bootstrap_contract import Epoch, Scope
from worker_deploy_result import DeploymentFailure


def scope() -> Scope:
    """Use creation coordinates intentionally distinct from current deployment."""
    return Scope(Epoch("a" * 40, "123", 45, "b" * 64, "1.94.0"),
                 "00000000-0000-0000-0000-000000000002",
                 "2026-10-01T00:00:00Z", "2026-10-01T00:00:01Z")


def receipt_value() -> dict:
    """Represent only loader-admitted input; tests never substitute JSON admission."""
    stores = scope()
    pins = {script: {"deployment": "00000000-0000-0000-0000-000000000003",
                     "version": "00000000-0000-0000-0000-000000000004"}
            for script in ("amail-mail", "amail-mail-maintenance", "amail-trace-sink")}
    return {"source_epoch": asdict(stores.epoch),
            "scope": {"database": stores.database, "database_name": stores.database_name,
                      "bucket": stores.bucket, "database_created_at": stores.database_created_at,
                      "bucket_created_at": stores.bucket_created_at},
            "resources": {"database": stores.database, "bucket": stores.bucket,
                          "queue": "c" * 32, "dlq": "d" * 32},
            "graph": {"pins": pins, "api_crons": [], "maintenance_crons": [], "topology": "api-scheduled"}}


class OnlineContractsTests(unittest.TestCase):
    """Verify write order, no release/recreation, private diagnostics and one attempt."""

    def test_failed_main_reports_source_phase_and_fixed_reason_not_provider_text(self):
        """The real operator entrypoint must not hide a specific predicate behind ValueError."""
        for reason, expected in (("fresh_online_event_consumer_unverified", "fresh_online_event_consumer_unverified"),
                                 ("private-token-mail-body", "unexpected")):
            output = io.StringIO()
            controller = Mock(phase="adapter_readback")
            controller.run.side_effect = ValueError(reason)
            with patch.object(online, "Online", return_value=controller), redirect_stdout(output):
                self.assertEqual(online.main(), 1)
            self.assertIn("phase=adapter_readback", output.getvalue())
            self.assertIn("reason=" + expected, output.getvalue())
            self.assertNotIn("private-token", output.getvalue())

    @classmethod
    def setUpClass(cls):
        """Keep all local fixtures beneath the repository-owned temporary tree."""
        (ROOT / ".temp").mkdir(exist_ok=True)

    def test_creation_epoch_remains_original_after_source_adoption(self):
        """V2 and V3 share scope names without relabelling their original creation."""
        value = receipt_value()
        self.assertEqual(online.receipt_scope(value), scope())
        value["creation_epoch"] = value["source_epoch"]
        value["source_epoch"] = asdict(Epoch("e" * 40, "456", 67, "f" * 64, "1.94.0"))
        self.assertEqual(online.receipt_scope(value), scope())
        value["scope"]["bucket"] = "arbitrary-bucket"
        with self.assertRaises(ValueError):
            online.receipt_scope(value)

    def test_unprotected_context_fails_before_artifact_access(self):
        """A local caller cannot access credentials or infer authorization from a flag."""
        with patch.dict(os.environ, {}, clear=True), patch.object(online, "require_artifact") as artifact:
            with self.assertRaises(ValueError):
                online.admit()
            artifact.assert_not_called()

    def test_admission_requires_all_components_and_current_epoch(self):
        """Identity is current same-run installed bytes, not the creation artifact."""
        environment = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": online.REPO,
                       "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
                       "GITHUB_RUN_ATTEMPT": "1", "GITHUB_JOB": "production-fresh-online",
                       "GITHUB_WORKFLOW_REF": f"{online.REPO}/.github/workflows/ci.yml@refs/heads/main",
                       "AMAIL_PRODUCTION_ONLINE_CONFIRM": online.CONFIRM,
                       "AMAIL_PRODUCTION_GRAPH_FREEZE": "FREEZE_PRODUCTION_GRAPH_WRITERS",
                       "AMAIL_PRODUCTION_ENVIRONMENT": "production", "AMAIL_WORKER_ARTIFACT_ID": "67"}
        identity = {"source_sha": "e" * 40, "run_id": "456", "rust": "1.94.0", "worker_build": "0.8.5"}
        with patch.dict(os.environ, environment, clear=True), patch.object(online, "require_artifact") as artifact:
            with patch.object(online.worker_artifact, "context", return_value=identity), patch.object(Path, "read_bytes", return_value=b"manifest"):
                result = online.admit()
            self.assertEqual(result.run_id, "456")
            self.assertEqual([call.args[0] for call in artifact.call_args_list], ["mail_api", "mail_ingress", "mail_events"])

    def test_captured_rejects_exit_and_wrong_classifier_without_leaking_output(self):
        """Only source-owned success labels escape subprocess boundaries."""
        for result in (Mock(returncode=1, stdout="credential", stderr="body"),
                       Mock(returncode=0, stdout="wrong classifier", stderr="")):
            with patch.object(online.subprocess, "run", return_value=result) as run:
                with self.assertRaisesRegex(ValueError, "^fresh_online_operation_unverified$"):
                    online.captured(["source-command"], "expected")
                self.assertTrue(run.call_args.kwargs["capture_output"])
                run.assert_called_once()

    def test_ingress_private_secret_removed_on_ambiguous_submit(self):
        """A printed partial version is not success and secrets never enter recovery."""
        (ROOT / ".temp").mkdir(exist_ok=True)
        seen = []
        def fail(command, *args, **kwargs):
            """Inspect the live private file, then emulate an ambiguous deploy."""
            path = Path(command[command.index("--secrets-file") + 1])
            seen.append(path)
            self.assertEqual(json.loads(path.read_text()), {"INGRESS_SECRET": "private"})
            self.assertNotIn("recovery", path.parts)
            raise DeploymentFailure("process_exit", "00000000-0000-0000-0000-000000000005")
        with patch.dict(os.environ, {"INGRESS_SECRET": "private"}), patch.object(online, "require_artifact"), patch.object(online, "submit", side_effect=fail):
            with self.assertRaises(DeploymentFailure):
                online.deploy_adapter("mail_ingress")
        self.assertEqual(len(seen), 1)
        self.assertFalse(seen[0].exists())

    def test_adapter_readback_requires_current_capture_and_exact_service(self):
        """An immutable handler or disabled root alone is not a privacy witness."""
        version = "00000000-0000-0000-0000-000000000005"
        versions = {"mail_ingress": version}
        immutable = {"id": version, "resources": {"script": {"handlers": ["email"]}, "bindings": [
            {"name": "MAIL_API_ORIGIN", "type": "plain_text", "text": "https://mail.moesegfault.dev"},
            {"name": "INGRESS_SECRET", "type": "secret_text"},
            {"name": "MAIL_API", "type": "service", "service": "amail-mail"}]}}
        worker = {"id": "current", "name": "amail-inbound", "logpush": False, "tail_consumers": [],
                  "observability": {"enabled": False, "logs": {"enabled": False},
                                    "traces": {"enabled": False}, "issues": {"enabled": False}}}
        def read(account, token, script, suffix):
            """Return exact documented readback shape for each fixed script endpoint."""
            if suffix.startswith("versions/"):
                return immutable
            if suffix == "subdomain":
                return {"enabled": False, "previews_enabled": False}
            if suffix == "schedules":
                return {"schedules": []}
            return {}
        with patch.object(online, "adapter_pins", return_value={"pins": "unchanged"}), patch.object(online, "verify_event_consumer"):
            with patch.object(online.capture, "readback", side_effect=read), patch.object(online.capture, "worker_readback", return_value=worker):
                self.assertEqual(online.verify_adapters(Mock(), scope(), versions), {"pins": "unchanged"})
                worker["observability"]["issues"]["enabled"] = True
                with self.assertRaisesRegex(ValueError, "adapter_capture"):
                    online.verify_adapters(Mock(), scope(), versions)
                worker["observability"]["issues"]["enabled"] = False
                immutable["resources"]["bindings"][-1]["service"] = "amail-mail-staging"
                with self.assertRaisesRegex(ValueError, "ingress_service"):
                    online.verify_adapters(Mock(), scope(), versions)

    def test_event_queue_requires_actual_consumer_and_unused_dlq(self):
        """A successful deploy cannot stand in for a connected lifecycle consumer."""
        queues = [{"queue_id": "a" * 32, "queue_name": "amail-sending-events"},
                  {"queue_id": "b" * 32, "queue_name": "amail-sending-events-dlq"}]
        details = {row["queue_id"]: {**row, "consumers": [], "consumers_total_count": 0} for row in queues}
        details["a" * 32].update({"consumers_total_count": 1, "consumers": [{"type": "worker", "script_name": "amail-events",
            "dead_letter_queue": "amail-sending-events-dlq", "settings": {"batch_size": 10, "max_wait_time_ms": 5000,
                                                                        "max_retries": 5, "retry_delay": 120}}]})
        provider = Mock(account="1" * 32)
        provider.get.side_effect = lambda path: details[path.rsplit("/", 1)[-1]]
        with patch.object(online.readback, "complete", return_value=queues):
            online.verify_event_consumer(provider)
            details["a" * 32]["consumers"][0]["script_name"] = "amail-events-staging"
            with self.assertRaisesRegex(ValueError, "event_consumer"):
                online.verify_event_consumer(provider)
            details["a" * 32]["consumers"][0]["script_name"] = "amail-events"
            details["b" * 32].update({"consumers_total_count": 1, "consumers": [{"type": "worker"}]})
            with self.assertRaisesRegex(ValueError, "dlq_consumer"):
                online.verify_event_consumer(provider)

    def exercise(self, folder: Path, *, fail_phase=None, graph_drift=False):
        """Drive mocked operations through the real fsynced controller state machine."""
        value = receipt_value()
        current = Epoch("e" * 40, "456", 67, "f" * 64, "1.94.0")
        receipt = Mock(value=value, artifact_id=89)
        provider = Mock(account="1" * 32)
        events = []
        def call(phase, result=None):
            """Collect semantic operations and stop at one selected ambiguous write."""
            events.append(phase)
            if phase == fail_phase:
                raise DeploymentFailure("process_exit", "00000000-0000-0000-0000-000000000005")
            return result
        def verify(*args, **kwargs):
            """Model old paused and new active runtime observations."""
            active = kwargs["maintenance_crons"] == online.CADENCE
            graph = json.loads(json.dumps(value["graph"]))
            if active:
                graph["maintenance_crons"] = list(online.CADENCE)
                graph["pins"]["amail-mail-maintenance"]["version"] = "00000000-0000-0000-0000-000000000005"
            elif graph_drift:
                graph["pins"]["amail-mail"]["deployment"] = "changed"
            self.assertTrue(kwargs["source_active"])
            return call("active" if active else "paused", graph)
        with ExitStack() as stack:
            patches = {"admit": lambda: call("admit", current), "load": lambda run: call("load", receipt),
                       "check_configs": lambda stores: call("source"), "capabilities": lambda stores: (provider, Mock()),
                       "captured": lambda *args, **kwargs: call("privacy" if "configure_sending_privacy.py" in str(args) else "dns"),
                       "email_events": lambda phase: call(phase),
                       "deploy_adapter": lambda component: call(component, "00000000-0000-0000-0000-000000000005"),
                       "forward_snapshot": lambda account: {"external": "unchanged"},
                       "adapter_pins": lambda *args: {"adapters": "same"},
                       "verify_adapters": lambda *args: {"adapters": "same"}}
            for name, action in patches.items():
                stack.enter_context(patch.object(online, name, side_effect=action))
            stack.enter_context(patch.object(online.readback, "verify", side_effect=verify))
            stack.enter_context(patch.object(online.bootstrap, "submit_once", side_effect=lambda *args: call("maintenance", "00000000-0000-0000-0000-000000000005")))
            controller = online.Online(folder)
            try:
                result = controller.run()
            except Exception:
                result = None
            return result, events

    def test_success_paused_before_writes_privacy_before_runtime_and_global_held(self):
        """Existing stores/API/sink remain; only cron activation is granted."""
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder:
            target = Path(folder)
            result, events = self.exercise(target)
            self.assertIsNotNone(result)
            self.assertEqual(events, ["admit", "load", "source", "paused", "dns", "privacy", "queues", "mail_ingress", "mail_events", "subscription", "maintenance", "active"])
            self.assertTrue(result["sendHeld"])
            self.assertEqual(result["send_release"], "NOT_GRANTED")
            self.assertEqual(result["creation_epoch"], asdict(scope().epoch))
            self.assertNotEqual(result["creation_epoch"], result["source_epoch"])
            self.assertEqual(json.loads((target / "receipt.json").read_text()), result)
            with self.assertRaises(FileExistsError):
                online.Online(target).run()

    def test_changed_paused_graph_stops_before_any_writes(self):
        """Receipt provenance alone cannot excuse deployment drift since pausing."""
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder:
            result, events = self.exercise(Path(folder), graph_drift=True)
            self.assertIsNone(result)
            self.assertEqual(events, ["admit", "load", "source", "paused"])
            self.assertFalse((Path(folder) / "receipt.json").exists())

    def test_partial_deploy_stops_once_and_persists_only_closed_diagnostics(self):
        """No subscription/maintenance follows ambiguous event deployment; no replay."""
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder:
            result, events = self.exercise(Path(folder), fail_phase="mail_events")
            self.assertIsNone(result)
            self.assertEqual(events.count("mail_events"), 1)
            self.assertNotIn("subscription", events)
            self.assertNotIn("maintenance", events)
            records = [json.loads(line) for line in (Path(folder) / "recovery/controller.jsonl").read_text().splitlines()]
            self.assertEqual(records[-1]["error_type"], "DeploymentFailure")
            self.assertEqual(records[-1]["version"], "00000000-0000-0000-0000-000000000005")
            self.assertFalse((Path(folder) / "receipt.json").exists())


if __name__ == "__main__":
    unittest.main()
