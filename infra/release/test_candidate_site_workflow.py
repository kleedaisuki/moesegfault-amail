"""Static workflow-scope regressions run only in hosted site CI.

These checks supplement source review; they do not parse arbitrary YAML or
prove provider permissions or default-branch registration.
"""

from pathlib import Path
import unittest

import check_candidate_site_gate as gate


ROOT = Path(__file__).resolve().parents[2]


class CandidateWorkflowTests(unittest.TestCase):
    """Keep source evidence site-only and mutation dispatch explicitly guarded."""

    def test_site_source_identity_and_no_mutation(self):
        """Hosted source job name matches the gate and receives no deploy secrets."""
        workflow = (ROOT / ".github/workflows" / gate.SOURCE_WORKFLOW).read_text(encoding="utf-8")
        self.assertIn(f"name: {gate.SOURCE_JOB}", workflow)
        for branch in gate.SOURCE_BRANCHES:
            self.assertIn(branch, workflow)
        for command in (
            "python -m unittest discover -s infra/release",
            "node --test scripts/check-release-state.test.mjs",
            "pnpm check:release-state candidate",
            "candidate_site.py prepare",
            "pnpm check:release-state published",
            "cmp public/_headers dist/_headers",
        ):
            self.assertIn(command, workflow)
        for prohibited in ("secrets.", "pnpm run deploy", "wrangler deploy", "crates/", "workers/", "ci.yml@"):
            self.assertNotIn(prohibited, workflow)

    def test_manual_mutation_boundary(self):
        """Deployment stays main-only, checked twice, and never cancels site writers."""
        workflow = (ROOT / ".github/workflows/site-candidate.yml").read_text(encoding="utf-8")
        self.assertIn("uses: ./.github/workflows/site-ci.yml", workflow)
        self.assertIn("github.event_name == 'workflow_dispatch'", workflow)
        self.assertIn("inputs.target == 'deploy-candidate'", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("default: checks", workflow)
        self.assertIn("DEPLOY_REVIEWED_PRODUCTION_CANDIDATE", workflow)
        self.assertIn("needs: source", workflow)
        self.assertIn("group: deploy-site-production", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertEqual(workflow.count("python infra/release/check_candidate_site_gate.py"), 2)
        self.assertIn("candidate_site.py smoke", workflow)
        for prohibited in ("  push:", "  pull_request:", "secrets: inherit", "AMAIL_RELEASE_STATE: published", "crates/", "workers/"):
            self.assertNotIn(prohibited, workflow)


if __name__ == "__main__":
    unittest.main()
