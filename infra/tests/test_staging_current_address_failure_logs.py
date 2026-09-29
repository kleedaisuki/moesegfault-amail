"""Synthetic, offline contracts for the bounded current-run log diagnostic."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import unittest
from unittest.mock import ANY, patch


sys.path.insert(0, str(Path(__file__).resolve().parent))
import staging_current_address_failure_logs as diagnostic  # noqa: E402
from staging_address_failure_logs import classify  # noqa: E402
from staging_trace_canary import CanaryError, QUERY_SHAPE_FIELDS  # noqa: E402


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
        """Type discovery does not relax the reviewed source contract."""

        status, output = self.invoke([{
            "$metadata": {"service": diagnostic.WORKER},
            "source": {"message": "private", "level": "error"},
        }])
        self.assertEqual(status, 1)
        self.assertIn("staging_current_address_source: object\n", output)
        self.assertIn("staging_current_address_incident: "
                      "UNVERIFIED (unreviewed_source_object)\n", output)
        self.assertNotIn("private", output)

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
