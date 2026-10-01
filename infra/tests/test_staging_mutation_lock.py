"""Shared same-repository staging resource exclusion; hosted source tests only."""

from pathlib import Path
import re
import unittest

from workflow_source import job_block


ROOT = Path(__file__).resolve().parents[2]
LOCK = "staging-native-mail-acceptance"


class StagingMutationLockTests(unittest.TestCase):
    """A quota campaign cannot overlap the repository's pinned service changes."""

    def assert_job_lock(self, block: str) -> None:
        """Require one resource lock and prohibit cancellation of a running writer."""
        self.assertEqual(block.count('    concurrency:\n'), 1)
        self.assertIn(f'      group: {LOCK}\n', block)
        self.assertIn('      cancel-in-progress: false\n', block)
        self.assertNotIn('cancel-in-progress: true', block)

    def test_ci_staging_mutators_share_quota_resource_lock(self) -> None:
        """Use job-level locking so dependent sink/API jobs cannot own the same lock."""
        source = (ROOT/'.github/workflows/ci.yml').read_text(encoding='utf-8')
        self.assertNotIn(f'group: {LOCK}', source.split('\njobs:\n', 1)[0])
        for name in ('staging-containment-settings', 'staging-current-worker-capture-off',
                     'staging-worker', 'staging-trace-sink', 'staging-ingress',
                     'staging-events', 'staging-identity-test-inbox'):
            with self.subTest(job=name):
                self.assert_job_lock(job_block(source, name))

    def test_quota_acceptance_and_exact_recovery_hold_same_resource_lock(self) -> None:
        """Both modes are one protected job, not separately interleavable phases."""
        source = (ROOT/'.github/workflows/staging-ten-address-acceptance.yml').read_text(encoding='utf-8')
        self.assertNotIn(f'group: {LOCK}', source.split('\njobs:\n', 1)[0])
        block = job_block(source, 'quota')
        self.assert_job_lock(block)
        self.assertIn("inputs.mode == 'accept'", block)
        self.assertIn("inputs.mode == 'recover'", block)

    def test_ci_mutation_dependencies_avoid_pending_sibling_replacement(self) -> None:
        """The default single-pending queue is not a multiple-writer workflow scheduler."""
        source = (ROOT/'.github/workflows/ci.yml').read_text(encoding='utf-8')
        for name, predecessor in (("staging-worker", "staging-trace-sink"),
                                  ("staging-ingress", "staging-worker"),
                                  ("staging-events", "staging-ingress"),
                                  ("staging-identity-test-inbox", "staging-events")):
            with self.subTest(job=name):
                match = re.search(r"^    needs: \[(.*?)\]$", job_block(source, name), re.MULTILINE)
                self.assertIsNotNone(match)
                self.assertIn(predecessor, match[1].split(", "))

    def test_standalone_inbox_deploy_uses_workflow_lock_without_reentrant_job_lock(self) -> None:
        """The manual main-branch inbox deployment must not bypass quota exclusion."""
        source = (ROOT/'.github/workflows/deploy-identity-test-inbox.yml').read_text(encoding='utf-8')
        header = source.split('\njobs:\n', 1)[0]
        self.assertIn(f'  group: {LOCK}\n', header)
        self.assertIn('  cancel-in-progress: false\n', header)
        self.assertNotIn('    concurrency:', job_block(source, 'deploy'))


if __name__ == '__main__':
    unittest.main()
