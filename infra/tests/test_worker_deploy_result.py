"""Hosted synthetic safe deployment diagnostics and bounded ambiguity contracts."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "deploy"))
import worker_deploy_result as deployer

VERSION = "11111111-1111-1111-1111-111111111111"
PRIVATE = "private-provider-body-token-poison"


class WorkerDeployResultTests(unittest.TestCase):
    """A useful recovery coordinate must not masquerade as accepted deployment."""

    def test_failing_exit_retains_exact_pin_without_retry_or_raw_output(self):
        """One UUID on failure is recovery-only; code/version count explain the refusal."""
        response = subprocess.CompletedProcess([], 7, f"{PRIVATE}\nCurrent Version ID: {VERSION}\n", PRIVATE)
        output = io.StringIO()
        with patch.object(deployer.subprocess, "run", return_value=response) as call, redirect_stdout(output):
            with self.assertRaises(deployer.DeploymentFailure) as failure:
                deployer.submit(["wrangler", "deploy"], "production", "mail_api")
        self.assertEqual(failure.exception.version, VERSION)
        call.assert_called_once()
        event = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual((event["process_exit_code"], event["version_count"], event["reason"]), (7, 1, "process_exit"))
        self.assertEqual(event["outcome"], "failure")
        self.assertNotIn(PRIVATE, output.getvalue())

    def test_timeout_is_ambiguous_and_never_replayed(self):
        """Do not mine a timed-out output for a presumed accepted recovery target."""
        output = io.StringIO()
        error = subprocess.TimeoutExpired(["wrangler", "deploy"], 600, output=PRIVATE)
        with patch.object(deployer.subprocess, "run", side_effect=error) as call, redirect_stdout(output):
            with self.assertRaises(subprocess.TimeoutExpired):
                deployer.submit(["wrangler", "deploy"], "staging", "trace_sink")
        call.assert_called_once()
        event = json.loads(output.getvalue().splitlines()[-1])
        self.assertEqual(event["reason"], "submit_timeout_ambiguous")
        self.assertEqual(event["error_type"], "TimeoutExpired")
        self.assertNotIn(PRIVATE, output.getvalue())

    def test_duplicate_and_oversized_output_supply_no_recovery_pin(self):
        """Never guess a first version or trust data past the output bound."""
        for text in (f"Current Version ID: {VERSION}\n" * 2, "x" * (deployer.LIMIT + 1)):
            with patch.object(deployer.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, text, PRIVATE)) as call:
                with self.assertRaises(deployer.DeploymentFailure) as failure:
                    deployer.submit(["wrangler", "deploy"], "production", "trace_sink")
                self.assertIsNone(failure.exception.version)
                call.assert_called_once()


if __name__ == "__main__":
    unittest.main()
