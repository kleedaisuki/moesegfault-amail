"""Affected check selection must preserve runtime coverage without repeating accepted work."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
import changes


class ChangesTests(unittest.TestCase):
    def test_delivery_and_browser_changes_do_not_rebuild_green_runtime(self) -> None:
        plan = changes.classify(["infra/ci/changes.py", ".github/workflows/ci.yml",
                                 "site/scripts/browser-acceptance.mjs"], event="push")
        self.assertFalse(plan.cli or plan.worker or plan.site or plan.full_infra)
        self.assertIn("infra.tests.test_ci_changes", plan.tests)

    def test_runtime_changes_select_affected_component(self) -> None:
        cli = changes.classify(["crates/amail/src/main.rs"], event="push")
        self.assertTrue(cli.cli)
        self.assertFalse(cli.worker)
        worker = changes.classify(["crates/mail-worker/migrations/0018_semantic_consent.sql"], event="pull_request")
        self.assertTrue(worker.worker)
        self.assertFalse(worker.cli)
        shared = changes.classify(["Cargo.lock"], event="push")
        self.assertTrue(shared.cli and shared.worker)

    def test_named_test_delta_is_focused_not_discovery(self) -> None:
        plan = changes.classify(["infra/tests/test_ci_changes.py"], event="push")
        self.assertEqual(plan.tests, ("infra.tests.test_ci_changes",))
        self.assertFalse(plan.full_infra)

    def test_new_manual_lanes_reuse_evidence_but_historical_checks_remain(self) -> None:
        for target in ("staging-semantic-inspect", "staging-semantic-recovery", "staging-semantic-e2e"):
            self.assertEqual(changes.classify([], event="workflow_dispatch", target=target), changes.Plan())
        production = changes.classify([], event="workflow_dispatch", target="production", confirm="RUN_PRODUCTION_V031")
        self.assertEqual(production, changes.Plan())
        self.assertTrue(changes.classify([], event="workflow_dispatch", target="staging").full_infra)
        repair = changes.classify([], event="workflow_dispatch", target="staging-maintenance-repair")
        self.assertTrue(repair.worker and repair.infra)
        self.assertFalse(repair.cli or repair.site)

    def test_synchronize_uses_previous_head(self) -> None:
        with patch.object(changes, "git", return_value="infra/ci/changes.py") as git:
            changes.delta({"before": "a" * 40, "pull_request": {"base": {"sha": "b" * 40}}},
                          "pull_request", "c" * 40)
        git.assert_called_once_with("diff", "--name-only", "a" * 40, "c" * 40)


if __name__ == "__main__":
    unittest.main()
