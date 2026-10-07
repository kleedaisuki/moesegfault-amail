"""Protected hosted browser/retained-trace workflow wiring contracts."""
import importlib.util
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

    def test_operator_and_activation_secrets_are_not_in_cli_environment(self):
        """Only the browser/parent harness receives protected capabilities."""
        with patch.dict(os.environ, {"BILLING_SERVICE_KEY": "private", "CLOUDFLARE_API_TOKEN": "private",
                                   "STAGING_E2E_AMAIL_ACTIVATION_CODE": "private"}):
            environment = mail.cli_env(ROOT / ".temp/test-cli-home")
        self.assertTrue({"BILLING_SERVICE_KEY", "CLOUDFLARE_API_TOKEN", "STAGING_E2E_AMAIL_ACTIVATION_CODE"}.isdisjoint(environment))

    def test_actual_trace_reader_calls_require_human_authorization_chain(self):
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

    def test_workflow_gates_lite_secret_and_uploads_exact_safe_artifact(self):
        """No browser profile, activation code or raw trace record is an artifact."""
        source = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("inputs.billing_confirm == 'RUN_STAGING_BILLING_V020' && inputs.billing_plan == 'lite' && secrets.STAGING_E2E_AMAIL_ACTIVATION_CODE", source)
        self.assertIn("path: .temp/staging-billing-evidence.json", source)
        self.assertIn("options: [free, lite]", source)

    def test_real_metering_is_opt_in_and_does_not_shorten_existing_job_budget(self):
        """Only the explicitly confirmed Lite/trace case receives metering capability."""
        source = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("inputs.confirm == 'RUN_STAGING_E2E' && inputs.billing_confirm == 'RUN_STAGING_BILLING_V020' "
                      "&& inputs.billing_plan == 'lite' && inputs.billing_trace && "
                      "inputs.billing_metering_confirm == 'RUN_STAGING_BILLING_METERING_V020'", source)
        self.assertIn("inputs.billing_metering_confirm == 'RUN_STAGING_BILLING_METERING_V020' && 50 || 40", source)
        self.assertIn("$env:AMAIL_STAGING_BILLING_METERING_CONFIRM -ne 'RUN_STAGING_BILLING_METERING_V020'", source)


if __name__ == "__main__":
    unittest.main()
