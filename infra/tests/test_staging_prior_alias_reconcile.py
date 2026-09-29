"""Offline tests for the two-alias read-only staging reconciliation gate."""

from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
from io import StringIO
import os
from pathlib import Path
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "staging_prior_alias_reconcile", Path(__file__).with_name("staging_prior_alias_reconcile.py")
)
assert SPEC and SPEC.loader
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class PriorAliasReconciliationTests(unittest.TestCase):
    """Demand complete provider/D1 evidence without exposing private targets."""

    def test_alias_derivation_matches_hosted_contract(self) -> None:
        """Derive the same private suffix, not a public run-ID-only address."""

        import hashlib
        import hmac

        password = "private-fixture-password"
        expected = hmac.new(
            password.encode(), b"amail-staging-e2e/v1:36524101354:1", hashlib.sha256
        ).hexdigest()[:16]
        self.assertEqual(
            CHECK.alias(password, "36524101354", "1"),
            f"e2e-{expected}@mail-staging.moesegfault.dev",
        )

    def test_exact_route_and_retired_owned_row_required(self) -> None:
        """An exact literal route or unreconciled D1 row blocks a clean result."""

        target = "e2e-test@mail-staging.moesegfault.dev"
        inventory = [{"matchers": [{"type": "literal", "field": "to", "value": target}]}]
        self.assertFalse(CHECK.route_absent(inventory, target))
        self.assertTrue(CHECK.route_absent(inventory, target + "x"))
        row = {"state": "retired", "cf_rule_id": None, "needs_reconcile": 0,
               "owner_iss": CHECK.ISSUER, "owner_sub": "fixture-owner"}
        self.assertEqual(CHECK.row_clean([row]), (True, "fixture-owner"))
        self.assertEqual(CHECK.row_clean([]), (True, None))
        for change in ({"state": "active"}, {"needs_reconcile": 1},
                       {"cf_rule_id": "opaque"}, {"owner_iss": "other-issuer"}):
            self.assertFalse(CHECK.row_clean([row | change])[0])

    def test_full_gate_checks_both_d1_rows_even_if_route_is_present(self) -> None:
        """A short-circuit must not hide D1 state behind a found route."""

        environment = {
            "STAGING_E2E_PASSWORD": "private-fixture-password",
            "CF_EMAIL_ROUTING_TOKEN": "private-route-token",
            "CLOUDFLARE_API_TOKEN": "private-api-token",
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
        }
        target = CHECK.alias(environment["STAGING_E2E_PASSWORD"], "36524101354", "1")
        with patch.dict(os.environ, environment, clear=True), patch.object(
            CHECK.sys, "argv", ["script", "READ_PRIOR_STAGING_ALIASES"]
        ), patch.object(CHECK, "rules", return_value=[{
            "matchers": [{"type": "literal", "field": "to", "value": target}]
        }]), patch.object(CHECK, "d1_row", return_value=[]) as d1, redirect_stdout(StringIO()) as output:
            self.assertEqual(CHECK.main(), 1)
        self.assertEqual(d1.call_count, 2)
        self.assertEqual(output.getvalue().splitlines(), [
            "prior_alias_first:not_clean", "prior_alias_second:clean", "prior_alias_gate:not_clean"
        ])
        self.assertNotIn(target, output.getvalue())
        self.assertNotIn("private", output.getvalue())

    def test_missing_secret_emits_only_three_fixed_unverified_labels(self) -> None:
        """Unavailable hosted credentials are a gate, never an address guess."""

        with patch.dict(os.environ, {}, clear=True), patch.object(
            CHECK.sys, "argv", ["script", "READ_PRIOR_STAGING_ALIASES"]
        ), redirect_stdout(StringIO()) as output:
            self.assertEqual(CHECK.main(), 1)
        self.assertEqual(output.getvalue().splitlines(), [
            "prior_alias_first:unverified", "prior_alias_second:unverified",
            "prior_alias_gate:unverified",
        ])

    def test_query_is_fixed_parameterized_select(self) -> None:
        """The D1 request carries only one fixed SELECT and a bound alias."""

        import json

        target = "e2e-test@mail-staging.moesegfault.dev"
        captured = []

        def fake_fetch(req):
            captured.append(req)
            return {"result": [{"success": True, "results": []}]}

        with patch.object(CHECK, "fetch", side_effect=fake_fetch):
            self.assertEqual(CHECK.d1_row("a" * 32, "token", target), [])
        self.assertEqual(captured[0].get_method(), "POST")
        body = json.loads(captured[0].data)
        self.assertEqual(body, {"sql": CHECK.SQL, "params": [target]})
        self.assertTrue(body["sql"].startswith("SELECT "))

    def test_short_page_with_larger_total_count_fails_closed(self) -> None:
        """A missing total_pages must not make a truncated first page complete."""

        payload = {
            "result": [{"matchers": []}],
            "result_info": {"page": 1, "per_page": 50, "count": 1, "total_count": 2},
        }
        with patch.object(CHECK, "fetch", return_value=payload):
            with self.assertRaisesRegex(CHECK.ReconcileFailure, "routing_inventory_unverified"):
                CHECK.rules("private-token")

    def test_complete_count_without_total_pages_is_accepted(self) -> None:
        """The live provider may omit total_pages but reports complete counts."""

        payload = {
            "result": [{"matchers": []}],
            "result_info": {"page": 1, "per_page": 50, "count": 1, "total_count": 1},
        }
        with patch.object(CHECK, "fetch", return_value=payload):
            self.assertEqual(CHECK.rules("private-token"), payload["result"])

    def test_manual_workflow_scopes_secrets_to_read_step(self) -> None:
        """An accidental job-wide token scope broadening fails review CI."""

        workflow = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        job = workflow.split("  staging-prior-alias-reconcile:\n", 1)[1].split(
            "\n  staging-routing-policy:", 1
        )[0]
        self.assertIn("inputs.target == 'staging-prior-alias-reconcile'", job)
        self.assertIn("READ_PRIOR_STAGING_ALIASES", job)
        self.assertIn("secrets.STAGING_E2E_PASSWORD", job)
        self.assertIn("secrets.CF_EMAIL_ROUTING_TOKEN", job)
        self.assertIn("secrets.CLOUDFLARE_API_TOKEN", job)
        self.assertNotIn("STAGING_E2E_OWNER_SUB", job)
        self.assertNotIn("\n    env:", job)


if __name__ == "__main__":
    unittest.main()
