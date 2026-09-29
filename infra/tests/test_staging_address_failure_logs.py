"""Offline synthetic checks for historic retained-log diagnosis."""

from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent))
import staging_address_failure_logs as diagnostic  # noqa: E402


REQUEST = "11111111-1111-4111-8111-111111111111"
TRACE = "1" * 32
ROOT_SPAN = "2" * 16


def event(phase: str, outcome: str, **extra: object) -> dict:
    """Make one reviewed mail API event with matching causal identifiers."""

    data = {
        "schema_version": 1, "service": "mail_api", "operation": "addresses_add",
        "phase": phase, "trace_id": TRACE,
        "span_id": ROOT_SPAN if phase == "request_exit" else "3" * 16,
        "request_id": REQUEST, "outcome": outcome, "duration_ms_bucket": 8,
    }
    if phase == "request_exit":
        data["http_status_class"] = 5
    else:
        data["parent_span_id"] = ROOT_SPAN
    data.update(extra)
    return data


def record(data: dict) -> dict:
    """Represent a retained Cloudflare record without a real address or token."""

    return {"$metadata": {"service": diagnostic.WORKER}, "source": json.dumps(data)}


class AddressFailureLogTests(unittest.TestCase):
    """Require causal evidence and suppress unreviewed platform payloads."""

    def test_provider_rejection_reports_only_numeric_facts(self) -> None:
        """A failed POST can be distinguished from an earlier list failure."""

        rows = [record(event("request_exit", "server_error")),
                record(event("routing_list", "success")),
                record(event("routing_create", "phase_failure",
                             provider_http_status=403, provider_error_code=10000))]
        self.assertEqual(
            diagnostic.classify(rows),
            "routing_create_phase_failure_outer_class_5_provider_http_403_provider_code_10000",
        )

    def test_list_failure_reports_pre_post_boundary(self) -> None:
        """A failed Routing Rules GET is not misreported as a POST denial."""

        rows = [record(event("request_exit", "server_error")),
                record(event("routing_list", "phase_failure"))]
        self.assertEqual(diagnostic.classify(rows), "routing_list_failed_outer_class_5")

    def test_missing_phase_is_unverified_not_no_post(self) -> None:
        """Sampling or retention gaps cannot establish a negative event."""

        with self.assertRaisesRegex(diagnostic.CanaryError, "routing_phase_missing_or_ambiguous"):
            diagnostic.classify([record(event("request_exit", "server_error"))])

    def test_ambiguous_requests_fail_closed(self) -> None:
        """The hardcoded window must identify exactly one add attempt."""

        rows = [record(event("request_exit", "server_error")),
                record(event("request_exit", "server_error")),
                record(event("routing_list", "phase_failure"))]
        with self.assertRaisesRegex(diagnostic.CanaryError, "address_add_root_missing_or_ambiguous"):
            diagnostic.classify(rows)

    def test_unreviewed_payload_cannot_be_emitted(self) -> None:
        """Private provider text in any returned row stops classification."""

        rows = [record(event("request_exit", "server_error")),
                {"$metadata": {"service": diagnostic.WORKER}, "source": "provider private text"}]
        with self.assertRaisesRegex(diagnostic.CanaryError, "unreviewed_log_payload"):
            diagnostic.classify(rows)

    def test_disagreeing_indexed_echo_fails_closed(self) -> None:
        """A second valid but different event view must not mask ambiguity."""

        rows = [record(event("request_exit", "server_error"))]
        rows[0]["$metadata"]["message"] = json.dumps(
            event("routing_list", "phase_failure")
        )
        with self.assertRaisesRegex(diagnostic.CanaryError, "retained_event_echo_disagrees"):
            diagnostic.classify(rows)

    def test_wrong_causal_parent_is_unverified(self) -> None:
        """An unrelated phase in the same time window is not evidence."""

        rows = [record(event("request_exit", "server_error")),
                record(event("routing_list", "phase_failure",
                             parent_span_id="9" * 16))]
        with self.assertRaisesRegex(diagnostic.CanaryError, "routing_phase_missing_or_ambiguous"):
            diagnostic.classify(rows)

    def test_service_values_are_exact_window_and_never_echoed(self) -> None:
        """Only exact expected membership permits the event query to follow."""

        row = {"dataset": "workers", "key": "$metadata.service",
               "type": "string", "value": diagnostic.WORKER}
        with patch.object(diagnostic, "request_json", return_value={"result": [row]}) as request:
            self.assertEqual(diagnostic.service_value_status("a" * 32, "fake"), "present")
        self.assertEqual(request.call_args.args[2], "values")
        body = request.call_args.args[3]
        self.assertEqual(body["timeframe"], {"from": diagnostic.START_MS,
                                             "to": diagnostic.END_MS})
        self.assertEqual(body["filters"][0]["value"], diagnostic.WORKER)
        for rows, expected in (([], "absent"),
                               ([{"dataset": "workers", "key": "$metadata.service",
                                  "type": "string", "value": "other-service"}], "unverified"),
                               ({"unexpected": "shape"}, "unverified")):
            with self.subTest(expected=expected):
                with patch.object(diagnostic, "request_json", return_value={"result": rows}):
                    self.assertEqual(diagnostic.service_value_status("a" * 32, "fake"), expected)

    def test_absent_service_stops_before_event_query(self) -> None:
        """No service value means UNVERIFIED, not an empty-window inference."""

        output = StringIO()
        with patch.object(sys, "argv", ["script", diagnostic.CONFIRMATION]), \
                patch.dict(diagnostic.os.environ, {
                    "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                    "CF_OBSERVABILITY_TOKEN": "fake",
                    "CLOUDFLARE_API_TOKEN": "fake",
                }), patch.object(diagnostic, "preflight"), \
                patch.object(diagnostic, "service_value_status", return_value="absent"), \
                patch.object(diagnostic, "retained_events") as query, redirect_stdout(output):
            self.assertEqual(diagnostic.main(), 1)
        query.assert_not_called()
        self.assertEqual(output.getvalue().strip().splitlines(), [
            "staging_address_service: service_value_absent",
            "staging_address_incident: UNVERIFIED (service_value_absent)",
        ])

    def test_values_permission_error_keeps_fixed_cause(self) -> None:
        """An authorization failure is not collapsed into a zero-value claim."""

        output = StringIO()
        with patch.object(sys, "argv", ["script", diagnostic.CONFIRMATION]), \
                patch.dict(diagnostic.os.environ, {
                    "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                    "CF_OBSERVABILITY_TOKEN": "fake",
                    "CLOUDFLARE_API_TOKEN": "fake",
                }), patch.object(diagnostic, "preflight"), \
                patch.object(diagnostic, "service_value_status",
                             side_effect=diagnostic.CanaryError("observability_permission_denied")), \
                patch.object(diagnostic, "retained_events") as query, redirect_stdout(output):
            self.assertEqual(diagnostic.main(), 1)
        query.assert_not_called()
        self.assertEqual(output.getvalue().strip().splitlines(), [
            "staging_address_service: service_value_unverified",
            "staging_address_incident: UNVERIFIED (observability_permission_denied)",
        ])


if __name__ == "__main__":
    unittest.main()
