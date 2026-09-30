"""Synthetic contracts for the new content-minimized historical shape query."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
import os
import sys
import unittest
from unittest.mock import patch

from infra.tests import staging_worker_r2_history_shape as shape

START = datetime(2026, 10, 1, 1, tzinfo=timezone.utc)
WINDOW = (START, START + timedelta(minutes=10))


def payload(sending=None, routing=None):
    """Construct minimal datasets without any message identity."""
    return {"data": {"viewer": {"zones": [{
        "sendingShape": [] if sending is None else sending,
        "routingShape": [] if routing is None else routing,
    }]}}}


class ShapeTests(unittest.TestCase):
    """Keep schema observations separate from delivery and raw event data."""

    def test_empty_and_normal_rows_are_only_schema(self):
        """Zero rows are not negative delivery evidence."""
        result = shape.diagnose(payload(), WINDOW)
        self.assertEqual(result["sending_rows"], "zero")
        self.assertEqual(result["sending_datetime"], "no_rows")
        row = {"datetime": "2026-10-01T01:03:00Z", "status": "private-status"}
        result = shape.diagnose(payload([row]), WINDOW)
        self.assertEqual(result["sending_datetime"], "utc_in_window")
        self.assertEqual(result["sending_status"], "string")
        self.assertNotIn("private", str(result))

    def test_null_mixed_invalid_and_full_are_bounded(self):
        """Full pages and type mismatches do not attest complete history."""
        null = {"datetime": None, "status": None}
        row = {"datetime": "2026-10-02T01:03:00Z", "status": "private"}
        self.assertEqual(shape.row_bins([null, row], WINDOW),
                         ("multiple", "mixed", "mixed"))
        self.assertEqual(shape.row_bins([null] * 100, WINDOW)[0], "full")
        self.assertEqual(shape.row_bins([null] * 101, WINDOW)[0], "invalid")
        self.assertEqual(shape.row_bins([{"datetime": True, "status": 1}], WINDOW),
                         ("one", "invalid", "invalid"))
        self.assertEqual(shape.date_bin("not-private-utc", WINDOW), "string_other")
        self.assertEqual(shape.date_bin(row["datetime"], WINDOW), "utc_outside_window")
        self.assertEqual(shape.row_bins([dict(row, secret="private")], WINDOW),
                         ("one", "invalid", "invalid"))

    def test_graphql_errors_are_not_accepted_or_printed(self):
        """Only canonical alias positions contribute to fixed error-path bins."""
        error = {"message": "private-provider-text", "extensions": {"id": "private"},
                 "path": ["viewer", "zones", 0, "sendingShape"]}
        self.assertEqual(shape.error_bins([error]), ("errors", "sending"))
        other = dict(error, path=["viewer", "zones", 0, "routingShape"])
        self.assertEqual(shape.error_bins([error, other]), ("errors", "both"))
        self.assertEqual(shape.error_bins([dict(error, path=["private"])]),
                         ("errors", "unscoped"))
        self.assertEqual(shape.error_bins([]), ("empty_errors", "none"))
        self.assertEqual(shape.error_bins([None]), ("invalid", "invalid"))
        result = shape.diagnose(dict(payload(), errors=[error]), WINDOW)
        self.assertEqual(result["graphql"], "errors")
        self.assertNotIn("private", str(result))

    def test_envelope_variants_are_described_not_normalized(self):
        """Unknown key names/values and unavailable datasets stay private."""
        result = shape.diagnose(dict(payload(), extensions={"private": "private"}), WINDOW)
        self.assertEqual(result["envelope"], "extra_keys")
        result = shape.diagnose({"data": {"viewer": {"zones": None}}}, WINDOW)
        self.assertEqual(result["zones"], "invalid")
        self.assertEqual(shape.diagnose({"data": {"viewer": {"zones": []}}}, WINDOW)["zones"],
                         "zero")
        self.assertEqual(shape.diagnose({"data": {"viewer": {"zones": [{}, {}]}}}, WINDOW)["zones"],
                         "multiple")

    def test_new_query_is_single_read_and_content_minimized(self):
        """Use unchanged bounds and different selection, never the old query."""
        class Reply:
            """Return synthetic JSON, recording bounded read size."""
            status = 200

            def __enter__(self):
                """Model response lifetime."""
                return self

            def __exit__(self, *_args):
                """No resource survives the synthetic response."""
                return None

            def read(self, limit):
                """Require the same finite body cap as the original."""
                self.limit = limit
                return json.dumps(payload()).encode()

        reply = Reply()
        with patch.object(shape.history.OPENER, "open", return_value=reply) as opening:
            self.assertEqual(shape.fetch("a" * 32, "private-token", WINDOW), payload())
        self.assertEqual(opening.call_count, 1)
        request = opening.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body["query"], shape.QUERY)
        self.assertNotEqual(shape.QUERY, shape.history.QUERY)
        for field in ("subject", "messageId", "ruleMatched", "errorDetail", "isLastEvent"):
            self.assertNotIn(field, shape.QUERY)
        self.assertEqual(body["variables"]["start"], "2026-10-01T01:00:00Z")
        self.assertEqual(body["variables"]["end"], "2026-10-01T01:10:00Z")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(reply.limit, shape.history.MAX_BODY + 1)

    def test_duplicate_json_and_oversize_are_rejected(self):
        """Never produce shape bins from ambiguous or unbounded JSON."""
        class Reply:
            """Serve a supplied synthetic body."""
            status = 200
            raw = b'{"data":null,"data":{}}'

            def __enter__(self):
                """Model response lifetime."""
                return self

            def __exit__(self, *_args):
                """Close response."""
                return None

            def read(self, _limit):
                """Return synthetic bytes."""
                return self.raw

        reply = Reply()
        with patch.object(shape.history.OPENER, "open", return_value=reply):
            with self.assertRaises(shape.history.HistoryError):
                shape.fetch("a" * 32, "private-token", WINDOW)
            reply.raw = b"x" * (shape.history.MAX_BODY + 1)
            with self.assertRaises(shape.history.HistoryError):
                shape.fetch("a" * 32, "private-token", WINDOW)

    def test_fixed_confirmation_identity_and_original_window(self):
        """Reject different runs before any provider call; reuse provenance."""
        env = {"GITHUB_REPOSITORY": shape.history.REPOSITORY}
        with patch.dict(os.environ, env), \
                patch.object(shape.history, "historical_window", return_value=WINDOW) as provenance, \
                patch.object(shape, "fetch", return_value=payload()) as fetching:
            shape.run(shape.CONFIRM, shape.history.RUN)
            self.assertEqual(fetching.call_args.args[2], WINDOW)
            self.assertEqual(provenance.call_count, 1)
            with self.assertRaises(shape.history.HistoryError):
                shape.run(shape.CONFIRM, "different")
            with self.assertRaises(shape.history.HistoryError):
                shape.run(shape.history.CONFIRM, shape.history.RUN)
            self.assertEqual(fetching.call_count, 1)

    def test_output_is_closed_and_always_delivery_unverified(self):
        """Success and unexpected exceptions cannot leak private provider text."""
        for exception in (None, ValueError("private-provider-text")):
            stdout, stderr = StringIO(), StringIO()
            with patch.object(shape, "run", return_value=shape.diagnose(payload(), WINDOW),
                              side_effect=exception), \
                    patch.object(sys, "argv", ["shape", shape.CONFIRM, shape.history.RUN]), \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(shape.main(), 0 if exception is None else 1)
            self.assertEqual(stderr.getvalue(), "")
            self.assertNotIn("private", stdout.getvalue())
            if exception is None:
                self.assertIn("SHAPE_DIAGNOSED delivery=UNVERIFIED", stdout.getvalue())
            else:
                self.assertEqual(stdout.getvalue(),
                                 "worker_r2_history_shape=UNVERIFIED reason=internal\n")


if __name__ == "__main__":
    unittest.main()
