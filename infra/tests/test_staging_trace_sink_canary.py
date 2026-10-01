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

    def test_request_status_error_and_service_phase_constraints(self):
        """A safe-field vocabulary alone cannot bless an impossible causal event."""
        event = json.loads(fixture()[0]["source"])
        for change in ({"http_status_class": 4}, {"error_code": "dependency_failure"},
                       {"error_code": "unauthorized"}, {"span_id": None},
                       {"request_id": None}, {"response_bytes_bucket": 1},
                       {"provider_http_status": 200}, {"phase": "operation_exit"},
                       {"service": "mail_cli"}, {"operation": "maintenance"}):
            with self.subTest(change=change):
                self.assertFalse(sink.safe_event(dict(event, **change)))
        for status in (1, 2, 3):
            self.assertTrue(sink.safe_event(dict(event, http_status_class=status)))
        for status, outcome, error in ((4, "client_error", "unauthorized"),
                                       (5, "server_error", "service_unavailable")):
            self.assertTrue(sink.safe_event(dict(event, http_status_class=status,
                                                 outcome=outcome, error_code=error)))

    def test_maintenance_standalone_and_operation_scoped_parent(self):
        """Shared schema supports both Cron diagnostics and request warning children."""
        event = json.loads(fixture()[0]["source"])
        event.pop("http_status_class")
        event.update(phase="maintenance", outcome="phase_failure", error_code="dependency_failure",
                     diagnostic_code="storage_ledger_state_deferred")
        self.assertTrue(sink.safe_event(event))
        standalone = dict(event, operation="maintenance", parent_span_id=None)
        self.assertTrue(sink.safe_event(standalone))
        for bad in (dict(event, parent_span_id=None), dict(standalone, parent_span_id=C),
                    dict(event, diagnostic_code=None), dict(event, outcome="success"),
                    dict(event, request_bytes_bucket=0), dict(event, provider_error_code=0)):
            self.assertFalse(sink.safe_event(bad))

    def test_budget_deferral_has_exact_non_dependency_pair(self):
        """Budget denial is a standalone fixed condition, not provider failure."""
        event = json.loads(fixture()[0]["source"])
        event.pop("http_status_class")
        event.update(operation="maintenance", parent_span_id=None, phase="maintenance",
                     outcome="phase_failure", error_code="resource_deferred",
                     diagnostic_code="maintenance_budget_deferred")
        self.assertTrue(sink.safe_event(event))
        for change in ({"error_code": "dependency_failure"},
                       {"diagnostic_code": "outbound_reconciliation_failed"},
                       {"operation": "messages_send", "parent_span_id": C},
                       {"phase": "request_exit"}, {"outcome": "success"}):
            self.assertFalse(sink.safe_event(dict(event, **change)))

    def test_byte_buckets_up_to_four_gib_and_closed_provider_fields(self):
        """The mirror preserves Rust's 2^32 byte bound and routing-only provider data."""
        event = json.loads(fixture()[0]["source"])
        for bucket in (0, 1, 1 << 30, 1 << 31, 1 << 32):
            self.assertTrue(sink.safe_event(dict(event, request_bytes_bucket=bucket)))
        for bucket in (True, -1, 3, (1 << 32) + 1, 1 << 33):
            self.assertFalse(sink.safe_event(dict(event, request_bytes_bucket=bucket)))
        dependency = dict(event, phase="routing_create", http_status_class=None,
                          provider_http_status=200, provider_error_code=0)
        self.assertTrue(sink.safe_event(dependency))
        self.assertFalse(sink.safe_event(dict(dependency, phase="d1_read")))
        self.assertFalse(sink.safe_event(dict(dependency, parent_span_id=None)))
        self.assertFalse(sink.safe_event(dict(dependency, provider_error_code=True)))
        self.assertFalse(sink.safe_event(dict(dependency, provider_error_code=1 << 32)))
        self.assertFalse(sink.safe_event(dict(dependency, provider_http_status=600)))

    def test_client_exact_operation_set_and_legacy_optional_ids(self):
        """Only ten CLI wire operations permit legacy optional span/request fields."""
        event = json.loads(fixture()[0]["source"])
        event.update(service="mail_cli", phase="operation_exit", parent_span_id=None,
                     response_bytes_bucket=1 << 32, span_id=None, request_id=None)
        for operation in sink.CLI_OPERATIONS:
            self.assertTrue(sink.safe_event(dict(event, operation=operation)))
        for operation in ("unknown", "health", "inbound", "search_poll", "telemetry_upload", "maintenance"):
            self.assertFalse(sink.safe_event(dict(event, operation=operation)))
        self.assertTrue(sink.safe_event(dict(event, http_status_class=0, outcome="server_error")))
        self.assertFalse(sink.safe_event(dict(event, response_bytes_bucket=None)))
        self.assertFalse(sink.safe_event(dict(event, error_code="other_server")))
        self.assertFalse(sink.safe_event(dict(event, parent_span_id=C)))
        self.assertFalse(sink.canonical_uuid("11111111-1111-4111-7111-111111111111"))

    def test_source_records_and_pin_changes_never_pass(self):
        """Retained source rows or post-read deployment drift invalidate the proof."""
        account = "a" * 32
        for source_records, post_failure in (([{}], False), ([], True)):
            pins = [None, legacy.CanaryError("sink_serving_pin_unverified")] if post_failure else [None, None]
            with patch.dict(sink.os.environ, {"CLOUDFLARE_ACCOUNT_ID": account,
                             "CF_OBSERVABILITY_TOKEN": "synthetic", "CLOUDFLARE_API_TOKEN": "synthetic"}), \
                    patch.object(sink, "preflight", side_effect=pins), \
                    patch.object(legacy, "under_temp", side_effect=lambda path: path), \
                    patch.object(sink, "probe", return_value=(1000, 2000, (T, C, R), D, MARKERS)), \
                    patch.object(sink.time, "sleep"), \
                    patch.object(legacy, "retained_events", side_effect=[fixture(), source_records]):
                with self.assertRaises(legacy.CanaryError):
                    sink.execute(Path("synthetic-cli"), Path("synthetic-home"), R, D)

    def test_missing_roots_requeries_same_window_without_new_traffic(self):
        """Only readback repeats; stable row IDs and original time/service stay fixed."""
        records = fixture()
        with patch.dict(sink.os.environ, {"CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                         "CF_OBSERVABILITY_TOKEN": "synthetic", "CLOUDFLARE_API_TOKEN": "synthetic"}), \
                patch.object(sink, "preflight"), \
                patch.object(legacy, "under_temp", side_effect=lambda path: path), \
                patch.object(sink, "probe", return_value=(1000, 2000, (T, C, R), D, MARKERS)) as probe, \
                patch.object(sink.time, "sleep"), \
                patch.object(legacy, "retained_events", side_effect=[records[:1], records, []]) as read:
            sink.execute(Path("synthetic-cli"), Path("synthetic-home"), R, D)
        probe.assert_called_once()
        self.assertEqual(read.call_args_list[0].args, read.call_args_list[1].args)
        self.assertEqual(read.call_args_list[0].kwargs, {"service": sink.SINK})
        self.assertEqual(read.call_args_list[1].kwargs, {"service": sink.SINK})
        self.assertEqual(read.call_args_list[0].args[2:], (1000, 122000))


if __name__ == "__main__":
    unittest.main()
