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

    return {"$metadata": {"id": event["request_id"], "service": canary.WORKER,
                          "type": "cf-worker-log"},
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

    def test_unreviewed_custom_log_fails(self) -> None:
        """Arbitrary console text cannot coexist with a broad schema pass."""

        records = events() + [{"$metadata": {"id": "custom", "service": canary.WORKER,
                                             "type": "cf-worker-log"},
                               "source": "some free-form diagnostic"}]
        with self.assertRaisesRegex(canary.CanaryError, "unreviewed_retained_payload"):
            canary.assess(records, (T, C, R), D, MARKERS)

    def test_missing_type_cannot_hide_unreviewed_payload(self) -> None:
        """Cloudflare's optional type field is not a privacy bypass."""

        records = events() + [{"$metadata": {"id": "untyped", "service": canary.WORKER},
                               "source": "unreviewed retained text"}]
        with self.assertRaisesRegex(canary.CanaryError, "unreviewed_retained_payload"):
            canary.assess(records, (T, C, R), D, MARKERS)

    def test_indexed_message_cannot_mask_unreviewed_source(self) -> None:
        """A valid metadata echo cannot certify arbitrary custom source text."""

        records = events()
        records[0]["$metadata"]["message"] = records[0]["source"]
        records[0]["source"] = "unreviewed custom text"
        with self.assertRaisesRegex(canary.CanaryError, "unreviewed_retained_payload"):
            canary.assess(records, (T, C, R), D, MARKERS)

    def test_unallowlisted_indexed_message_fails(self) -> None:
        """A safe source cannot mask a second JSON shape in indexed metadata."""

        records = events()
        indexed = json.loads(records[0]["source"])
        indexed["address"] = "synthetic@example.invalid"
        records[0]["$metadata"]["message"] = json.dumps(indexed)
        with self.assertRaisesRegex(canary.CanaryError, "application_event_schema_unallowlisted"):
            canary.assess(records, (T, C, R), D, MARKERS)

    def test_routing_numeric_phase_is_allowlisted(self) -> None:
        """Current Rust routing diagnostics use fixed numeric provider facts."""

        records = events()
        routing = json.loads(records[0]["source"])
        routing.update({"phase": "routing_create", "span_id": "7" * 16,
                        "parent_span_id": S, "provider_http_status": 403,
                        "provider_error_code": 10000, "outcome": "phase_failure"})
        records.append(row(routing))
        canary.assess(records, (T, C, R), D, MARKERS)

    def test_arbitrary_provider_fact_fails(self) -> None:
        """Provider diagnostics remain numeric, not response-text escape hatches."""

        records = events()
        routing = json.loads(records[0]["source"])
        routing.update({"phase": "routing_create", "span_id": "7" * 16,
                        "provider_http_status": "forbidden with secret"})
        records.append(row(routing))
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
