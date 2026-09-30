"""Synthetic privacy and classification contracts; no live provider calls."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
import json
import os
import sys
import unittest
import urllib.error
from unittest.mock import patch

from infra.tests import staging_worker_r2_history_error as probe

START = datetime(2026, 10, 1, 1, tzinfo=timezone.utc)
WINDOW = (START, START + timedelta(minutes=10))


def error(message, path=None, **extra):
    """Build synthetic private errors without printing them."""
    return dict(message=message, path=path, **extra)


def envelope():
    """Return metadata-only selected data, never an event identity."""
    return {"data": {"viewer": {"zones": [{
        "sendingErrorProbe": [{"__typename": "private-type"}],
        "routingErrorProbe": [],
    }]}}, "errors": None}


class ErrorClassTests(unittest.TestCase):
    """Verify narrow public templates and unchanged investigation bounds."""

    def test_documented_categories_and_unknown_are_closed(self):
        """Do not guess from generic forbidden/schema keywords."""
        cases = {
            "Unauthorized": "authentication",
            "not authorized for that account": "authorization_or_dataset_access",
            "zones [private-zone] are not authorized": "authorization_or_dataset_access",
            "does not have access to the path private-path": "authorization_or_dataset_access",
            "unknown field private-field": "schema_or_field",
            "error parsing args private-args": "arguments_or_filter",
            "query contains error, please review it and retry": "query_invalid",
            "cannot request data older than private-window": "dataset_limit",
            "rate limiter budget depleted, try again after 5 minutes": "rate_or_resource",
            "unable to execute query, please try again later": "service_unavailable",
            "Internal server error": "internal",
            "private-prefix Unauthorized": "unclassified",
            "Forbidden private-field": "unclassified",
            "unauthorized": "unclassified",
            "unknown field\nprivate": "unclassified",
        }
        for message, expected in cases.items():
            self.assertEqual(probe.message_class(error(message)), expected)

    def test_budget_code_is_known_not_arbitrary_extension(self):
        """Only the documented budget code adds a category."""
        self.assertEqual(probe.message_class(error("private", extensions={"code": "budget"})),
                         "rate_or_resource")
        self.assertEqual(probe.message_class(error("private", extensions={"code": "private"})),
                         "unclassified")
        self.assertEqual(probe.message_class(error("Unauthorized", extensions={"code": "budget"})),
                         "mixed")
        self.assertEqual(probe.message_class(error("x" * 2049)), "invalid")
        self.assertEqual(probe.message_class(error(None)), "invalid")

    def test_error_arrays_preserve_conflicts_and_cardinality_bounds(self):
        """No unknown or contradictory error disappears into a known answer."""
        self.assertEqual(probe.errors_bin([error("Unauthorized"), error("private")])[0], "mixed")
        self.assertEqual(probe.errors_bin([]), ("no_errors", "none"))
        self.assertEqual(probe.errors_bin([error("Unauthorized")] * 101), ("invalid", "invalid"))
        self.assertEqual(probe.errors_bin([None]), ("invalid", "invalid"))
        self.assertEqual(probe.errors_bin({}), ("invalid", "invalid"))

    def test_documented_string_indices_and_canonical_names(self):
        """Correct the previous unscoped-path interpretation safely."""
        for index in (0, "0"):
            self.assertEqual(probe.error_scope(error("private",
                             ["viewer", "zones", index, "emailSendingAdaptive"])), "sending")
            self.assertEqual(probe.error_scope(error("private",
                             ["viewer", "zones", index, "routingErrorProbe"])), "routing")
        for index in (False, 0.0, "00", 1):
            self.assertEqual(probe.error_scope(error("private",
                             ["viewer", "zones", index, "emailSendingAdaptive"])), "unscoped")
        self.assertEqual(probe.error_scope(error("private", ["private"])), "unscoped")
        self.assertEqual(probe.error_scope(error("private", "private")), "invalid")

    def test_minimal_response_never_exposes_type_or_data_claim(self):
        """Shape compatibility is not delivery, even with no provider errors."""
        self.assertEqual(probe.minimal_data(envelope()), "minimal_shape")
        self.assertEqual(probe.minimal_data({"data": None}), "unverified")
        bad = envelope()
        bad["data"]["viewer"]["zones"][0]["sendingErrorProbe"] *= 2
        self.assertEqual(probe.minimal_data(bad), "invalid")

    def test_one_distinct_query_keeps_window_and_selects_no_event_content(self):
        """Provider call is singular, no redirect/retry/new historical interval."""
        class Reply:
            """Serve one bounded synthetic response."""
            status = 200

            def __enter__(self):
                """Open response lifetime."""
                return self

            def __exit__(self, *_args):
                """Close response lifetime."""
                return None

            def read(self, limit):
                """Record the finite response-body bound."""
                self.limit = limit
                return json.dumps(envelope()).encode()

        reply = Reply()
        with patch.object(probe.history.OPENER, "open", return_value=reply) as opening:
            self.assertEqual(probe.fetch("a" * 32, "private-token", WINDOW)[0], "ok")
        self.assertEqual(opening.call_count, 1)
        body = json.loads(opening.call_args.args[0].data)
        self.assertNotEqual(body["query"], probe.history.QUERY)
        self.assertEqual(body["variables"]["start"], "2026-10-01T01:00:00Z")
        self.assertEqual(body["variables"]["end"], "2026-10-01T01:10:00Z")
        for private_field in ("subject", "messageId", "errorDetail", "status", "ruleMatched"):
            self.assertNotIn(private_field, probe.QUERY)
        self.assertEqual(probe.QUERY.count("limit: 1"), 2)
        self.assertEqual(probe.QUERY.count("{ __typename }"), 2)
        self.assertEqual(reply.limit, probe.history.MAX_BODY + 1)

    def test_http_error_body_is_bounded_and_no_second_request(self):
        """HTTP metadata and in-memory error text remain separate evidence."""
        body = json.dumps({"errors": [error("not authorized for that account")]}).encode()
        response = urllib.error.HTTPError(probe.history.API, 403, "private-reason", {},
                                          BytesIO(body))
        with patch.object(probe.history.OPENER, "open", side_effect=response) as opening:
            status, payload = probe.fetch("a" * 32, "private-token", WINDOW)
        self.assertEqual(opening.call_count, 1)
        self.assertEqual(status, "forbidden")
        self.assertEqual(probe.errors_bin(payload["errors"])[0], "authorization_or_dataset_access")

    def test_exact_identity_gates_before_provider_and_reuses_provenance(self):
        """Different run/confirmation never causes a request."""
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": probe.history.REPOSITORY}), \
                patch.object(probe.history, "historical_window", return_value=WINDOW) as provenance, \
                patch.object(probe, "fetch", return_value=("ok", envelope())) as fetching:
            self.assertEqual(probe.run(probe.CONFIRM, probe.history.RUN)["data"], "minimal_shape")
            self.assertEqual(fetching.call_args.args[2], WINDOW)
            self.assertEqual(provenance.call_count, 1)
            for confirmation, original in ((probe.CONFIRM, "other"),
                                           (probe.history.CONFIRM, probe.history.RUN)):
                with self.assertRaises(probe.history.HistoryError):
                    probe.run(confirmation, original)
            self.assertEqual(fetching.call_count, 1)

    def test_output_cannot_interpolate_raw_fields_or_exception(self):
        """Only a closed result survives either successful or failed handling."""
        for exception in (None, ValueError("private-provider-text")):
            stdout, stderr = StringIO(), StringIO()
            with patch.object(probe, "run", return_value={
                    "http": "ok", "errors": "unclassified", "scope": "unscoped",
                    "data": "unverified"}, side_effect=exception), \
                    patch.object(sys, "argv", ["probe", probe.CONFIRM, probe.history.RUN]), \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(probe.main(), 0 if exception is None else 1)
            self.assertEqual(stderr.getvalue(), "")
            self.assertNotIn("private", stdout.getvalue())
            if exception is None:
                self.assertIn("CLASSIFIED delivery=UNVERIFIED", stdout.getvalue())
            else:
                self.assertEqual(stdout.getvalue(),
                                 "worker_r2_history_error=UNVERIFIED reason=internal\n")


if __name__ == "__main__":
    unittest.main()
