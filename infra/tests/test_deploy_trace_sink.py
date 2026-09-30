"""Synthetic contracts for privacy-preserving sink deployment pin extraction."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("deploy_sink", Path(__file__).parents[1] / "deploy/deploy_trace_sink.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
VERSION = "11111111-1111-1111-1111-111111111111"


class DeploySinkTests(unittest.TestCase):
    """No ambiguous version output or deployment failure can produce a trusted pin."""

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


if __name__ == "__main__":
    unittest.main()
