"""Test the narrow retained-span reader without contacting any external service."""

from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

from infra.tests import staging_trace_witness as trace


TRACE = "0123456789abcdef0123456789abcdef"


def spans() -> list[dict]:
    """Create distinct synthetic CLI/server/client/remote IDs with true ancestry."""
    base = {"schema_version": 1, "operation": "billing_session_create",
            "trace_id": TRACE, "occurred_at_ms": 1_790_000_000_123,
            "duration_ms": 7, "outcome": "success"}
    return [dict(base, event_id=f"00000000-0000-4000-8000-{n:012}", service=service,
                 phase=phase, span_id=str(n) * 16,
                 **({"parent_span_id": str(n - 1) * 16} if n > 1 else {}))
            for n, service, phase in [(1, "mail_cli", "operation_exit"),
                                      (2, "mail_api", "request_exit"),
                                      (3, "mail_api", "billing_http"),
                                      (4, "billing", "request_exit")]]


class TraceWitnessTest(unittest.TestCase):
    """A retained chain is stronger evidence than a successful upload response."""

    def test_real_parent_chain_and_redelivery_are_required(self):
        """Exact duplicate delivery is harmless; missing ancestry never passes."""
        rows = spans()
        report = trace.witness(rows + [rows[0]], TRACE)
        self.assertEqual(report["retained_span_count"], 4)
        self.assertTrue(report["cli_retained"])
        self.assertEqual(report["billing_client_span_id"], "3" * 16)
        for missing in range(4):
            with self.assertRaisesRegex(trace.TraceWitnessError, "retained_trace_chain_incomplete"):
                trace.witness(rows[:missing] + rows[missing + 1:], TRACE)

    def test_human_approval_must_join_creation_context(self):
        """A same-trace but disconnected authorization is not accepted."""
        rows = spans()
        server = dict(rows[-1], event_id="00000000-0000-4000-8000-000000000006",
                      service="subscribe", operation="amail.authorization.approve",
                      span_id="6" * 16, parent_span_id="4" * 16)
        client = dict(server, event_id="00000000-0000-4000-8000-000000000007",
                      phase="dependency_exit", span_id="7" * 16, parent_span_id="6" * 16)
        approve = dict(rows[-1], event_id="00000000-0000-4000-8000-000000000005",
                       operation="billing_authorize", span_id="5" * 16, parent_span_id="7" * 16)
        self.assertTrue(trace.witness(rows + [server, client, approve], TRACE, require_authorization=True)["human_authorization_retained"])
        with self.assertRaisesRegex(trace.TraceWitnessError, "retained_trace_chain_incomplete"):
            trace.witness(rows + [server, approve], TRACE, require_authorization=True)
        approve["parent_span_id"] = "9" * 16
        with self.assertRaisesRegex(trace.TraceWitnessError, "retained_trace_chain_incomplete"):
            trace.witness(rows + [server, client, approve], TRACE, require_authorization=True)

    def test_private_or_invalid_records_fail_with_fixed_labels(self):
        """No poison payload is returned inside a validation exception."""
        marker = "SYNTHETIC_PRIVATE_AUTHORIZATION_CODE"
        for key, value in [("url", marker), ("operation", marker),
                           ("duration_ms", marker), ("span_id", marker),
                           ("parent_span_id", "3" * 16)]:
            rows = copy.deepcopy(spans())
            rows[2][key] = value
            with self.assertRaises(trace.TraceWitnessError) as failure:
                trace.witness(rows, TRACE)
            self.assertNotIn(marker, str(failure.exception))

    def test_query_is_staging_only_bounded_and_dry(self):
        """No arbitrary Worker name, account-wide scan or unbounded history exists."""
        query = trace.query_body(trace.SCRIPTS["mail_api"], TRACE, 1000, 2000)
        self.assertTrue(query["dry"])
        self.assertEqual(query["parameters"]["filters"][0]["value"], "amail-trace-sink-staging")
        self.assertEqual(query["parameters"]["needle"]["value"], TRACE)
        self.assertEqual(query["limit"], 128)
        for script, end in [("amail-trace-sink", 2000), (trace.SCRIPTS["mail_api"], 901_001)]:
            with self.assertRaises(trace.TraceWitnessError):
                trace.query_body(script, TRACE, 1000, end)

    def test_reader_discards_provider_envelope_before_returning(self):
        """Only a validated projection survives the privileged API read."""
        row = spans()[2]
        envelope = {"success": True, "result": {"events": {"count": 1, "events": [
            {"source": {"message": json.dumps(row)}, "$workers": {"scriptName": "amail-trace-sink-staging"},
             "$metadata": {"unexpected_private_provider_context": "private"}}
        ]}}}

        class Reply:
            """Bounded in-memory stand-in for a single HTTP response."""
            status = 200

            def __enter__(self):
                """Match urllib response context management."""
                return self

            def __exit__(self, *args):
                """No external resource exists."""

            def read(self, limit):
                """Respect the reader's requested maximum bytes."""
                return json.dumps(envelope).encode()[:limit]

        with patch("urllib.request.OpenerDirector.open", return_value=Reply()):
            result = trace.read_records("a" * 32, "SYNTHETIC_PRIVATE_API_TOKEN",
                                        trace.SCRIPTS["mail_api"], TRACE, 1000, 2000)
        self.assertEqual(result, [row])
        self.assertNotIn("private", json.dumps(result))

    def test_service_reader_uses_fixed_post_and_auth_header_only(self):
        """Billing/Subscribe spans are D1 records, never HTTP console metadata."""
        row = spans()[-1]
        reply = json.dumps({"schema_version": 1, "spans": [row]}).encode()

        class Reply:
            """One bounded service response for the private read contract."""
            status = 200

            def __enter__(self):
                """Match urllib response context management."""
                return self

            def __exit__(self, *args):
                """No external resource exists."""

            def read(self, limit):
                """Return only a typed bounded payload."""
                return reply[:limit]

        with patch("urllib.request.OpenerDirector.open", return_value=Reply()) as call:
            result = trace.read_service_records("billing", "SYNTHETIC_PRIVATE_SERVICE_KEY", TRACE)
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, "https://billing-staging.moesegfault.dev/v1/service/amail/trace-query")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data), {"trace_id": TRACE})
        self.assertEqual(result, [row])
        self.assertNotIn("SYNTHETIC_PRIVATE_SERVICE_KEY", json.dumps(result))

    def test_async_delivery_accepts_only_closed_scheduler_link(self):
        """Usage can join the source request without pretending Cron is its parent."""
        delivery = dict(spans()[2], operation="maintenance",
                        linked_trace_id="9" * 32, linked_span_id="8" * 16)
        self.assertEqual(trace.validate_span(delivery, "mail_api", TRACE), delivery)
        for key in ["linked_trace_id", "linked_span_id"]:
            invalid = delivery.copy()
            del invalid[key]
            with self.assertRaises(trace.TraceWitnessError):
                trace.validate_span(invalid, "mail_api", TRACE)


if __name__ == "__main__":
    unittest.main()
