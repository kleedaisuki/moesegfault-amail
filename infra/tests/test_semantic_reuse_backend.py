"""Only migration/API/maintenance advance; no schedules, sink or release changes."""
from __future__ import annotations

from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
sys.path.insert(0, str(ROOT / "infra/ci"))
import mail_backend_artifact as artifact
import semantic_reuse_backend as deploy


class SemanticReuseDeploymentTests(unittest.TestCase):
    def test_ingress_only_deploy_inherits_all_other_secrets(self) -> None:
        submitted: list[dict[str, str]] = []
        def submit(command: list[str], *args: object, **kwargs: object) -> str:
            path = Path(command[command.index("--secrets-file") + 1])
            submitted.append(json.loads(path.read_text(encoding="utf-8")))
            return "new-api"
        with patch.dict(os.environ, {"INGRESS_SECRET": "synthetic-staging-secret", "CLOUDFLARE_ACCOUNT_ID": "a",
                                     "CLOUDFLARE_API_TOKEN": "x"}, clear=True), \
             patch.object(deploy, "require_artifact"), patch.object(deploy.previous.prior, "journal"), \
             patch.object(deploy, "submit", side_effect=submit), patch.object(deploy, "pin_api", return_value="match"):
            deploy.replace("staging", "api", ingress_only=True)
        self.assertEqual(submitted, [{"INGRESS_SECRET": "synthetic-staging-secret"}])

    def test_explicit_ingress_restoration_writes_only_api_configuration(self) -> None:
        (ROOT / ".temp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder, ExitStack() as stack:
            root = Path(folder)
            (root / ".temp").mkdir()
            stack.enter_context(patch.object(deploy, "ROOT", root))
            stack.enter_context(patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "a", "CLOUDFLARE_API_TOKEN": "x",
                "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "124", "AMAIL_STAGING_INGRESS_RESTORE": "true"}))
            stack.enter_context(patch.object(artifact, "context"))
            stack.enter_context(patch.object(artifact, "ADMISSION", Mock(is_file=Mock(return_value=True))))
            stack.enter_context(patch.object(artifact, "original_identity", return_value={"source_sha": artifact.PARTIAL_SOURCE, "run_id": artifact.PARTIAL_RUN}))
            stack.enter_context(patch.object(deploy, "require_artifact"))
            stack.enter_context(patch.object(deploy, "observe", return_value=({"retained": {}, "graph": {}}, {})))
            stack.enter_context(patch.object(deploy, "DatabaseClient"))
            schema = stack.enter_context(patch.object(deploy, "schema"))
            write = stack.enter_context(patch.object(deploy, "replace", return_value="new-api"))
            migration = stack.enter_context(patch.object(deploy.subprocess, "run"))
            deploy.restore_staging_ingress()
            write.assert_called_once_with("staging", "api", ingress_only=True)
            migration.assert_not_called()
            self.assertEqual(schema.call_args.args[-1], 19)
            value = json.loads((root / ".temp/semantic-reuse-ingress-restore.json").read_text())
            self.assertEqual(value["credential_source"], "INGRESS_SECRET_STAGING")
            self.assertEqual(value["old_api_version"], "75bbcb55-e6f5-42e3-b65b-acb6dbc990c9")
            self.assertEqual(value["new_api_version"], "new-api")

    def test_completed_staging_verification_never_repeats_writes(self) -> None:
        (ROOT / ".temp").mkdir(exist_ok=True)
        origin = {"schema": "semantic-index-reuse/v1", "realm": "staging", "migration": 19,
                  "run_id": deploy.COMPLETED_STAGING_RUN, "source_sha": deploy.COMPLETED_STAGING_SOURCE,
                  "api_version": "75bbcb55-e6f5-42e3-b65b-acb6dbc990c9",
                  "maintenance_version": "0ee61a70-4040-40fe-a117-48d41c92f2de",
                  "sink_version": deploy.STAGING["amail-trace-sink-staging"], "cron_changed": False,
                  "retained_fingerprint": deploy.previous.prior.digest({}),
                  "policy_fingerprint": deploy.previous.prior.digest({})}
        run = {"id": int(deploy.COMPLETED_STAGING_RUN), "head_sha": deploy.COMPLETED_STAGING_SOURCE,
               "head_branch": artifact.BRANCH, "repository": {"full_name": artifact.accepted.REPO},
               "status": "completed", "conclusion": "success", "event": "workflow_dispatch",
               "path": ".github/workflows/ci.yml", "run_attempt": 1}
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder, ExitStack() as stack:
            root = Path(folder)
            path = root / ".temp/ci/semantic-reuse-completed/semantic-reuse-staging.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(origin), encoding="utf-8")
            stack.enter_context(patch.object(deploy, "ROOT", root))
            stack.enter_context(patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "a", "CLOUDFLARE_API_TOKEN": "x",
                                                       "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "124"}))
            stack.enter_context(patch.object(artifact, "context"))
            stack.enter_context(patch.object(artifact, "original_identity"))
            stack.enter_context(patch.object(artifact.accepted, "github", return_value=run))
            stack.enter_context(patch.object(artifact.accepted, "successful_jobs"))
            stack.enter_context(patch.object(artifact.accepted, "runtime_closure"))
            stack.enter_context(patch.object(deploy, "observe", return_value=({"retained": {}, "graph": {}}, {})))
            stack.enter_context(patch.object(deploy, "DatabaseClient"))
            schema = stack.enter_context(patch.object(deploy, "schema"))
            write = stack.enter_context(patch.object(deploy, "replace"))
            migration = stack.enter_context(patch.object(deploy.subprocess, "run"))
            deploy.verify_completed()
            schema.assert_called_once()
            write.assert_not_called()
            migration.assert_not_called()
            value = json.loads((root / ".temp/semantic-reuse-staging.json").read_text())
            self.assertEqual(value["run_id"], "124")
            self.assertEqual(value["original_deployment_run"], deploy.COMPLETED_STAGING_RUN)
            self.assertEqual(value["completion_mode"], "read_only")

    def test_staging_api_capture_uses_staging_pin_not_production_capture_writer(self) -> None:
        with patch.dict(os.environ, {name: "synthetic" for name in
                ("OPENROUTER_API_KEY", "CF_EMAIL_ROUTING_TOKEN", "BILLING_SERVICE_KEY", "INGRESS_SECRET",
                 "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN")}), \
             patch.object(deploy, "require_artifact"), \
             patch.object(deploy.previous.prior, "journal"), \
             patch.object(deploy, "submit", return_value="new-api"), \
             patch.object(deploy, "pin_api", return_value="match") as pin, \
             patch.object(deploy.previous.prior.readback, "capture_off") as production_capture:
            self.assertEqual(deploy.replace("staging", "api"), "new-api")
            pin.assert_called_once()
            production_capture.assert_not_called()

    def test_production_observe_uses_the_existing_adapter_verifier(self) -> None:
        with patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "a", "CLOUDFLARE_API_TOKEN": "synthetic"}), \
             patch.object(deploy.previous.prior.graph, "global_policy", return_value={"state": "allowed"}), \
             patch.object(deploy.previous.prior.graph, "verify", return_value={"pins": {}}), \
             patch.object(deploy.previous, "FreshProvider"), \
             patch.object(deploy.adapters, "lifecycle_snapshot", return_value={}), \
             patch.object(deploy.previous.prior.graph, "direct_forward_snapshot", return_value={}), \
             patch.object(deploy.previous.legacy, "adapter_snapshot", return_value={}) as retained:
            deploy.observe("production", dict(deploy.PRODUCTION))
            retained.assert_called_once()

    def test_migration_fence_precedes_only_api_and_maintenance_without_cold_cron(self) -> None:
        (ROOT / ".temp").mkdir(exist_ok=True)
        events: list[str] = []
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder, ExitStack() as stack:
            stack.enter_context(patch.object(deploy, "ROOT", Path(folder)))
            (Path(folder) / ".temp").mkdir()
            stack.enter_context(patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "a", "CLOUDFLARE_API_TOKEN": "x",
                                                       "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123"}))
            stack.enter_context(patch.object(artifact, "context"))
            stack.enter_context(patch.object(deploy, "require_artifact"))
            stack.enter_context(patch.object(deploy, "observe", return_value=({"retained": {}, "graph": {}}, {})))
            stack.enter_context(patch.object(deploy, "DatabaseClient"))
            stack.enter_context(patch.object(deploy.previous.prior, "journal"))
            stack.enter_context(patch.object(deploy, "schema", side_effect=lambda _db, _realm, count: events.append(f"schema{count}")))
            stack.enter_context(patch.object(deploy.subprocess, "run", side_effect=lambda *a, **k: events.append("migration") or Mock(returncode=0)))
            stack.enter_context(patch.object(deploy, "replace", side_effect=lambda _realm, role: events.append(role) or role))
            deploy.run("staging")
            self.assertEqual(events, ["schema18", "migration", "schema19", "api", "maintenance"])
            receipt = json.loads((Path(folder) / ".temp/semantic-reuse-staging.json").read_text())
            self.assertFalse(receipt["cron_changed"])
            self.assertEqual(receipt["migration"], 19)

    def test_named_partial_runs_only_remaining_maintenance(self) -> None:
        (ROOT / ".temp").mkdir(exist_ok=True)
        events: list[str] = []
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder, ExitStack() as stack:
            stack.enter_context(patch.object(deploy, "ROOT", Path(folder)))
            (Path(folder) / ".temp").mkdir()
            stack.enter_context(patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "a", "CLOUDFLARE_API_TOKEN": "x",
                                                       "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123"}))
            stack.enter_context(patch.object(artifact, "context"))
            stack.enter_context(patch.object(artifact, "ADMISSION", Mock(is_file=Mock(return_value=True))))
            stack.enter_context(patch.object(deploy, "require_artifact"))
            observe = stack.enter_context(patch.object(deploy, "observe", return_value=({"retained": {}, "graph": {}}, {})))
            stack.enter_context(patch.object(deploy, "DatabaseClient"))
            stack.enter_context(patch.object(deploy.previous.prior, "journal"))
            stack.enter_context(patch.object(deploy, "schema", side_effect=lambda _db, _realm, count: events.append(f"schema{count}")))
            migration = stack.enter_context(patch.object(deploy.subprocess, "run"))
            stack.enter_context(patch.object(deploy, "replace", side_effect=lambda _realm, role: events.append(role) or role))
            deploy.run("staging", resume=True)
            self.assertEqual(events, ["schema19", "maintenance"])
            migration.assert_not_called()
            self.assertEqual(observe.call_args_list[0].args[1]["amail-mail-staging"], "75bbcb55-e6f5-42e3-b65b-acb6dbc990c9")


if __name__ == "__main__":
    unittest.main()
