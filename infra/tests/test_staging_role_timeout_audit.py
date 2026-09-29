"""Synthetic privacy and exact-run contracts for the failed role SMTP audit."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import staging_role_timeout_audit as audit


def row(**changes: object) -> dict:
    """Construct a complete aggregate row with no private message fields."""

    value = {key: 0 for key in audit.COUNTS}
    value.update(checked_at=0, lease_until=0)
    value.update(changes)
    return value


class Response:
    """Minimal in-memory Cloudflare API response for request-shape tests."""

    status = 200

    def __init__(self, value: dict):
        """Encode only a synthetic D1 aggregate response."""

        self.buffer = BytesIO(json.dumps({"success": True, "result": [
            {"success": True, "results": [value]}
        ]}).encode())

    def __enter__(self):
        """Match urllib response context-manager behavior."""

        return self

    def __exit__(self, *_args):
        """Leave the synthetic response scope without suppression."""

        return False

    def read(self, size: int) -> bytes:
        """Honor the bounded read used by the production diagnostic."""

        return self.buffer.read(size)


class RoleTimeoutAuditTests(unittest.TestCase):
    """Pin the narrow SQL, provider labels, and secret-scoped workflow."""

    def test_d1_uses_bound_aggregate_select_only(self) -> None:
        """Never select raw arrivals or interpolate private fields in SQL."""

        with patch.object(audit.urllib.request, "urlopen", return_value=Response(row())) as open_url:
            self.assertEqual(audit.query("a" * 32, "secret-token")["on_n"], 0)
        request = open_url.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(payload["params"], [audit.START, audit.END, audit.LATE_END])
        self.assertTrue(payload["sql"].startswith("SELECT\n"))
        self.assertIn("FROM role_arrivals WHERE role='staging_probe'", payload["sql"])
        for forbidden in ("SELECT *", "SELECT id", "SELECT received_at", "SELECT role",
                          "SELECT forward_updated_at", "subject", "sender", "destination"):
            self.assertNotIn(forbidden, payload["sql"])

    def test_shape_and_consistency_fail_closed(self) -> None:
        """An added field, invalid count, or split-state mismatch cannot print data."""

        for bad in (row(extra="private"), row(on_n=1), row(on_n=True),
                    row(on_n=1, on_accepted=1), row(checked_at=None)):
            with self.subTest(bad=bad), patch.object(audit.urllib.request, "urlopen", return_value=Response(bad)):
                with self.assertRaises(audit.AuditError):
                    audit.query("a" * 32, "token")

    def test_fixed_labels_and_historical_lease_limit(self) -> None:
        """Later singleton overwrite is unknown, not historical Cron failure."""

        sample = row(on_n=1, on_accepted=1, on_marked=1, late_n=2,
                     late_unknown=1, late_accepted=1, late_pending=1, late_marked=1,
                     checked_at=audit.END + 1, lease_until=audit.END + 10)
        self.assertEqual(audit.health(sample), ("overwritten", "overwritten"))
        self.assertEqual(audit.bucket(sample["late_n"]), "multiple")
        self.assertEqual(audit.state(sample, "late", "unknown", "accepted"), "mixed")
        env = {"CF_ZONE_ID": audit.role_probe.ZONE, "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
               "CLOUDFLARE_API_TOKEN": "private-api-token",
               "CF_EMAIL_ROUTING_TOKEN": "private-routing-token",
               "AMAIL_STAGING_ROLE_VERSION": "b5269cce-6384-444e-9cf3-81e360fec6c3"}
        with patch.dict(os.environ, env, clear=True), patch.object(sys, "argv", ["script", audit.CONFIRM, audit.RUN]), \
                patch.object(audit, "provider_state", return_value=("absent", "four_direct", "match")), \
                patch.object(audit, "query", return_value=sample), redirect_stdout(StringIO()) as output:
            self.assertEqual(audit.main(), 0)
        rendered = output.getvalue()
        self.assertIn("role_timeout_arrival=one", rendered)
        self.assertIn("role_timeout_late_arrival=multiple", rendered)
        self.assertIn("role_timeout_health_checked_during_probe=overwritten", rendered)
        for private in ("private", "36603362864", "b5269cce", "179070"):
            self.assertNotIn(private, rendered)

    def test_wrong_run_rejected_before_provider_access(self) -> None:
        """An unrelated run cannot use this manually dispatched diagnostic."""

        with patch.object(sys, "argv", ["script", audit.CONFIRM, "36603362865"]), \
                patch.object(audit, "query") as query, redirect_stdout(StringIO()) as output:
            self.assertEqual(audit.main(), 1)
        query.assert_not_called()
        self.assertEqual(output.getvalue().strip(), "role_timeout_audit=coordinates_invalid")

    def test_workflow_scopes_secrets_to_final_step(self) -> None:
        """The manual target cannot accidentally run on push or leak credentials early."""

        workflow = (HERE.parents[1] / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = workflow.split("  staging-role-timeout-audit:\n", 1)[1].split(
            "\n  staging-trace-canary:", 1)[0]
        self.assertIn("inputs.target == 'staging-role-timeout-audit'", job)
        self.assertIn("READ_FIRST_ROLE_SMTP_AGGREGATES", job)
        self.assertIn("36603362864", job)
        self.assertNotIn("\n    env:", job)
        self.assertNotIn("secrets.", job.split(
            "      - name: Read bounded role D1 aggregates and current provider state only", 1)[0])
        self.assertEqual(job.count("secrets.CLOUDFLARE_API_TOKEN"), 1)
        self.assertEqual(job.count("secrets.CF_EMAIL_ROUTING_TOKEN"), 1)
        self.assertNotIn("wrangler", job.lower())


if __name__ == "__main__":
    unittest.main()
