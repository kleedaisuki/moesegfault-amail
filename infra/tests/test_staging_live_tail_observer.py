"""Hostile synthetic frames for the offline-only staging live-tail observer."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import unittest

from staging_live_tail_observer import (
    MAX_FRAME_BYTES, MAX_SECONDS, TailObserver, WORKER,
)


TRACE = "a" * 32
ROOT_SPAN = "b" * 16
REQUEST = "01234567-89ab-cdef-0123-456789abcdef"


def event(phase: str, outcome: str, **changes: object) -> dict:
    """Build the Worker schema, with no address or provider prose."""

    data = {
        "schema_version": 1, "service": "mail_api", "operation": "addresses_add",
        "phase": phase, "trace_id": TRACE,
        "span_id": ROOT_SPAN if phase == "request_exit" else ("c" if phase == "routing_list" else "d") * 16,
        "request_id": REQUEST, "outcome": outcome, "duration_ms_bucket": 8,
    }
    if phase == "request_exit":
        data["http_status_class"] = 2 if outcome == "success" else 5
        if outcome == "server_error":
            data["error_code"] = "other_server"
        elif outcome == "client_error":
            data["http_status_class"] = 4
            data["error_code"] = "other_client"
    else:
        data["parent_span_id"] = ROOT_SPAN
        if outcome == "phase_failure":
            data["error_code"] = "dependency_failure"
    data.update(changes)
    return data


def frame(*events: dict, script: str = WORKER, **changes: object) -> bytes:
    """Wrap console JSON in Cloudflare's documented live-tail envelope."""

    data = {
        "outcome": "ok", "scriptName": script, "exceptions": [],
        "diagnosticsChannelEvents": [], "eventTimestamp": 1790664950000,
        "event": {"request": {
            "method": "POST", "url": "https://private.invalid/secret@example.invalid",
            "headers": {"Authorization": "Bearer private-token"},
        }},
        "logs": [{"level": "log", "timestamp": 1790664950000,
                  "message": [json.dumps(item)]} for item in events],
    }
    data.update(changes)
    return json.dumps(data).encode()


class LiveTailObserverTests(unittest.TestCase):
    """Only fixed public labels may leave a complete or failed observation."""

    def observe(self, *events: dict) -> str:
        """Feed one synthetic connected frame and intentionally end the stream."""

        observer = TailObserver()
        self.assertEqual(observer.connected(), "stream_connected")
        observer.feed(frame(*events))
        return observer.finish(clean_end=True, expected_request_id=REQUEST)

    def test_list_failure(self) -> None:
        """A linked failed list is evidence of a pre-create failure."""

        self.assertEqual(self.observe(event("routing_list", "phase_failure"),
                                      event("request_exit", "server_error")),
                         "routing_list_failed")

    def test_create_failure_keeps_only_numeric_provider_facts(self) -> None:
        """Even an HTTP 200 create response can be a failed provider operation."""

        self.assertEqual(self.observe(event("routing_list", "success"),
                                      event("routing_create", "phase_failure",
                                            provider_http_status=200, provider_error_code=10000),
                                      event("request_exit", "server_error")),
                         "routing_create_failed_provider_http_200_code_10000")

    def test_create_success_then_outer_failure(self) -> None:
        """A later failure must not be mislabeled as a provider failure."""

        self.assertEqual(self.observe(event("routing_list", "success"),
                                      event("routing_create", "success"),
                                      event("request_exit", "server_error")),
                         "routing_create_succeeded_later_failure")

    def test_success_with_existing_rule(self) -> None:
        """A successful root need not create a new rule."""

        self.assertEqual(self.observe(event("routing_list", "success"),
                                      event("request_exit", "success")),
                         "e2e_address_add_succeeded")

    def test_authenticated_cli_parent_is_valid(self) -> None:
        """The server root can itself be the child of an authenticated CLI span."""

        self.assertEqual(self.observe(event("routing_list", "success"),
                                      event("routing_create", "success"),
                                      event("request_exit", "success",
                                            parent_span_id="f" * 16)),
                         "e2e_address_add_succeeded")

    def test_missing_or_duplicate_causal_evidence(self) -> None:
        """Missing list, duplicate root, or wrong parent cannot classify a cause."""

        self.assertEqual(self.observe(event("request_exit", "server_error")),
                         "UNVERIFIED (phase_missing)")
        root = event("request_exit", "server_error")
        self.assertEqual(self.observe(event("routing_list", "phase_failure"), root, root),
                         "UNVERIFIED (causal_ambiguity)")
        self.assertEqual(self.observe(event("routing_list", "phase_failure",
                                            parent_span_id="e" * 16), root),
                         "UNVERIFIED (causal_ambiguity)")

    def test_order_and_outcome_must_be_consistent(self) -> None:
        """A create before list and a failed list with success root are ambiguous."""

        self.assertEqual(self.observe(event("routing_create", "phase_failure"),
                                      event("routing_list", "success"),
                                      event("request_exit", "server_error")),
                         "UNVERIFIED (phase_order)")
        self.assertEqual(self.observe(event("routing_list", "phase_failure"),
                                      event("request_exit", "success")),
                         "UNVERIFIED (outcome_inconsistent)")

    def test_sensitive_unknown_event_never_reaches_stdout(self) -> None:
        """Unknown keys, raw console text and sensitive envelope data fail closed."""

        output = io.StringIO()
        observer = TailObserver()
        with redirect_stdout(output):
            observer.connected()
            observer.feed(frame(event("routing_list", "success",
                                      private_url="https://private.invalid/secret@example.invalid")))
            label = observer.finish(clean_end=True, expected_request_id=REQUEST)
        self.assertEqual(label, "UNVERIFIED (event_schema)")
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("private", label)

    def test_raw_or_wrong_service_and_sampling_fail_closed(self) -> None:
        """Only exact service and un-sampled reviewed frames are accepted."""

        for raw, expected in (
            (frame(script="other-worker"), "service_unverified"),
            (frame(sampleRate=0.5), "sampled_stream"),
            (frame(logs=[{"level": "log", "timestamp": 1,
                          "message": ["sensitive raw console message"]}]), "unreviewed_record"),
            (frame(exceptions=[{"message": "secret@example.invalid"}]), "unreviewed_record"),
        ):
            observer = TailObserver()
            observer.connected()
            observer.feed(raw)
            self.assertEqual(observer.finish(clean_end=True, expected_request_id=REQUEST),
                             f"UNVERIFIED ({expected})")

    def test_limits_loss_and_cleanup_failure(self) -> None:
        """Overflow, drop, timeout and non-clean shutdown never infer a cause."""

        observer = TailObserver()
        self.assertEqual(observer.finish(clean_end=True, expected_request_id=REQUEST),
                         "UNVERIFIED (not_connected)")
        observer.connected()
        observer.feed(b" " * (MAX_FRAME_BYTES + 1))
        self.assertEqual(observer.finish(clean_end=True, expected_request_id=REQUEST),
                         "UNVERIFIED (stream_limit)")

        observer = TailObserver()
        observer.connected()
        observer.feed(frame(event("routing_list", "phase_failure"),
                            event("request_exit", "server_error")))
        observer.lost()
        self.assertEqual(observer.finish(clean_end=True, expected_request_id=REQUEST),
                         "UNVERIFIED (stream_loss)")

        observer = TailObserver()
        observer.connected()
        observer.feed(frame(event("routing_list", "phase_failure"),
                            event("request_exit", "server_error")))
        self.assertEqual(observer.finish(clean_end=False, expected_request_id=REQUEST),
                         "UNVERIFIED (stream_loss)")

        clock = [0.0]
        observer = TailObserver(now=lambda: clock[0])
        observer.connected()
        clock[0] = MAX_SECONDS + 1
        observer.feed(frame())
        self.assertEqual(observer.finish(clean_end=True, expected_request_id=REQUEST),
                         "UNVERIFIED (stream_limit)")

    def test_malformed_types_cannot_raise_or_echo(self) -> None:
        """Hostile JSON types are fixed failures, not uncaught tracebacks."""

        for malformed in (
            event("routing_list", "success", phase=[]),
            event("routing_list", "success", error_code=[]),
            event("routing_list", "success", provider_http_status=True),
        ):
            observer = TailObserver()
            observer.connected()
            observer.feed(frame(malformed))
            self.assertEqual(observer.finish(clean_end=True, expected_request_id=REQUEST),
                             "UNVERIFIED (event_schema)")

    def test_duplicate_json_keys_are_not_silently_overwritten(self) -> None:
        """Even apparently harmless duplicate envelope keys make evidence unusable."""

        observer = TailObserver()
        observer.connected()
        observer.feed(frame()[:-1] + b',"scriptName":"amail-mail-staging"}')
        self.assertEqual(observer.finish(clean_end=True, expected_request_id=REQUEST),
                         "UNVERIFIED (stream_malformed)")

    def test_private_request_binding_rejects_another_caller(self) -> None:
        """One unrelated staging add must never become the authorized E2E result."""

        observer = TailObserver()
        observer.connected()
        observer.feed(frame(event("routing_list", "success"),
                            event("request_exit", "success")))
        self.assertEqual(observer.finish(clean_end=True),
                         "UNVERIFIED (provenance_unbound)")
        self.assertEqual(observer.finish(clean_end=True, expected_request_id="not-a-uuid"),
                         "UNVERIFIED (provenance_unbound)")
        self.assertEqual(observer.finish(
            clean_end=True, expected_request_id="ffffffff-ffff-ffff-ffff-ffffffffffff"),
            "UNVERIFIED (provenance_mismatch)")

    def test_producer_impossible_events_are_not_evidence(self) -> None:
        """Required bucket and phase/error invariants match trace.rs::Event."""

        missing_duration = event("routing_list", "success")
        del missing_duration["duration_ms_bucket"]
        missing_root_error = event("request_exit", "server_error")
        del missing_root_error["error_code"]
        for malformed in (
            missing_duration,
            event("routing_list", "success", response_bytes_bucket=8),
            event("request_exit", "success", error_code="other_server"),
            missing_root_error,
            event("routing_create", "phase_failure", error_code=None),
            event("routing_create", "phase_failure", provider_http_status=None),
            event("routing_list", "success", request_bytes_bucket=8),
            event("routing_list", "success", duration_ms_bucket=3),
        ):
            observer = TailObserver()
            observer.connected()
            observer.feed(frame(malformed))
            self.assertEqual(observer.finish(clean_end=True, expected_request_id=REQUEST),
                             "UNVERIFIED (event_schema)")


if __name__ == "__main__":
    unittest.main()
