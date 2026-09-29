"""Offline safety checks for the hosted staging retained-log workflow."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location(
    "staging_hosted_trace_canary", HERE / "staging_hosted_trace_canary.py"
)
assert SPEC and SPEC.loader
HOSTED = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HOSTED)


class HostedTraceSafetyTests(unittest.TestCase):
    """Reject unsafe or premature work without accessing live services."""

    def test_missing_observability_secret_stops_before_network(self) -> None:
        """A dedicated missing secret must be diagnosable without login."""

        environment = {
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
            "CLOUDFLARE_API_TOKEN": "private-deploy-token",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(HOSTED.HostedTraceError, "observability_secret_missing"):
                HOSTED.preflight_live()

    def test_full_mode_requires_confirmation_before_preflight(self) -> None:
        """No API or browser is touched when the operator omitted confirmation."""

        with patch.object(HOSTED, "preflight_live") as preflight:
            with self.assertRaisesRegex(HOSTED.HostedTraceError, "explicit_staging_confirmation_required"):
                HOSTED.execute("canary", "")
            preflight.assert_not_called()

    def test_preflight_failure_stops_before_credential_access(self) -> None:
        """A settings or permission failure cannot trigger native login."""

        with patch.object(HOSTED, "preflight_live", side_effect=HOSTED.HostedTraceError("observability_permission_denied")):
            with patch.object(HOSTED, "validated_credential") as credential:
                with self.assertRaisesRegex(HOSTED.HostedTraceError, "observability_permission_denied"):
                    HOSTED.execute("canary", HOSTED.CONFIRMATION)
                credential.assert_not_called()

    def test_preflight_mode_never_reads_staging_credential(self) -> None:
        """The cheap capability probe needs no Identity account secret."""

        output = StringIO()
        with patch.object(HOSTED, "preflight_live", return_value=("a" * 32, "deploy", "observe")):
            with patch.object(HOSTED, "validated_credential") as credential:
                with redirect_stdout(output):
                    HOSTED.execute("preflight", "")
                credential.assert_not_called()
        self.assertEqual(output.getvalue().strip(), "staging_trace_hosted: preflight_verified")

    def test_unexpected_error_never_echoes_private_text(self) -> None:
        """Provider and local exception payloads are not job-log material."""

        output = StringIO()
        with patch.object(HOSTED, "execute", side_effect=RuntimeError("token=DO_NOT_PRINT")):
            with patch.object(sys, "argv", ["script", "--mode", "preflight"]):
                with redirect_stderr(output):
                    self.assertEqual(HOSTED.main(), 1)
        self.assertEqual(output.getvalue().strip(), "staging_trace_hosted: UNVERIFIED (unexpected_failure)")


if __name__ == "__main__":
    unittest.main()
