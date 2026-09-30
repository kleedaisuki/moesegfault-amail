"""Hosted rollout provenance denial contracts; never query live services locally."""
import base64
import importlib.util
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

    def responses(self):
        """Use minimal safe historical TOML and exact successful deployment evidence."""
        source = '[env.staging]\nname="amail-mail-staging"\n[env.staging.observability]\nenabled=false\nhead_sampling_rate=1.0\nredact_query_string=true\n[env.staging.observability.logs]\nenabled=false\ninvocation_logs=false\n[env.staging.observability.traces]\nenabled=false\n[env.staging.observability.issues]\nenabled=false\n'
        return [json.dumps({"id": 123, "run_attempt": 1, "status": "completed", "conclusion": "success",
                "head_branch": "codex/amail-v0.1.0", "path": ".github/workflows/ci.yml", "head_sha": "a" * 40}),
                json.dumps({"total_count": 1, "jobs": [{"id": 456, "name": "Deploy isolated staging mail API", "conclusion": "success"}]}),
                f"Current Version ID: {VERSION}\n",
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
            evidence.assert_called_once_with(RUN, VERSION)
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
