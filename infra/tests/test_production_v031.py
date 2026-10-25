"""Forward semantic-consent rollout keeps customer state and cannot replay writes."""
from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import production_v031 as deploy


class ProductionV031Tests(unittest.TestCase):
    def setUp(self) -> None:
        (ROOT / ".temp").mkdir(exist_ok=True)

    def environment(self, mode: str = "upgrade") -> dict[str, str]:
        return {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": deploy.prior.REPO,
                "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
                "AMAIL_PRODUCTION_ENVIRONMENT": "production", "GITHUB_RUN_ATTEMPT": "1",
                "AMAIL_PRODUCTION_GRAPH_FREEZE": "FREEZE_PRODUCTION_GRAPH_WRITERS",
                "AMAIL_PRODUCTION_CONFIRM": "INSPECT_PRODUCTION_V031" if mode == "inspect" else "RUN_PRODUCTION_V031",
                "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123",
                "CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "synthetic"}

    def test_only_explicit_trusted_first_attempt_can_inspect_or_mutate(self) -> None:
        for mode in ("inspect", "upgrade"):
            base = self.environment(mode)
            with patch.dict(os.environ, base, clear=True):
                deploy.context(mode)
            for key, value in (("GITHUB_REF", "refs/heads/codex/v0.3.1-semantic-consent"),
                               ("GITHUB_RUN_ATTEMPT", "2"), ("AMAIL_PRODUCTION_GRAPH_FREEZE", ""),
                               ("AMAIL_PRODUCTION_CONFIRM", "RUN_PRODUCTION_V030")):
                with self.subTest(mode=mode, key=key), patch.dict(os.environ, {**base, key: value}, clear=True):
                    with self.assertRaisesRegex(ValueError, "^production_v031_context_unverified$"):
                        deploy.context(mode)

    def test_same_run_artifact_gates_and_historical_writer_exclusion(self) -> None:
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        body = source.split("  production-v031:\n", 1)[1].split("  production-v030:\n", 1)[0]
        self.assertIn("inputs.confirm == 'RUN_PRODUCTION_V031' && github.ref == 'refs/heads/main'", body)
        self.assertIn("needs: [cli, worker, worker-build, site, dns, provider-live]", body)
        self.assertIn("environment: production", body)
        self.assertLess(body.index("python infra/ci/worker_artifact.py restore"),
                        body.index("python infra/deploy/production_v031.py upgrade"))
        for name in ("deploy-worker", "deploy-trace-sink", "deploy-ingress", "deploy-events", "deploy-site"):
            job = source.split(f"  {name}:\n", 1)[1].split("    needs:", 1)[0]
            self.assertIn("inputs.confirm != 'RUN_PRODUCTION_V031'", job)
        inspect = source.split("  production-v031-inspect:\n", 1)[1].split("  production-v031:\n", 1)[0]
        self.assertIn("INSPECT_PRODUCTION_V031", inspect)
        self.assertNotIn("wrangler", inspect)

    def model(self, stack: ExitStack, receipt: Path, actions: list[str]) -> dict[str, Mock]:
        provider = Mock(account="a" * 32, token="synthetic")
        stack.enter_context(patch.object(deploy, "FreshProvider", return_value=provider))
        stack.enter_context(patch.object(deploy, "RECEIPT", receipt))
        for obj, name in ((deploy, "unchanged_adapters"), (deploy.prior.retained, "check_configs"),
                          (deploy.prior.readback, "complete"), (deploy, "require_artifact"),
                          (deploy.prior, "journal"), (deploy.usd, "billing_ready"),
                          (deploy, "recorded_schema")):
            stack.enter_context(patch.object(obj, name))
        stack.enter_context(patch.object(deploy, "old_usage_model", return_value="standard"))
        stack.enter_context(patch.object(deploy, "health_ready"))

        def observe(provider: object, pins: dict[str, Any], *args: Any, **kwargs: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
            return {"graph": {"pins": dict(pins)}, "adapters": {}}, {"state": "allowed"}, {"contact": "private-snapshot"}

        stack.enter_context(patch.object(deploy, "observe", side_effect=observe))
        calls: dict[str, Mock] = {}
        for name, result in (("pause_maintenance", "paused-maintenance"), ("quiesce", {"old_http_drain": "NOT_CLAIMED"}), ("migrate", 11)):
            def operation(*args: Any, label: str = name, value: Any = result) -> Any:
                actions.append(label)
                return value
            calls[name] = stack.enter_context(patch.object(deploy, name, side_effect=operation))

        def replace(provider: object, role: str) -> str:
            actions.append(role)
            return "new-" + role

        calls["replace"] = stack.enter_context(patch.object(deploy.usd, "replace", side_effect=replace))
        return calls

    def test_inspection_has_no_writes_or_private_snapshot_output(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder, ExitStack() as stack:
            receipt, actions = Path(folder) / "receipt.json", []
            self.model(stack, receipt, actions)
            with patch.dict(os.environ, self.environment("inspect"), clear=True):
                deploy.run("inspect")
            self.assertEqual(actions, [])
            self.assertNotIn("private-snapshot", receipt.read_text(encoding="utf-8"))
            self.assertEqual(json.loads(receipt.read_text())["origin_run"], "40116604490")

    def test_sink_api_pause_bound_schema_activation_order_preserves_adapters(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder, ExitStack() as stack:
            receipt, actions = Path(folder) / "receipt.json", []
            self.model(stack, receipt, actions)
            with patch.dict(os.environ, self.environment(), clear=True):
                deploy.run("upgrade")
            self.assertEqual(actions, ["sink", "api", "pause_maintenance", "quiesce", "migrate", "maintenance"])
            result = json.loads(receipt.read_text())
            self.assertEqual(result["preserved_addresses"], 11)
            self.assertEqual(result["semantic_default_after_upgrade"], "disabled")
            self.assertTrue(result["schema_migration_applied"])
            self.assertEqual(result["old_http_drain"], "NOT_CLAIMED")

    def test_ambiguous_submit_stops_without_replay_or_success_receipt(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder, ExitStack() as stack:
            receipt, actions = Path(folder) / "receipt.json", []
            calls = self.model(stack, receipt, actions)
            calls["replace"].side_effect = ["new-sink", deploy.DeploymentFailure("submit_timeout_ambiguous")]
            with patch.dict(os.environ, self.environment(), clear=True), self.assertRaises(deploy.DeploymentFailure):
                deploy.run("upgrade")
            self.assertEqual(calls["replace"].call_count, 2)
            calls["pause_maintenance"].assert_not_called()
            calls["migrate"].assert_not_called()
            self.assertFalse(receipt.exists())

    def test_old_local_attempt_refuses_before_any_provider_reads(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder:
            receipt = Path(folder) / "receipt.json"
            receipt.write_text("complete", encoding="utf-8")
            with patch.object(deploy, "RECEIPT", receipt), patch.object(deploy, "FreshProvider") as provider, \
                 patch.dict(os.environ, self.environment(), clear=True), self.assertRaises(ValueError):
                deploy.run("upgrade")
            provider.assert_not_called()

    def test_only_0018_applies_and_vectors_ownership_default_off_are_verified(self) -> None:
        provider = Mock(account="a" * 32, token="synthetic")
        owned = {"private-mailbox": {"owner_sub": "private-owner", "created_at": 1}}
        with patch.object(deploy, "recorded_schema") as schema, \
             patch.object(deploy, "embedding_count", side_effect=[7, 7]), \
             patch.object(deploy, "database") as client, \
             patch.object(deploy.usd, "ownership", side_effect=[owned, owned]), \
             patch.object(deploy, "require_artifact"), patch.object(deploy.prior, "journal"), \
             patch.object(deploy.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as command:
            client.return_value.query.return_value = {"results": [{"enabled": 0}]}
            self.assertEqual(deploy.migrate(provider), 1)
            self.assertEqual([call.args[1] for call in schema.call_args_list], [17, 18])
            self.assertEqual(command.call_args.args[0], ["wrangler", "d1", "migrations", "apply", "MAIL_DB", "--remote"])

    def test_migration_rejects_unexpected_vector_loss(self) -> None:
        with patch.object(deploy, "recorded_schema"), patch.object(deploy, "embedding_count", side_effect=[7, 6]), \
             patch.object(deploy, "database") as client, patch.object(deploy.usd, "ownership", return_value={}), \
             patch.object(deploy, "require_artifact"), patch.object(deploy.prior, "journal"), \
             patch.object(deploy.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")):
            client.return_value.query.return_value = {"results": [{"enabled": 0}]}
            with self.assertRaisesRegex(ValueError, "^production_v031_embeddings_unverified$"):
                deploy.migrate(Mock())

    def test_pause_preserves_allowed_policy_without_authorizing_other_graph_states(self) -> None:
        policy = {"state": "allowed"}
        for realm, state, crons in (("staging", "paused", ()), ("production", "prepared", ()),
                                    ("production", "paused", ("*/5 * * * *",))):
            with self.subTest(realm=realm, state=state), self.assertRaisesRegex(ValueError, "^split_policy_unverified$"):
                deploy.prior.graph.verify(realm, state, expected_policy=policy, old_crons=crons)
        with patch.object(deploy.prior.graph, "api_config", side_effect=ValueError("later-contract-check")), \
             self.assertRaisesRegex(ValueError, "^later-contract-check$"):
            deploy.prior.graph.verify("production", "paused", expected_policy=policy)

    def test_quiescence_keeps_pins_and_actual_paused_cron_through_platform_bound(self) -> None:
        provider = Mock(account="a" * 32, token="synthetic")
        with patch.object(deploy, "observe") as observe, patch.object(deploy.legacy, "select"), \
             patch.object(deploy.prior.graph, "serving", return_value=dict(deploy.PINS)), \
             patch.object(deploy.prior.retained.maintenance, "verify") as verify, \
             patch.object(deploy.prior.graph, "global_policy", return_value={"state": "allowed"}), \
             patch.object(deploy.time, "monotonic", side_effect=[0, 0, deploy.WINDOW_SECONDS]), \
             patch.object(deploy.time, "sleep") as sleep:
            witness = deploy.quiesce(provider, dict(deploy.PINS), {"state": "allowed"}, {})
        self.assertEqual(observe.call_count, 2)
        self.assertEqual(verify.call_count, 2)
        sleep.assert_called_once_with(60)
        self.assertEqual(witness["observed_monotonic_seconds"], 1860)
        self.assertEqual(witness["old_http_drain"], "NOT_CLAIMED")

    def test_only_modern_usage_models_admit_old_scheduled_bound(self) -> None:
        for usage in (None, "bundled", "standard", "unbound"):
            row = {"resources": {"script_runtime": {"usage_model": usage}}}
            with self.subTest(usage=usage), patch.object(deploy.prior.graph.capture, "readback", return_value=row):
                if usage in ("standard", "unbound"):
                    self.assertEqual(deploy.old_usage_model(Mock()), usage)
                else:
                    with self.assertRaisesRegex(ValueError, "^production_v031_old_invocation_bound_unverified$"):
                        deploy.old_usage_model(Mock())

    def test_unknown_errors_cannot_publish_provider_prose(self) -> None:
        output = io.StringIO()
        with patch.object(sys, "argv", ["production_v031.py", "inspect"]), \
             patch.object(deploy, "run", side_effect=ValueError("private-provider-prose")), redirect_stdout(output):
            self.assertEqual(deploy.main(), 1)
        self.assertNotIn("private", output.getvalue())

    def test_public_health_requires_exact_version_without_redirect_or_authentication(self) -> None:
        response = Mock(status=200)
        response.read.return_value = b'{"status":"ok","version":"0.3.1","api_version":2}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch.object(deploy.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = response
            deploy.health_ready()
        request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://mail.moesegfault.dev/health")
        self.assertIsNone(request.get_header("Authorization"))
        self.assertIs(opener.call_args.args[0], deploy.NoRedirect)


if __name__ == "__main__":
    unittest.main()
