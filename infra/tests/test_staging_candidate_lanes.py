"""Candidate coordinates may select staging, never cross-confirm another lane."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
from staging_candidate import LANES, reviewed
import staging_rollout as rollout


class CandidateLaneTests(unittest.TestCase):
    def test_temporary_domain_dns_parser_is_installed_before_each_helper(self) -> None:
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for job, following, relative in (("staging-inspect", "staging-e2e", ""),
                                          ("staging-worker", "staging-ingress", "../../")):
            body = source.split(f"  {job}:\n", 1)[1].split(f"  {following}:\n", 1)[0]
            install = f"python -m pip install --only-binary=:all: -r {relative}infra/dns/requirements.txt"
            helper = "python infra/provider/ensure_tmpaddr_staging.py"
            self.assertLess(body.index(install), body.index(helper))

    def test_manual_dependency_cache_writes_stay_on_reviewed_refs(self) -> None:
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        conditions = [line.strip() for line in source.splitlines()
                      if "save-if:" in line or ("github.event_name" in line
                          and "steps.worker-bundler-cache.outputs.cache-hit != 'true'" in line)]
        self.assertEqual(len(conditions), 3)
        for condition in conditions:
            self.assertIn("(github.event_name == 'push' || github.event_name == 'workflow_dispatch') &&", condition)
            self.assertNotIn("pull_request", condition)
            for ref in ("refs/heads/main", *LANES):
                self.assertIn(ref, condition)
        self.assertEqual(source.count("cache-workspace-crates: false"), 2)
        self.assertEqual(source.count("cache-on-failure: true"), 2)

    def test_each_lane_requires_its_own_action_confirmation(self) -> None:
        for ref, confirmations in LANES.items():
            for read_only in (False, True):
                with self.subTest(ref=ref, read_only=read_only):
                    self.assertTrue(reviewed(ref, confirmations[int(read_only)], read_only=read_only))
                    self.assertFalse(reviewed(ref, confirmations[int(not read_only)], read_only=read_only))
                    for other_ref, other_confirmations in LANES.items():
                        if other_ref != ref:
                            self.assertFalse(reviewed(ref, other_confirmations[int(read_only)], read_only=read_only))
        self.assertFalse(reviewed("refs/heads/main", "RUN_STAGING_V030"))

    def test_v030_rollout_context_admits_only_paired_hosted_coordinates(self) -> None:
        environment = {"GITHUB_ACTIONS": "true", "GITHUB_OUTPUT": "unused",
                       "GITHUB_REF": "refs/heads/codex/v0.3.0-multitenant",
                       "AMAIL_STAGING_DEPLOY_CONFIRM": "RUN_STAGING_V030",
                       "AMAIL_STAGING_INSPECT_CONFIRM": "INSPECT_STAGING_V030"}
        with patch.dict(os.environ, environment, clear=True):
            rollout.context()
            rollout.context(read_only=True)
        with patch.dict(os.environ, {**environment, "AMAIL_STAGING_DEPLOY_CONFIRM": "RUN_STAGING_V020"}, clear=True):
            with self.assertRaises(ValueError):
                rollout.context()


if __name__ == "__main__":
    unittest.main()
