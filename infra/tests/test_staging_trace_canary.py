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


def query_run(status: str = "COMPLETED", dry: bool = True,
              view: str = "events", service: str = canary.WORKER,
              start: int = 1000) -> dict:
    """Return the documented run echo for a fixed synthetic query window."""

    return {
        "status": status, "dry": dry,
        "timeframe": {"from": start, "to": 2000},
        "query": {"parameters": {
            "view": view, "datasets": [], "filterCombination": "and",
            "filters": [{"key": "$metadata.service", "operation": "eq",
                         "type": "string", "value": service}],
        }},
    }


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

    def test_safe_event_nested_beside_unreviewed_field_fails(self) -> None:
        """A known event inside a larger source object cannot bless siblings."""

        records = events()
        valid = json.loads(records[0]["source"])
        records[0]["source"] = {"event": valid, "unreviewed": "other private data"}
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

    def test_paginated_count_drift_cannot_certify_completeness(self) -> None:
        """A later smaller total must not turn a partial first page into all rows."""

        first = [{"$metadata": {"id": f"id-{index}"}} for index in range(200)]
        second = [{"$metadata": {"id": f"id-{index}"}} for index in range(200, 250)]
        with patch.object(canary, "query_page", side_effect=[
            {"count": 300, "events": first}, {"count": 250, "events": second},
        ]):
            with self.assertRaisesRegex(canary.CanaryError, "observability_count_malformed"):
                canary.retained_events("1" * 32, "fake", 1000, 2000)

    def test_paginated_duplicate_id_cannot_certify_completeness(self) -> None:
        """Repeated rows cannot fill the reported total, regardless of count."""

        first = [{"$metadata": {"id": f"id-{index}"}} for index in range(200)]
        second = [{"$metadata": {"id": "id-199"}}]
        with patch.object(canary, "query_page", side_effect=[
            {"count": 201, "events": first}, {"count": 201, "events": second},
        ]):
            with self.assertRaisesRegex(canary.CanaryError, "observability_cursor_stalled"):
                canary.retained_events("1" * 32, "fake", 1000, 2000)

    def test_query_uses_documented_nested_view(self) -> None:
        """Cloudflare defines the events view inside parameters, not top-level."""

        payload = {"success": True, "result": {
            "run": query_run(),
            "events": {"count": 0, "events": []},
        }}
        with patch.object(canary, "request_json", return_value=payload) as request:
            self.assertEqual(canary.query_page("1" * 32, "fake", 1000, 2000, None)["count"], 0)
        body = request.call_args.args[3]
        self.assertEqual(body["parameters"]["view"], "events")
        self.assertNotIn("view", body)

    def test_explicit_zero_event_view_is_not_a_privacy_pass(self) -> None:
        """A completed empty container is valid data, but no canary evidence."""

        payload = {"success": True, "result": {
            "run": query_run(),
            "events": {"count": 0, "events": []},
        }}
        with patch.object(canary, "request_json", return_value=payload):
            self.assertEqual(canary.query_page("1" * 32, "fake", 1000, 2000, None)["events"], [])
        with patch.object(canary, "query_page", return_value=payload["result"]["events"]):
            self.assertEqual(canary.retained_events("1" * 32, "fake", 1000, 2000), [])
        with self.assertRaisesRegex(canary.CanaryError, "retained_window_empty"):
            canary.assess([], (T, C, R), D, MARKERS)

    def test_absent_view_is_not_zero_events(self) -> None:
        """The optional events field may be absent, but cannot prove absence."""

        payload = {"success": True, "result": {"run": query_run()}}
        with patch.object(canary, "request_json", return_value=payload):
            with self.assertRaisesRegex(canary.CanaryError, "observability_events_view_absent"):
                canary.query_page("1" * 32, "fake", 1000, 2000, None)

    def test_missing_run_cannot_verify_dry_completion(self) -> None:
        """A result without its documented run object is not a usable page."""

        payload = {"success": True, "result": {"events": {"count": 0, "events": []}}}
        with patch.object(canary, "request_json", return_value=payload):
            with self.assertRaisesRegex(canary.CanaryError, "observability_run_malformed"):
                canary.query_page("1" * 32, "fake", 1000, 2000, None)

    def test_unfinished_and_unknown_query_statuses_fail(self) -> None:
        """Do not read a page whose query run has not completed."""

        for status, code in (("STARTED", "observability_query_incomplete"),
                             ("FAILED", "observability_query_status_unverified")):
            with self.subTest(status=status):
                payload = {"success": True, "result": {
                    "run": query_run(status=status),
                    "events": {"count": 0, "events": []},
                }}
                with patch.object(canary, "request_json", return_value=payload):
                    with self.assertRaisesRegex(canary.CanaryError, code):
                        canary.query_page("1" * 32, "fake", 1000, 2000, None)

    def test_missing_count_cannot_look_like_complete_page(self) -> None:
        """A present list with no total count does not certify completeness."""

        payload = {"success": True, "result": {
            "run": query_run(),
            "events": {"events": []},
        }}
        with patch.object(canary, "request_json", return_value=payload):
            with self.assertRaisesRegex(canary.CanaryError, "observability_count_malformed"):
                canary.query_page("1" * 32, "fake", 1000, 2000, None)

    def test_echoed_wrong_view_or_persisted_query_fails(self) -> None:
        """A provider echo contradicting the dry events request is not trusted."""

        for run in (query_run(dry=False), query_run(view="traces"),
                    query_run(service="other-service"), query_run(start=999)):
            with self.subTest(run=run):
                payload = {"success": True, "result": {
                    "run": run, "events": {"count": 0, "events": []},
                }}
                with patch.object(canary, "request_json", return_value=payload):
                    with self.assertRaisesRegex(canary.CanaryError,
                                                "observability_query_echo_unverified"):
                        canary.query_page("1" * 32, "fake", 1000, 2000, None)

    def test_query_shape_reports_each_echo_component_without_values(self) -> None:
        """The diagnostic names a mismatch, not the provider-supplied value."""

        run = query_run(status="STARTED", dry=False, view="traces",
                        service="other-service", start=999)
        parameters = run["query"]["parameters"]
        parameters["datasets"] = ["other-dataset"]
        parameters["filterCombination"] = "or"
        parameters["needle"] = {"value": "private-text"}
        shape = canary.query_shape({"run": run, "events": {}}, 1000, 2000)
        self.assertEqual(shape, {
            "run_status": "started", "dry": "false", "timeframe": "mismatch",
            "view": "mismatch", "datasets": "mismatch",
            "filter_combination": "mismatch", "service_filter": "mismatch",
            "narrowing": "mismatch", "events_container": "present",
        })
        self.assertNotIn("other-service", str(shape))
        self.assertNotIn("private-text", str(shape))

    def test_query_shape_is_reported_before_strict_echo_rejection(self) -> None:
        """A failed echo still reveals the independent event-container shape."""

        payload = {"success": True, "result": {
            "run": query_run(service="other-service"), "events": {},
        }}
        reports: list[dict[str, str]] = []
        with patch.object(canary, "request_json", return_value=payload):
            with self.assertRaisesRegex(canary.CanaryError,
                                        "observability_query_echo_unverified"):
                canary.query_page("1" * 32, "fake", 1000, 2000, None, reports.append)
        self.assertEqual(reports[0]["service_filter"], "mismatch")
        self.assertEqual(reports[0]["events_container"], "present")

    def test_query_shape_distinguishes_absent_and_invalid_view(self) -> None:
        """Neither an absent nor a malformed view is an explicit empty page."""

        self.assertEqual(canary.query_shape({"run": query_run()}, 1000, 2000)[
            "events_container"], "absent")
        self.assertEqual(canary.query_shape({"run": query_run(), "events": []}, 1000, 2000)[
            "events_container"], "invalid")


if __name__ == "__main__":
    unittest.main()
