"""Privacy cutover exercises real orchestration order without provider writes."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import staging_rollout as rollout


class SemanticCutoverTests(unittest.TestCase):
    def environment(self) -> dict[str, str]:
        return {"GITHUB_REF": "refs/heads/codex/v0.3.1-semantic-consent",
                "GITHUB_ACTIONS": "true", "GITHUB_SHA": "a" * 40,
                "GITHUB_RUN_ID": "123", "GITHUB_OUTPUT": "unused",
                "AMAIL_STAGING_DEPLOY_CONFIRM": "RUN_STAGING_V031",
                "CLOUDFLARE_ACCOUNT_ID": "b" * 32, "CLOUDFLARE_API_TOKEN": "synthetic",
                "AMAIL_TRACE_QUEUE_ID": "c" * 32, "AMAIL_EXPECTED_WORKER_VERSION": "new-api"}

    def test_pause_pins_api_and_modern_scheduler_before_migration(self) -> None:
        observed: list[str] = []
        predecessor = {"rollout": "split", "scripts": {rollout.MAINTENANCE: {"version": "old-maintenance"}}}
        runtime = {"resources": {"script_runtime": {"usage_model": "standard"}}}
        with patch.dict(os.environ, self.environment(), clear=True), \
             patch.object(rollout, "predecessor", return_value=predecessor), \
             patch.object(rollout.capture, "readback", return_value=runtime), \
             patch.object(rollout, "deploy_maintenance", side_effect=lambda active: observed.append(f"deploy:{active}") or "paused"), \
             patch.object(rollout, "pin_api", side_effect=lambda *args, **kwargs: observed.append("api-pin") or "match"), \
             patch.object(rollout, "verify_maintenance", side_effect=lambda *args, **kwargs: observed.append("paused-pin")), \
             patch.object(rollout.graph, "held_send"), \
             patch.object(rollout.time, "monotonic", side_effect=[0, 0, rollout.WINDOW_SECONDS]), \
             patch.object(rollout.time, "sleep") as sleep, \
             patch.object(rollout, "write") as write:
            rollout.semantic_quiesce()
        self.assertEqual(observed, ["deploy:False", "api-pin", "paused-pin", "api-pin", "paused-pin"])
        sleep.assert_called_once_with(60)
        witness = write.call_args.args[1]
        self.assertEqual(witness["old_http_drain"], "NOT_CLAIMED")
        self.assertEqual(witness["observed_monotonic_seconds"], rollout.WINDOW_SECONDS)

    def test_unknown_cron_runtime_stops_before_first_write(self) -> None:
        predecessor = {"rollout": "split", "scripts": {rollout.MAINTENANCE: {"version": "old"}}}
        with patch.dict(os.environ, self.environment(), clear=True), \
             patch.object(rollout, "predecessor", return_value=predecessor), \
             patch.object(rollout.capture, "readback", return_value={}), \
             patch.object(rollout, "deploy_maintenance") as deploy:
            with self.assertRaisesRegex(ValueError, "staging_old_invocation_bound_unverified"):
                rollout.semantic_quiesce()
            deploy.assert_not_called()

    def test_api_drift_stops_without_witness_or_replay(self) -> None:
        predecessor = {"rollout": "split", "scripts": {rollout.MAINTENANCE: {"version": "old"}}}
        runtime = {"resources": {"script_runtime": {"usage_model": "standard"}}}
        with patch.dict(os.environ, self.environment(), clear=True), \
             patch.object(rollout, "predecessor", return_value=predecessor), \
             patch.object(rollout.capture, "readback", return_value=runtime), \
             patch.object(rollout, "deploy_maintenance", return_value="paused") as deploy, \
             patch.object(rollout, "pin_api", return_value="version_mismatch"), \
             patch.object(rollout, "write") as write:
            with self.assertRaisesRegex(ValueError, "staging_cutover_api_changed"):
                rollout.semantic_quiesce()
            deploy.assert_called_once_with(False)
            write.assert_not_called()

    def test_workflow_orders_failclosed_api_pause_then_migration(self) -> None:
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        body = source.split("  staging-worker:\n", 1)[1].split("  staging-ingress:\n", 1)[0]
        steps = ["Install fail-closed semantic API before consent migration",
                 "Pause consent-aware maintenance and bound old scheduled cohort",
                 "Apply staging D1 migrations only",
                 "Replace scheduled-only maintenance with bounded legacy cutover"]
        positions = [body.index(name) for name in steps]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("steps.guarded_api.outputs.version", body)

    def test_activation_requires_same_run_completed_witness(self) -> None:
        with patch.dict(os.environ, self.environment(), clear=True), \
             patch.object(rollout, "predecessor", return_value={"rollout": "split"}), \
             patch.object(rollout, "semantic_activation_ready", side_effect=ValueError("staging_semantic_witness_unverified")), \
             patch.object(rollout, "deploy_maintenance") as deploy:
            with self.assertRaisesRegex(ValueError, "staging_semantic_witness_unverified"):
                rollout.cutover()
            deploy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
