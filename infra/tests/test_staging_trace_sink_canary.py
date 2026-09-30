"""Offline contracts for Queue-sink privacy, identity deduplication and parentage.

Run in GitHub Actions; fixtures contain synthetic identifiers only.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import staging_trace_canary as legacy
import staging_trace_sink_canary as sink
import staging_hosted_trace_sink_canary as hosted

T, C, S = "1" * 32, "2" * 16, "3" * 16
R, D = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
MARKERS = tuple(f"amail_{kind}_canary_{'a' * 32}" for kind in ("path", "query", "body", "header"))


def fixture() -> list[dict]:
    """Two valid roots in complete synthetic retained records."""
    common = {"schema_version": 1, "service": "mail_api", "phase": "request_exit", "duration_ms_bucket": 8}
    events = [dict(common, event_id=R, operation="addresses_list", trace_id=T, span_id=S,
                   parent_span_id=C, request_id=R, outcome="success", http_status_class=2),
              dict(common, event_id=D, operation="unknown", trace_id="4" * 32, span_id="5" * 16,
                   request_id=D, outcome="client_error", error_code="unauthorized", http_status_class=4)]
    return [{"$metadata": {"service": sink.SINK, "id": str(index), "type": "cf-worker-log"},
             "$workers": {"truncated": False, "event": {"queue": "amail-trace-events-staging"}},
             "dataset": "workers", "source": json.dumps(event)} for index, event in enumerate(events)]


class SinkCanaryTests(unittest.TestCase):
    """A passing bounded trace cannot conceal markers or ambiguous identities."""
    def test_valid_roots_and_identical_redelivery_pass(self):
        """Queue at-least-once delivery is deduplicated by stable typed event ID."""
        records = fixture()
        duplicate = deepcopy(records[0])
        duplicate["$metadata"]["id"] = "2"
        sink.assess(records + [duplicate], (T, C, R), D, MARKERS)

    def test_every_marker_in_any_record_carrier_fails(self):
        """Platform enrichment, keys and application payload all undergo whole-row scan."""
        for marker in MARKERS:
            for carrier in ("metadata", "workers", "source", "key"):
                records = fixture()
                if carrier == "metadata":
                    records[0]["$metadata"]["url"] = marker
                elif carrier == "workers":
                    records[0]["$workers"]["event"]["body"] = marker
                elif carrier == "source":
                    records[0]["source"] += marker
                else:
                    records[0][marker] = "value"
                with self.assertRaisesRegex(legacy.CanaryError, "^synthetic_marker_retained$"):
                    sink.assess(records, (T, C, R), D, MARKERS)

    def test_truncated_missing_and_conflicting_event_copies_fail(self):
        """No incomplete view or event-ID aliasing is accepted."""
        for value in (True, None, "false"):
            records = fixture()
            records[0]["$workers"]["truncated"] = value
            with self.assertRaises(legacy.CanaryError):
                sink.assess(records, (T, C, R), D, MARKERS)
        records = fixture()
        duplicate = deepcopy(records[0])
        duplicate["$metadata"]["id"] = "2"
        event = json.loads(duplicate["source"])
        event["duration_ms_bucket"] = 16
        duplicate["source"] = json.dumps(event)
        with self.assertRaisesRegex(legacy.CanaryError, "^sink_duplicate_event_conflict$"):
            sink.assess(records + [duplicate], (T, C, R), D, MARKERS)

    def test_bad_parent_and_untrusted_anonymous_trace_fail(self):
        """Anonymous traceparent must not join the authenticated or adversarial trace."""
        for index, key, value in ((0, "parent_span_id", "8" * 16),
                                   (1, "parent_span_id", C), (1, "trace_id", T),
                                   (1, "trace_id", "a" * 32)):
            records = fixture()
            event = json.loads(records[index]["source"])
            event[key] = value
            records[index]["source"] = json.dumps(event)
            with self.assertRaises(legacy.CanaryError):
                sink.assess(records, (T, C, R), D, MARKERS)

    def test_schema_omits_unknown_fields_bool_numbers_and_noncanonical_ids(self):
        """Arbitrary trace attributes never become approved diagnostic data."""
        event = json.loads(fixture()[0]["source"])
        self.assertTrue(sink.safe_event(event))
        for key, value in (("subject", "private"), ("http_status_class", True),
                           ("event_id", "not-an-id"), ("trace_id", "0" * 32),
                           ("duration_ms_bucket", 3)):
            bad = dict(event, **{key: value})
            self.assertFalse(sink.safe_event(bad))

    def test_sink_query_requires_sink_echo_not_source_echo(self):
        """Service parameter changes both transport and its independent echo check."""
        filt = {"key": "$metadata.service", "operation": "eq", "type": "string", "value": sink.SINK}
        self.assertTrue(legacy.expected_service_filter(filt, sink.SINK))
        self.assertFalse(legacy.expected_service_filter(filt))

    def test_wrapper_guard_precedes_any_preflight(self):
        """A misspelled confirmation cannot start even a private API read."""
        with patch.object(sink, "preflight") as read:
            with self.assertRaises(legacy.CanaryError):
                hosted.execute("canary", "WRONG", R, D)
            read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
