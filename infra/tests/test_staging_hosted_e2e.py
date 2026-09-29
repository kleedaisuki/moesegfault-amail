"""Mock-only safety checks for the manual hosted Windows staging probe."""

from __future__ import annotations

from contextlib import redirect_stderr
import hmac
import hashlib
import importlib.util
from io import StringIO
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "staging_hosted_e2e", Path(__file__).with_name("staging_hosted_e2e.py")
)
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


class HostedHarnessSafetyTests(unittest.TestCase):
    """Exercise private recoverability and fixed-label failure semantics."""

    def test_typed_stage_labels_are_bounded(self) -> None:
        """Preserve fixed stage codes but never echo provider or secret payloads."""

        self.assertEqual(
            HARNESS.safe_stage_code(Exception("cli_native_login_failed")),
            "cli_native_login_failed",
        )
        self.assertEqual(
            HARNESS.safe_stage_code(Exception("smtp_submission_failed_cleanup_address_or_route_cleanup_failed")),
            "smtp_submission_failed_cleanup_address_or_route_cleanup_failed",
        )
        self.assertEqual(
            HARNESS.safe_stage_code(Exception("smtp token=DO_NOT_PRINT")),
            "unexpected_failure",
        )

    def test_recovery_suffix_requires_secret_and_run_coordinates(self) -> None:
        """A public run URL alone must not reveal the synthetic alias suffix."""

        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123456", "GITHUB_RUN_ATTEMPT": "2"}):
            suffix = HARNESS.recoverable_run_nonce("protected-test-password")
            other = HARNESS.recoverable_run_nonce("different-test-password")
        expected = hmac.new(
            b"protected-test-password", b"amail-staging-e2e/v1:123456:2", hashlib.sha256
        ).hexdigest()[:16]
        self.assertEqual(suffix, expected)
        self.assertNotEqual(suffix, other)
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "not-a-run", "GITHUB_RUN_ATTEMPT": "2"}):
            with self.assertRaises(HARNESS.HostedProbeError):
                HARNESS.recoverable_run_nonce("protected-test-password")

    def test_home_must_be_unique_inside_run(self) -> None:
        """Never continue with an arbitrary auth store after a partial login."""

        HARNESS.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=HARNESS.TEMP) as directory:
            run_dir = Path(directory)
            with self.assertRaises(HARNESS.HostedProbeError):
                HARNESS.unique_auth_home(run_dir)
            (run_dir / "amail-home-one").mkdir()
            self.assertEqual(HARNESS.unique_auth_home(run_dir).name, "amail-home-one")
            (run_dir / "amail-home-two").mkdir()
            with self.assertRaises(HARNESS.HostedProbeError):
                HARNESS.unique_auth_home(run_dir)

    def test_unexpected_exception_does_not_leak_detail(self) -> None:
        """Suppress credentials and provider strings in the hosted job log."""

        output = StringIO()
        with patch.object(HARNESS, "execute", side_effect=Exception("secret=DO_NOT_PRINT")):
            with redirect_stderr(output):
                self.assertEqual(HARNESS.main(), 1)
        self.assertEqual(output.getvalue().strip(), "staging_hosted_e2e_failed:unexpected_failure")


if __name__ == "__main__":
    unittest.main()
