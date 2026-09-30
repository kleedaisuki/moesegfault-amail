"""Synthetic shape-only diagnosis contracts; no provider data or live queries."""
import contextlib
import io
import os
import re
import unittest
from http.client import BadStatusLine, IncompleteRead
from pathlib import Path
from unittest.mock import MagicMock, patch

import staging_settings_audit_shape as subject
import staging_settings_patch_audit as transport

ACCOUNT = "a" * 32


def envelope(count="1"):
    """Use synthetic private values while preserving only relevant container shapes."""
    return {"success": True, "errors": [], "result": [{"id": "PRIVATE_ID",
        "action": {"time": "PRIVATE_TIME", "result": "PRIVATE_OUTCOME"},
        "raw": {"method": "PRIVATE_METHOD", "uri": "PRIVATE_URI", "status_code": 299},
        "actor": {"email": "PRIVATE_EMAIL"}, "resource": {"request": "PRIVATE_BODY"}}],
        "result_info": {"count": count, "cursor": ""}}


class ShapeTests(unittest.TestCase):
    """Schema observation is independent of historical success and original acceptance."""

    def test_type_presence_bins_are_closed(self):
        """Never stringify content, unknown keys or identifiers into a type result."""
        for value, expected in ((subject.MISSING, "missing"), (None, "null"),
            (True, "boolean"), (0, "number"), (1.0, "number"), ("PRIVATE", "string"),
            ({"PRIVATE": "PRIVATE"}, "object"), (["PRIVATE"], "array"), (object(), "other")):
            self.assertEqual(subject.shape(value), expected)
        self.assertEqual(subject.group([]), "no_rows")
        self.assertEqual(subject.group(["object", "null"]), "mixed")

    def test_numeric_count_exposes_strict_mismatch_without_changing_gate(self):
        """A bounded frame can be inspected while original numeric count remains rejected."""
        for count, strict in (("1", "match"), (1, "mismatch"), (1.0, "mismatch")):
            status, values = subject.diagnose_payload(envelope(count))
            self.assertEqual(status, "SHAPE_DIAGNOSED")
            self.assertEqual(values["strict_count"], strict)
            self.assertEqual(values["count_relation"], "match")
            self.assertEqual(values["raw_status_shape"], "number")
            self.assertEqual(values["action_result_shape"], "string")
            # Private synthetic raw/action values are intentionally not inspected.
            # An unchanged outcome classifier must never admit this fixture.
            self.assertEqual(transport.classify(envelope(count), ACCOUNT)[0], "UNVERIFIED")

    def test_envelope_schema_and_optional_presence_are_distinct(self):
        """Standard known optional fields are named locally, not enumerated from provider data."""
        data = envelope()
        data["messages"] = []
        status, values = subject.diagnose_payload(data)
        self.assertEqual(status, "UNVERIFIED")
        self.assertEqual(values["messages_shape"], "array")
        self.assertEqual(values["envelope_keys"], "unknown")
        for payload, expected in ((None, "null"), ([], "array"), ("PRIVATE", "string"), (False, "boolean")):
            status, values = subject.diagnose_payload(payload)
            self.assertEqual(status, "UNVERIFIED")
            self.assertEqual(values["envelope_shape"], expected)

    def test_continuation_oversized_rows_and_count_drift_are_unverified(self):
        """Never process more than 100 rows or silently accept a continuation signal."""
        for changes in ({"cursor": "PRIVATE"}, {"cursor": None}, {"count": 2},
                        {"count": True}, {"count": "01"}, {"has_more": False}):
            data = envelope()
            data["result_info"].update(changes)
            self.assertEqual(subject.diagnose_payload(data)[0], "UNVERIFIED")
        data = envelope()
        del data["result_info"]["cursor"]
        status, values = subject.diagnose_payload(data)
        self.assertEqual(status, "UNVERIFIED")
        self.assertEqual(values["cursor_shape"], "missing")
        data = envelope()
        data["result"] *= 101
        status, values = subject.diagnose_payload(data)
        self.assertEqual(status, "UNVERIFIED")
        self.assertEqual(values["rows_bound"], "exceeded")
        self.assertEqual(values["row_shape"], "skipped")
        for count in (float("nan"), float("inf"), 10 ** 1000, [], "PRIVATE"):
            self.assertIsNone(subject.count_shape(count)[1])

    def test_row_action_raw_shapes_are_aggregated_without_names(self):
        """Mixed or unknown shape data remains diagnostic only, never matched to a PATCH."""
        data = envelope("2")
        data["result"].append({"action": None, "raw": {"PRIVATE_KEY": "PRIVATE"}})
        status, values = subject.diagnose_payload(data)
        self.assertEqual(status, "UNVERIFIED")
        self.assertEqual(values["action_shape"], "mixed")
        self.assertEqual(values["raw_keys"], "mixed")
        self.assertNotIn("PRIVATE", str(values))
        data = {"success": True, "result": [], "result_info": {"count": "0", "cursor": ""}}
        status, values = subject.diagnose_payload(data)
        self.assertEqual(status, "SHAPE_DIAGNOSED")
        self.assertEqual(values["row_shape"], "no_rows")

    def test_original_object_guard_and_shared_transport_remain_private(self):
        """Refactoring for envelope types does not admit scalar responses to old classifier."""
        with patch.object(transport, "read_audit_payload", return_value=["PRIVATE"]):
            with self.assertRaises(transport.AuditReadError):
                transport.read_audit(ACCOUNT, "PRIVATE_TOKEN")
        env = {"CLOUDFLARE_ACCOUNT_ID": ACCOUNT, "CLOUDFLARE_API_TOKEN": "PRIVATE_TOKEN",
            "AMAIL_SETTINGS_AUDIT_SHAPE_CONFIRM": subject.CONFIRM, "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/codex/amail-v0.1.0",
            "GITHUB_SHA": "b" * 40}
        for phase, error in (("open", BadStatusLine("PRIVATE_STATUS")),
                             ("read", IncompleteRead(b"PRIVATE_BODY", 100))):
            response, opener = MagicMock(), MagicMock()
            response.status = 200
            response.__enter__.return_value = response
            opener.open.return_value = response
            if phase == "open":
                opener.open.side_effect = error
            else:
                response.read.side_effect = error
            out, err = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, env, clear=True), patch.object(transport, "build_opener", return_value=opener), \
                 contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(subject.main(), 1)
            self.assertIn("staging_settings_audit_shape_read=transport", out.getvalue())
            self.assertNotIn("PRIVATE", out.getvalue())
            self.assertEqual(err.getvalue(), "")
            opener.open.assert_called_once()

    def test_output_guard_and_credentials_after_tests(self):
        """All displayed names come from source enums; no status/URI/actor/ID content exists."""
        env = {"CLOUDFLARE_ACCOUNT_ID": ACCOUNT, "CLOUDFLARE_API_TOKEN": "PRIVATE_TOKEN",
            "AMAIL_SETTINGS_AUDIT_SHAPE_CONFIRM": subject.CONFIRM, "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/codex/amail-v0.1.0",
            "GITHUB_SHA": "b" * 40}
        out = io.StringIO()
        with patch.dict(os.environ, env, clear=True), patch.object(subject, "read_audit_payload", return_value=envelope()) as reader, \
             contextlib.redirect_stdout(out):
            self.assertEqual(subject.main(), 0)
        reader.assert_called_once_with(ACCOUNT, "PRIVATE_TOKEN")
        self.assertEqual(len(out.getvalue().splitlines()), len(subject.FIELDS) + 1)
        for private in ("PRIVATE", ACCOUNT, "299", "historical", "attestation", "Current Version ID"):
            self.assertNotIn(private, out.getvalue())
        with patch.dict(os.environ, {**env, "GITHUB_RUN_ATTEMPT": "2"}, clear=True), \
             patch.object(subject, "read_audit_payload") as reader, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(subject.main(), 1)
            reader.assert_not_called()
        source = (Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = re.split(r"(?m)^  [a-z0-9-]+:\n",
                       source.split("  staging-settings-audit-shape:\n", 1)[1], maxsplit=1)[0]
        self.assertLess(job.index("test_staging_settings_audit_shape.py"), job.index("secrets.CLOUDFLARE_API_TOKEN"))
        self.assertIn("environment: staging", job)
        self.assertNotIn("wrangler", job)


if __name__ == "__main__":
    unittest.main()
