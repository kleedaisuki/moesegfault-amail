"""Synthetic, offline contracts for the bounded current-run log diagnostic."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import ANY, patch


sys.path.insert(0, str(Path(__file__).resolve().parent))
import staging_current_address_failure_logs as diagnostic  # noqa: E402
from staging_address_failure_logs import classify  # noqa: E402
from staging_trace_canary import CanaryError, QUERY_SHAPE_FIELDS  # noqa: E402


REQUEST = "11111111-1111-4111-8111-111111111111"
TRACE = "1" * 32
ROOT_SPAN = "2" * 16


def event(phase: str, outcome: str, **extra: object) -> dict:
    """Build a producer-shaped address trace without real identifiers."""

    data = {
        "schema_version": 1, "service": "mail_api", "operation": "addresses_add",
        "phase": phase, "trace_id": TRACE,
        "span_id": ROOT_SPAN if phase == "request_exit" else
        "3" * 16 if phase == "routing_list" else "4" * 16,
        "request_id": REQUEST, "outcome": outcome, "duration_ms_bucket": 8,
    }
    if phase == "request_exit":
        data.update(http_status_class=5, error_code="service_unavailable")
    else:
        data["parent_span_id"] = ROOT_SPAN
        if outcome != "success":
            data["error_code"] = "dependency_failure"
    data.update(extra)
    return data


def trace_record(data: dict, timestamp: int, *, private_source: bool = True) -> dict:
    """Echo one synthetic Worker console log through provider metadata."""

    message = json.dumps(data, separators=(",", ":"))
    source = {"message": message, "level": "log"}
    if private_source:
        source["provider-private-unknown-key"] = "private-mailbox-text"
    return {
        "timestamp": timestamp,
        "$metadata": {"service": diagnostic.WORKER, "message": message,
                      "level": "log"},
        "source": source,
    }


class CurrentAddressFailureLogTests(unittest.TestCase):
    """Constrain schema probing and conditional causality to fixed labels."""

    def test_current_window_covers_entire_hosted_mail_step(self) -> None:
        """No claimed exact add timestamp may shorten the known job interval."""

        self.assertEqual(diagnostic.START_MS, 1790676700000)
        self.assertEqual(diagnostic.END_MS, 1790676967000)
        self.assertEqual(diagnostic.CONFIRMATION,
                         "READ_STAGING_ADDRESS_INCIDENT_36553799873")

    def test_object_discriminator_never_emits_private_key_or_value(self) -> None:
        """Unknown source keys and body contents reduce only to fixed types."""

        private = "unique-private-mailbox-or-provider-text"
        records = [{
            "$metadata": {"service": diagnostic.WORKER, "message": private,
                          "type": "cf-worker-log"},
            "source": {"message": {"payload": private}, private: private,
                       "level": "error"},
        }]
        summary = diagnostic.shape_summary(records)
        self.assertEqual(summary["source"], "object")
        self.assertEqual(summary["source_object_message"], "object")
        self.assertEqual(summary["source_object_other_keys"], "present")
        self.assertEqual(summary["source_object_key_bucket"], "two_to_four")
        self.assertEqual(summary["source_object_logs"], "absent")
        self.assertEqual(summary["source_object_timestamp"], "absent")
        self.assertEqual(summary["metadata_type"], "worker_log")
        self.assertEqual(summary["metadata_message"], "string")
        self.assertNotIn(private, str(summary))

    def test_wrong_service_does_not_yield_payload_shape(self) -> None:
        """A silently ignored service filter makes the entire query unverified."""

        with self.assertRaisesRegex(CanaryError, "service_filter_unverified"):
            diagnostic.shape_summary([{"$metadata": {"service": "unrelated"},
                                       "source": {"message": "private"}}])

    def test_mixed_or_empty_shape_categories_are_fixed(self) -> None:
        """No event counts, identities, or arbitrary source key names emerge."""

        rows = [
            {"$metadata": {"service": diagnostic.WORKER}, "source": None},
            {"$metadata": {"service": diagnostic.WORKER, "type": "unknown"},
             "source": {"event": ["private"], "data": "private",
                        "logs": [], "timestamp": 123}},
        ]
        summary = diagnostic.shape_summary(rows)
        self.assertEqual(summary["source"], "mixed")
        self.assertEqual(summary["source_object_message"], "absent")
        self.assertEqual(summary["source_object_event"], "list")
        self.assertEqual(summary["source_object_data"], "string")
        self.assertEqual(summary["source_object_logs"], "list")
        self.assertEqual(summary["source_object_timestamp"], "other")
        self.assertEqual(summary["source_object_key_bucket"], "two_to_four")
        self.assertEqual(summary["metadata_type"], "mixed")
        self.assertEqual(diagnostic.shape_summary([])["source"], "none")

    @staticmethod
    def invoke(records: list[dict], *, classifier: object = None) -> tuple[int, str]:
        """Exercise the public fixed-output boundary with synthetic records."""

        output = StringIO()
        if classifier is None:
            classifier = classify
        with patch.object(sys, "argv", ["script", diagnostic.CONFIRMATION]), \
                patch.dict(diagnostic.os.environ, {
                    "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                    "CF_OBSERVABILITY_TOKEN": "fake",
                    "CLOUDFLARE_API_TOKEN": "fake",
                }), patch.object(diagnostic, "preflight"), \
                patch.object(diagnostic, "retained_events", return_value=records) as query, \
                patch.object(diagnostic, "classify", side_effect=classifier), \
                redirect_stdout(output):
            status = diagnostic.main()
        query.assert_called_once_with("a" * 32, "fake", diagnostic.START_MS,
                                      diagnostic.END_MS, shape_reporter=ANY)
        return status, output.getvalue()

    def test_positive_causality_is_explicitly_window_conditional(self) -> None:
        """A causal result cannot falsely claim captured request-ID identity."""

        status, output = self.invoke(
            [{"$metadata": {"service": diagnostic.WORKER}, "source": "{}"}],
            classifier=lambda _: "routing_list_failed_outer_class_5",
        )
        self.assertEqual(status, 0)
        self.assertIn("staging_current_address_incident: "
                      "window_consistent_routing_list_failed_outer_class_5\n", output)
        self.assertNotIn("fake", output)

    def test_unreviewed_source_object_cannot_become_causal_result(self) -> None:
        """Type discovery alone does not produce a positive candidate."""

        status, output = self.invoke([{
            "$metadata": {"service": diagnostic.WORKER},
            "source": {"message": "private", "level": "error"},
        }])
        self.assertEqual(status, 1)
        self.assertIn("staging_current_address_source: object\n", output)
        self.assertIn("staging_current_address_retained_privacy: "
                      "UNVERIFIED (unreviewed_source_object)\n", output)
        self.assertIn("staging_current_address_incident: "
                      "UNVERIFIED (candidate_root_missing_or_ambiguous)\n", output)
        self.assertNotIn("private", output)

    def test_positive_list_failure_never_claims_exhaustive_privacy_or_no_post(self) -> None:
        """A linked failed phase is useful evidence despite opaque extra fields."""

        rows = [
            trace_record(event("routing_list", "phase_failure"), diagnostic.START_MS + 10),
            trace_record(event("request_exit", "server_error"), diagnostic.START_MS + 11),
            {"timestamp": diagnostic.START_MS + 12,
             "$metadata": {"service": diagnostic.WORKER, "message": "private-mailbox-text"},
             "source": {"unreviewed": "private-mailbox-text"}},
        ]
        status, output = self.invoke(rows)
        self.assertEqual(status, 1)
        self.assertIn("staging_current_address_incident: "
                      "candidate_window_consistent_routing_list_phase_failure_outer_class_5\n",
                      output)
        self.assertIn("staging_current_address_retained_privacy: UNVERIFIED", output)
        self.assertNotIn("private-mailbox-text", output)
        self.assertNotIn("no_post", output)

    def test_positive_create_failure_exposes_only_bounded_numeric_facts(self) -> None:
        """Provider status/code are emitted only from producer-shaped child."""

        rows = [
            trace_record(event("routing_list", "success"), diagnostic.START_MS + 10),
            trace_record(event("routing_create", "phase_failure",
                               provider_http_status=403, provider_error_code=10000),
                         diagnostic.START_MS + 11),
            trace_record(event("request_exit", "server_error"), diagnostic.START_MS + 12),
        ]
        status, output = self.invoke(rows)
        self.assertEqual(status, 1)
        self.assertIn(
            "candidate_window_consistent_routing_create_phase_failure_"
            "outer_class_5_provider_http_403_provider_code_10000", output,
        )
        self.assertNotIn("private-mailbox-text", output)

    def test_absent_child_never_implies_earlier_d1_or_no_post(self) -> None:
        """A root without linked positive phases cannot support a cause."""

        status, output = self.invoke([
            trace_record(event("request_exit", "server_error"), diagnostic.START_MS + 10)
        ])
        self.assertEqual(status, 1)
        self.assertIn("UNVERIFIED (candidate_phase_missing_or_ambiguous)", output)
        self.assertNotIn("d1", output)
        self.assertNotIn("no_post", output)

    def test_duplicate_roots_and_wrong_parent_reject_candidate(self) -> None:
        """Time-window coincidence cannot be promoted to an exact chain."""

        first = trace_record(event("request_exit", "server_error"), diagnostic.START_MS + 12)
        second = trace_record(event("request_exit", "server_error"), diagnostic.START_MS + 13)
        list_ok = trace_record(event("routing_list", "success"), diagnostic.START_MS + 10)
        create_bad = trace_record(event("routing_create", "phase_failure",
                                        parent_span_id="9" * 16), diagnostic.START_MS + 11)
        status, output = self.invoke([first, second, list_ok, create_bad])
        self.assertEqual(status, 1)
        self.assertIn("UNVERIFIED (candidate_root_missing_or_ambiguous)", output)
        status, output = self.invoke([first, list_ok, create_bad])
        self.assertEqual(status, 1)
        self.assertIn("UNVERIFIED (candidate_phase_missing_or_ambiguous)", output)

    def test_duplicate_json_key_and_source_echo_mismatch_fail_closed(self) -> None:
        """A metadata JSON lookalike without an exact source echo is not evidence."""

        root = trace_record(event("request_exit", "server_error"), diagnostic.START_MS + 12)
        root["$metadata"]["message"] = root["$metadata"]["message"].replace(
            '"schema_version":1', '"schema_version":1,"schema_version":1', 1
        )
        status, output = self.invoke([root])
        self.assertEqual(status, 1)
        self.assertIn("UNVERIFIED (candidate_message_schema_unverified)", output)
        root = trace_record(event("request_exit", "server_error"), diagnostic.START_MS + 12)
        root["source"]["message"] = "attacker-controlled-other-value"
        status, output = self.invoke([root])
        self.assertEqual(status, 1)
        self.assertIn("UNVERIFIED (candidate_source_echo_unverified)", output)
        self.assertNotIn("attacker-controlled-other-value", output)

    def test_out_of_window_candidate_rejected_even_with_query_echo(self) -> None:
        """Provider-side filter errors cannot silently widen the causal window."""

        root = trace_record(event("request_exit", "server_error"), diagnostic.END_MS + 1)
        status, output = self.invoke([root])
        self.assertEqual(status, 1)
        self.assertIn("UNVERIFIED (candidate_timestamp_unverified)", output)

    def test_multibyte_message_cannot_bypass_utf8_byte_bound(self) -> None:
        """Producer-only ASCII and UTF-8 byte checks reject long lookalikes."""

        row = trace_record(event("request_exit", "server_error"), diagnostic.START_MS + 10)
        private = "é" * 3000
        message = row["$metadata"]["message"].replace(
            '"operation":"addresses_add"',
            '"operation":"addresses_add","comment":"' + private + '"', 1,
        )
        self.assertLess(len(message), 4096)
        self.assertGreater(len(message.encode("utf-8")), 4096)
        row["$metadata"]["message"] = message
        row["source"]["message"] = message
        self.assertIsNone(diagnostic.candidate_event(row))

    def test_query_failure_reports_component_shape_without_source(self) -> None:
        """Failed query response cannot become an absence or D1 finding."""

        output = StringIO()
        with patch.object(sys, "argv", ["script", diagnostic.CONFIRMATION]), \
                patch.dict(diagnostic.os.environ, {
                    "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                    "CF_OBSERVABILITY_TOKEN": "fake",
                    "CLOUDFLARE_API_TOKEN": "fake",
                }), patch.object(diagnostic, "preflight"), \
                patch.object(diagnostic, "retained_events",
                             side_effect=CanaryError("observability_query_incomplete")), \
                redirect_stdout(output):
            status = diagnostic.main()
        self.assertEqual(status, 1)
        self.assertEqual(output.getvalue().count("staging_address_query_"),
                         len(QUERY_SHAPE_FIELDS))
        self.assertIn("UNVERIFIED (observability_query_incomplete)", output.getvalue())
        self.assertNotIn("staging_current_address_source", output.getvalue())


if __name__ == "__main__":
    unittest.main()
