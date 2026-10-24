"""Keep hosted rejection diagnostics precise without copying untrusted output."""
from __future__ import annotations

import json
import unittest
from typing import Any

import staging_v030_profiles as probe


def error_record(code: object, status: object = None) -> bytes:
    data: dict[str, Any] = {"code": code, "http_status": status,
                            "request_id": "private-request-id", "message": "private-provider-prose"}
    return json.dumps({"schema": "amail.machine.v1", "event": "error", "data": data}).encode()


class ProfileRejectionDiagnosticsTests(unittest.TestCase):
    def test_expected_denial_still_passes(self) -> None:
        probe.check_rejection(1, b"", error_record("user_profile_required", 403),
                              "user_profile_required", "permanent")

    def test_protocol_mismatch_identifies_case_and_closed_code(self) -> None:
        with self.assertRaises(probe.ProfileProbeError) as caught:
            probe.check_rejection(1, b"", error_record("http_error", 403),
                                  "user_profile_required", "permanent")
        self.assertEqual(str(caught.exception),
                         "profiles_permanent_expected_user_profile_required_actual_http_error_http403_errors1")

    def test_private_code_and_invalid_http_status_are_not_copied(self) -> None:
        with self.assertRaises(probe.ProfileProbeError) as caught:
            probe.check_rejection(1, b"", error_record("private-capability@example.test", "private-status"),
                                  "mailbox_in_use", "reader_during_writer")
        self.assertEqual(str(caught.exception),
                         "profiles_reader_during_writer_expected_mailbox_in_use_actual_unknown_httpnone_errors1")

    def test_error_count_is_observable_without_record_payloads(self) -> None:
        stderr: bytes = b"\n".join([error_record("mailbox_in_use", 409)] * 2)
        with self.assertRaises(probe.ProfileProbeError) as caught:
            probe.check_rejection(1, b"", stderr, "mailbox_in_use", "writer_during_readers")
        self.assertEqual(str(caught.exception),
                         "profiles_writer_during_readers_expected_mailbox_in_use_actual_unknown_httpnone_errors2")

    def test_success_and_missing_error_still_fail(self) -> None:
        with self.assertRaisesRegex(probe.ProfileProbeError, "forbidden_operation_succeeded$"):
            probe.check_rejection(0, b"", b"", "mailbox_in_use", "reader_during_writer")
        with self.assertRaisesRegex(probe.ProfileProbeError, "errors0$"):
            probe.check_rejection(1, b"", b"", "mailbox_in_use", "reader_during_writer")

    def test_profile_failure_http_status_comes_from_typed_details(self) -> None:
        record: bytes = json.dumps({"schema": "amail.machine.v1", "event": "error", "data": {
            "code": "profile_request_failed", "details": {"status": 409, "private": "secret"}}}).encode()
        with self.assertRaises(probe.ProfileProbeError) as caught:
            probe.check_rejection(1, b"", record, "mailbox_in_use", "writer_during_readers")
        self.assertEqual(str(caught.exception),
                         "profiles_writer_during_readers_expected_mailbox_in_use_actual_profile_request_failed_http409_errors1")


if __name__ == "__main__":
    unittest.main()
