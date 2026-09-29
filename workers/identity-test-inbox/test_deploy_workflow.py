"""Check both staging inbox deploy paths preserve the all-alias interlock."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class DeployWorkflowTests(unittest.TestCase):
    """Keep the source-only and deployed-state gates in both workflows."""

    def test_private_inbox_jobs_audit_all_aliases_and_deployed_binding(self) -> None:
        """An open B route must block replacement, not just an open A route."""

        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        start = ci.index("  staging-identity-test-inbox:")
        end = ci.index("\n  staging-role-monitor:", start)
        jobs = [
            ci[start:end],
            (ROOT / ".github/workflows/deploy-identity-test-inbox.yml").read_text(encoding="utf-8"),
        ]
        for job in jobs:
            with self.subTest(job=job[:40]):
                self.assertEqual(job.count("ensure_route.py --all-absent"), 2)
                self.assertEqual(job.count("check_config.py --live --deployed"), 1)
                deploy = job.index("run: wrangler deploy")
                self.assertLess(job.index("ensure_route.py --all-absent"), deploy)
                self.assertGreater(job.rindex("ensure_route.py --all-absent"), deploy)
                self.assertGreater(job.index("check_config.py --live --deployed"), deploy)


if __name__ == "__main__":
    unittest.main()
