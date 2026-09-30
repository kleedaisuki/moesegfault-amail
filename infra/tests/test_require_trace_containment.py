"""Hosted rollout provenance denial contracts; never query live services locally."""
import base64
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("containment", Path(__file__).parents[1] / "deploy/require_trace_containment.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
VERSION = "11111111-1111-1111-1111-111111111111"
RUN = "123"


class ContainmentTests(unittest.TestCase):
    """A successful run alone cannot prove the exact still-serving safe deployment."""

    def responses(self, *, kind="deploy-v1"):
        """Use minimal safe historical TOML and exact successful deployment evidence."""
        source = '[env.staging]\nname="amail-mail-staging"\n[env.staging.observability]\nenabled=false\nhead_sampling_rate=1.0\nredact_query_string=true\n[env.staging.observability.logs]\nenabled=false\ninvocation_logs=false\n[env.staging.observability.traces]\nenabled=false\n[env.staging.observability.issues]\nenabled=false\n'
        return [json.dumps({"id": 123, "run_attempt": 1, "status": "completed", "conclusion": "success",
                "event": "workflow_dispatch",
                "repository": {"full_name": MODULE.REPO},
                "head_branch": "codex/amail-v0.1.0", "path": ".github/workflows/ci.yml", "head_sha": "a" * 40}),
                json.dumps({"total_count": 1, "jobs": [{"id": 456, "name": MODULE.JOBS[kind], "conclusion": "success",
                    "status": "completed", "run_id": 123, "run_attempt": 1, "head_sha": "a" * 40}]}),
                (f"Current Version ID: {VERSION}\n" if kind == "deploy-v1" else
                 f"job\tstep\t2026-09-30T00:00:00Z {MODULE.SETTINGS_MARKER}settings-v1 version={MODULE.SETTINGS_VERSION}\n"),
                json.dumps({"encoding": "base64", "content": base64.b64encode(source.encode()).decode()})]

    def test_exact_evidence(self):
        """Reviewed run, job, version and historical safe source are all necessary."""
        with patch.object(MODULE, "gh", side_effect=self.responses()):
            MODULE.immutable_evidence(RUN, VERSION)

    def test_failed_run_denied_before_logs(self):
        """Never infer deployment completion from partial successful job output."""
        run = json.loads(self.responses()[0]); run["conclusion"] = "failure"
        with patch.object(MODULE, "gh", return_value=json.dumps(run)) as call:
            with self.assertRaisesRegex(ValueError, "run_unverified"):
                MODULE.immutable_evidence(RUN, VERSION)
            self.assertEqual(call.call_count, 1)

    def test_malformed_job_shape_denied(self):
        """Provider-shape drift is a fixed-label failure, not an uncaught traceback."""
        replies = self.responses(); replies[1] = json.dumps({"total_count": 1, "jobs": ["unknown"]})
        with patch.object(MODULE, "gh", side_effect=replies):
            with self.assertRaisesRegex(ValueError, "jobs_incomplete"):
                MODULE.immutable_evidence(RUN, VERSION)

    def test_rerun_identity_denied(self):
        """A reused run ID cannot stand in for an immutable first-attempt deployment."""
        run = json.loads(self.responses()[0]); run["run_attempt"] = 2
        with patch.object(MODULE, "gh", return_value=json.dumps(run)):
            with self.assertRaisesRegex(ValueError, "run_unverified"):
                MODULE.immutable_evidence(RUN, VERSION)

    def test_duplicate_version_output_denied(self):
        """Repeated deploy output is ambiguous rather than an arbitrary winner."""
        replies = self.responses(); replies[2] *= 2
        with patch.object(MODULE, "gh", side_effect=replies):
            with self.assertRaisesRegex(ValueError, "deploy_version_unverified"):
                MODULE.immutable_evidence(RUN, VERSION)

    def test_historical_source_capture_or_identity_denied(self):
        """Current safe readback cannot replace missing historical Issues/source intent."""
        for before, after in (
                ('[env.staging.observability.issues]\nenabled=false\n', ''),
                ('[env.staging.observability.issues]\nenabled=false',
                 '[env.staging.observability.issues]\nenabled=true'),
                ('name="amail-mail-staging"', 'name="unrelated-worker"')):
            with self.subTest(after=after):
                replies = self.responses()
                envelope = json.loads(replies[3])
                source = base64.b64decode(envelope["content"]).decode().replace(before, after)
                envelope["content"] = base64.b64encode(source.encode()).decode()
                replies[3] = json.dumps(envelope)
                with patch.object(MODULE, "gh", side_effect=replies):
                    with self.assertRaisesRegex(ValueError, "source_privacy_unverified"):
                        MODULE.immutable_evidence(RUN, VERSION)

    def test_malformed_historical_environment_denied(self):
        """Malformed TOML shape raises a fixed failure instead of leaking a traceback."""
        for source in ('env="unknown"', '[env]\nstaging="unknown"'):
            with self.subTest(source=source):
                replies = self.responses()
                replies[3] = json.dumps({"encoding": "base64", "content":
                                        base64.b64encode(source.encode()).decode()})
                with patch.object(MODULE, "gh", side_effect=replies):
                    with self.assertRaisesRegex(ValueError, "source_privacy_unverified"):
                        MODULE.immutable_evidence(RUN, VERSION)

    def worker(self):
        """Model explicit capture-off despite inactive provider preference defaults."""
        return {"name": MODULE.SCRIPT, "id": "private-worker-id", "logpush": False,
                "tail_consumers": [], "observability": {"enabled": False,
                "redact_query_string": False, "head_sampling_rate": 1,
                "logs": {"enabled": False, "invocation_logs": True, "persist": True},
                "traces": {"enabled": False}, "issues": {"enabled": False}}}

    def test_effective_capture_off_with_unsupported_legacy_passes(self):
        """Accept only positive current-resource proof bracketed by exact traffic pins."""
        replies = [{}, {}, {"observability": None, "tail_consumers": None}, {}]
        with patch.object(MODULE, "immutable_evidence") as evidence, patch.object(
                MODULE, "fetch", side_effect=replies) as fetch, patch.object(
                MODULE, "worker_readback", return_value=self.worker()) as resource, patch.object(
                MODULE, "serving_deployment", side_effect=[("d", VERSION), ("d", VERSION)]):
            MODULE.verify(RUN, VERSION, "a", "t")
            evidence.assert_called_once_with(RUN, VERSION, kind="deploy-v1")
            resource.assert_called_once_with("a", "t", MODULE.SCRIPT)
            self.assertEqual([call.args[2] for call in fetch.call_args_list],
                             ["deployments?per_page=1&page=1", "settings", "script-settings",
                              "deployments?per_page=1&page=1"])

    def test_effective_capture_or_export_or_identity_denied(self):
        """Issues ambiguity, previews, other Workers and export channels fail closed."""
        variants = []
        for section in ("logs", "traces", "issues"):
            worker = self.worker(); del worker["observability"][section]
            variants.append(worker)
            worker = self.worker(); worker["observability"][section]["enabled"] = True
            variants.append(worker)
        for key, value in (("name", "unrelated-worker"), ("id", ""),
                           ("logpush", True), ("tail_consumers", None),
                           ("tail_consumers", [{"service": "unrelated"}])):
            worker = self.worker(); worker[key] = value; variants.append(worker)
        worker = self.worker(); del worker["observability"]
        worker["previews_base_config"] = {"observability": self.worker()["observability"]}
        variants.append(worker)
        worker = self.worker(); worker["observability"]["logs"]["destinations"] = ["external"]
        variants.append(worker)
        for worker in variants:
            with self.subTest(worker=worker), patch.object(MODULE, "immutable_evidence"), patch.object(
                    MODULE, "fetch", return_value={}), patch.object(
                    MODULE, "worker_readback", return_value=worker), patch.object(
                    MODULE, "serving_deployment", return_value=("d", VERSION)):
                with self.assertRaisesRegex(ValueError, "serving_privacy_unverified"):
                    MODULE.verify(RUN, VERSION, "a", "t")

    def test_legacy_contradiction_denied(self):
        """Unsupported legacy absence is different from an explicit capture/export conflict."""
        for legacy in ({"observability": {"issues": {"enabled": True}}},
                       {"logpush": True}, {"tail_consumers": ["unrelated"]}):
            with self.subTest(legacy=legacy), patch.object(MODULE, "immutable_evidence"), patch.object(
                    MODULE, "fetch", side_effect=[{}, legacy, {}]), patch.object(
                    MODULE, "worker_readback", return_value=self.worker()), patch.object(
                    MODULE, "serving_deployment", return_value=("d", VERSION)):
                with self.assertRaisesRegex(ValueError, "serving_privacy_unverified"):
                    MODULE.verify(RUN, VERSION, "a", "t")

    def test_current_resource_unavailable_denied(self):
        """A provider/readback failure never falls back to historical intent."""
        with patch.object(MODULE, "immutable_evidence"), patch.object(MODULE, "fetch", return_value={}), patch.object(
                MODULE, "worker_readback", side_effect=ValueError("readback_unavailable")), patch.object(
                MODULE, "serving_deployment", return_value=("d", VERSION)):
            with self.assertRaisesRegex(ValueError, "readback_unavailable"):
                MODULE.verify(RUN, VERSION, "a", "t")

    def test_settings_exact_evidence(self):
        """A successful dedicated first-attempt settings run proves only its own kind."""
        with patch.object(MODULE, "gh", side_effect=self.responses(kind="settings-v1")):
            MODULE.immutable_evidence(RUN, MODULE.SETTINGS_VERSION, kind="settings-v1")

    def test_settings_run_provenance_denied(self):
        """No other trigger, branch, path, SHA, rerun or failed run can substitute."""
        for key, value in (("event", "push"), ("head_branch", "main"),
                           ("path", ".github/workflows/other.yml"), ("head_sha", "mutable"),
                           ("run_attempt", 2), ("conclusion", "failure"),
                           ("status", "in_progress"), ("id", 999),
                           ("repository", {"full_name": "unrelated/repository"})):
            with self.subTest(key=key):
                replies = self.responses(kind="settings-v1")
                run = json.loads(replies[0]); run[key] = value; replies[0] = json.dumps(run)
                with patch.object(MODULE, "gh", side_effect=replies):
                    with self.assertRaisesRegex(ValueError, "run_unverified"):
                        MODULE.immutable_evidence(RUN, MODULE.SETTINGS_VERSION, kind="settings-v1")

    def test_settings_job_run_or_source_pin_denied(self):
        """The named job must belong to the exact first-attempt run and immutable SHA."""
        for key, value in (("id", "456"), ("status", "in_progress"),
                           ("run_id", 999), ("run_attempt", 2), ("head_sha", "b" * 40)):
            with self.subTest(key=key):
                replies = self.responses(kind="settings-v1")
                jobs = json.loads(replies[1]); jobs["jobs"][0][key] = value; replies[1] = json.dumps(jobs)
                with patch.object(MODULE, "gh", side_effect=replies):
                    with self.assertRaisesRegex(ValueError, "settings_job_unverified"):
                        MODULE.immutable_evidence(RUN, MODULE.SETTINGS_VERSION, kind="settings-v1")

    def test_settings_job_provenance_denied(self):
        """Exact complete dedicated job evidence is necessary, not diagnostic success."""
        variants = [
            {"total_count": 2, "jobs": [{"id": 456, "name": MODULE.JOBS["settings-v1"], "conclusion": "success"}]},
            {"total_count": 1, "jobs": [{"id": 456, "name": MODULE.JOBS["deploy-v1"], "conclusion": "success"}]},
            {"total_count": 1, "jobs": [{"id": 456, "name": MODULE.JOBS["settings-v1"], "conclusion": "failure"}]},
            {"total_count": 2, "jobs": [{"id": index, "name": MODULE.JOBS["settings-v1"], "conclusion": "success"}
                                      for index in (456, 789)]},
        ]
        for jobs in variants:
            with self.subTest(jobs=jobs):
                replies = self.responses(kind="settings-v1"); replies[1] = json.dumps(jobs)
                with patch.object(MODULE, "gh", side_effect=replies):
                    with self.assertRaisesRegex(ValueError, "jobs_incomplete|settings_job_unverified"):
                        MODULE.immutable_evidence(RUN, MODULE.SETTINGS_VERSION, kind="settings-v1")

    def test_settings_marker_ambiguity_denied(self):
        """Only one anchored exact marker passes; mixed kinds/deploy output never do."""
        marker = f"{MODULE.SETTINGS_MARKER}settings-v1 version={MODULE.SETTINGS_VERSION}"
        for log in ("", marker + "\n" + marker, marker + "\n" + MODULE.SETTINGS_MARKER + "deploy-v1",
                    marker.replace(MODULE.SETTINGS_VERSION, VERSION), marker + " suffix",
                    "arbitrary_" + marker, marker + "\nCurrent Version ID: " + MODULE.SETTINGS_VERSION,
                    marker.replace("settings-v1", "settings-v2")):
            with self.subTest(log=log):
                replies = self.responses(kind="settings-v1"); replies[2] = log
                with patch.object(MODULE, "gh", side_effect=replies):
                    with self.assertRaisesRegex(ValueError, "settings_attestation_unverified"):
                        MODULE.immutable_evidence(RUN, MODULE.SETTINGS_VERSION, kind="settings-v1")

    def test_settings_unsafe_historical_source_denied(self):
        """A correct marker never substitutes for historical explicit Issues-off intent."""
        replies = self.responses(kind="settings-v1")
        envelope = json.loads(replies[3])
        source = base64.b64decode(envelope["content"]).decode().replace(
            '[env.staging.observability.issues]\nenabled=false\n', '')
        envelope["content"] = base64.b64encode(source.encode()).decode()
        replies[3] = json.dumps(envelope)
        with patch.object(MODULE, "gh", side_effect=replies):
            with self.assertRaisesRegex(ValueError, "source_privacy_unverified"):
                MODULE.immutable_evidence(RUN, MODULE.SETTINGS_VERSION, kind="settings-v1")

    def test_settings_future_source_queue_does_not_claim_deployment(self):
        """Run-head Queue intent is allowed only because this kind patches observability."""
        replies = self.responses(kind="settings-v1")
        envelope = json.loads(replies[3])
        source = base64.b64decode(envelope["content"]).decode() + (
            '\n[[env.staging.queues.producers]]\nbinding="TRACE_EVENTS"\nqueue="amail-trace-events-staging"\n')
        envelope["content"] = base64.b64encode(source.encode()).decode()
        replies[3] = json.dumps(envelope)
        with patch.object(MODULE, "gh", side_effect=replies):
            MODULE.immutable_evidence(RUN, MODULE.SETTINGS_VERSION, kind="settings-v1")

    def test_kind_selection_and_settings_version_are_explicit(self):
        """No automatic fallback, unknown evidence kind or other one-shot version."""
        for kind, version in (("unknown", VERSION), ("settings-v1", VERSION)):
            with patch.object(MODULE, "gh") as call:
                with self.assertRaisesRegex(ValueError, "evidence_kind_unverified"):
                    MODULE.immutable_evidence(RUN, version, kind=kind)
                call.assert_not_called()
        with patch.object(MODULE, "gh", side_effect=self.responses(kind="settings-v1")):
            with self.assertRaisesRegex(ValueError, "deploy_job_unverified"):
                MODULE.immutable_evidence(RUN, MODULE.SETTINGS_VERSION)

    def test_settings_live_binding_pin_required(self):
        """Recheck immutable version bindings within the capture-off deployment bracket."""
        version = MODULE.SETTINGS_VERSION
        replies = [{}, {"id": version}, {}, {}, {}]
        with patch.object(MODULE, "immutable_evidence") as evidence, patch.object(
                MODULE, "fetch", side_effect=replies) as fetch, patch.object(
                MODULE, "bindings_match", return_value=True) as bindings, patch.object(
                MODULE, "worker_readback", return_value=self.worker()), patch.object(
                MODULE, "serving_deployment", side_effect=[("d", version), ("d", version)]):
            MODULE.verify(RUN, version, "a", "t", kind="settings-v1")
            evidence.assert_called_once_with(RUN, version, kind="settings-v1")
            bindings.assert_called_once_with({"id": version}, version)
            self.assertEqual(fetch.call_args_list[1].args[2], f"versions/{version}")

    def test_settings_extra_queue_binding_denied(self):
        """Settings evidence may not admit a producer binding in the serving version."""
        version = MODULE.SETTINGS_VERSION
        resource = {"id": version, "resources": {"bindings": [
            {"name": "MAIL_DB", "type": "d1", "database_id": "db"},
            {"name": "TRACE_EVENTS", "type": "queue", "queue_name": "amail-trace-events-staging"}]}}
        with patch.dict(MODULE.bindings_match.__globals__, {"expected_bindings": lambda: {"MAIL_DB": ("d1", "db")}}), patch.object(
                MODULE, "immutable_evidence"), patch.object(MODULE, "fetch", side_effect=[{}, resource]), patch.object(
                MODULE, "worker_readback") as worker, patch.object(MODULE, "serving_deployment", return_value=("d", version)):
            with self.assertRaisesRegex(ValueError, "serving_bindings_unverified"):
                MODULE.verify(RUN, version, "a", "t", kind="settings-v1")
            worker.assert_not_called()

    def test_cli_kind_threading_and_fixed_failure(self):
        """Default compatibility and explicit selection preserve private fixed outputs."""
        for kind in (None, "settings-v1"):
            argv = ["require_trace_containment.py", "--run", RUN, "--version", MODULE.SETTINGS_VERSION]
            if kind:
                argv.extend(["--kind", kind])
            output = io.StringIO()
            with patch.object(MODULE.sys, "argv", argv), patch.dict(MODULE.os.environ,
                    {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "private-token"}), patch.object(
                    MODULE, "verify", side_effect=ValueError("private-provider-response")) as verify, redirect_stdout(output):
                self.assertEqual(MODULE.main(), 1)
                verify.assert_called_once_with(RUN, MODULE.SETTINGS_VERSION, "a" * 32, "private-token",
                                               kind=kind or "deploy-v1")
            self.assertEqual(output.getvalue(), "trace_containment=UNVERIFIED\n")

    def test_split_or_changed_serving_denied(self):
        """Live version drift stops the rollout even after immutable evidence passed."""
        with patch.object(MODULE, "immutable_evidence"), patch.object(MODULE, "fetch"), patch.object(
                MODULE, "serving_deployment", return_value=None):
            with self.assertRaisesRegex(ValueError, "serving_version_unverified"):
                MODULE.verify(RUN, VERSION, "a", "t")
        with patch.object(MODULE, "immutable_evidence"), patch.object(MODULE, "fetch"), patch.object(
                MODULE, "worker_readback") as worker, patch.object(
                MODULE, "serving_deployment", return_value=("d", "22222222-2222-2222-2222-222222222222")):
            with self.assertRaisesRegex(ValueError, "serving_version_unverified"):
                MODULE.verify(RUN, VERSION, "a", "t")
            worker.assert_not_called()
        with patch.object(MODULE, "immutable_evidence"), patch.object(MODULE, "fetch"), patch.object(
                MODULE, "worker_readback", return_value=self.worker()), patch.object(
                MODULE, "effective_api_settings", return_value=True), patch.object(MODULE, "serving_deployment",
                side_effect=[("d", VERSION), ("changed", VERSION)]):
            with self.assertRaisesRegex(ValueError, "serving_version_changed"):
                MODULE.verify(RUN, VERSION, "a", "t")


if __name__ == "__main__":
    unittest.main()
