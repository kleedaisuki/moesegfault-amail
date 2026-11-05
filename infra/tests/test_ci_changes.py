"""Affected check selection must preserve runtime coverage without repeating accepted work."""
from __future__ import annotations

from pathlib import Path
import json
import os
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
        self.assertFalse(plan.cli or plan.worker or plan.site)
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

    def test_worker_selection_preserves_only_affected_roles_and_journeys(self) -> None:
        cases = (
            ("workers/role-monitor/src/lib.rs", ("workers/role-monitor",)),
            ("workers/identity-test-inbox/src/lib.rs", ("workers/identity-test-inbox",)),
            ("crates/mail-worker/migrations/0019_incremental_embeddings.sql", ("crates/mail-worker",)),
            ("infra/tests/worker-boundary/semantic-consent.test.mjs", ("crates/mail-worker",)),
            ("workers/mail-events/src/lib.rs", tuple(project for project in changes.WORKER_PROJECTS
                                                      if project in changes.QUEUE_PROJECTS)),
            ("Cargo.lock", changes.WORKER_PROJECTS),
        )
        for path, projects in cases:
            with self.subTest(path=path):
                plan = changes.classify([path], event="pull_request")
                self.assertEqual(plan.worker_projects, projects)
        self.assertFalse(changes.boundary_tests(("workers/role-monitor",)))
        self.assertIn("semantic-consent.test.mjs", changes.boundary_tests(("crates/mail-worker",)))
        self.assertEqual(changes.boundary_tests(tuple(changes.QUEUE_PROJECTS)), ("trace-sink.test.mjs",))
        schema = changes.classify(["crates/trace-schema/src/lib.rs"], event="pull_request")
        self.assertEqual(set(schema.worker_projects), {
            "crates/mail-worker", "workers/role-monitor", *changes.QUEUE_PROJECTS})
        full = changes.classify([], event="workflow_dispatch", target="staging")
        self.assertEqual(full.worker_projects, changes.WORKER_PROJECTS)

    def test_native_reuse_preserves_independent_site_and_worker_test_changes(self) -> None:
        event = ROOT / ".temp/test-selection-event.json"
        output = ROOT / ".temp/test-selection-output.txt"
        (ROOT / ".temp").mkdir(exist_ok=True)
        event.write_text("{}", encoding="utf-8")
        output.write_text("", encoding="utf-8")
        self.addCleanup(event.unlink)
        self.addCleanup(output.unlink)
        environment = {"GITHUB_EVENT_PATH": str(event), "GITHUB_OUTPUT": str(output),
                       "GITHUB_EVENT_NAME": "pull_request", "GITHUB_SHA": "a" * 40}
        with patch.dict(os.environ, environment), patch.object(sys, "argv", ["changes.py", "plan"]), \
             patch.object(changes, "native_scope", return_value=True), \
             patch.object(changes, "delta", return_value=["site/src/pages/index.astro",
                 "infra/tests/worker-boundary/semantic-consent.test.mjs"]):
            changes.main()
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        self.assertEqual(values["cli"], "false")
        self.assertEqual(values["site"], "true")
        self.assertEqual(values["worker"], "true")
        self.assertEqual(json.loads(values["worker_projects"]), ["crates/mail-worker"])

    def test_named_test_delta_is_focused_not_discovery(self) -> None:
        plan = changes.classify(["infra/tests/test_ci_changes.py"], event="push")
        self.assertEqual(plan.tests, ("infra.tests.test_ci_changes",))

    def test_new_manual_lanes_reuse_evidence_but_historical_checks_remain(self) -> None:
        for target in ("staging-semantic-inspect", "staging-semantic-recovery", "staging-semantic-e2e"):
            self.assertEqual(changes.classify([], event="workflow_dispatch", target=target), changes.Plan())
        production = changes.classify([], event="workflow_dispatch", target="production", confirm="RUN_PRODUCTION_V031")
        self.assertEqual(production, changes.Plan())
        self.assertTrue(changes.classify([], event="workflow_dispatch", target="staging").infra)
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
