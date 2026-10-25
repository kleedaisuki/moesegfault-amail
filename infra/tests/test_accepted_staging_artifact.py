"""Incremental promotion admission, without builds, providers or repeated runtime tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
import accepted_staging_artifact as promotion


class AcceptedStagingArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        (ROOT / ".temp").mkdir(exist_ok=True)
        self.sha, self.current = "a" * 40, "b" * 40
        self.source = {"source_sha": self.sha, "run_id": "123", "run_attempt": 1,
                       "artifact_id": 10, "cli_artifact_id": 11}

    def metadata(self, suffix: str) -> dict[str, Any]:
        if suffix == "runs/123":
            return {"id": 123, "head_sha": self.sha, "head_branch": promotion.BRANCH,
                    "repository": {"full_name": promotion.REPO}, "status": "completed",
                    "conclusion": "failure", "run_attempt": 1, "event": "workflow_dispatch",
                    "path": ".github/workflows/ci.yml"}
        if suffix.endswith("/jobs?per_page=100"):
            jobs = [{"name": name, "status": "completed", "conclusion": "success"} for name in promotion.REQUIRED]
            return {"total_count": len(jobs), "jobs": jobs}
        artifacts = [{"id": 10, "name": f"worker-native-modules-{self.sha}", "expired": False,
                      "workflow_run": {"head_sha": self.sha}},
                     {"id": 11, "name": "cli-candidate-v0.3.1-123", "expired": False,
                      "workflow_run": {"head_sha": self.sha}}]
        return {"total_count": 2, "artifacts": artifacts}

    def test_failed_writer_is_not_repeated_and_does_not_discard_green_source_gates(self) -> None:
        with patch.object(promotion, "github", side_effect=self.metadata):
            self.assertEqual(promotion.producer("123"), self.source)

    def test_one_failed_required_source_gate_blocks_reuse(self) -> None:
        def metadata(suffix: str) -> dict[str, Any]:
            value = self.metadata(suffix)
            if "jobs" in value:
                value["jobs"][0]["conclusion"] = "failure"
            return value
        with patch.object(promotion, "github", side_effect=metadata), self.assertRaisesRegex(ValueError, "required_gate_failed"):
            promotion.producer("123")

    def test_expired_or_foreign_artifact_is_never_adopted(self) -> None:
        for field, value in (("expired", True), ("workflow_run", {"head_sha": "c" * 40})):
            def metadata(suffix: str) -> dict[str, Any]:
                result = self.metadata(suffix)
                if "artifacts" in result:
                    result["artifacts"][0][field] = value
                return result
            with self.subTest(field=field), patch.object(promotion, "github", side_effect=metadata), \
                 self.assertRaisesRegex(ValueError, "artifact_unverified"):
                promotion.producer("123")

    def test_runtime_change_or_missing_ancestry_blocks_reuse(self) -> None:
        for failure in range(4):
            results = [subprocess.CompletedProcess([], int(index == failure), self.current, "") for index in range(4)]
            if failure == 3:
                results[3] = subprocess.CompletedProcess([], 0, self.sha, "")
            with self.subTest(failure=failure), patch.object(promotion, "git", side_effect=results), \
                 self.assertRaisesRegex(ValueError, "runtime_changed"):
                promotion.runtime_closure(self.sha, self.current)

    def test_staging_acceptance_requires_actual_success_not_only_source_success(self) -> None:
        with patch.object(promotion, "run_metadata", return_value={"conclusion": "failure"}), \
             self.assertRaisesRegex(ValueError, "journey_required"):
            promotion.acceptance("456", self.source, self.current)

    def test_successful_journey_keeps_distinct_producer_and_acceptance_coordinates(self) -> None:
        with patch.object(promotion, "run_metadata", return_value={"conclusion": "success", "head_sha": "c" * 40}), \
             patch.object(promotion, "successful_jobs") as jobs, patch.object(promotion, "runtime_closure"), \
             patch.object(promotion, "git", return_value=subprocess.CompletedProcess([], 0, "", "")), \
             patch.object(promotion, "unique_artifact", return_value=12):
            value = promotion.acceptance("456", self.source, self.current)
        self.assertEqual(value, {"run_id": "456", "source_sha": "c" * 40, "artifact_id": 12})
        jobs.assert_called_once_with("456", frozenset({promotion.ACCEPTANCE_JOB}))

    def test_receipt_must_bind_exact_source_and_three_deployed_runtime_pins(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder:
            path = Path(folder) / "receipt.json"
            state = {"producer": self.source, "acceptance": {"run_id": "456", "source_sha": self.current, "artifact_id": 12}}
            value = {"schema": "staging-semantic-acceptance/v1", "source_run_id": "123", "source_sha": self.sha,
                     "run_id": "456", "checkout_sha": self.current,
                     **{key: "12345678-1234-1234-1234-123456789abc" for key in ("api_version", "maintenance_version", "sink_version")}}
            path.write_text(json.dumps(value), encoding="utf-8")
            with patch.object(promotion, "ACCEPTANCE", path):
                self.assertEqual(promotion.verify_acceptance_receipt(state), value)
                value["source_run_id"] = "999"
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "receipt_invalid"):
                    promotion.verify_acceptance_receipt(state)

    def test_restore_uses_original_identity_without_rewriting_manifest_or_host_identity(self) -> None:
        state = {"producer": self.source}
        with patch.object(promotion, "read_state", return_value=state), \
             patch.object(promotion, "verify_installed") as verify, \
             patch.object(promotion.subprocess, "run") as run, \
             patch.dict(os.environ, {"GITHUB_SHA": self.current, "GITHUB_RUN_ID": "789"}):
            promotion.restore()
            env = run.call_args.kwargs["env"]
            self.assertEqual((env["GITHUB_SHA"], env["GITHUB_RUN_ID"]), (self.sha, "123"))
            self.assertEqual(os.environ["GITHUB_SHA"], self.current)
            self.assertEqual(os.environ["GITHUB_RUN_ID"], "789")
            verify.assert_called_once_with()

    def test_production_requires_protected_main_and_explicit_freeze(self) -> None:
        identity = {"source_sha": self.current, "run_id": "789", "run_attempt": 1}
        environment = {"GITHUB_REPOSITORY": promotion.REPO, "GITHUB_EVENT_NAME": "workflow_dispatch",
                       "GITHUB_RUN_ATTEMPT": "1", "GITHUB_REF": "refs/heads/main",
                       "AMAIL_ACCEPTED_ARTIFACT_PURPOSE": "production", "AMAIL_PRODUCTION_ENVIRONMENT": "production",
                       "AMAIL_PRODUCTION_CONFIRM": "RUN_PRODUCTION_V031",
                       "AMAIL_PRODUCTION_GRAPH_FREEZE": "FREEZE_PRODUCTION_GRAPH_WRITERS"}
        with patch.object(promotion.artifact, "context", return_value=identity), patch.dict(os.environ, environment, clear=True):
            self.assertEqual(promotion.context("production"), identity)
            os.environ["AMAIL_PRODUCTION_GRAPH_FREEZE"] = ""
            with self.assertRaisesRegex(ValueError, "context_unverified"):
                promotion.context("production")

    def test_installed_bytes_keep_original_manifest_and_reject_post_restore_changes(self) -> None:
        identity = {"schema": "worker-native-artifact/v1", "source_sha": self.current,
                    "run_id": "789", "run_attempt": 1, "worker_build": "0.8.5", "rust": "1.98.1"}
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder:
            base = Path(folder)
            for tree in promotion.artifact.TREES:
                (base / tree / "worker").mkdir(parents=True)
                (base / tree / "index.js").write_text("export {};", encoding="utf-8")
                (base / tree / "worker/shim.mjs").write_text("export {};", encoding="utf-8")
            for name in promotion.artifact.ENTRY_FILES:
                (base / name).parent.mkdir(parents=True, exist_ok=True)
                (base / name).write_text("export {};", encoding="utf-8")
            hashes = promotion.artifact.files(base)
            bundle = base / "bundle"
            for name in hashes:
                (bundle / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(base / name, bundle / name)
            manifest = {**identity, "source_sha": self.sha, "run_id": "123", "files": hashes}
            path = bundle / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            original = path.read_bytes()
            state = {"producer": self.source, "orchestration": identity}
            with patch.object(promotion, "read_state", return_value=state), \
                 patch.object(promotion, "ROOT", base), patch.object(promotion.artifact, "FOLDER", bundle):
                promotion.verify_installed()
                self.assertEqual(path.read_bytes(), original)
                (base / promotion.artifact.TREES[0] / "index.js").write_text("changed", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "file_integrity_mismatch"):
                    promotion.verify_installed()

    def test_production_job_tests_only_new_adapter_and_restores_original_checked_bytes(self) -> None:
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        body = source.split("  production-v031:\n", 1)[1].split("  production-v030:\n", 1)[0]
        self.assertIn("needs: production-v031-promotion-checks", body)
        self.assertIn("actions: read", body)
        self.assertIn("inputs.staging_acceptance_run", body)
        self.assertIn("steps.source.outputs.artifact_id", body)
        self.assertNotIn("cargo ", body)
        self.assertLess(body.index("accepted_staging_artifact.py restore"), body.index("production_v031.py upgrade"))


if __name__ == "__main__":
    unittest.main()
