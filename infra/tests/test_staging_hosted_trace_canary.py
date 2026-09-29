"""Offline safety checks for the hosted staging retained-log workflow."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
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

    def test_child_failure_code_is_exact_and_allowlisted(self) -> None:
        """Expose only exact fixed child stages, never arbitrary child output."""

        for code in (
                "deployed_privacy_settings_unverified",
                "cli_list_not_correlatable",
                "rejected_url_contract_failed",
                "observability_events_view_absent",
                "unreviewed_retained_payload",
                "application_event_schema_unallowlisted",
                "cli_api_parentage_invalid",
                "local_probe_unavailable",
        ):
            with self.subTest(code=code):
                output = f"staging_trace_canary: UNVERIFIED ({code})\n".encode("ascii")
                self.assertEqual(HOSTED.child_failure_code(output), code)
        for output in (b"secret=private\nstaging_trace_canary: UNVERIFIED (observability_events_view_absent)",
                       b"staging_trace_canary: UNVERIFIED (private_provider_text)",
                       b"staging_trace_canary: retained_marker_absence_and_cli_api_parentage_verified"):
            with self.subTest(output=output):
                self.assertEqual(HOSTED.child_failure_code(output), "retained_canary_unverified")

    def test_child_success_requires_exact_fixed_line(self) -> None:
        """A zero exit alone cannot stand in for the child proof assertion."""

        success = HOSTED.CHILD_SUCCESS
        self.assertTrue(HOSTED.child_success_verified(success + b"\n"))
        self.assertTrue(HOSTED.child_success_verified(success + b"\r\n"))
        for output in (None, b"", success, b" " + success + b"\n",
                       success + b"\nprivate", success + b"\n" + b"x" * 161,
                       success + b"\n\xff"):
            with self.subTest(output=output):
                self.assertFalse(HOSTED.child_success_verified(output))

    def test_zero_exit_without_proof_line_remains_unverified(self) -> None:
        """The hosted verdict fails closed even when a child exits zero."""

        run_dir = HOSTED.TEMP / "staging-hosted-trace-unit"
        identity = SimpleNamespace(
            ProbeError=type("ProbeError", (Exception,), {}),
            store_credential=lambda *_: None,
            native_login=lambda *_: None,
        )
        with patch.object(HOSTED, "preflight_live", return_value=("a" * 32, "deploy", "observe")), \
                patch.object(HOSTED, "validated_credential", return_value=("synthetic_user", "private_password")), \
                patch.object(HOSTED, "BUILT_BINARY", SimpleNamespace(is_file=lambda: True)), \
                patch.object(HOSTED, "os", SimpleNamespace(name="nt")), \
                patch.object(HOSTED.tempfile, "mkdtemp", return_value=str(run_dir)), \
                patch.object(HOSTED.shutil, "copy2"), \
                patch.object(HOSTED, "unique_auth_home", return_value=run_dir / "home"), \
                patch.object(HOSTED, "canary_environment", return_value={}), \
                patch.object(HOSTED.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=b"")) as probe, \
                patch.object(HOSTED, "remove_run_dir") as cleanup, \
                patch.dict(sys.modules, {"staging_identity_cdp": identity}):
            with self.assertRaisesRegex(HOSTED.HostedTraceError, "retained_canary_success_unconfirmed"):
                HOSTED.execute("canary", HOSTED.CONFIRMATION)
            probe.return_value = SimpleNamespace(returncode=0, stdout=HOSTED.CHILD_SUCCESS + b"\r\n")
            with redirect_stdout(StringIO()) as output:
                HOSTED.execute("canary", HOSTED.CONFIRMATION)
            self.assertEqual(output.getvalue().strip(), "staging_trace_hosted: retained_canary_verified")
        self.assertEqual(cleanup.call_count, 2)

    def test_primary_and_cleanup_failures_remain_visible(self) -> None:
        """A failed retained query must not be hidden by a cleanup lock."""

        run_dir = HOSTED.TEMP / "staging-hosted-trace-unit"
        identity = SimpleNamespace(
            ProbeError=type("ProbeError", (Exception,), {}),
            store_credential=lambda *_: None,
            native_login=lambda *_: None,
        )
        with patch.object(HOSTED, "preflight_live", return_value=("a" * 32, "deploy", "observe")), \
                patch.object(HOSTED, "validated_credential", return_value=("synthetic_user", "private_password")), \
                patch.object(HOSTED, "BUILT_BINARY", SimpleNamespace(is_file=lambda: True)), \
                patch.object(HOSTED, "os", SimpleNamespace(name="nt")), \
                patch.object(HOSTED.tempfile, "mkdtemp", return_value=str(run_dir)), \
                patch.object(HOSTED.shutil, "copy2"), \
                patch.object(HOSTED, "unique_auth_home", return_value=run_dir / "home"), \
                patch.object(HOSTED, "canary_environment", return_value={}), \
                patch.object(HOSTED.subprocess, "run", return_value=SimpleNamespace(returncode=1)) as probe, \
                patch.object(HOSTED, "remove_run_dir", side_effect=HOSTED.HostedTraceError("run_cleanup_failed")) as cleanup, \
                patch.dict(sys.modules, {"staging_identity_cdp": identity}):
            for run_error, child_output, primary in (
                (None, None, "retained_canary_unverified"),
                (None, b"staging_trace_canary: UNVERIFIED (observability_events_view_absent)\n",
                 "observability_events_view_absent"),
                (HOSTED.subprocess.TimeoutExpired("synthetic", 240), None,
                 "retained_canary_timed_out"),
            ):
                with self.subTest(primary=primary):
                    probe.side_effect = run_error
                    probe.return_value = SimpleNamespace(returncode=1, stdout=child_output)
                    with self.assertRaises(HOSTED.HostedTraceError) as caught:
                        HOSTED.execute("canary", HOSTED.CONFIRMATION)
                    self.assertEqual(str(caught.exception), f"{primary}; run_cleanup_failed")
        self.assertEqual(cleanup.call_count, 3)
        cleanup.assert_any_call(run_dir)

    def test_transient_windows_lock_is_retried_and_removed(self) -> None:
        """Retry a transient Windows lock without accepting an undeleted tree."""

        HOSTED.TEMP.mkdir(exist_ok=True)
        run_dir = Path(tempfile.mkdtemp(prefix="staging-hosted-trace-unit-", dir=HOSTED.TEMP))
        (run_dir / "fixture.txt").write_text("synthetic", encoding="utf-8")
        real_rmtree = shutil.rmtree
        calls = 0

        def locked_once(path: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                error = PermissionError("private path must not be printed")
                error.winerror = 32
                raise error
            real_rmtree(path)

        try:
            with patch.object(HOSTED.shutil, "rmtree", side_effect=locked_once), \
                    patch.object(HOSTED.time, "sleep") as sleep:
                HOSTED.remove_run_dir(run_dir)
            self.assertEqual(calls, 2)
            sleep.assert_called_once_with(HOSTED.CLEANUP_RETRY_DELAYS[0])
            self.assertFalse(run_dir.exists())
        finally:
            if run_dir.exists():
                real_rmtree(run_dir)


if __name__ == "__main__":
    unittest.main()
