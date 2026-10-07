"""Exact staging maintenance issuer repair and checked-in deployment contracts."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import check_mail_maintenance as maintenance


class MaintenanceIssuerTests(unittest.TestCase):
    """Only the source-owned broken version may omit one issuer binding."""

    def test_real_config_requires_same_staging_issuer_as_api(self):
        """The deployed config, not a synthetic fixture, supplies the Billing issuer."""
        current = maintenance.maintenance_config("staging", active=True)
        self.assertEqual(current["vars"]["IDENTITY_ISSUER"],
                         maintenance.api_config("staging")["vars"]["IDENTITY_ISSUER"])
        bindings = maintenance.expected_bindings("staging", "b" * 32)
        self.assertEqual(bindings["IDENTITY_ISSUER"],
                         ("plain_text", "https://identity-staging.moesegfault.dev"))
        self.assertNotIn("IDENTITY_ISSUER", maintenance.expected_bindings("production", "b" * 32))

    def test_exact_repair_retains_every_other_binding(self):
        """Rejecting immutable content still exposes the exact expected map to this test."""
        version = maintenance.MISSING_ISSUER_PREDECESSOR
        deployment = ("synthetic-deployment", version)
        with patch.object(maintenance, "serving_deployment", return_value=deployment), \
                patch.object(maintenance.capture, "readback", return_value={}), \
                patch.object(maintenance, "_bindings_match", return_value=False) as compare:
            with self.assertRaisesRegex(ValueError, "^maintenance_bindings_unverified$"):
                maintenance.verify_missing_issuer_predecessor("a" * 32, "synthetic-token", "b" * 32)
        expected = maintenance.expected_bindings("staging", "b" * 32)
        del expected["IDENTITY_ISSUER"]
        self.assertEqual(compare.call_args.args[2], expected)
        self.assertEqual(expected["BILLING_SERVICE_KEY"], ("secret_text", None))
        for name in ("BILLING_BASE_URL", "BILLING_SUBSCRIBE_ORIGIN", "BILLING_RETURN_URL"):
            self.assertIn(name, expected)

    def test_exception_never_admits_other_cohorts_or_states(self):
        """No provider read occurs for production, wrong UUID, old cohort or changed Cron."""
        base = dict(realm="staging", state="active", account="a" * 32, token="synthetic-token",
                    version=maintenance.MISSING_ISSUER_PREDECESSOR, queue_id="b" * 32,
                    missing_issuer_predecessor=True)
        cases = ({"realm": "production"}, {"state": "paused"}, {"predecessor": True},
                 {"version": "11111111-1111-4111-8111-111111111111"},
                 {"api_crons": maintenance.CADENCE})
        for change in cases:
            with self.subTest(change=change), patch.object(maintenance.capture, "readback") as read:
                with self.assertRaisesRegex(ValueError, "^maintenance_issuer_predecessor_unreviewed$"):
                    maintenance.verify(**dict(base, **change))
                read.assert_not_called()

    def test_normal_historical_pin_still_requires_issuer(self):
        """The historical UUID alone does not enable the repair exception."""
        version = maintenance.MISSING_ISSUER_PREDECESSOR
        with patch.object(maintenance, "serving_deployment", return_value=("deployment", version)), \
                patch.object(maintenance.capture, "readback", return_value={}), \
                patch.object(maintenance, "_bindings_match", return_value=False) as compare:
            with self.assertRaisesRegex(ValueError, "^maintenance_bindings_unverified$"):
                maintenance.verify("staging", "active", "a" * 32, "synthetic-token", version, "b" * 32)
        self.assertIn("IDENTITY_ISSUER", compare.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
