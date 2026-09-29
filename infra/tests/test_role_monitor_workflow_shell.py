"""Catch malformed Bash in the staging role-monitor post-deploy safety gate."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml"
STEP = "      - name: Confirm deploy did not open the synthetic SMTP route"


def final_route_script(source: str) -> str:
    """Extract only the exact role-monitor post-deploy block from GitHub YAML."""

    lines = source.splitlines()
    starts = [index for index, line in enumerate(lines) if line == STEP]
    if len(starts) != 1:
        raise ValueError("role post-deploy gate is missing or duplicated")
    start = starts[0]
    if lines[start + 1 : start + 3] != ["        shell: bash", "        run: |"]:
        raise ValueError("role post-deploy gate is not a Bash block")
    body: list[str] = []
    for line in lines[start + 3 :]:
        if line and not line.startswith("          "):
            break
        body.append(line[10:] if line else "")
    if not body or "staging_route.py" not in "\n".join(body):
        raise ValueError("role post-deploy gate body is missing")
    return "\n".join(body) + "\n"


class RoleMonitorWorkflowShellTests(unittest.TestCase):
    """Validate the exact shell command before provider deployment is attempted."""

    def test_post_deploy_gate_is_parseable_bash(self) -> None:
        """The original missing `fi` fails Bash parsing before any route audit runs."""

        script = final_route_script(WORKFLOW.read_text(encoding="utf-8"))
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("Bash syntax check requires the hosted Linux runner")
        result = subprocess.run([bash, "-n"], input=script, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, "role post-deploy Bash has invalid syntax")

    def test_missing_fi_regression_fixture_is_rejected(self) -> None:
        """Prove the syntax check distinguishes the known failure from a fixed gate."""

        bash = shutil.which("bash")
        if not bash:
            self.skipTest("Bash syntax check requires the hosted Linux runner")
        broken = "if [ \"$state\" != absent ]; then\n  exit 1\n"
        result = subprocess.run([bash, "-n"], input=broken, capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
