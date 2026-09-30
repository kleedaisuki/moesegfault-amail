"""Offline source and denial contracts for the dormant outbound workflow.

Run in GitHub CI; tests never perform login, grant a release gate, or send mail.
"""

from __future__ import annotations

import importlib.util
from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch


HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location(
    "staging_hosted_outbound_canary", HERE / "staging_hosted_outbound_canary.py"
)
assert SPEC and SPEC.loader
HOSTED = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HOSTED)


class HostedOutboundWorkflowTests(unittest.TestCase):
    """Protect the dispatch, secret placement, and fixed-log boundary."""

    def test_reusable_workflow_has_no_direct_dispatch_or_secret_inputs(self) -> None:
        """A branch-local workflow cannot independently spend a canary grant."""

        source = (ROOT / ".github/workflows/staging-outbound-canary.yml").read_text(encoding="utf-8")
        header, steps = source.split("    steps:\n", 1)
        self.assertIn("  workflow_call:", header)
        self.assertNotIn("workflow_dispatch:", header)
        self.assertEqual(header.count("        type: string"), 1)
        self.assertIn("inputs.confirm == 'RUN_STAGING_OUTBOUND_CANARY'", header)
        self.assertIn("github.ref == 'refs/heads/main'", header)
        self.assertIn("environment: staging", header)
        self.assertIn("runs-on: windows-latest", header)
        self.assertIn("cancel-in-progress: false", header)
        self.assertNotIn("upload-artifact", steps)

    def test_secrets_are_only_in_final_python_step(self) -> None:
        """Do not expose control-plane, Identity, or mailbox data during builds."""

        source = (ROOT / ".github/workflows/staging-outbound-canary.yml").read_text(encoding="utf-8")
        prefix, final = source.split("      - name: Native PKCE and one guarded outbound canary\n", 1)
        self.assertNotIn("${{ secrets.", prefix)
        self.assertEqual(final.count("${{ secrets."), 12)
        self.assertEqual(final.count("        run:"), 1)
        self.assertIn("run: python infra/tests/staging_hosted_outbound_canary.py", final)
        self.assertNotIn("--sender", source)
        self.assertNotIn("--recipient", source)
        for name in (
            "STAGING_E2E_USERNAME", "STAGING_E2E_PASSWORD", "STAGING_E2E_OWNER_SUB",
            "AMAIL_CANARY_SENDER", "AMAIL_CANARY_RECIPIENT", "AMAIL_CANARY_IMAP_HOST",
            "AMAIL_CANARY_IMAP_USER", "AMAIL_CANARY_IMAP_PASSWORD",
            "AMAIL_CANARY_AUTHSERV_ID", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN",
            "AMAIL_STAGING_CANARY_RECOVERY_KEY",
        ):
            self.assertIn(f"{name}: ${{{{ secrets.{name} }}}}", final)
        self.assertNotIn("secrets: inherit", source)
        self.assertIn("test_staging_canary_recovery.py", prefix)
        self.assertIn("test_staging_hosted_outbound_canary.py", prefix)
        self.assertIn("test_staging_outbound_canary.py", prefix)

    def test_confirmation_and_hosted_windows_precede_capability_read(self) -> None:
        """The Python entry point independently denies an accidental local run."""

        with patch.dict(os.environ, {"AMAIL_OUTBOUND_CONFIRM": HOSTED.CONFIRM}, clear=True):
            with patch.object(HOSTED, "config") as config:
                with self.assertRaisesRegex(HOSTED.HostedOutboundError, "hosted_windows_required"):
                    HOSTED.validate()
                config.assert_not_called()
        with patch.object(HOSTED.os, "name", "nt"), patch.dict(os.environ, {
            "GITHUB_ACTIONS": "true", "AMAIL_OUTBOUND_CONFIRM": "wrong",
        }, clear=True):
            with patch.object(HOSTED, "config") as config:
                with self.assertRaisesRegex(HOSTED.HostedOutboundError, "explicit_staging_confirmation_required"):
                    HOSTED.validate()
                config.assert_not_called()

    def test_post_login_wait_requires_fresh_exact_grant(self) -> None:
        """A ready marker follows controls; polling reads but cannot grant."""

        output = StringIO()
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}), \
                patch.object(HOSTED, "config", return_value={}) as config, \
                patch.object(HOSTED, "privacy_ready") as privacy, \
                patch.object(HOSTED, "inbox_ready") as inbox, \
                patch.object(HOSTED, "preflight_controls") as controls, \
                patch.object(HOSTED, "grant_watermark", return_value=SimpleNamespace(audit_id=100)) as watermark, \
                patch.object(HOSTED, "grant_ready", side_effect=[False, True]) as grant, \
                patch.object(HOSTED.time, "sleep") as sleep, \
                patch.object(HOSTED.time, "monotonic", side_effect=[0, 1, 2]), \
                redirect_stdout(output):
            observed = HOSTED.await_operator_grant("probe@mail-staging.moesegfault.dev")
        self.assertEqual(observed.audit_id, 100)
        self.assertEqual(output.getvalue(), "staging_outbound_ready_for_one_use_grant\n")
        config.assert_called_once()
        privacy.assert_called_once()
        inbox.assert_called_once()
        self.assertEqual(controls.call_count, 3)
        watermark.assert_called_once()
        self.assertEqual(watermark.call_args.args[1:], ("123", "1"))
        self.assertEqual(grant.call_count, 2)
        self.assertTrue(all(call.kwargs["after"].audit_id == 100 for call in grant.call_args_list))
        sleep.assert_called_once_with(5)


if __name__ == "__main__":
    unittest.main()
