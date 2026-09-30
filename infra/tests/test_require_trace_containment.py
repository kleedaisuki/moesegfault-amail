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
        source = '[env.staging.observability]\nenabled=false\nhead_sampling_rate=1.0\nredact_query_string=true\n[env.staging.observability.logs]\nenabled=false\ninvocation_logs=false\n[env.staging.observability.traces]\nenabled=false\n'
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

    def test_split_or_changed_serving_denied(self):
        """Live version drift stops the rollout even after immutable evidence passed."""
        with patch.object(MODULE, "immutable_evidence"), patch.object(MODULE, "fetch"), patch.object(
                MODULE, "serving_deployment", return_value=None):
            with self.assertRaisesRegex(ValueError, "serving_version_unverified"):
                MODULE.verify(RUN, VERSION, "a", "t")
        with patch.object(MODULE, "immutable_evidence"), patch.object(MODULE, "fetch"), patch.object(
                MODULE, "safe_settings", return_value=True), patch.object(MODULE, "serving_deployment",
                side_effect=[("d", VERSION), ("changed", VERSION)]):
            with self.assertRaisesRegex(ValueError, "serving_version_changed"):
                MODULE.verify(RUN, VERSION, "a", "t")


if __name__ == "__main__":
    unittest.main()
