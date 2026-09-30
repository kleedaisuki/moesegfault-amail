"""Synthetic fail-closed checks for one hosted alias reconciliation."""

from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
from io import StringIO
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from workflow_source import job_block


HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location(
    "staging_hosted_alias_reconcile", HERE / "staging_hosted_alias_reconcile.py"
)
assert SPEC and SPEC.loader
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)

ENV = {
    "STAGING_E2E_PASSWORD": "private-fixture-password",
    "CF_EMAIL_ROUTING_TOKEN": "private-route-token",
    "CLOUDFLARE_API_TOKEN": "private-api-token",
    "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
}


class HostedAliasReconciliationTests(unittest.TestCase):
    """Ensure exact run identity and both control-plane reads are required."""

    def run_gate(self, argv: list[str], inventory: list[dict], rows: list[dict]) -> tuple[int, str]:
        """Exercise the script with synthetic private provider responses."""

        with patch.dict(os.environ, ENV, clear=True), patch.object(CHECK.sys, "argv", argv), patch.object(
            CHECK, "rules", return_value=inventory
        ), patch.object(CHECK, "d1_row", return_value=rows), redirect_stdout(StringIO()) as output:
            return CHECK.main(), output.getvalue()

    def test_clean_exact_run_alias(self) -> None:
        """A complete inventory and absent/retired D1 row pass without leaking alias."""

        argv = ["script", CHECK.CONFIRM, "36533465672", "1"]
        code, output = self.run_gate(argv, [{"matchers": []}], [])
        self.assertEqual(code, 0)
        self.assertEqual(output.splitlines(), [
            "hosted_alias_route:absent", "hosted_alias_row:clean", "hosted_alias_gate:clean"
        ])
        self.assertNotIn("e2e-", output)
        target = CHECK.alias(ENV["STAGING_E2E_PASSWORD"], "36533465672", "1")
        with patch.dict(os.environ, ENV, clear=True), patch.object(CHECK.sys, "argv", argv), patch.object(
            CHECK, "rules", return_value=[]
        ), patch.object(CHECK, "d1_row", return_value=[]) as d1, redirect_stdout(StringIO()):
            self.assertEqual(CHECK.main(), 0)
        d1.assert_called_once_with("a" * 32, "private-api-token", target)

    def test_route_and_d1_failure_are_independent(self) -> None:
        """One unreadable control plane cannot mask a known dirty state in the other."""

        argv = ["script", CHECK.CONFIRM, "36533465672", "1"]
        target = CHECK.alias(ENV["STAGING_E2E_PASSWORD"], "36533465672", "1")
        code, output = self.run_gate(argv, [{"matchers": [{"type": "literal", "field": "to", "value": target}]}], [])
        self.assertEqual(code, 1)
        self.assertIn("hosted_alias_gate:not_clean", output)
        with patch.dict(os.environ, ENV, clear=True), patch.object(CHECK.sys, "argv", argv), patch.object(
            CHECK, "rules", side_effect=RuntimeError("SECRET_ALIAS")
        ), patch.object(CHECK, "d1_row", return_value=[{
            "state": "active", "cf_rule_id": None, "needs_reconcile": 0,
            "owner_iss": "https://identity-staging.moesegfault.dev", "owner_sub": "owner",
        }]), redirect_stdout(StringIO()) as output:
            self.assertEqual(CHECK.main(), 1)
        self.assertEqual(output.getvalue().splitlines(), [
            "hosted_alias_route:unverified", "hosted_alias_row:not_clean", "hosted_alias_gate:not_clean"
        ])
        self.assertNotIn("SECRET_ALIAS", output.getvalue())

    def test_bad_coordinates_do_not_read_secrets_or_provider(self) -> None:
        """Reject missing/ambiguous run metadata before any external read."""

        for args in (["script", CHECK.CONFIRM, "0", "1"],
                     ["script", CHECK.CONFIRM, "123", "01"],
                     ["script", CHECK.CONFIRM, "123", "1000"],
                     ["script", CHECK.CONFIRM, "123"],
                     ["script", "WRONG", "123", "1"]):
            with self.subTest(args=args), patch.dict(os.environ, {}, clear=True), patch.object(
                CHECK.sys, "argv", args
            ), patch.object(CHECK, "rules") as inventory, redirect_stdout(StringIO()) as output:
                self.assertEqual(CHECK.main(), 1)
                inventory.assert_not_called()
                self.assertIn("hosted_alias_gate:unverified", output.getvalue())

    def test_workflow_secrets_are_scoped_to_final_read_step(self) -> None:
        """Reject accidental job-wide secret scope or mutation permission."""

        workflow = (HERE.parents[1] / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        job = job_block(workflow, "staging-hosted-alias-reconcile")
        self.assertIn("inputs.target == 'staging-hosted-alias-reconcile'", job)
        self.assertIn("READ_ONE_STAGING_ALIAS", job)
        self.assertIn("secrets.STAGING_E2E_PASSWORD", job)
        self.assertIn("secrets.CF_EMAIL_ROUTING_TOKEN", job)
        self.assertIn("secrets.CLOUDFLARE_API_TOKEN", job)
        self.assertNotIn("\n    env:", job)
        self.assertNotIn("wrangler", job)


if __name__ == "__main__":
    unittest.main()
