"""Check both staging inbox deploy paths preserve the all-alias interlock."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/tests"))
from workflow_source import job_block


class DeployWorkflowTests(unittest.TestCase):
    """Keep the source-only and deployed-state gates in both workflows."""

    def assert_inbox_contract(self, job: str) -> None:
        """Check all-alias interlocks and deployed bindings in only the target job."""
        self.assertEqual(job.count("ensure_route.py --all-absent"), 2)
        self.assertEqual(job.count("check_config.py --live --deployed"), 1)
        deploy = job.index("run: wrangler deploy")
        self.assertLess(job.index("ensure_route.py --all-absent"), deploy)
        self.assertGreater(job.rindex("ensure_route.py --all-absent"), deploy)
        self.assertGreater(job.index("check_config.py --live --deployed"), deploy)

    def test_private_inbox_jobs_audit_all_aliases_and_deployed_binding(self) -> None:
        """An open B route must block replacement, not just an open A route."""

        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        standalone = (ROOT / ".github/workflows/deploy-identity-test-inbox.yml").read_text(encoding="utf-8")
        jobs = [
            job_block(ci, "staging-identity-test-inbox"),
            job_block(standalone, "deploy"),
        ]
        for job in jobs:
            with self.subTest(job=job[:40]):
                self.assert_inbox_contract(job)

    def test_missing_role_successor_and_adjacent_job_do_not_change_inbox_contract(self) -> None:
        """Deleting the role deploy or inserting a neighbor cannot contaminate checks."""
        source = (
            "jobs:\n  staging-identity-test-inbox:\n    steps:\n"
            "      - run: python ensure_route.py --all-absent\n"
            "      - run: wrangler deploy\n"
            "      - run: python ensure_route.py --all-absent\n"
            "      - run: python check_config.py --live --deployed\n"
            "  unrelated_new:\n    env:\n      TOKEN: ${{ secrets.UNRELATED }}\n"
            "    steps:\n      - run: echo PRIVATE_NEIGHBOR\n"
            "  deploy-trace-sink:\n    steps:\n      - run: echo sink\n"
        )
        self.assertNotIn("  staging-role-monitor:", source)
        block = job_block(source, "staging-identity-test-inbox")
        self.assert_inbox_contract(block)
        self.assertNotIn("secrets.", block)
        self.assertNotIn("PRIVATE_NEIGHBOR", block)
        self.assertNotIn("echo sink", block)
        self.assertEqual(job_block(source.replace("\n", "\r\n"), "staging-identity-test-inbox"), block)

    def test_adjacent_job_cannot_supply_missing_postdeploy_interlock_or_binding(self) -> None:
        """A neighboring successful audit does not prove the inbox job audited B."""
        source = (
            "jobs:\n  staging-identity-test-inbox:\n    steps:\n"
            "      - run: python ensure_route.py --all-absent\n"
            "      - run: wrangler deploy\n"
            "  unrelated_new:\n    steps:\n"
            "      - run: python ensure_route.py --all-absent\n"
            "      - run: python check_config.py --live --deployed\n"
        )
        block = job_block(source, "staging-identity-test-inbox")
        self.assertNotIn("check_config.py --live --deployed", block)
        with self.assertRaises(AssertionError):
            self.assert_inbox_contract(block)


if __name__ == "__main__":
    unittest.main()
