"""Guard the distinct manual current-Worker operation without provider access."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml"
TARGET = "staging-current-worker-capture-off"


def job_block(source: str, target: str) -> str:
    """Extract one top-level job; reject missing or duplicated safety targets."""
    pattern = rf"^  {re.escape(target)}:\n(.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)"
    matches = re.findall(pattern, source, re.MULTILINE | re.DOTALL)
    if len(matches) != 1:
        raise ValueError("workflow safety job missing or duplicated")
    return matches[0]


def guard_script(block: str) -> str:
    """Extract the confirmation Bash body, never the credential-bearing command."""
    before_tests = block.split("      - name: Test synthetic", 1)[0]
    script = before_tests.split("        run: |\n", 1)[1]
    return "\n".join(line[10:] for line in script.splitlines()) + "\n"


class CurrentWorkerWorkflowTests(unittest.TestCase):
    """Prevent automatic mutation, credential-first execution or shared retry drift."""

    def setUp(self) -> None:
        """Read only the source workflow; no credentials or network are needed."""
        self.source = WORKFLOW.read_text(encoding="utf-8")
        self.block = job_block(self.source, TARGET)

    def test_manual_branch_environment_and_service_lock(self) -> None:
        """The operation shares Mail serialization and cannot run on push or PR."""
        for requirement in (
            "github.event_name == 'workflow_dispatch' &&",
            f"inputs.target == '{TARGET}' &&",
            "github.ref == 'refs/heads/codex/amail-v0.1.0'",
            "    environment: staging\n", "      group: deploy-mail-staging\n",
            "      cancel-in-progress: false\n", "    timeout-minutes: 5\n",
        ):
            self.assertIn(requirement, self.block)
        self.assertNotIn("always()", self.block)
        self.assertNotIn("continue-on-error", self.block)

    def test_exact_source_tests_precede_only_credential_step(self) -> None:
        """The helper and workflow contracts run before project secrets are exposed."""
        secret_index = self.block.index("${{ secrets.")
        for filename in ("test_staging_current_worker_capture_off.py",
                         "test_current_worker_capture_off_workflow.py",
                         "test_check_observability.py"):
            self.assertLess(self.block.index(filename), secret_index)
        self.assertEqual(self.block.count("${{ secrets."), 2)
        self.assertEqual(self.block.count("run: python infra/deploy/apply_staging_current_worker_capture_off.py"), 1)
        for mapping in (
            "AMAIL_EXPECTED_WORKER_VERSION: ${{ inputs.expected_worker_version }}",
            "AMAIL_CURRENT_WORKER_CONFIRM: ${{ inputs.confirm }}",
            "AMAIL_CURRENT_WORKER_FREEZE: ${{ inputs.mail_deploy_freeze }}",
        ):
            self.assertIn(mapping, self.block)
        self.assertNotIn("wrangler", self.block)
        self.assertNotIn("apply_staging_capture_off.py", self.block)

    def test_dispatch_inputs_reused_and_legacy_target_unchanged(self) -> None:
        """One dedicated Mail freeze input stays below the platform cap; v1 remains."""
        header = self.source.split("\njobs:", 1)[0]
        dispatch = header.split("  workflow_dispatch:\n", 1)[1]
        inputs = re.findall(r"^      ([a-zA-Z0-9_]+):$", dispatch, re.MULTILINE)
        self.assertEqual(len(inputs), 24)
        for name in ("target", "confirm", "expected_worker_version", "mail_deploy_freeze"):
            self.assertIn(name, inputs)
        legacy = job_block(self.source, "staging-containment-settings")
        self.assertIn("APPLY_STAGING_API_CAPTURE_OFF_SETTINGS", legacy)
        self.assertIn("run: python infra/deploy/apply_staging_capture_off.py", legacy)
        self.assertNotIn("AMAIL_CURRENT_WORKER_", legacy)

    def test_confirmation_gate_rejects_every_wrong_input_and_retry(self) -> None:
        """Hosted Bash exercises the real non-mutating guard, not a mock predicate."""
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("Guard execution requires hosted Linux Bash")
        script = guard_script(self.block)
        approved = {
            "CURRENT_WORKER_CONFIRM": "APPLY_STAGING_CURRENT_WORKER_CAPTURE_OFF",
            "EXPECTED_VERSION": "c3f6401a-1e84-4f51-91df-ae77d90683e9",
            "DEPLOY_FREEZE": "FREEZE_STAGING_MAIL_DEPLOYS",
            "GITHUB_RUN_ATTEMPT": "1",
        }
        def run(values: dict[str, str]) -> int:
            """Run only the extracted input guard, with no Cloudflare environment."""
            return subprocess.run([bash], input=script, text=True, capture_output=True,
                                  env={**os.environ, **values}, check=False).returncode
        self.assertEqual(run(approved), 0)
        for key in approved:
            for wrong in ("", "WRONG", "2"):
                with self.subTest(key=key, value=wrong):
                    self.assertNotEqual(run({**approved, key: wrong}), 0)


if __name__ == "__main__":
    unittest.main()
