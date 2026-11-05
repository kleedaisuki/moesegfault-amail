"""Protected hosted browser/retained-trace workflow wiring contracts."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/tests"))
import staging_hosted_e2e as hosted
import staging_trace_witness as reader
import staging_mail_e2e as mail


class BillingWorkflowTests(unittest.TestCase):
    """Human activation and retained-span privileges cannot reach the agent CLI."""

    def test_operator_and_activation_secrets_are_not_in_cli_environment(self) -> None:
        """Only the browser/parent harness receives protected capabilities."""
        with patch.dict(os.environ, {"BILLING_SERVICE_KEY": "private", "CLOUDFLARE_API_TOKEN": "private",
                                   "STAGING_E2E_AMAIL_ACTIVATION_CODE": "private"}):
            environment = mail.cli_env(ROOT / ".temp/test-cli-home")
        self.assertTrue({"BILLING_SERVICE_KEY", "CLOUDFLARE_API_TOKEN", "STAGING_E2E_AMAIL_ACTIVATION_CODE"}.isdisjoint(environment))

    def test_actual_trace_reader_calls_require_human_authorization_chain(self) -> None:
        """Successful browser result is not substituted for retained causal records."""
        evidence = {"trace_ids": ["a" * 32], "started_at_ms": 1000}
        with patch.dict(os.environ, {"BILLING_SERVICE_KEY": "private", "CLOUDFLARE_API_TOKEN": "private",
                                   "CLOUDFLARE_ACCOUNT_ID": "b" * 32}), \
             patch.object(hosted.time, "time", return_value=2), \
             patch.object(reader, "read_records", return_value=[{"mail": True}]) as mail_read, \
             patch.object(reader, "read_service_records", side_effect=[[{"billing": True}], [{"subscribe": True}]]) as service_read, \
             patch.object(reader, "witness", return_value={"verified": True}) as verify:
            self.assertEqual(hosted.retained_billing_trace(evidence), {"verified": True})
        self.assertEqual(mail_read.call_args.args[2], "amail-trace-sink-staging")
        self.assertEqual([call.args[0] for call in service_read.call_args_list], ["billing", "subscribe"])
        verify.assert_called_once_with([{"mail": True}, {"billing": True}, {"subscribe": True}], "a" * 32,
                                       require_cli=True, require_authorization=True)

if __name__ == "__main__":
    unittest.main()
