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


if __name__ == "__main__":
    unittest.main()
