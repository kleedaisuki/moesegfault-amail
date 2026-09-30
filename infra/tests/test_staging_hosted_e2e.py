"""Mock-only safety checks for the manual hosted Windows staging probe."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hmac
import hashlib
import importlib.util
from io import StringIO
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from workflow_source import job_block


SPEC = importlib.util.spec_from_file_location(
    "staging_hosted_e2e", Path(__file__).with_name("staging_hosted_e2e.py")
)
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


class HostedHarnessSafetyTests(unittest.TestCase):
    """Exercise private recoverability and fixed-label failure semantics."""

    def test_semantic_probe_requires_explicit_boolean_switch(self) -> None:
        """The first inbound run remains independent of provider indexing."""

        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(HARNESS.semantic_requested())
        with patch.dict(os.environ, {"AMAIL_STAGING_SEMANTIC_E2E": "1"}):
            self.assertTrue(HARNESS.semantic_requested())
        with patch.dict(os.environ, {"AMAIL_STAGING_SEMANTIC_E2E": "yes"}):
            with self.assertRaises(HARNESS.HostedProbeError) as caught:
                HARNESS.semantic_requested()
        self.assertEqual(str(caught.exception), "semantic_confirmation_invalid")

    def test_isolation_requires_independent_literal_confirmation(self) -> None:
        """A's SMTP confirmation cannot authorize B identity or ID operations."""

        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(HARNESS.isolation_requested())
        with patch.dict(os.environ, {"AMAIL_STAGING_ISOLATION_E2E": "1"}, clear=True):
            with self.assertRaises(HARNESS.HostedProbeError) as caught:
                HARNESS.isolation_requested()
        self.assertEqual(str(caught.exception), "isolation_confirmation_missing")
        with patch.dict(os.environ, {
            "AMAIL_STAGING_ISOLATION_E2E": "1",
            "AMAIL_STAGING_ISOLATION_CONFIRM": "RUN_STAGING_TWO_PRINCIPAL_ISOLATION",
        }, clear=True):
            self.assertTrue(HARNESS.isolation_requested())

    def test_exact_cosine_requires_semantic_confirmation(self) -> None:
        """The optional operator path is off by default and cannot piggyback."""

        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(HARNESS.exact_cosine_requested(False))
        cases = [
            ({"AMAIL_STAGING_EXACT_COSINE_E2E": "yes"}, False, "exact_cosine_switch_invalid"),
            ({"AMAIL_STAGING_EXACT_COSINE_E2E": "1"}, True, "exact_cosine_confirmation_missing"),
            ({"AMAIL_STAGING_EXACT_COSINE_E2E": "1",
              "AMAIL_STAGING_EXACT_COSINE_CONFIRM": "RUN_STAGING_EXACT_COSINE",
             }, False, "exact_cosine_confirmation_missing"),
        ]
        for values, semantic, expected in cases:
            with self.subTest(expected=expected), patch.dict(os.environ, values, clear=True):
                with self.assertRaises(HARNESS.HostedProbeError) as caught:
                    HARNESS.exact_cosine_requested(semantic)
                self.assertEqual(str(caught.exception), expected)
        with patch.dict(os.environ, {
            "AMAIL_STAGING_EXACT_COSINE_E2E": "1",
            "AMAIL_STAGING_EXACT_COSINE_CONFIRM": "RUN_STAGING_EXACT_COSINE",
        }, clear=True):
            self.assertTrue(HARNESS.exact_cosine_requested(True))

    def test_identity_readback_binds_b_login_to_b_contact(self) -> None:
        """Different contact principals alone cannot prove the B CLI session."""

        source = (HARNESS.ROOT / "infra/tests/staging_hosted_e2e.py").read_text(encoding="utf-8")
        self.assertIn("contacts[FIRST][3] != username", source)
        self.assertIn("contacts[ADDRESS][3] != username_b", source)

    def test_manual_workflow_wires_default_off_semantic_input(self) -> None:
        """A reviewer must be able to dispatch the optional stage explicitly."""

        workflow = (HARNESS.ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        inputs = workflow.split("  workflow_dispatch:\n", 1)[1].split("\npermissions:", 1)[0]
        semantic = re.search(r"(?ms)^      semantic:\n(.*?)(?=^      [a-z_]+:|\Z)", inputs)
        self.assertIsNotNone(semantic)
        self.assertIn("default: false", semantic.group(1))
        self.assertIn("type: boolean", semantic.group(1))
        job = job_block(workflow, "staging-e2e")
        self.assertIn("inputs.target == 'staging-e2e'", job)
        self.assertIn(
            "AMAIL_STAGING_SEMANTIC_E2E: ${{ inputs.semantic && '1' || '0' }}", job
        )
        self.assertEqual(workflow.count("AMAIL_STAGING_SEMANTIC_E2E:"), 1)
        self.assertIn("AMAIL_STAGING_EXACT_COSINE_E2E: ${{ inputs.exact_cosine && '1' || '0' }}", job)
        self.assertNotIn("OPENROUTER_API_KEY: ${{ inputs.exact_cosine && secrets.OPENROUTER_API_KEY || '' }}", job)

    def test_staging_snapshot_receives_account_id_only_in_execution_step(self) -> None:
        """Fail before login if the bounded D1 readback cannot be authenticated."""

        workflow = (HARNESS.ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        job = job_block(workflow, "staging-e2e")
        execution = "      - name: Execute staging native and inbound-mail acceptance\n"
        before, step = job.split(execution, 1)
        self.assertIn("CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}", step)
        self.assertIn("CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}", step)
        self.assertNotIn("CLOUDFLARE_ACCOUNT_ID:", before)

    def test_success_marker_distinguishes_basic_and_semantic_scope(self) -> None:
        """A basic pass must never look like a semantic-search pass."""

        for enabled, expected in (
            (False, "staging_hosted_native_login_and_inbound_mail_verified"),
            (True, "staging_hosted_native_login_inbound_and_semantic_verified"),
        ):
            with self.subTest(semantic=enabled), patch.object(
                HARNESS, "execute", return_value=enabled
            ), redirect_stdout(StringIO()) as output:
                self.assertEqual(HARNESS.main(), 0)
            self.assertEqual(output.getvalue().strip(), expected)

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
