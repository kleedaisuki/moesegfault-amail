"""Normal production rollout preserves paid state and advances only owned roles."""
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
import ensure_email_events as subscriptions
import production_v030 as deploy
import pin_staging_mail as api_contract
import check_mail_maintenance as cron_contract


class ProductionV030Tests(unittest.TestCase):
    def environment(self, *, inspect: bool = False) -> dict[str, str]:
        return {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": deploy.prior.REPO,
                "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
                "AMAIL_PRODUCTION_ENVIRONMENT": "production", "GITHUB_RUN_ATTEMPT": "1",
                "AMAIL_PRODUCTION_GRAPH_FREEZE": "FREEZE_PRODUCTION_GRAPH_WRITERS",
                "AMAIL_PRODUCTION_CONFIRM": "INSPECT_PRODUCTION_V030" if inspect else "RUN_PRODUCTION_V030",
                "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123",
                "CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "synthetic"}

    def test_main_first_attempt_freeze_and_distinct_confirmation_are_required(self) -> None:
        for mode in ("inspect", "upgrade"):
            base = self.environment(inspect=mode == "inspect")
            with patch.dict(os.environ, base, clear=True):
                deploy.context(mode)
            for field, value in (("GITHUB_REF", "refs/heads/codex/v0.3.0-multitenant"),
                                 ("GITHUB_RUN_ATTEMPT", "2"), ("AMAIL_PRODUCTION_GRAPH_FREEZE", ""),
                                 ("AMAIL_PRODUCTION_CONFIRM", "RUN_PRODUCTION_SPLIT_UPGRADE")):
                with self.subTest(mode=mode, field=field), patch.dict(os.environ, {**base, field: value}, clear=True):
                    with self.assertRaises(ValueError):
                        deploy.context(mode)

    def test_v030_job_cannot_start_historical_writers_or_skip_source_admission(self) -> None:
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        body = source.split("  production-v030:\n", 1)[1].split("  production-inspect:\n", 1)[0]
        self.assertIn("inputs.confirm == 'RUN_PRODUCTION_V030' && github.ref == 'refs/heads/main'", body)
        self.assertIn("needs: [cli, worker, worker-build, site, dns, provider-live]", body)
        self.assertIn("environment: production", body)
        self.assertLess(body.index("python infra/ci/worker_artifact.py restore"),
                        body.index("python infra/deploy/production_v030.py upgrade"))
        for name in ("deploy-worker", "deploy-trace-sink", "deploy-ingress", "deploy-events", "deploy-site"):
            job = source.split(f"  {name}:\n", 1)[1].split("    needs:", 1)[0]
            self.assertIn("inputs.confirm != 'RUN_PRODUCTION_V030'", job)

    def test_only_exact_completed_usd_production_versions_may_omit_tmp_binding(self) -> None:
        for version, omitted in ((deploy.PINS["amail-mail"][1], True),
                                  ("12345678-1234-1234-1234-123456789abc", False)):
            with patch.object(api_contract, "_bindings_match", return_value=True) as compare:
                api_contract.bindings_match({}, version, phase="queue-api", queue_id="b" * 32, realm="production")
            self.assertEqual("MAIL_TMP_DOMAIN" not in compare.call_args.args[2], omitted)
        version = deploy.PINS["amail-mail-maintenance"][1]
        with patch.object(cron_contract, "serving_deployment", return_value=("deployment", version)), \
             patch.object(cron_contract.capture, "readback", return_value={}), \
             patch.object(cron_contract, "_bindings_match", return_value=False) as compare:
            with self.assertRaisesRegex(ValueError, "^maintenance_bindings_unverified$"):
                cron_contract.verify("production", "active", "a" * 32, "synthetic", version, "b" * 32)
        self.assertNotIn("MAIL_TMP_DOMAIN", compare.call_args.args[2])

    def model(self, stack: ExitStack, receipt: Path, actions: list[str]) -> dict[str, Mock]:
        provider = Mock(account="a" * 32, token="synthetic")
        stack.enter_context(patch.object(deploy, "FreshProvider", return_value=provider))
        stack.enter_context(patch.object(deploy, "unchanged_retained"))
        stack.enter_context(patch.object(deploy.prior.retained, "check_configs"))
        stack.enter_context(patch.object(deploy.prior.readback, "complete", return_value=[]))
        stack.enter_context(patch.object(deploy, "RECEIPT", receipt))
        stack.enter_context(patch.object(deploy, "require_artifact"))
        stack.enter_context(patch.object(deploy.prior, "journal"))
        stack.enter_context(patch.object(deploy.usd, "billing_ready"))

        def observe(*args: Any, **kwargs: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
            return {"graph": {"pins": args[1]}, "adapters": {}}, {"state": "allowed"}, {"private": "private-contact"}

        stack.enter_context(patch.object(deploy, "observe", side_effect=observe))
        calls = {}
        for name, value in (("domain_ready", None), ("migrate", 4), ("replace_events", "new-events")):
            def operation(*args: Any, label: str = name, result: Any = value) -> Any:
                actions.append(label)
                return result
            calls[name] = stack.enter_context(patch.object(deploy, name, side_effect=operation))

        def replace(provider: object, role: str) -> str:
            actions.append(role)
            return "new-" + role

        calls["replace"] = stack.enter_context(patch.object(deploy.usd, "replace", side_effect=replace))
        def subscribe(*args: str) -> None:
            actions.append("subscription")
        calls["subscription"] = stack.enter_context(patch.object(subscriptions, "ensure_subscription", side_effect=subscribe))
        return calls

    def test_inspection_has_no_writer_and_keeps_private_snapshot_out_of_receipt(self) -> None:
        (ROOT / ".temp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder, ExitStack() as stack:
            actions: list[str] = []
            receipt = Path(folder) / "receipt.json"
            self.model(stack, receipt, actions)
            with patch.dict(os.environ, self.environment(inspect=True), clear=True):
                deploy.run("inspect")
            self.assertEqual(actions, [])
            self.assertNotIn("private-contact", receipt.read_text())
            self.assertFalse(json.loads(receipt.read_text())["temporary_lifecycle"])

    def test_existing_local_attempt_is_refused_before_network_or_writes(self) -> None:
        (ROOT / ".temp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder:
            receipt = Path(folder) / "receipt.json"
            receipt.write_text("already-complete", encoding="utf-8")
            with patch.dict(os.environ, self.environment(), clear=True), patch.object(deploy, "RECEIPT", receipt), \
                 patch.object(deploy, "FreshProvider") as provider, self.assertRaises(ValueError):
                deploy.run("upgrade")
            provider.assert_not_called()

    def test_schema_events_subscription_maintenance_api_order_and_no_other_roles(self) -> None:
        (ROOT / ".temp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder, ExitStack() as stack:
            actions: list[str] = []
            receipt = Path(folder) / "receipt.json"
            calls = self.model(stack, receipt, actions)
            with patch.dict(os.environ, self.environment(), clear=True):
                deploy.run("upgrade")
            self.assertEqual(actions, ["domain_ready", "migrate", "replace_events", "subscription", "maintenance", "api"])
            calls["subscription"].assert_called_once_with("amail-sending-events", "amail-tmpaddr-lifecycle", "tmpaddr.moesegfault.dev")
            result = json.loads(receipt.read_text())
            self.assertTrue(result["temporary_lifecycle"])
            self.assertEqual(result["preserved_addresses"], 4)
            self.assertEqual(result["old_http_drain"], "NOT_CLAIMED")
            self.assertEqual(result["graph"]["pins"]["amail-trace-sink"], list(deploy.PINS["amail-trace-sink"]))

    def test_ambiguous_api_submit_is_not_retried_and_no_success_receipt_is_written(self) -> None:
        (ROOT / ".temp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder, ExitStack() as stack:
            actions: list[str] = []
            receipt = Path(folder) / "receipt.json"
            calls = self.model(stack, receipt, actions)
            calls["replace"].side_effect = ["new-maintenance", deploy.DeploymentFailure("submit_timeout_ambiguous")]
            with patch.dict(os.environ, self.environment(), clear=True), self.assertRaises(deploy.DeploymentFailure):
                deploy.run("upgrade")
            self.assertEqual(calls["replace"].call_count, 2)
            self.assertFalse(receipt.exists())

    def test_migration_preserves_owned_rows_and_never_uses_free_initialization(self) -> None:
        provider = Mock(account="a" * 32, token="synthetic")
        expected = sorted(path.name for path in (ROOT / "crates/mail-worker/migrations").glob("*.sql"))
        owned = {"private-mailbox": {"owner_sub": "private-owner", "created_at": 1}}
        with patch.object(deploy.usd, "DatabaseClient") as client, \
             patch.object(deploy.usd, "ownership", side_effect=[owned, owned]), \
             patch.object(deploy, "require_artifact"), patch.object(deploy.prior, "journal"), \
             patch.object(deploy.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as command:
            client.return_value.query.return_value = {"results": [{"name": name} for name in expected[:15]]}
            self.assertEqual(deploy.migrate(provider), 1)
            client.return_value.query.assert_called_once_with("SELECT name FROM d1_migrations ORDER BY id LIMIT 100")
            self.assertEqual(command.call_args.args[0], ["wrangler", "d1", "migrations", "apply", "MAIL_DB", "--remote"])

    def test_unknown_errors_are_closed_and_original_epoch_is_completed_usd(self) -> None:
        self.assertEqual(deploy.ORIGIN_RUN, "37660780530")
        self.assertEqual(deploy.PINS["amail-mail-maintenance"][1], "271e6d3f-9355-4804-b0c4-0d2426ad6c5a")
        output = io.StringIO()
        with patch.object(sys, "argv", ["production_v030.py", "inspect"]), \
             patch.object(deploy, "run", side_effect=ValueError("private-provider-prose")), redirect_stdout(output):
            self.assertEqual(deploy.main(), 1)
        self.assertNotIn("private", output.getvalue())


if __name__ == "__main__":
    unittest.main()
