"""Hosted exact-main inbox artifact admission and unchanged source workflow guards."""

from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
import inbox_worker_artifact as admission
from workflow_source import job_block

SHA = "a" * 40


def fixture():
    """A complete original main build contains every platform and native gate."""
    run = {"id": 123, "run_attempt": 1, "path": ".github/workflows/ci.yml", "status": "completed",
           "conclusion": "success", "head_branch": "main", "head_sha": SHA, "event": "push",
           "repository": {"full_name": admission.REPO}}
    jobs = [{"name": name, "status": "completed", "conclusion": "success"} for name in admission.REQUIRED]
    return run, {"jobs": jobs, "total_count": len(jobs)}, {
        "artifacts": [{"name": "worker-native-modules-" + SHA, "id": 789, "expired": False}], "total_count": 1}


class InboxWorkerArtifactTests(unittest.TestCase):
    """No main ancestry exemption, producer-only gate or missing artifact rebuild exists."""

    def test_full_exact_main_original_coordinates(self):
        """A separate orchestration run consumes this original identity, not new labels."""
        self.assertEqual(admission.identity(*fixture(), SHA), {
            "source_sha": SHA, "run_id": "123", "run_attempt": 1, "artifact_id": 789})

    def test_wrong_source_event_repository_attempt_and_partial_checks_refuse(self):
        """Old main, PRs, reruns and an individually green producer cannot pass."""
        for field, value in (("head_sha", "b" * 40), ("head_branch", "branch"),
                             ("event", "pull_request"), ("run_attempt", 2), ("run_attempt", True),
                             ("conclusion", "failure"), ("status", "in_progress"),
                             ("repository", {"full_name": "untrusted/repo"})):
            run, jobs, artifacts = fixture()
            run[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                admission.identity(run, jobs, artifacts, SHA)
        for name in admission.REQUIRED:
            run, jobs, artifacts = fixture()
            next(row for row in jobs["jobs"] if row["name"] == name)["conclusion"] = "skipped"
            with self.subTest(name=name), self.assertRaises(ValueError):
                admission.identity(run, jobs, artifacts, SHA)

    def test_expired_duplicate_and_truncated_inventory_refuse(self):
        """A unique artifact and count-complete inventories are non-optional."""
        for mode in ("expired", "duplicate", "partial_jobs", "partial_artifacts", "bool_artifact"):
            run, jobs, artifacts = fixture()
            if mode == "expired":
                artifacts["artifacts"][0]["expired"] = True
            if mode == "duplicate":
                artifacts["artifacts"] *= 2
                artifacts["total_count"] = 2
            if mode == "partial_jobs":
                jobs["total_count"] += 1
            if mode == "partial_artifacts":
                artifacts["total_count"] += 1
            if mode == "bool_artifact":
                artifacts["artifacts"][0]["id"] = True
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                admission.identity(run, jobs, artifacts, SHA)

    def test_optional_default_selection_never_borrows_an_ancestor(self):
        """Omitting the new input preserves supported dispatch without unsafe fallback."""
        run, jobs, artifacts = fixture()
        answers = [{"workflow_runs": [run], "total_count": 1}, jobs, artifacts]
        with patch.object(admission, "api", side_effect=answers) as api:
            self.assertEqual(admission.select("", SHA)["run_id"], "123")
        self.assertIn("head_sha=" + SHA, api.call_args_list[0].args[0])
        old = {**run, "head_sha": "b" * 40}
        with patch.object(admission, "api", return_value={"workflow_runs": [old], "total_count": 1}) as api:
            with self.assertRaises(ValueError):
                admission.select("", SHA)
        api.assert_called_once()

    def test_restore_uses_original_run_with_unchanged_checkout_and_refuses_drift(self):
        """Hash verification runs under original source/run identity, never rebuilding."""
        (ROOT / ".temp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder:
            state = Path(folder) / "state.json"
            value = {**admission.identity(*fixture(), SHA), "checkout_sha": SHA, "orchestration_run_id": "456"}
            state.write_text(json.dumps(value))
            environment = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main",
                           "GITHUB_SHA": SHA, "GITHUB_RUN_ID": "456", "GITHUB_RUN_ATTEMPT": "1"}
            with patch.object(admission, "STATE", state), patch.dict(os.environ, environment, clear=True), patch.object(admission.subprocess, "run") as call:
                admission.restore()
                self.assertEqual(call.call_args.kwargs["env"]["GITHUB_RUN_ID"], "123")
                self.assertEqual(call.call_args.kwargs["env"]["GITHUB_SHA"], SHA)
                self.assertEqual(call.call_args.args[0][-1], "restore")
                call.reset_mock()
                state.write_text(json.dumps({**value, "source_sha": "b" * 40}))
                with self.assertRaises(ValueError):
                    admission.restore()
                call.assert_not_called()

    def test_standalone_workflow_identity_locks_and_route_guards_remain(self):
        """Exact artifact admission precedes all provider operations; users keep the lane."""
        source = (ROOT / ".github/workflows/deploy-identity-test-inbox.yml").read_text()
        block = job_block(source, "deploy")
        self.assertIn("name: Deploy staging Identity test inbox", source)
        self.assertIn("required: false", source)
        self.assertIn("group: staging-native-mail-acceptance", source.split("jobs:", 1)[0])
        self.assertIn("cancel-in-progress: false", source)
        self.assertIn("if: github.ref == 'refs/heads/main'", block)
        self.assertIn("environment: staging", block)
        self.assertNotIn("rustup update stable", source)
        self.assertNotIn("worker-build --release", source)
        self.assertNotIn("cargo install worker-build", source)
        self.assertNotIn("validated_worker_build", source)
        self.assertIn("artifact-ids: ${{ steps.source.outputs.artifact_id }}", block)
        self.assertIn("run-id: ${{ steps.source.outputs.run_id }}", block)
        self.assertEqual(block.count("ensure_route.py --all-absent"), 2)
        self.assertIn("check_config.py --live --deployed", block)
        self.assertLess(block.index("inbox_worker_artifact.py restore"), block.index("ensure_route.py"))
        self.assertLess(block.index("inbox_worker_artifact.py restore"), block.index("wrangler deploy"))


if __name__ == "__main__":
    unittest.main()
