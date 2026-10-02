"""Synthetic staging admission, one-shot cutover and preserved backlog contracts."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import staging_rollout as rollout
import staging_resume as resume
import inspect_staging as inspector
import check_staging_adapters as adapters


class StagingRolloutTests(unittest.TestCase):
    """The provider bound never degenerates into a sleep or a backlog purge."""

    def environment(self) -> dict:
        """Build only synthetic fixed realm coordinates."""
        return {"GITHUB_REF": rollout.BRANCH, "GITHUB_ACTIONS": "true",
                "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123",
                "GITHUB_OUTPUT": str(ROOT / ".temp/unused-test-output"),
                "AMAIL_STAGING_DEPLOY_CONFIRM": rollout.CONFIRM,
                "CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "synthetic",
                "AMAIL_EXPECTED_WORKER_VERSION": "new-api", "AMAIL_TRACE_QUEUE_ID": "b" * 32}

    def predecessor(self, kind: str = "legacy") -> dict:
        """Return a projected snapshot without mail, addresses or credentials."""
        return {"source_sha": "a" * 40, "run_id": "123", "rollout": kind,
                "old_usage_model": "standard", "scripts": {rollout.API: {"version": "old-api"}}}

    def test_context_refuses_other_branches_or_confirmation(self):
        """No ordinary main action can invoke this staging-only writer."""
        for field, value in (("GITHUB_REF", "refs/heads/main"),
                             ("AMAIL_STAGING_DEPLOY_CONFIRM", "wrong"), ("GITHUB_ACTIONS", "false")):
            with patch.dict(os.environ, dict(self.environment(), **{field: value}), clear=True):
                with self.assertRaises(ValueError):
                    rollout.context()

    def test_read_confirmation_cannot_enter_any_writer_phase(self):
        """Inspection confirmation is independently admitted, never a write token."""
        environment = self.environment()
        environment.pop("AMAIL_STAGING_DEPLOY_CONFIRM")
        environment.update({"AMAIL_STAGING_INSPECT_CONFIRM": rollout.INSPECT_CONFIRM,
                            "AMAIL_STAGING_RESUME_RUN": resume.ORIGIN_RUN})
        with patch.dict(os.environ, environment, clear=True):
            rollout.context(read_only=True)
            for operation in (rollout.context, rollout.before_api, rollout.cutover):
                with self.assertRaises(ValueError):
                    operation()
        environment["AMAIL_STAGING_RESUME_RUN"] = "unreviewed"
        with patch.dict(os.environ, environment, clear=True), self.assertRaises(ValueError):
            rollout.context(read_only=True)

    def test_main_logs_only_closed_failure_reason_and_read_dispatch(self):
        """Unknown provider prose never enters logs and inspection selects only reads."""
        for error, expected in ((ValueError("staging_resume_dirty_tracked_tree"), "staging_resume_dirty_tracked_tree"),
                                (ValueError("private arbitrary provider text"), "unknown"),
                                (RuntimeError("staging_resume_dirty_tracked_tree"), "unknown")):
            output = io.StringIO()
            with patch.object(sys, "argv", ["staging_rollout.py", "inspect-preflight"]), \
                 patch.object(rollout, "preflight", side_effect=error) as preflight, redirect_stdout(output):
                self.assertEqual(rollout.main(), 1)
            preflight.assert_called_once_with(read_only=True)
            self.assertEqual(output.getvalue(), f"staging_rollout_inspect-preflight=UNVERIFIED reason={expected}\n")

    def test_immutable_runtime_model_supplies_the_positive_bound(self):
        """Use the documented version schema without requiring mutable settings."""
        for usage in ("standard", "unbound"):
            version = {"resources": {"script_runtime": {"usage_model": usage},
                                      "script": {"handlers": ["fetch", "scheduled"]}}}
            self.assertEqual(rollout.bounded_usage_model(version), usage)

    def test_bundled_unknown_or_wrong_field_cannot_borrow_a_modern_bound(self):
        """A mutable or wrong-path Standard value cannot mask immutable Bundled."""
        for version in ({"resources": {"script_runtime": {"usage_model": "bundled"},
                                       "script": {"usage_model": "standard"}}},
                        {"resources": {"script": {"usage_model": "standard"}}},
                        {"resources": {"script_runtime": {"usage_model": "unknown"}}}, {}):
            with self.assertRaises(ValueError):
                rollout.bounded_usage_model(version)

    def test_legacy_cutover_rechecks_capabilities_and_preserves_live_leases(self):
        """Documented bounds plus repeated provider pins admit, not elapsed age alone."""
        temporary = ROOT / ".temp"
        temporary.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary) as folder:
            witness = Path(folder) / "witness.json"
            with patch.dict(os.environ, self.environment(), clear=True), \
                 patch.object(rollout, "predecessor", return_value=self.predecessor()), \
                 patch.object(rollout, "deploy_maintenance", side_effect=("paused", "active")) as deploy, \
                 patch.object(rollout, "pin_api", return_value="match") as api, \
                 patch.object(rollout, "verify_maintenance") as maintenance, \
                 patch.object(rollout.graph, "held_send") as hold, \
                 patch.object(rollout, "lease_fences", return_value={"embedding_leases": 2, "projection_leases": 1}), \
                 patch.object(rollout.time, "monotonic", side_effect=(0, 0, rollout.WINDOW_SECONDS)), \
                 patch.object(rollout.time, "sleep") as sleep, patch.object(rollout, "WITNESS", witness):
                rollout.cutover()
            self.assertEqual([call.args[0] for call in deploy.call_args_list], [False, True])
            self.assertEqual(api.call_count, 2)
            self.assertEqual(maintenance.call_count, 2)
            self.assertEqual(hold.call_count, 2)
            sleep.assert_called_once_with(60)
            value = json.loads(witness.read_text())
            self.assertEqual(value["execution_leases_preserved"], {"embedding_leases": 2, "projection_leases": 1})
            self.assertNotIn("backlog", value)

    def test_changed_api_blocks_activation_without_replay(self):
        """A serving drift keeps maintenance paused even after a long observed age."""
        with patch.dict(os.environ, self.environment(), clear=True), \
             patch.object(rollout, "predecessor", return_value=self.predecessor()), \
             patch.object(rollout, "deploy_maintenance", return_value="paused") as deploy, \
             patch.object(rollout, "pin_api", return_value="deployment_changed"), \
             patch.object(rollout.time, "monotonic", return_value=0):
            with self.assertRaises(ValueError):
                rollout.cutover()
        deploy.assert_called_once_with(False)

    def test_split_replacement_does_not_repeat_legacy_wait(self):
        """The initial cutover cost is not a permanent constant factor."""
        with patch.dict(os.environ, self.environment(), clear=True), \
             patch.object(rollout, "predecessor", return_value=self.predecessor("split")), \
             patch.object(rollout, "deploy_maintenance") as deploy, patch.object(rollout.time, "sleep") as sleep:
            rollout.cutover()
        deploy.assert_called_once_with(True)
        sleep.assert_not_called()

    def partial_graph(self) -> tuple[dict, dict]:
        """Use the actual non-content snapshot as synthetic owned phase-zero pins."""
        api = {"present": True, "deployment": resume.API_DEPLOYMENT, "version": resume.API_VERSION,
               "handlers": ["fetch", "scheduled"], "crons": ["*/5 * * * *"],
               "capture_off": True, "usage_model": "standard"}
        original = {"scripts": {rollout.API: api, "amail-inbound-staging": {"version": "ingress"},
                               "amail-events-staging": {"version": "events"}}}
        value = {"source_sha": "a" * 40, "run_id": "123", "scripts": deepcopy(original["scripts"]),
                 "queues": {}, "sink_checks": {"topology_checked": "api-only",
                 "immutable_capabilities": True, "retained_settings": True,
                 "private_surfaces": True, "queue_trigger": True}}
        value["scripts"][rollout.MAINTENANCE] = {"present": False}
        value["scripts"]["amail-trace-sink-staging"] = {
            "present": True, "version": resume.SINK_VERSION,
            "deployment": "73892f24-1e84-406a-b025-3879580597e1",
            "handlers": ["queue"], "crons": [], "capture_off": False, "privacy_safe": True}
        for name, identity in (("amail-trace-events-staging", resume.QUEUE),
                               ("amail-trace-dlq-staging", resume.DLQ)):
            value["queues"][name] = {"present": True, "queue_id": identity,
                                      "bounded_retention": True, "producers": []}
        owned = {"predecessor": original, "sink_version": resume.SINK_VERSION,
                 "queue": resume.QUEUE, "dlq": resume.DLQ}
        return value, owned

    def admit_partial(self, value: dict, owned: dict, confirm: bool = True) -> tuple[dict, dict]:
        """Exercise preflight with no provider calls, mutations or scratch output."""
        environment = self.environment()
        if confirm:
            environment["AMAIL_STAGING_RESUME_RUN"] = resume.ORIGIN_RUN
        version = {"resources": {"script_runtime": {"usage_model": "standard"}}}
        with patch.dict(os.environ, environment, clear=True), \
             patch.object(rollout, "inspect", return_value=deepcopy(value)), \
             patch.object(rollout.capture, "readback", return_value=version), \
             patch.object(rollout, "containment_bindings_match", return_value=True), \
             patch.object(resume, "load_resume", return_value=owned), \
             patch.object(rollout.graph, "held_send") as hold, \
             patch.object(rollout, "write") as write, patch.object(rollout, "output") as output:
            rollout.preflight()
            hold.assert_called_once_with("staging")
            return write.call_args.args[1], dict(call.args for call in output.call_args_list)

    def test_partial_resume_preserves_current_epoch_and_skips_owned_sink_writes(self):
        """Original ownership permits reuse, never an old artifact identity."""
        value, owned = self.partial_graph()
        recorded, output = self.admit_partial(value, owned)
        self.assertEqual(recorded["source_sha"], "a" * 40)
        self.assertEqual(recorded["run_id"], "123")
        self.assertEqual(recorded["resume_origin_run"], resume.ORIGIN_RUN)
        self.assertEqual(output, {"reuse_sink": "true", "queue_id": resume.QUEUE,
                                 "dlq_id": resume.DLQ, "sink_version": resume.SINK_VERSION,
                                 "rollout": "legacy"})

    def test_partial_resume_rejects_phase_drift_and_missing_private_predicates(self):
        """No producer, private surface, capability or ownership drift is adopted."""
        value, owned = self.partial_graph()
        variants = []
        for name, bad in (("queue_trigger", False), ("private_surfaces", False),
                          ("retained_settings", False), ("immutable_capabilities", None)):
            changed = deepcopy(value)
            changed["sink_checks"][name] = bad
            variants.append(changed)
        for field, bad in (("producers", [rollout.API]), ("bounded_retention", False),
                           ("queue_id", "unowned")):
            changed = deepcopy(value)
            changed["queues"]["amail-trace-events-staging"][field] = bad
            variants.append(changed)
        changed = deepcopy(value)
        changed["scripts"][rollout.API]["version"] = "different"
        variants.append(changed)
        changed = deepcopy(value)
        changed["scripts"]["amail-trace-sink-staging"]["version"] = "different"
        variants.append(changed)
        changed = deepcopy(value)
        changed["scripts"]["amail-trace-sink-staging"]["privacy_safe"] = False
        variants.append(changed)
        for changed in variants:
            with self.subTest(value=changed), self.assertRaises(ValueError):
                self.admit_partial(changed, owned)
        with self.assertRaises(ValueError):
            self.admit_partial(value, owned, confirm=False)

    def test_diagnostic_observed_ids_do_not_replace_reviewed_pins(self):
        """An inspection failure still restores caller-reviewed ownership pins."""
        environment = self.environment()
        def observed():
            """Simulate a failed diagnostic after it projected observed IDs."""
            os.environ["AMAIL_TRACE_QUEUE_ID"] = "observed-unowned"
            os.environ["AMAIL_TRACE_DLQ_ID"] = "observed-unowned-dlq"
            raise ValueError("synthetic_read_failure")
        with patch.dict(os.environ, environment, clear=True), \
             patch.object(rollout, "inspect", side_effect=observed):
            with self.assertRaises(ValueError):
                rollout.preflight()
            self.assertEqual(os.environ["AMAIL_TRACE_QUEUE_ID"], environment["AMAIL_TRACE_QUEUE_ID"])
            self.assertNotIn("AMAIL_TRACE_DLQ_ID", os.environ)

    def test_split_diagnostic_emits_closed_reason_without_provider_prose(self):
        """Observed live pins support diagnosis, not deployment or resource adoption."""
        value = {"scripts": {name: {"version": version} for name, version in
                 (("amail-mail-staging", "api"), ("amail-mail-maintenance-staging", "maintenance"),
                  ("amail-trace-sink-staging", "sink"))}}
        with patch.dict(os.environ, {}, clear=True), patch.object(rollout.graph, "verify") as verify:
            self.assertEqual(inspector.split_diagnostic(value), {"exact_graph": True, "reason": "verified"})
            verify.assert_called_once_with("staging", "active")
        for failure, expected in (("split_role_absence_unverified", "split_role_absence_unverified"),
                                  ("arbitrary private provider text", "unknown")):
            with patch.dict(os.environ, {}, clear=True), \
                 patch.object(rollout.graph, "verify", side_effect=ValueError(failure)):
                self.assertEqual(inspector.split_diagnostic(value), {"exact_graph": False, "reason": expected})

    def test_routing_diagnostic_projects_only_matcher_shapes(self):
        """The existing exact-zone reader produces no recipients/actions/identifiers."""
        import ensure_role_forwarding as forwarding
        rows = [{"matchers": None, "private": "private value"}, {}, {"matchers": []}, {"matchers": "private value"}]
        with patch.dict(os.environ, {"CF_EMAIL_ROUTING_TOKEN": "synthetic"}), \
             patch.object(forwarding, "rules", return_value=rows):
            self.assertEqual(inspector.routing_diagnostic("account"), {"available": True, "rows": 4,
                "matchers": {"null": 1, "missing": 1, "list": 1, "invalid": 1}})

    def test_legacy_role_projection_contains_capabilities_not_private_values(self):
        """Independent role DB is not Mail DB; no secret values enter artifacts."""
        bindings = [{"type": "d1", "database_id": "unrelated-role-database"},
                    {"type": "secret_text", "name": "private-secret-name", "text": "private-secret-value"},
                    {"type": "queue", "queue_id": "c" * 32}]
        version = {"resources": {"bindings": bindings, "script": {"handlers": ["email", "scheduled"]}}}
        with patch.dict(os.environ, {}, clear=True):
            facts = inspector.role_capabilities(version)
        self.assertEqual(facts, {"handlers": ["email", "scheduled"], "mail_database_bound": False,
                                 "mail_service_bound": False, "mail_body_bucket_bound": False,
                                 "mail_trace_queue_bound": False})
        self.assertNotIn("private", json.dumps(facts))
        version["resources"]["bindings"] = {"result": bindings + [
            {"type": "d1", "database_id": "74f35f95-42ce-482c-86e6-dffbdd35cbbe"},
            {"type": "service", "service": "amail-mail-staging"},
            {"type": "r2_bucket", "bucket_name": "moesegfault-mail-raw-staging"},
            {"type": "queue", "queue_name": "amail-trace-events-staging", "queue_id": "c" * 32}]}
        self.assertTrue(all(value for name, value in inspector.role_capabilities(version).items() if name != "handlers"))

    def test_graph_default_stdout_contract_is_preserved(self):
        """Only explicit staging diagnostics append the safe structural reason."""
        for arguments, expected in ((["--realm", "production", "--state", "active"], "mail_split_graph=UNVERIFIED\n"),
                                    (["--realm", "staging", "--state", "active", "--diagnostic"],
                                     "mail_split_graph=UNVERIFIED reason=split_role_absence_unverified\n")):
            output = io.StringIO()
            with patch.object(sys, "argv", ["check_mail_split_graph.py", *arguments]), \
                 patch.object(rollout.graph, "verify", side_effect=ValueError("split_role_absence_unverified")), \
                 redirect_stdout(output):
                self.assertEqual(rollout.graph.main(), 1)
            self.assertEqual(output.getvalue(), expected)

    def test_independent_role_is_bracketed_and_every_mail_edge_is_rejected(self):
        """Retaining an independent contact Worker never grants it Mail capabilities."""
        version_id = "b" * 8 + "-" + "-".join(["b" * 4] * 3) + "-" + "b" * 12
        deployment = {"deployments": [{"id": "a" * 8 + "-" + "-".join(["a" * 4] * 3) + "-" + "a" * 12,
                       "strategy": "percentage", "versions": [{"version_id": version_id, "percentage": 100}]}]}
        version = {"id": version_id, "resources": {"bindings": [{"type": "d1", "database_id": "independent-role-db"}],
                                                  "script": {"handlers": ["email", "scheduled"]}}}
        reads = [deployment, version, {"schedules": [{"cron": "*/5 * * * *"}]}, deployment]
        with patch.object(rollout.capture, "readback", side_effect=reads):
            result = rollout.graph.independent_role_snapshot("account", "token")
        self.assertEqual(result["crons"], ["*/5 * * * *"])
        for binding in ({"type": "d1", "database_id": "74f35f95-42ce-482c-86e6-dffbdd35cbbe"},
                        {"type": "r2_bucket", "bucket_name": "moesegfault-mail-raw-staging"},
                        *({"type": "service", "service": name} for name in
                          ("amail-mail-staging", "amail-mail-maintenance-staging", "amail-trace-sink-staging")),
                        {"type": "queue", "queue_name": "amail-trace-events-staging", "queue_id": "c" * 32},
                        {"type": "queue", "queue_name": "amail-trace-dlq-staging", "queue_id": "c" * 32}):
            changed = deepcopy(version)
            changed["resources"]["bindings"].append(binding)
            with patch.object(rollout.capture, "readback", side_effect=[deployment, changed]), self.assertRaises(ValueError):
                rollout.graph.independent_role_snapshot("account", "token")
        with patch.object(rollout.capture, "readback", side_effect=reads[:-1] + [{"deployments": []}]), self.assertRaises(ValueError):
            rollout.graph.independent_role_snapshot("account", "token")

    def test_missing_role_targets_never_prove_independent_capabilities(self):
        """Both Queue ID spellings are supported, but malformed/conflicting views stop."""
        def project(binding):
            return rollout.graph.role_capabilities({"resources": {"bindings": [binding], "script": {"handlers": ["scheduled"]}}})
        for kind, field in (("d1", "database_id"), ("r2_bucket", "bucket_name"), ("service", "service")):
            for value in (None, "", "   ", 12):
                with self.assertRaises(ValueError):
                    project({"type": kind, field: value})
            with self.assertRaises(ValueError):
                project({"type": kind})
        for binding in ({"type": "queue"}, {"type": "queue", "queue_name": "unresolved-name"},
                        {"type": "queue", "queue_id": None}, {"type": "queue", "id": 12},
                        {"type": "queue", "queue_id": "c" * 32, "id": "d" * 32},
                        {"type": "queue", "queue_id": "c" * 32, "queue_name": ""}):
            with self.assertRaises(ValueError):
                project(binding)
        with patch.dict(os.environ, {"AMAIL_TRACE_QUEUE_ID": "c" * 32}):
            self.assertTrue(project({"type": "queue", "id": "c" * 32})["mail_trace_queue_bound"])
            self.assertTrue(project({"type": "queue", "id": "c" * 32, "queue_id": "c" * 32})["mail_trace_queue_bound"])

    def test_active_resume_reuses_proven_api_and_maintenance_under_exact_queue_pins(self):
        """A completed cutover is not replayed when only remaining adapters/site need writes."""
        value, owned = self.partial_graph()
        owned.update({"phase": "active", "api_version": "01f14a8e-d5b1-41f9-9f8c-325c2e288ba7",
                      "maintenance_version": "3d23d537-6379-4fcb-84c2-2c1b8a9f4857"})
        value["scripts"][rollout.API].update({"version": owned["api_version"],
          "deployment": "7c6c70e5-d617-4119-9dff-846f5f204a3c", "handlers": ["fetch"], "crons": []})
        value["scripts"][rollout.MAINTENANCE] = {"present": True, "version": owned["maintenance_version"],
          "deployment": "ad083bc6-e1c0-4ee6-81af-d19c4261ec50", "handlers": ["scheduled"],
          "crons": ["*/5 * * * *"], "capture_off": True}
        environment = dict(self.environment(), AMAIL_STAGING_RESUME_RUN="37058617870")
        with patch.dict(os.environ, environment, clear=True), \
             patch.object(rollout, "inspect", return_value=value), patch.object(resume, "load_resume", return_value=owned), \
             patch.object(rollout.graph, "verify") as graph, patch.object(rollout, "write"), \
             patch.object(rollout, "output") as output, patch.object(rollout, "deploy_maintenance") as deploy:
            rollout.preflight()
            self.assertEqual(os.environ["AMAIL_TRACE_QUEUE_ID"], resume.QUEUE)
            self.assertEqual(os.environ["AMAIL_TRACE_DLQ_ID"], resume.DLQ)
        graph.assert_called_once_with("staging", "active")
        deploy.assert_not_called()
        self.assertEqual(dict(call.args for call in output.call_args_list)["reuse_api"], "true")

    def test_adapters_resume_requires_fresh_exact_adapter_verification_before_reuse(self):
        """Only-site continuation cannot skip the failed boundary's repaired contract."""
        value, owned = self.partial_graph()
        owned.update({"phase": "adapters", "api_version": resume.ACTIVE_API,
                      "maintenance_version": resume.ACTIVE_MAINTENANCE,
                      "ingress_version": resume.ADAPTER_INGRESS, "events_version": resume.ADAPTER_EVENTS})
        value["scripts"][rollout.API].update(version=resume.ACTIVE_API,
          deployment="7c6c70e5-d617-4119-9dff-846f5f204a3c", handlers=["fetch"], crons=[])
        value["scripts"][rollout.MAINTENANCE] = {"present": True, "version": resume.ACTIVE_MAINTENANCE,
          "deployment": "ad083bc6-e1c0-4ee6-81af-d19c4261ec50", "crons": ["*/5 * * * *"]}
        for script, version, deployment in ((adapters.INGRESS, resume.ADAPTER_INGRESS, "6059657f-0e89-43e5-98a9-f604952c2a56"),
                                            (adapters.EVENTS_WORKER, resume.ADAPTER_EVENTS, "d65dc034-3aa9-4b94-948a-d495b367cd08")):
            value["scripts"][script] = {"version": version, "deployment": deployment}
        for failure in (None, ValueError("adapter_subscription_unverified")):
            with patch.dict(os.environ, dict(self.environment(), AMAIL_STAGING_RESUME_RUN=resume.ADAPTER_RUN), clear=True), \
                 patch.object(rollout, "inspect", return_value=value), patch.object(resume, "load_resume", return_value=owned), \
                 patch.object(rollout.graph, "verify"), patch.object(adapters, "verify", side_effect=failure) as verify, \
                 patch.object(rollout, "write"), patch.object(rollout, "output") as output:
                if failure:
                    with self.assertRaisesRegex(ValueError, "^staging_resume_adapter_graph_unverified$"):
                        rollout.preflight()
                    output.assert_not_called()
                else:
                    rollout.preflight()
                    self.assertEqual(dict(call.args for call in output.call_args_list)["reuse_adapters"], "true")
                verify.assert_called_once_with(resume.ADAPTER_INGRESS, resume.ADAPTER_EVENTS)


if __name__ == "__main__":
    unittest.main()
