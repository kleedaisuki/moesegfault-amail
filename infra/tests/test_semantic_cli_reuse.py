"""Only unchanged accepted CLI bytes feed the new semantic-only real journey."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
import accepted_staging_artifact as accepted
import staging_cli as staging


class SemanticReuseTests(unittest.TestCase):
    def environment(self, output: Path) -> dict[str, str]:
        return {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_REF": "refs/heads/codex/v0.3.1-semantic-consent",
                "GITHUB_RUN_ATTEMPT": "1", "AMAIL_SOURCE_RUN": staging.SEMANTIC_RUN,
                "AMAIL_STAGING_SEMANTIC_CONFIRM": "RUN_STAGING_SEMANTIC_V031",
                "GITHUB_SHA": "b" * 40, "GITHUB_OUTPUT": str(output)}

    def test_admission_preserves_producer_identity_separate_from_checkout(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder:
            output = Path(folder) / "output"
            current: dict[str, Any] = {"source_sha": "b" * 40, "run_id": "456", "run_attempt": 1,
                                       "version": "0.3.1", "rust": "1.98.1"}
            with patch.dict(os.environ, self.environment(output), clear=True), \
                 patch.object(accepted, "runtime_closure") as closure, \
                 patch.object(accepted, "producer", return_value={"source_sha": staging.SEMANTIC_SHA, "cli_artifact_id": 123}), \
                 patch.object(staging.candidate, "context", return_value=current), \
                 patch.object(staging, "ADMISSION", Path(folder) / "admission.json"):
                value = staging.admit_semantic(staging.SEMANTIC_RUN)
            closure.assert_called_once_with(staging.SEMANTIC_SHA, "b" * 40)
            self.assertEqual(value["identity"]["source_sha"], staging.SEMANTIC_SHA)
            self.assertEqual(value["identity"]["run_id"], staging.SEMANTIC_RUN)
            self.assertEqual(value["orchestration_sha"], "b" * 40)
            self.assertEqual(output.read_text(), "artifact_id=123\n")

    def test_changed_runtime_stops_before_artifact_selection(self) -> None:
        with patch.dict(os.environ, self.environment(ROOT / ".temp/unused-output"), clear=True), \
             patch.object(accepted, "runtime_closure", side_effect=ValueError("accepted_source_runtime_changed")), \
             patch.object(accepted, "producer") as producer:
            with self.assertRaisesRegex(ValueError, "accepted_source_runtime_changed"):
                staging.admit_semantic(staging.SEMANTIC_RUN)
            producer.assert_not_called()

    def test_ordinary_e2e_confirmation_cannot_select_reuse_path(self) -> None:
        environment = self.environment(ROOT / ".temp/unused-output")
        environment["AMAIL_STAGING_SEMANTIC_CONFIRM"] = "RUN_STAGING_E2E"
        with patch.dict(os.environ, environment, clear=True), patch.object(accepted, "producer") as producer:
            with self.assertRaisesRegex(ValueError, "candidate_semantic_context_unverified"):
                staging.admit_semantic(staging.SEMANTIC_RUN)
            producer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
