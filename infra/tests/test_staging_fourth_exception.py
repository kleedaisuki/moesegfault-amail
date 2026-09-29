"""Synthetic privacy and fail-closed tests for the fourth staging exception probe."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


PATH = Path(__file__).resolve().parents[1] / "provider" / "probe_staging_fourth_exception.py"
SPEC = importlib.util.spec_from_file_location("probe_staging_fourth_exception", PATH)
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def response(rows: list[dict]) -> dict:
    """Construct a completed service-filtered dry Cloudflare event view."""

    body = probe.query_body()
    return {"success": True, "errors": [], "result": {
        "run": {"status": "COMPLETED", "dry": True, "timeframe": body["timeframe"],
                "query": {"parameters": body["parameters"]}},
        "events": {"count": len(rows), "events": rows},
    }}


def row(error: object = None, outcome: str | None = None) -> dict:
    """Construct one event with deliberately irrelevant private source data."""

    result = {"$metadata": {"service": probe.WORKER, "error": error},
              "timestamp": probe.START_MS + 1,
              "$workers": {"scriptName": probe.WORKER},
              "source": {"url": "PRIVATE_URL", "message": "PRIVATE_MAIL_BODY"}}
    if outcome is not None:
        result["$workers"]["outcome"] = outcome
    return result


class ExceptionProbeTests(unittest.TestCase):
    """Ensure raw provider data never becomes a returned classification."""

    def test_exact_wasm_literal(self) -> None:
        """Classify a literal without assuming it caused the address add."""

        payload = response([row("RuntimeError: unreachable", "exception")])
        self.assertEqual(probe.classify(payload, probe.query_body()),
                         "one_wasm_unreachable_not_attributed")

    def test_private_error_remains_closed(self) -> None:
        """Map arbitrary private error text to a fixed, non-identifying label."""

        payload = response([row("PRIVATE_MAIL_BODY", "exception")])
        label = probe.classify(payload, probe.query_body())
        self.assertEqual(label, "one_other_or_absent_not_attributed")
        self.assertNotIn("PRIVATE", label)

    def test_non_exception_is_not_a_negative_proof(self) -> None:
        """A quiet retained view cannot contradict the invocation metric."""

        self.assertEqual(probe.classify(response([row()]), probe.query_body()),
                         "no_exception_record_not_absence_proof")

    def test_wrong_scope_fails(self) -> None:
        """Reject a provider response containing another service's event."""

        payload = response([row("RuntimeError: unreachable")])
        payload["result"]["events"]["events"][0]["$metadata"]["service"] = "other"
        with self.assertRaises(probe.Unverified):
            probe.classify(payload, probe.query_body())

    def test_missing_script_name_fails(self) -> None:
        """An absent Worker identity cannot inherit the requested script name."""

        payload = response([row("RuntimeError: unreachable", "exception")])
        del payload["result"]["events"]["events"][0]["$workers"]["scriptName"]
        with self.assertRaises(probe.Unverified):
            probe.classify(payload, probe.query_body())

    def test_incomplete_view_fails(self) -> None:
        """Reject truncation rather than call partial results complete."""

        payload = response([row("RuntimeError: unreachable")])
        payload["result"]["events"]["count"] = 2
        with self.assertRaises(probe.Unverified):
            probe.classify(payload, probe.query_body())

    def test_confirmation_blocks_fetch(self) -> None:
        """Prevent accidental use as a general-purpose log reader."""

        with self.assertRaises(probe.Unverified):
            probe.run("wrong", "0" * 32, "secret")


if __name__ == "__main__":
    unittest.main()
