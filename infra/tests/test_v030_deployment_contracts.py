"""Temporary-domain rollout preserves exact immutable USD predecessor contracts."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import check_mail_maintenance as maintenance
import ensure_email_events as events
import pin_staging_mail as pin


class DeploymentContracts(unittest.TestCase):
    def test_only_exact_usd_api_pin_can_omit_temporary_domain(self) -> None:
        for realm, version, omitted in (("staging", "c33b65b1-d2a4-4902-9fa3-15e74baf1819", True),
                                         ("production", "c33b65b1-d2a4-4902-9fa3-15e74baf1819", False),
                                         ("staging", "12345678-1234-1234-1234-123456789abc", False)):
            with self.subTest(realm=realm, version=version), patch.object(pin, "_bindings_match", return_value=True) as compare:
                pin.bindings_match({}, version, phase="queue-api", queue_id="b" * 32, realm=realm)
                self.assertEqual("MAIL_TMP_DOMAIN" not in compare.call_args.args[2], omitted)

    def test_only_exact_usd_maintenance_pin_can_omit_temporary_domain(self) -> None:
        for version, omitted in (("acbf4790-6e80-4bd3-aab2-095c9937759d", True),
                                  ("12345678-1234-1234-1234-123456789abc", False)):
            with self.subTest(version=version), \
                 patch.object(maintenance, "serving_deployment", return_value=("deployment", version)), \
                 patch.object(maintenance.capture, "readback", return_value={}), \
                 patch.object(maintenance, "_bindings_match", return_value=False) as compare:
                with self.assertRaisesRegex(ValueError, "^maintenance_bindings_unverified$"):
                    maintenance.verify("staging", "active", "a" * 32, "synthetic", version, "b" * 32)
                self.assertEqual("MAIL_TMP_DOMAIN" not in compare.call_args.args[2], omitted)

    def test_v030_subscription_adds_one_exact_path_and_preserves_original(self) -> None:
        environment = {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "synthetic",
                       "GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/codex/v0.3.0-multitenant",
                       "AMAIL_STAGING_DEPLOY_CONFIRM": "RUN_STAGING_V030"}
        args = ["ensure_email_events.py", "--target", "staging", "--phase", "subscription"]
        with patch.dict(os.environ, environment, clear=True), patch.object(sys, "argv", args), \
             patch.object(events, "ensure_subscription") as ensure, redirect_stdout(io.StringIO()):
            self.assertEqual(events.main(), 0)
            self.assertEqual([call.args for call in ensure.call_args_list], [
                ("amail-sending-events-staging", "amail-sending-lifecycle-staging", "mail-staging.moesegfault.dev"),
                ("amail-sending-events-staging", "amail-tmpaddr-lifecycle-staging", "tmpaddr-staging.moesegfault.dev")])
        with patch.dict(os.environ, {**environment, "AMAIL_STAGING_DEPLOY_CONFIRM": "RUN_STAGING_V020"}, clear=True), \
             patch.object(sys, "argv", args), patch.object(events, "ensure_subscription") as ensure, \
             redirect_stdout(io.StringIO()):
            self.assertEqual(events.main(), 1)
            ensure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
