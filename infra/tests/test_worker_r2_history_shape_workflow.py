"""Guard the reduced historical schema lane without provider credentials."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

from test_current_worker_capture_off_workflow import job_block

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml"
TARGET = "staging-worker-r2-history-shape"
CONFIRM = "READ_WORKER_R2_HISTORY_BASELINE_SHAPE_36751791789"


def valid_dispatch_inputs(inputs: list[str]) -> bool:
    """Permit compatible input additions while enforcing platform and lane contracts."""
    return (len(inputs) <= 25 and len(inputs) == len(set(inputs))
            and {"target", "confirm"}.issubset(inputs))


class HistoryShapeWorkflowTests(unittest.TestCase):
    """Keep the one historical read isolated from mutation and workflow retries."""

    def setUp(self) -> None:
        """Load the checked-in workflow; tests perform no network operations."""
        self.source = WORKFLOW.read_text(encoding="utf-8")
        self.block = job_block(self.source, TARGET)

    def test_manual_branch_staging_read_only(self) -> None:
        """No automatic event, broader privilege or failure bypass is allowed."""
        for text in (
            "github.event_name == 'workflow_dispatch' &&",
            f"inputs.target == '{TARGET}' &&",
            "github.ref == 'refs/heads/codex/amail-v0.1.0'",
            "    environment: staging\n", "    timeout-minutes: 5\n",
            "      contents: read\n", "      actions: read\n",
        ):
            self.assertIn(text, self.block)
        for text in ("always()", "continue-on-error", "wrangler", "curl ",
                     "CF_EMAIL_ROUTING_TOKEN", "CLOUDFLARE_API_TOKEN",
                     "upload-artifact", "write\n"):
            self.assertNotIn(text, self.block)

    def test_tests_before_single_credential_step_and_fixed_run(self) -> None:
        """Synthetic contracts precede the sole provider/GitHub credential step."""
        credential_index = self.block.index("CF_OBSERVABILITY_TOKEN:")
        for filename in ("test_staging_worker_r2_delivery_history.py",
                         "test_staging_worker_r2_history_shape.py",
                         "test_worker_r2_history_shape_workflow.py"):
            self.assertLess(self.block.index(filename), credential_index)
        self.assertEqual(self.block.count("${{ secrets."), 1)
        self.assertEqual(self.block.count("${{ github.token }}"), 1)
        self.assertEqual(self.block.count("run: python infra/tests/staging_worker_r2_history_shape.py"), 1)
        self.assertIn('"$HISTORY_CONFIRM" 36751791789', self.block)
        self.assertNotIn("staging_worker_r2_delivery_history.py \"", self.block)

    def test_existing_inputs_and_legacy_target_preserved(self) -> None:
        """The distinct shape target reuses confirm without increasing input count."""
        header = self.source.split("\njobs:", 1)[0]
        dispatch = header.split("  workflow_dispatch:\n", 1)[1]
        inputs = re.findall(r"^      ([a-zA-Z0-9_]+):$", dispatch, re.MULTILINE)
        self.assertTrue(valid_dispatch_inputs(inputs))
        self.assertIn(TARGET, header)
        legacy = job_block(self.source, "staging-worker-r2-delivery-history")
        self.assertIn("READ_WORKER_R2_DELIVERY_HISTORY_36751791789", legacy)
        self.assertNotIn("staging_worker_r2_history_shape.py", legacy)

    def test_dispatch_input_boundaries_uniqueness_and_required_names(self) -> None:
        """Twenty-five distinct inputs are valid; overflow and missing contracts fail."""
        approved = ["target", "confirm"] + [f"optional_{index}" for index in range(23)]
        self.assertTrue(valid_dispatch_inputs(approved))
        self.assertTrue(valid_dispatch_inputs(["target", "confirm"]))
        for invalid in (approved + ["overflow"], ["target", "confirm", "confirm"],
                        ["target"], ["confirm"], []):
            with self.subTest(inputs=invalid):
                self.assertFalse(valid_dispatch_inputs(invalid))

    def test_bash_guard_rejects_wrong_confirmation_and_retry(self) -> None:
        """Run only the extracted input gate on hosted Linux, never the live helper."""
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("Guard execution requires hosted Linux Bash")
        prefix = self.block.split("      - uses: actions/setup-python", 1)[0]
        body = prefix.split("        run: |\n", 1)[1]
        script = "\n".join(line[10:] for line in body.splitlines()) + "\n"
        for confirmation, attempt, expected in ((CONFIRM, "1", 0),
                                               ("", "1", 1),
                                               ("WRONG", "1", 1),
                                               (CONFIRM, "2", 1),
                                               (CONFIRM, "", 1)):
            with self.subTest(confirmation=confirmation, attempt=attempt):
                result = subprocess.run(
                    [bash], input=script, text=True, capture_output=True, check=False,
                    env={**os.environ, "HISTORY_CONFIRM": confirmation,
                         "GITHUB_RUN_ATTEMPT": attempt})
                self.assertEqual(result.returncode, expected)


if __name__ == "__main__":
    unittest.main()
