"""Synthetic contracts for privacy-preserving sink deployment pin extraction."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parents[1] / "deploy"))
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("deploy_sink", Path(__file__).parents[1] / "deploy/deploy_trace_sink.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
VERSION = "11111111-1111-1111-1111-111111111111"


class DeploySinkTests(unittest.TestCase):
    """No ambiguous version output or deployment failure can produce a trusted pin."""

    def setUp(self):
        """Provider parser tests assume the separately tested byte verification passed."""
        patcher = patch.object(MODULE, "require_artifact")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_exact_pin_and_command(self):
        """Use a single exact generated UUID, preserving realm isolation."""
        response = subprocess.CompletedProcess([], 0, f"Current Version ID: {VERSION}\n", "")
        with patch.object(MODULE.subprocess, "run", return_value=response) as call:
            self.assertEqual(MODULE.deploy("staging"), VERSION)
            self.assertEqual(call.call_args.args[0], ["wrangler", "deploy", "--env", "staging"])

    def test_missing_duplicate_and_failure_denied(self):
        """Do not choose a first version or retry a possibly completed deployment."""
        for stdout, code in [("", 0), (f"Current Version ID: {VERSION}\n" * 2, 0), (f"Current Version ID: {VERSION}\n", 1)]:
            with self.subTest(code=code), patch.object(MODULE.subprocess, "run", return_value=subprocess.CompletedProcess([], code, stdout, "")) as call:
                with self.assertRaises(ValueError):
                    MODULE.deploy("production")
                self.assertEqual(call.call_count, 1)

    def test_artifact_failure_never_submits(self):
        """An unverified artifact cannot invoke Wrangler even once."""
        with patch.object(MODULE, "require_artifact", side_effect=ValueError("artifact_provenance_mismatch")), patch.object(MODULE.subprocess, "run") as call:
            with self.assertRaises(ValueError):
                MODULE.deploy("production")
        call.assert_not_called()

    def test_main_failure_preserves_recovery_pin_but_still_fails(self):
        """A dependent API job cannot proceed after a failed sink with a printed UUID."""
        root = Path(__file__).resolve().parents[2]
        (root / ".temp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root / ".temp") as folder:
            output = Path(folder) / "step-output"
            response = subprocess.CompletedProcess([], 9, f"Current Version ID: {VERSION}\n", "private-provider-output")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), patch.object(sys, "argv", ["deploy_trace_sink.py", "--target", "production"]), patch.object(MODULE.subprocess, "run", return_value=response) as call:
                self.assertEqual(MODULE.main(), 1)
            self.assertEqual(output.read_text(), f"version={VERSION}\n")
            call.assert_called_once()


if __name__ == "__main__":
    unittest.main()
