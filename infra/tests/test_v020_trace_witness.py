"""Test the narrow retained-span reader without contacting any external service."""

from __future__ import annotations

import copy
import json
import os
import unittest
import urllib.error
from unittest.mock import Mock, patch

from infra.tests import staging_trace_witness as trace
from infra.tests import staging_hosted_e2e as hosted


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

    def test_http_errors_keep_only_fixed_numeric_status_classification(self):
        """Real forbidden/unauthorized reads must be actionable without exposing HTTPError prose."""
        marker = "SYNTHETIC_PRIVATE_HTTP_REASON_TOKEN_URL"
        cases = {401: "unauthorized", 403: "forbidden", 404: "not_found",
                 429: "rate_limited", 503: "server_error", 302: "redirect_rejected",
                 418: "client_error"}
        for status, kind in cases.items():
            for boundary in ["provider", "service"]:
                with self.subTest(status=status, boundary=boundary):
                    body = Mock()
                    body.read.side_effect = AssertionError("HTTP error bodies must never be read")
                    error = urllib.error.HTTPError(f"https://private.invalid/{marker}", status,
                                                   marker, {"private-header": marker}, body)
                    with patch("urllib.request.OpenerDirector.open", side_effect=error):
                        with self.assertRaises(trace.TraceWitnessError) as failure:
                            if boundary == "provider":
                                trace.read_records("a" * 32, marker, trace.SCRIPTS["mail_api"], TRACE, 1000, 2000)
                            else:
                                trace.read_service_records("billing", marker, TRACE)
                    self.assertEqual(failure.exception.safe_label, f"retained_trace_{boundary}_{kind}")
                    self.assertNotIn(marker, str(failure.exception))
                    body.read.assert_not_called()

    def test_retained_retry_reports_exact_safe_stage_and_cause(self):
        """The bounded loop must not erase which retained boundary failed."""
        environment = {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "private",
                       "BILLING_SERVICE_KEY": "private"}
        evidence = {"trace_ids": [TRACE], "started_at_ms": 1000}
        for stage, label in [("mail_sink_read", "retained_trace_provider_forbidden"),
                             ("billing_read", "retained_trace_service_unauthorized"),
                             ("subscribe_read", "retained_span_fields_invalid"),
                             ("chain_validation", "retained_trace_chain_incomplete")]:
            with self.subTest(stage=stage), patch.dict(os.environ, environment, clear=True), \
                    patch.dict("sys.modules", {"staging_trace_witness": trace}), \
                    patch.object(hosted.time, "monotonic", side_effect=[0, 1, 2, 91, 92]), \
                    patch.object(hosted.time, "time", return_value=2), \
                    patch.object(hosted.time, "sleep") as sleep, \
                    patch.object(trace, "read_records", return_value=[]) as mail, \
                    patch.object(trace, "read_service_records", return_value=[]) as service, \
                    patch.object(trace, "witness", return_value={}) as witness:
                failure = trace.TraceWitnessError(label)
                if stage == "mail_sink_read":
                    mail.side_effect = failure
                elif stage == "billing_read":
                    service.side_effect = failure
                elif stage == "subscribe_read":
                    service.side_effect = [[], failure]
                else:
                    witness.side_effect = failure
                with self.assertRaises(hosted.HostedProbeError) as result:
                    hosted.retained_billing_trace(evidence)
                self.assertEqual(str(result.exception), f"billing_retained_trace_unverified_{stage}_{label}")
                sleep.assert_not_called()

    def test_unknown_exception_labels_cannot_escape_retained_retry(self):
        """A future misconstructed typed error still cannot turn private text into diagnostics."""
        marker = "SYNTHETIC_PRIVATE_FUTURE_PROVIDER_TEXT"
        with patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                                     "CLOUDFLARE_API_TOKEN": marker, "BILLING_SERVICE_KEY": marker}, clear=True), \
                patch.dict("sys.modules", {"staging_trace_witness": trace}), \
                patch.object(hosted.time, "monotonic", side_effect=[0, 1, 2, 91, 92]), \
                patch.object(hosted.time, "time", return_value=2), \
                patch.object(trace, "read_records", side_effect=trace.TraceWitnessError(marker)):
            with self.assertRaises(hosted.HostedProbeError) as result:
                hosted.retained_billing_trace({"trace_ids": [TRACE], "started_at_ms": 1000})
        self.assertEqual(str(result.exception),
                         "billing_retained_trace_unverified_mail_sink_read_retained_trace_unexpected_failure")
        self.assertNotIn(marker, str(result.exception))


if __name__ == "__main__":
    unittest.main()
