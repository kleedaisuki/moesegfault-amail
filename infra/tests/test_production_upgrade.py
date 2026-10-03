"""Bounded production rolling-upgrade contracts; no provider or deployment IO."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
sys.path.insert(0, str(ROOT / "infra/operator"))
import production_upgrade as upgrade
import direct_contact_health as health


class ProductionUpgradeTests(unittest.TestCase):
    """Live policy, owned graph and failure ordering remain authoritative."""

    def policy(self, state="allowed"):
        """Private synthetic operator fields are preserved, not rewritten."""
        return {"scope": "global", "owner_iss": "*", "owner_sub": "*", "state": state,
                "reason_code": "approved", "actor": "synthetic", "note_ref": "private-case", "updated_at": 1}

    def environment(self):
        """Only the existing trusted main/manual/protected lane admits writes."""
        return {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": upgrade.REPO,
                "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_RUN_ATTEMPT": "1", "AMAIL_PRODUCTION_ENVIRONMENT": "production",
                "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123",
                "AMAIL_PRODUCTION_GRAPH_FREEZE": "FREEZE_PRODUCTION_GRAPH_WRITERS",
                "AMAIL_PRODUCTION_GRAPH_CONFIRM": upgrade.CONFIRM,
                "AMAIL_UPGRADE_POLICY_FINGERPRINT": "a" * 64,
                "AMAIL_UPGRADE_EXTERNAL_FINGERPRINT": "b" * 64}

    def test_exact_global_policy_accepts_allowed_or_held_without_mutation(self):
        """The new read does not silently impose the historical hold requirement."""
        with patch.object(health, "DatabaseClient") as client:
            for state in ("allowed", "held"):
                row = self.policy(state)
                client.return_value.query.return_value = {"results": [row]}
                self.assertEqual(upgrade.graph.global_policy(), row)
                self.assertEqual(client.return_value.query.call_args.args[0],
                                 "SELECT * FROM send_policy WHERE scope='global'")
            client.return_value.query.return_value = {"results": [self.policy(), self.policy()]}
            with self.assertRaises(health.HealthError):
                upgrade.graph.global_policy()

    def test_policy_preservation_is_only_for_production_active_state(self):
        """Staging and activation cannot bypass their unchanged held contract."""
        for realm, state in (("staging", "active"), ("production", "paused")):
            with self.assertRaisesRegex(ValueError, "split_policy_unverified"):
                upgrade.graph.verify(realm, state, expected_policy=self.policy())

    def test_retained_subscription_matches_documented_destination_not_invented_row_type(self):
        """Use the API response shape; wrong selectors and extra delivery paths stop."""
        from check_staging_adapters import forwarding
        from ensure_email_events import EVENTS, ZONE
        provider = type("Provider", (), {"account": "a" * 32, "token": "synthetic"})()
        queues = [{"queue_name": "amail-sending-events", "queue_id": "b" * 32},
                  {"queue_name": "amail-sending-events-dlq", "queue_id": "c" * 32}]
        row = {"id": "synthetic-id", "name": "amail-sending-lifecycle", "enabled": True,
               "source": {"type": "email.sending", "zone_id": ZONE, "domain": "mail.moesegfault.dev",
                          "name": "returned display label"},
               "destination": {"type": "queues.queue", "queue_id": "b" * 32}, "events": EVENTS.split(",")}
        wrong_destination = deepcopy(row)
        wrong_destination["destination"]["type"] = "queues"
        wrong_scope = deepcopy(row)
        wrong_scope["source"]["domain"] = "other.invalid"
        extra_path = deepcopy(row)
        extra_path["id"] = "additional-path"
        extra_path["source"]["domain"] = "other.invalid"
        unknown_selector = deepcopy(row)
        unknown_selector["source"]["unknown_selector"] = "private"
        with patch.object(upgrade.retained, "verify_adapters", return_value=upgrade.ADAPTER_PINS), \
             patch.object(upgrade.retained.readback, "complete", return_value=queues), \
             patch.object(upgrade.graph, "direct_forward_snapshot", return_value={}), \
             patch.object(forwarding, "pages", return_value=[row]) as pages:
            self.assertEqual(upgrade.retained_snapshot(provider)["subscription"], [row])
            for rows in ([wrong_destination], [wrong_scope], [unknown_selector], [row, deepcopy(row)], [row, extra_path]):
                pages.return_value = rows
                with self.assertRaisesRegex(ValueError, "retained_subscription_unverified"):
                    upgrade.retained_snapshot(provider)

    def test_read_confirmation_cannot_authorize_write_or_wrong_context(self):
        """Inspection and replacement are different explicit capabilities."""
        env = self.environment()
        with patch.dict(os.environ, env, clear=True):
            upgrade.context("upgrade")
        env["AMAIL_PRODUCTION_GRAPH_CONFIRM"] = "INSPECT_PRODUCTION_V012"
        with patch.dict(os.environ, env, clear=True):
            upgrade.context("inspect")
            with self.assertRaises(ValueError):
                upgrade.context("upgrade")
        for key, value in (("GITHUB_REF", "refs/heads/candidate"), ("GITHUB_RUN_ATTEMPT", "2"),
                           ("AMAIL_PRODUCTION_GRAPH_FREEZE", "")):
            with patch.dict(os.environ, dict(self.environment(), **{key: value}), clear=True):
                with self.assertRaises(ValueError):
                    upgrade.context("upgrade")

    def test_no_mutation_after_failed_owned_preflight(self):
        """A failed serving/privacy/policy read never becomes a bootstrap."""
        with patch.object(upgrade, "context"), patch.object(upgrade, "observe", side_effect=ValueError("drift")), \
             patch.object(upgrade.subprocess, "run") as migrate, patch.object(upgrade, "replace") as replace:
            with self.assertRaises(ValueError):
                upgrade.run("upgrade")
            migrate.assert_not_called()
            replace.assert_not_called()

    def test_rolling_order_keeps_policy_and_does_not_replay_failed_second_submit(self):
        """Additive migration precedes API, old maintenance stays active until replaced."""
        order = []
        def replace(provider, role):
            order.append(role)
            if role == "maintenance":
                raise TimeoutError("ambiguous submit")
            return "a" * 8 + "-" + "a" * 4 + "-" + "a" * 4 + "-" + "a" * 4 + "-" + "a" * 12
        with patch.object(upgrade, "context"), patch.object(upgrade, "observe", return_value=({}, self.policy(), object())), \
             patch.object(upgrade, "journal"), \
             patch.object(upgrade, "require_artifact", side_effect=lambda value: order.append("artifact")), \
             patch.object(upgrade.subprocess, "run", side_effect=lambda *args, **kwargs:
                          (order.append("migration") or type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})())), \
             patch.object(upgrade.graph, "verify", side_effect=lambda *args, **kwargs: order.append("graph")), \
             patch.object(upgrade, "select_pins"), patch.object(upgrade, "replace", side_effect=replace) as submit:
            with self.assertRaises(TimeoutError):
                upgrade.run("upgrade")
            self.assertEqual(order, ["artifact", "migration", "graph", "api", "graph", "maintenance"])
            self.assertEqual(submit.call_count, 2)

    def test_owned_source_retention_rejects_runtime_change_and_dependency_edit(self):
        """Only Cargo package.version may differ in retained component trees."""
        result = type("Result", (), {"returncode": 0, "stdout": "workers/mail-ingress/src/lib.rs\n"})()
        with patch.object(upgrade.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(ValueError, "retained_source_changed"):
                upgrade.unchanged_components()

    def test_expected_policy_drift_blocks_before_next_write(self):
        """A concurrent operator hold/allow/note change is respected by stopping."""
        with patch.object(upgrade, "unchanged_components"), patch.object(upgrade.retained, "check_configs"), \
             patch.object(upgrade, "maintenance_config"), patch.object(upgrade.graph, "global_policy", return_value=self.policy()), \
             patch.dict(os.environ, {"AMAIL_UPGRADE_POLICY_FINGERPRINT": "f" * 64}), \
             patch.object(upgrade.graph, "verify") as verify:
            with self.assertRaisesRegex(ValueError, "policy_changed"):
                upgrade.observe(original=True)
            verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
