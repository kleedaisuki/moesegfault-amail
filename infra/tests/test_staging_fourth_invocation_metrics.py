"""Offline privacy and schema contracts for the fourth E2E metrics probe."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "provider"))
import probe_staging_fourth_invocation_metrics as probe  # noqa: E402


def row(status: str = "success", at: str = probe.START, requests: int = 1, errors: int = 0) -> dict:
    """Make a synthetic selected-row response with no real account data."""

    return {"dimensions": {"datetime": at, "scriptName": probe.WORKER, "status": status},
            "sum": {"requests": requests, "errors": errors}}


def payload(rows: list[dict]) -> dict:
    """Wrap selected rows in the official Workers Metrics account shape."""

    return {"data": {"viewer": {"accounts": [{"workersInvocationsAdaptive": rows}]}},
            "errors": None}


class MetricsTests(unittest.TestCase):
    """Exercise positive aggregates and fail-closed hostile provider responses."""

    def test_fixed_scope_query_and_no_details(self) -> None:
        """The requested projection cannot retrieve paths or raw exceptions."""

        self.assertIn("limit: 100", probe.QUERY)
        self.assertIn("scriptName: $scriptName", probe.QUERY)
        self.assertIn("datetime_geq: $datetimeStart", probe.QUERY)
        self.assertIn("datetime_leq: $datetimeEnd", probe.QUERY)
        self.assertNotIn("url", probe.QUERY.lower())
        self.assertNotIn("message", probe.QUERY.lower())

    def test_single_status_counts_are_bounded(self) -> None:
        """Distinct seconds may aggregate into one allowlisted status bucket."""

        result = probe.classify(payload([row("success", requests=2), row("success", probe.END, 3)]))
        self.assertEqual(result, [("success", 5, 0)])

    def test_query_output_is_only_fixed_labels(self) -> None:
        """Neither raw response nor token/account escapes via formatted output."""

        with patch.object(probe, "fetch", return_value=payload([row("scriptThrewException", errors=1)])):
            lines = probe.run(probe.CONFIRM, "a" * 32, "sensitive-token")
        self.assertEqual(lines, [
            "metrics_status=scriptThrewException requests=1 errors=1",
            "metrics_result=aggregate_only_not_request_attributed",
        ])

    def test_mixed_status_is_not_attributed(self) -> None:
        """A busy window is explicitly unverified despite valid buckets."""

        with patch.object(probe, "fetch", return_value=payload([row(), row("internalError", probe.END, 1, 1)])):
            lines = probe.run(probe.CONFIRM, "a" * 32, "secret")
        self.assertEqual(lines[-1], "metrics_result=UNVERIFIED reason=mixed")

    def test_malformed_responses_fail_closed(self) -> None:
        """Do not display unexpected provider data or accept ambiguous counts."""

        bad = [
            {}, {**payload([row()]), "errors": [{"message": "PRIVATE"}]},
            payload([]), payload([row()] * probe.LIMIT),
            payload([row(status="unexpected-private-status")]),
            payload([row(at="2026-09-29T12:24:31Z")]),
            payload([row(at="2026-09-29T12:25:42Z")]),
            payload([row(at="2026-09-29T12:24:32+00:00")]),
            payload([row(requests=True)]), payload([row(requests=-1)]),
            payload([row(requests=1, errors=2)]),
            payload([row(requests=probe.MAX_COUNT + 1)]),
            payload([row(), row()]),
            payload([{"dimensions": {**row()["dimensions"], "url": "PRIVATE"}, "sum": row()["sum"]}]),
            payload([{"dimensions": row()["dimensions"], "sum": {**row()["sum"], "message": "PRIVATE"}}]),
        ]
        wrong_script = payload([row()])
        wrong_script["data"]["viewer"]["accounts"][0]["workersInvocationsAdaptive"][0]["dimensions"]["scriptName"] = "other"
        bad.append(wrong_script)
        for value in bad:
            with self.subTest(value=str(value)[:30]), self.assertRaises(probe.Unverified):
                probe.classify(value)

    def test_duplicate_json_keys_rejected(self) -> None:
        """An attacker cannot shadow a selected GraphQL field in JSON."""

        with self.assertRaises(probe.Unverified):
            json.loads('{"data":{},"data":{"private":"SECRET"}}', object_pairs_hook=probe._unique_object)

    def test_main_suppresses_provider_payload_and_traceback(self) -> None:
        """Unexpected exceptions and GraphQL errors yield only fixed reasons."""

        output = StringIO()
        with patch.object(probe, "fetch", side_effect=RuntimeError("PRIVATE alias, URL, token, stack")), \
             patch.dict("os.environ", {"CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                                       "CF_OBSERVABILITY_TOKEN": "PRIVATE"}), \
             patch.object(sys, "argv", ["probe", probe.CONFIRM]), redirect_stdout(output):
            result = probe.main()
        self.assertEqual(result, 1)
        self.assertEqual(output.getvalue(), "metrics_result=UNVERIFIED reason=internal\n")

    def test_unreviewed_failure_reason_cannot_escape(self) -> None:
        """Even a future accidental dynamic error reason is not printable."""

        output = StringIO()
        with patch.object(probe, "fetch", side_effect=probe.Unverified("PRIVATE alias URL token")), \
             patch.dict("os.environ", {"CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                                       "CF_OBSERVABILITY_TOKEN": "PRIVATE"}), \
             patch.object(sys, "argv", ["probe", probe.CONFIRM]), redirect_stdout(output):
            result = probe.main()
        self.assertEqual(result, 1)
        self.assertEqual(output.getvalue(), "metrics_result=UNVERIFIED reason=internal\n")

    def test_optional_graphql_errors_key_and_unknown_status(self) -> None:
        """Missing optional errors is accepted, undocumented status is not."""

        good = payload([row()])
        del good["errors"]
        self.assertEqual(probe.classify(good), [("success", 1, 0)])
        with self.assertRaises(probe.Unverified):
            probe.classify(payload([row(status="other")]))

    def test_confirmation_gates_network(self) -> None:
        """A missing one-incident confirmation never opens a network request."""

        with patch.object(probe, "fetch") as fetch, self.assertRaises(probe.Unverified):
            probe.run("wrong", "a" * 32, "secret")
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
