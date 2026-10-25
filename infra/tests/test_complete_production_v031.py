"""Only the named final-readiness failure permits read-only production completion."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import complete_production_v031 as completion


class CompletionTests(unittest.TestCase):
    def rows(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for index, role in enumerate(("sink", "api", "maintenance_pause", "migration", "maintenance")):
            for state in ("intent", "observed" if role == "migration" else "version_captured"):
                row: dict[str, Any] = {"schema": "production-upgrade-partial/v1", "source_sha": completion.ORIGIN_SOURCE,
                                       "run_id": completion.ORIGIN_RUN, "run_attempt": 1, "phase": role, "state": state}
                if state == "version_captured":
                    row["version"] = f"12345678-1234-1234-1234-{index:012d}"
                result.append(row)
        return result

    def encode(self, rows: list[dict[str, Any]]) -> str:
        return "\n".join(json.dumps(row) for row in rows)

    def test_exact_original_flow_retains_all_captured_versions_without_repeating_wait(self) -> None:
        value = completion.journal(self.encode(self.rows()))
        self.assertEqual(set(value), {"sink", "api", "maintenance_pause", "maintenance"})
        self.assertNotEqual(value["maintenance_pause"], value["maintenance"])

    def test_missing_duplicate_reordered_ambiguous_or_foreign_original_phase_is_rejected(self) -> None:
        original = self.rows()
        reordered = self.rows()
        reordered[6], reordered[8] = reordered[8], reordered[6]
        ambiguous = self.rows()
        ambiguous[3]["state"] = "ambiguous_version_captured"
        foreign = self.rows()
        foreign[7]["source_sha"] = "f" * 40
        for rows in (original[:-1], original + original[:1], reordered, ambiguous, foreign):
            with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, "journal_unverified"):
                completion.journal(self.encode(rows))

    def test_only_final_health_type_failure_can_be_completed(self) -> None:
        line = "production_v031=UNVERIFIED reason=production_v031_health_unverified class=ValueError"
        completion.closed_failure(line)
        for log in ("", line + "\n" + line, line.replace("health", "schema"), line.replace("ValueError", "TypeError")):
            with self.subTest(log=log), self.assertRaisesRegex(ValueError, "failure_unverified"):
                completion.closed_failure(log)

    def test_origin_requires_completed_failed_first_attempt_at_exact_immutable_source(self) -> None:
        value = {"id": int(completion.ORIGIN_RUN), "head_sha": completion.ORIGIN_SOURCE, "head_branch": "main",
                 "repository": {"full_name": completion.accepted.REPO}, "path": ".github/workflows/ci.yml",
                 "event": "workflow_dispatch", "status": "completed", "conclusion": "failure", "run_attempt": 1}
        completion.run_identity(value, completion.ORIGIN_RUN, "failure")
        for key, item in (("status", "in_progress"), ("conclusion", "cancelled"), ("run_attempt", 2), ("head_sha", "f" * 40)):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "origin_unverified"):
                completion.run_identity({**value, key: item}, completion.ORIGIN_RUN, "failure")

    def test_no_other_failed_job_or_step_is_reinterpreted_as_success(self) -> None:
        writer = {"id": 1, "name": completion.WRITER, "status": "completed", "conclusion": "failure",
                  "steps": [{"name": completion.WRITE_STEP, "conclusion": "failure"}]}
        self.assertEqual(completion.writer_identity([writer]), 1)
        for jobs in ([writer, {**writer, "id": 2}], [{**writer, "steps": [{"name": "Artifact restore", "conclusion": "failure"}]}]):
            with self.subTest(jobs=jobs), self.assertRaisesRegex(ValueError, "failure_unverified"):
                completion.writer_identity(jobs)

    def test_completion_context_is_read_only_trusted_main_named_original_and_freeze(self) -> None:
        environment = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": completion.accepted.REPO,
                       "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
                       "GITHUB_RUN_ATTEMPT": "1", "AMAIL_PRODUCTION_ENVIRONMENT": "production",
                       "AMAIL_PRODUCTION_CONFIRM": "COMPLETE_PRODUCTION_V031",
                       "AMAIL_PRODUCTION_GRAPH_FREEZE": "FREEZE_PRODUCTION_GRAPH_WRITERS",
                       "AMAIL_PRODUCTION_COMPLETION_RUN": completion.ORIGIN_RUN,
                       "GITHUB_SHA": "b" * 40, "GITHUB_RUN_ID": "123"}
        with patch.dict(os.environ, environment, clear=True), patch.object(completion.accepted, "runtime_closure"):
            completion.context()
            os.environ["AMAIL_PRODUCTION_CONFIRM"] = "RUN_PRODUCTION_V031"
            with self.assertRaisesRegex(ValueError, "context_unverified"):
                completion.context()

    def test_workflow_completion_has_no_deployment_migration_or_repeated_runtime_suite(self) -> None:
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = source.split("  production-v031-complete:\n", 1)[1].split("  production-v031-promotion-checks:\n", 1)[0]
        self.assertIn("COMPLETE_PRODUCTION_V031", job)
        self.assertIn("environment: production", job)
        self.assertIn("actions: read", job)
        self.assertNotIn("wrangler", job)
        self.assertNotIn("cargo ", job)
        self.assertIn("complete_production_v031.py complete", job)


if __name__ == "__main__":
    unittest.main()
