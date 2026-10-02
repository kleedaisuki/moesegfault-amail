"""Synthetic staging admission, one-shot cutover and preserved backlog contracts."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import staging_rollout as rollout


class StagingRolloutTests(unittest.TestCase):
    """The provider bound never degenerates into a sleep or a backlog purge."""

    def environment(self) -> dict:
        """Build only synthetic fixed realm coordinates."""
        return {"GITHUB_REF": rollout.BRANCH, "GITHUB_ACTIONS": "true",
                "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123",
                "GITHUB_OUTPUT": str(ROOT / ".temp/unused-test-output"),
                "AMAIL_STAGING_DEPLOY_CONFIRM": rollout.CONFIRM,
                "CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "synthetic",
                "AMAIL_EXPECTED_WORKER_VERSION": "new-api", "AMAIL_TRACE_QUEUE_ID": "b" * 32}

    def predecessor(self, kind: str = "legacy") -> dict:
        """Return a projected snapshot without mail, addresses or credentials."""
        return {"source_sha": "a" * 40, "run_id": "123", "rollout": kind,
                "old_usage_model": "standard", "scripts": {rollout.API: {"version": "old-api"}}}

    def test_context_refuses_other_branches_or_confirmation(self):
        """No ordinary main action can invoke this staging-only writer."""
        for field, value in (("GITHUB_REF", "refs/heads/main"),
                             ("AMAIL_STAGING_DEPLOY_CONFIRM", "wrong"), ("GITHUB_ACTIONS", "false")):
            with patch.dict(os.environ, dict(self.environment(), **{field: value}), clear=True):
                with self.assertRaises(ValueError):
                    rollout.context()

    def test_immutable_runtime_model_supplies_the_positive_bound(self):
        """Use the documented version schema without requiring mutable settings."""
        for usage in ("standard", "unbound"):
            version = {"resources": {"script_runtime": {"usage_model": usage},
                                      "script": {"handlers": ["fetch", "scheduled"]}}}
            self.assertEqual(rollout.bounded_usage_model(version), usage)

    def test_bundled_unknown_or_wrong_field_cannot_borrow_a_modern_bound(self):
        """A mutable or wrong-path Standard value cannot mask immutable Bundled."""
        for version in ({"resources": {"script_runtime": {"usage_model": "bundled"},
                                       "script": {"usage_model": "standard"}}},
                        {"resources": {"script": {"usage_model": "standard"}}},
                        {"resources": {"script_runtime": {"usage_model": "unknown"}}}, {}):
            with self.assertRaises(ValueError):
                rollout.bounded_usage_model(version)

    def test_legacy_cutover_rechecks_capabilities_and_preserves_live_leases(self):
        """Documented bounds plus repeated provider pins admit, not elapsed age alone."""
        temporary = ROOT / ".temp"
        temporary.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary) as folder:
            witness = Path(folder) / "witness.json"
            with patch.dict(os.environ, self.environment(), clear=True), \
                 patch.object(rollout, "predecessor", return_value=self.predecessor()), \
                 patch.object(rollout, "deploy_maintenance", side_effect=("paused", "active")) as deploy, \
                 patch.object(rollout, "pin_api", return_value="match") as api, \
                 patch.object(rollout, "verify_maintenance") as maintenance, \
                 patch.object(rollout.graph, "held_send") as hold, \
                 patch.object(rollout, "lease_fences", return_value={"embedding_leases": 2, "projection_leases": 1}), \
                 patch.object(rollout.time, "monotonic", side_effect=(0, 0, rollout.WINDOW_SECONDS)), \
                 patch.object(rollout.time, "sleep") as sleep, patch.object(rollout, "WITNESS", witness):
                rollout.cutover()
            self.assertEqual([call.args[0] for call in deploy.call_args_list], [False, True])
            self.assertEqual(api.call_count, 2)
            self.assertEqual(maintenance.call_count, 2)
            self.assertEqual(hold.call_count, 2)
            sleep.assert_called_once_with(60)
            value = json.loads(witness.read_text())
            self.assertEqual(value["execution_leases_preserved"], {"embedding_leases": 2, "projection_leases": 1})
            self.assertNotIn("backlog", value)

    def test_changed_api_blocks_activation_without_replay(self):
        """A serving drift keeps maintenance paused even after a long observed age."""
        with patch.dict(os.environ, self.environment(), clear=True), \
             patch.object(rollout, "predecessor", return_value=self.predecessor()), \
             patch.object(rollout, "deploy_maintenance", return_value="paused") as deploy, \
             patch.object(rollout, "pin_api", return_value="deployment_changed"), \
             patch.object(rollout.time, "monotonic", return_value=0):
            with self.assertRaises(ValueError):
                rollout.cutover()
        deploy.assert_called_once_with(False)

    def test_split_replacement_does_not_repeat_legacy_wait(self):
        """The initial cutover cost is not a permanent constant factor."""
        with patch.dict(os.environ, self.environment(), clear=True), \
             patch.object(rollout, "predecessor", return_value=self.predecessor("split")), \
             patch.object(rollout, "deploy_maintenance") as deploy, patch.object(rollout.time, "sleep") as sleep:
            rollout.cutover()
        deploy.assert_called_once_with(True)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
