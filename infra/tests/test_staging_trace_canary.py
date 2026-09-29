"""Synthetic, offline tests for the retained-log canary's fail-closed logic."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent))
import staging_trace_canary as canary  # noqa: E402


T = "1" * 32
C = "2" * 16
S = "3" * 16
R = "11111111-1111-4111-8111-111111111111"
D = "22222222-2222-4222-8222-222222222222"
MARKERS = ("amail_path_canary_test", "amail_query_canary_test")


def row(event: dict) -> dict:
    """Represent a Cloudflare retained log with a JSON-text Rust console event."""

    return {"$metadata": {"id": event["request_id"], "service": canary.WORKER},
            "source": json.dumps(event)}


def events() -> list[dict]:
    """Create a valid CLI-parented API root plus an anonymous denied root."""

    return [row({"schema_version": 1, "service": "mail_api",
                 "operation": "addresses_list", "phase": "request_exit",
                 "trace_id": T, "span_id": S, "parent_span_id": C,
                 "request_id": R, "outcome": "success", "http_status_class": 2,
                 "duration_ms_bucket": 8}),
            row({"schema_version": 1, "service": "mail_api",
                 "operation": "unknown", "phase": "request_exit",
                 "trace_id": "4" * 32, "span_id": "5" * 16,
                 "request_id": D, "outcome": "client_error", "http_status_class": 4,
                 "duration_ms_bucket": 8})]


class StagingTraceCanaryTests(unittest.TestCase):
    """Require complete coverage, no marker, and exact causal parentage."""

    def test_valid_records_pass(self) -> None:
        """A safe root is linked to the CLI span and denial is independent."""

        canary.assess(events(), (T, C, R), D, MARKERS)

    def test_canary_in_platform_metadata_fails(self) -> None:
        """Do not inspect only application JSON; platform metadata can leak."""

        records = events()
        records[1]["$metadata"]["url"] = "/" + MARKERS[0]
        with self.assertRaisesRegex(canary.CanaryError, "synthetic_url_marker_retained"):
            canary.assess(records, (T, C, R), D, MARKERS)

    def test_unallowlisted_custom_event_field_fails(self) -> None:
        """An accidentally logged address fails even without matching the canary."""

        records = events()
        root = json.loads(records[0]["source"])
        root["address"] = "synthetic@example.invalid"
        records[0]["source"] = json.dumps(root)
        with self.assertRaisesRegex(canary.CanaryError, "application_event_schema_unallowlisted"):
            canary.assess(records, (T, C, R), D, MARKERS)

    def test_malformed_enum_fails_without_type_error(self) -> None:
        """Provider data cannot provoke a raw exception from set membership."""

        records = events()
        root = json.loads(records[0]["source"])
        root["operation"] = {"unexpected": "value"}
        records[0]["source"] = json.dumps(root)
        with self.assertRaisesRegex(canary.CanaryError, "application_event_schema_unallowlisted"):
            canary.assess(records, (T, C, R), D, MARKERS)

    def test_wrong_parent_fails(self) -> None:
        """Matching a trace ID alone is not a causal CLI-to-API proof."""

        records = events()
        root = json.loads(records[0]["source"])
        root["parent_span_id"] = "6" * 16
        records[0]["source"] = json.dumps(root)
        with self.assertRaisesRegex(canary.CanaryError, "cli_api_parentage_invalid"):
            canary.assess(records, (T, C, R), D, MARKERS)

    def test_incomplete_page_fails(self) -> None:
        """A truncated provider page cannot prove absence across retained logs."""

        with patch.object(canary, "query_page", return_value={"count": 2, "events": events()[:1]}):
            with self.assertRaisesRegex(canary.CanaryError, "observability_page_incomplete"):
                canary.retained_events("1" * 32, "fake", 1000, 2000)

    def test_exact_count_passes(self) -> None:
        """A complete small page is enough; no unnecessary cursor is invented."""

        with patch.object(canary, "query_page", return_value={"count": 2, "events": events()}):
            self.assertEqual(len(canary.retained_events("1" * 32, "fake", 1000, 2000)), 2)

    def test_query_uses_documented_nested_view(self) -> None:
        """Cloudflare defines the events view inside parameters, not top-level."""

        payload = {"success": True, "result": {"events": {"count": 0, "events": []}}}
        with patch.object(canary, "request_json", return_value=payload) as request:
            self.assertEqual(canary.query_page("1" * 32, "fake", 1000, 2000, None)["count"], 0)
        body = request.call_args.args[3]
        self.assertEqual(body["parameters"]["view"], "events")
        self.assertNotIn("view", body)


if __name__ == "__main__":
    unittest.main()
