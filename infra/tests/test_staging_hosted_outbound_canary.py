"""Offline source and denial contracts for the dormant outbound workflow.

Run in GitHub CI; tests never perform login, grant a release gate, or send mail.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
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
        self.assertEqual(final.count("${{ secrets."), 11)
        self.assertEqual(final.count("        run:"), 1)
        self.assertIn("run: python infra/tests/staging_hosted_outbound_canary.py", final)
        self.assertNotIn("--sender", source)
        self.assertNotIn("--recipient", source)
        for name in (
            "STAGING_E2E_USERNAME", "STAGING_E2E_PASSWORD", "STAGING_E2E_OWNER_SUB",
            "AMAIL_CANARY_SENDER", "AMAIL_CANARY_RECIPIENT", "AMAIL_CANARY_IMAP_HOST",
            "AMAIL_CANARY_IMAP_USER", "AMAIL_CANARY_IMAP_PASSWORD",
            "AMAIL_CANARY_AUTHSERV_ID", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN",
        ):
            self.assertIn(f"{name}: ${{{{ secrets.{name} }}}}", final)
        self.assertNotIn("secrets: inherit", source)

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


if __name__ == "__main__":
    unittest.main()
