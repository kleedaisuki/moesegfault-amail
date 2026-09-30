"""Hosted synthetic secret-file and ambiguous role-deployment contracts."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import deploy_staging_role_monitor as deployer

VERSION = "11111111-1111-4111-8111-111111111111"


class RoleDeployTests(unittest.TestCase):
    """A single staging-only deployment never prints/retries sensitive provider output."""

    def environment(self) -> dict:
        """Use synthetic secret placeholders, never a real confidential destination."""
        return {"AMAIL_ROLE_ROLLOUT_CONFIRM": deployer.CONFIRM,
                "ROLE_FORWARD_DESTINATION": "synthetic@example.invalid",
                "CF_EMAIL_ROUTING_TOKEN": "synthetic-token", "CLOUDFLARE_ACCOUNT_ID": "a" * 32}

    def test_secret_file_is_repo_scoped_and_removed_after_all_outcomes(self) -> None:
        """Even ambiguous provider failure does not leave destination/token on disk."""
        temporary = ROOT / ".temp"
        temporary.mkdir(exist_ok=True)
        for output, status, accepted in ((f"Current Version ID: {VERSION}\n", 0, True),
                                         (f"Current Version ID: {VERSION}\n" * 2, 0, False),
                                         ("private-provider-error", 1, False)):
            with tempfile.TemporaryDirectory(dir=temporary) as root:
                expected_root = Path(root)
                (expected_root / "workers/role-monitor").mkdir(parents=True)
                seen = []
                def run(command, **kwargs):
                    self.assertEqual(command[:5], ["wrangler", "deploy", "--env", "staging", "--secrets-file"])
                    self.assertEqual(kwargs["cwd"], expected_root / "workers/role-monitor")
                    self.assertTrue(kwargs["capture_output"])
                    path = Path(command[-1])
                    seen.append(path)
                    self.assertEqual(path.parent, expected_root / ".temp")
                    self.assertEqual(json.loads(path.read_text())["ROLE_FORWARD_DESTINATION"], "synthetic@example.invalid")
                    return subprocess.CompletedProcess(command, status, output, "private-provider-detail")
                with patch.object(deployer, "ROOT", expected_root), \
                        patch.dict(os.environ, self.environment()), \
                        patch.object(deployer.subprocess, "run", side_effect=run) as call:
                    if accepted:
                        self.assertEqual(deployer.deploy(), VERSION)
                    else:
                        with self.assertRaises(ValueError):
                            deployer.deploy()
                    self.assertEqual(call.call_count, 1)
                self.assertEqual(len(seen), 1)
                self.assertFalse(seen[0].exists())

    def test_confirmation_precedes_mutation(self) -> None:
        """Missing or unrelated confirmation cannot write secrets or deploy."""
        with patch.dict(os.environ, {**self.environment(), "AMAIL_ROLE_ROLLOUT_CONFIRM": "wrong"}), \
                patch.object(deployer.tempfile, "mkstemp") as write, \
                patch.object(deployer.subprocess, "run") as run, self.assertRaises(ValueError):
            deployer.deploy()
        write.assert_not_called()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
