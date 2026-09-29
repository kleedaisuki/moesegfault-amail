"""Synthetic contract tests for the fifth exact-run, aggregate-only diagnostic."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import staging_fifth_mail_audit as audit


def result(**changes: object) -> dict:
    """Build a complete synthetic D1 aggregate row without message data."""

    row = {key: 0 for key in audit.COUNTS}
    row.update(address_state="retired", needs_reconcile=0, owner_expected=1, generation_present=1)
    row.update(changes)
    return row


class FifthMailAuditTests(unittest.TestCase):
    """Pin the exact-run, SQL, shape, and log-privacy boundaries."""

    def test_query_is_bound_select_and_shape_checked(self) -> None:
        """D1 receives one parameterized aggregate SELECT, not message rows."""

        with patch.object(audit, "fetch", return_value={"result": [
            {"success": True, "results": [result(inbound_active=2, signal_active=1,
                                                   distractor_active=1, embedding_pending=2)]}
        ]}) as fetch:
            row = audit.aggregate("a" * 32, "private-token", "e2e-0123456789abcdef@mail-staging.moesegfault.dev")
        self.assertEqual(row["inbound_active"], 2)
        request = fetch.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(body["params"], [
            "e2e-0123456789abcdef@mail-staging.moesegfault.dev", audit.ISSUER,
            "AMAIL-E2E-0123456789abcdef-Signal", "AMAIL-E2E-0123456789abcdef-Distractor",
        ])
        sql = body["sql"].lower()
        self.assertTrue(sql.startswith("with exact_address as"))
        self.assertNotIn("select *", sql)
        for forbidden in ("select m.subject", "m.body_text", "m.metadata_json", "m.recipients_json",
                          "m.embedding_json as", "w.last_error_code"):
            self.assertNotIn(forbidden, sql)
        self.assertIn("m.address=?1", sql)
        self.assertIn("a.owner_iss=?2", sql)
        self.assertIn("m.subject=?3", sql)
        self.assertIn("m.subject=?4", sql)

    def test_malformed_or_inconsistent_aggregate_fails_closed(self) -> None:
        """No row content may be reported when D1 changes or miscounts."""

        for bad in (result(inbound_active=1), result(inbound_active=True),
                    result(inbound_active=1, embedding_pending=1),
                    result(address_state="unknown"), result(extra="secret"),
                    result(address_state=None, needs_reconcile=None, owner_expected=0, generation_present=1),
                    result(owner_expected=0, generation_present=1)):
            with self.subTest(bad=bad), patch.object(audit, "fetch", return_value={
                "result": [{"success": True, "results": [bad]}]
            }):
                with self.assertRaises(audit.ReconcileFailure):
                    audit.aggregate("a" * 32, "token", "e2e-0123456789abcdef@mail-staging.moesegfault.dev")

    def test_exact_coordinates_and_fixed_private_output(self) -> None:
        """Reject other run metadata before secret reads; never echo providers."""

        env = {"STAGING_E2E_PASSWORD": "private-fixture-password",
               "CF_EMAIL_ROUTING_TOKEN": "private-route-token",
               "CLOUDFLARE_API_TOKEN": "private-api-token",
               "CLOUDFLARE_ACCOUNT_ID": "a" * 32}
        args = ["script", audit.CONFIRM, audit.RUN, audit.ATTEMPT]
        with patch.dict(os.environ, env, clear=True), patch.object(sys, "argv", args), \
                patch.object(audit, "rules", side_effect=RuntimeError("secret provider body")), \
                patch.object(audit, "aggregate", return_value=result(
                    inbound_active=3, signal_active=2, distractor_active=1,
                    embedding_pending=3)), redirect_stdout(StringIO()) as output:
            self.assertEqual(audit.main(), 1)
        self.assertIn("fifth_mail_inbound_active:more", output.getvalue())
        self.assertIn("fifth_mail_signal_active:2", output.getvalue())
        self.assertIn("fifth_mail_route:unverified", output.getvalue())
        for secret in ("private", "provider", "e2e-", "36589042183"):
            self.assertNotIn(secret, output.getvalue())
        with patch.object(sys, "argv", ["script", audit.CONFIRM, audit.RUN, "2"]), \
                patch.object(audit, "required") as required, redirect_stdout(StringIO()):
            self.assertEqual(audit.main(), 1)
            required.assert_not_called()

    def test_wrong_issuer_cannot_pass_as_absent(self) -> None:
        """An unexpected issuer row is visible as mismatch, never a clean gate."""

        env = {"STAGING_E2E_PASSWORD": "private-fixture-password",
               "CF_EMAIL_ROUTING_TOKEN": "private-route-token",
               "CLOUDFLARE_API_TOKEN": "private-api-token",
               "CLOUDFLARE_ACCOUNT_ID": "a" * 32}
        args = ["script", audit.CONFIRM, audit.RUN, audit.ATTEMPT]
        with patch.dict(os.environ, env, clear=True), patch.object(sys, "argv", args), \
                patch.object(audit, "rules", return_value=[]), \
                patch.object(audit, "aggregate", return_value=result(
                    owner_expected=0, generation_present=None)), redirect_stdout(StringIO()) as output:
            self.assertEqual(audit.main(), 1)
        self.assertIn("fifth_mail_owner:mismatch", output.getvalue())

    def test_workflow_scopes_secrets_to_final_step(self) -> None:
        """Both exact-run jobs expose credentials only to their final execution step."""

        workflow = (HERE.parents[1] / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = workflow.split("  staging-fifth-mail-audit:\n", 1)[1].split(
            "\n  staging-fifth-mail-cleanup:", 1)[0]
        self.assertIn("inputs.target == 'staging-fifth-mail-audit'", job)
        self.assertIn("READ_FIFTH_MAIL_AGGREGATES", job)
        self.assertIn("36589042183", job)
        self.assertIn("ALIAS_ATTEMPT -ne '1'", job)
        self.assertNotIn("\n    env:", job)
        self.assertEqual(job.count("secrets.STAGING_E2E_PASSWORD"), 1)
        self.assertNotIn("secrets.STAGING_E2E_PASSWORD", job.split(
            "      - name: Read exact D1 aggregates and route absence only", 1)[0])
        self.assertNotIn("wrangler", job)

        cleanup = workflow.split("  staging-fifth-mail-cleanup:\n", 1)[1].split(
            "\n  staging-routing-write-probe:", 1)[0]
        self.assertIn("inputs.target == 'staging-fifth-mail-cleanup'", cleanup)
        self.assertIn("DELETE_FIFTH_MAIL_EXACT_FIXTURES", cleanup)
        self.assertIn("36589042183", cleanup)
        self.assertIn("ALIAS_ATTEMPT -ne '1'", cleanup)
        self.assertNotIn("\n    env:", cleanup)
        self.assertEqual(cleanup.count("secrets.STAGING_E2E_PASSWORD"), 1)
        self.assertNotIn("secrets.STAGING_E2E_PASSWORD", cleanup.split(
            "      - name: Verify exact fixtures and delete only their owner-scoped CLI IDs", 1)[0])


if __name__ == "__main__":
    unittest.main()
