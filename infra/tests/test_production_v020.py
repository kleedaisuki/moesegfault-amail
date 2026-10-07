"""USD production promotion ordering and ownership preservation without provider IO."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import production_v020 as release
import pin_staging_mail as api
import check_mail_maintenance as maintenance


class ProductionV020Tests(unittest.TestCase):
    """A new release must not weaken the original graph or replay a financial action."""

    def test_current_realms_require_billing_and_old_production_exception_is_exact(self):
        """Only the two immutable old versions can omit new capabilities."""
        expected = api.expected_bindings("queue-api", "a" * 32, realm="production")
        self.assertIn("BILLING_SERVICE_KEY", expected)
        self.assertEqual(expected["BILLING_RETURN_URL"][1], "https://amail.moesegfault.dev/billing/return")
        with patch.object(api, "_bindings_match") as compare:
            self.assertFalse(api.bindings_match({}, "unknown", phase="queue-api", queue_id="a" * 32,
                                               realm="production", predecessor=True))
            compare.assert_not_called()
        with self.assertRaisesRegex(ValueError, "maintenance_pin_unreviewed"):
            maintenance.verify("production", "active", "a" * 32, "synthetic", "unknown", "b" * 32, predecessor=True)

    def test_live_ownership_survives_schema_and_legitimate_concurrent_addition(self):
        """Only original immutable ownership tuples are required, not frozen user activity."""
        first = {"owned": {"address": "owned", "owner_iss": "issuer", "owner_sub": "subject", "created_at": 1}}
        later = {**deepcopy(first), "new": {"address": "new"}}
        with patch.object(release, "ownership", side_effect=[first, later]), \
             patch.object(release.prior, "journal"), \
             patch.object(release.subprocess, "run", return_value=type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()), \
             patch.object(release, "query", return_value=[{"owners": 1, "invalid": 0}]):
            self.assertEqual(release.migrate(object())["preserved_addresses"], 1)

    def test_schema_cannot_hide_missing_ownership_or_authorized_spend(self):
        """Lost/changed tuples and non-Free/currency/budget defaults stop before API replacement."""
        with patch.object(release.prior, "journal"), \
             patch.object(release.subprocess, "run", return_value=type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()):
            with patch.object(release, "ownership", side_effect=[{"owned": {"id": 1}}, {}]):
                with self.assertRaisesRegex(ValueError, "ownership_changed"):
                    release.migrate(object())
            with patch.object(release, "ownership", return_value={}), \
                 patch.object(release, "query", return_value=[{"owners": 1, "invalid": 1}]):
                with self.assertRaisesRegex(ValueError, "free_migration_unverified"):
                    release.migrate(object())

    def exercise(self, failure=None):
        """Run the real coordinator with only boundary IO mocked; retain exact submit order."""
        order = []
        policy = {"state": "allowed"}
        def observe(pins, *args):
            resolved = {name: (pair[0] or "new-deployment", pair[1]) for name, pair in pins.items()}
            return {"pins": resolved}, policy, object()
        def replace(role):
            order.append(role)
            if role == failure:
                raise TimeoutError("ambiguous submit")
            return "11111111-1111-4111-8111-111111111111"
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder, \
             patch.object(release, "ROOT", Path(folder)), \
             patch.dict(os.environ, {"GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123"}), \
             patch.object(release.prior, "context"), patch.object(release.prior, "output"), \
             patch.object(release.prior, "retained_snapshot", return_value={}), \
             patch.object(release, "observe", side_effect=observe), \
             patch.object(release, "billing_ready", side_effect=lambda: order.append("billing-read")), \
             patch.object(release, "migrate", side_effect=lambda provider: order.append("migration") or {}), \
             patch.object(release, "replace", side_effect=replace):
            if failure:
                with self.assertRaises(TimeoutError):
                    release.run("upgrade")
            else:
                release.run("upgrade")
        return order

    def test_typed_sink_precedes_schema_and_producers_without_policy_write(self):
        """New linked spans need a compatible consumer before producer replacement."""
        self.assertEqual(self.exercise(), ["billing-read", "sink", "migration", "api", "maintenance"])

    def test_unknown_api_submit_is_not_repeated_and_maintenance_is_not_touched(self):
        """Failure coordinates require owned reconciliation, not another invocation."""
        self.assertEqual(self.exercise("api"), ["billing-read", "sink", "migration", "api"])

    def test_failed_dependency_preflight_performs_no_schema_or_worker_write(self):
        """An unreachable production bridge cannot turn into an unmetered rollout."""
        with patch.object(release.prior, "context"), \
             patch.object(release, "observe", return_value=({}, {"state": "allowed"}, object())), \
             patch.object(release, "billing_ready", side_effect=ValueError("production_billing_unverified")), \
             patch.object(release, "replace") as replace, patch.object(release, "migrate") as migrate:
            with self.assertRaises(ValueError):
                release.run("upgrade")
            replace.assert_not_called()
            migrate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
