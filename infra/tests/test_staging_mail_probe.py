"""Cheap local contracts for the hosted SMTP/progressive-disclosure probe."""

from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import staging_mail_e2e as probe


class ProbeContractTests(unittest.TestCase):
    """Keep relation provenance and native JSONL handling independent of providers."""

    def test_second_fixture_uses_first_verified_data_receipt(self):
        """Relations are unavailable until the first SMTP DATA was accepted."""
        address = "owned@" + probe.STAGING.domain
        first, first_oracle = probe.make_mail(address, "0" * 16, True)
        second, second_oracle = probe.make_mail(address, "0" * 16, False)
        parent, child = "<first@example.org>", "<second@example.org>"
        observed = []

        def data(raw):
            """Record exact submission order without submitting mail."""
            observed.append(raw)
            if len(observed) == 1:
                self.assertNotIn(b"In-Reply-To:", raw)
                self.assertIsNone(first_oracle["provider_message_id"])
                return 250, f"2.0.0 Ok {parent}".encode()
            self.assertEqual(first_oracle["provider_message_id"], parent)
            self.assertIn(f"In-Reply-To: {parent}".encode(), raw)
            self.assertIn(f"References: {parent}".encode(), raw)
            self.assertIn(f"Reply-To: {address}".encode(), raw)
            return 250, f"2.0.0 Ok {child}".encode()

        with patch.object(probe.smtplib, "SMTP_SSL") as transport:
            smtp = transport.return_value.__enter__.return_value
            smtp.mail.return_value = (250, b"ok")
            smtp.rcpt.return_value = (250, b"ok")
            smtp.data.side_effect = data
            probe.smtp_send_receipts("private", address,
                                    [(first, first_oracle), (second, second_oracle)], relate_second=True)
        self.assertEqual(len(observed), 2)
        self.assertEqual(second_oracle["provider_message_id"], child)
        self.assertEqual(second_oracle["in_reply_to"], parent)
        self.assertEqual(second_oracle["references"], [parent])
        self.assertEqual(second_oracle["reply_to"], address)

    def test_unverified_first_receipt_never_submits_second(self):
        """A provider response cannot be guessed into a reply relationship."""
        address = "owned@" + probe.STAGING.domain
        fixtures = [probe.make_mail(address, "1" * 16, rich) for rich in (True, False)]
        with patch.object(probe.smtplib, "SMTP_SSL") as transport:
            smtp = transport.return_value.__enter__.return_value
            smtp.mail.return_value = (250, b"ok")
            smtp.rcpt.return_value = (250, b"ok")
            smtp.data.return_value = (250, b"accepted without verified identifier")
            with self.assertRaisesRegex(probe.ProbeFailure, "smtp_receipt_unverified"):
                probe.smtp_send_receipts("private", address, fixtures, relate_second=True)
            self.assertEqual(smtp.data.call_count, 1)
        self.assertNotIn("In-Reply-To", fixtures[1][0])

    def test_missing_send_intent_requires_stop(self):
        """The probe accepts native empty events but rejects resend-like recovery."""
        topics = ["send", "events", "search", "machine"]

        def values(binary, env, *args, failure):
            """Return native CLI shapes only, never the HTTP events envelope."""
            if args[0] == "discover":
                topic = args[1] if len(args) > 1 else "index"
                body = {"topics": topics, "explore": "amail discover TOPIC"} if topic == "index" else {}
                if topic == "send":
                    body["children"] = ["send.schema", "events"]
                if topic == "events":
                    body["children"] = ["events.schema"]
                if topic == "search":
                    body["metadata_keys"] = ["rfc_message_id", "in_reply_to", "references", "reply_to"]
                return [{"schema": "amail.discover.v1", "topic": topic, "capabilities": body}]
            if args[0] == "events":
                return []
            return [{"policy": {"state": "held", "code": "send_held"},
                     "interpretation": "advisory_not_reservation_or_recipient_authorization",
                     "links": {"events": "/v1/events", "send_receipt": "/v1/sends/{idempotency_key}"},
                     "quotas": [{"kind": k, "used": 0, "limit": 5, "remaining": 5, "reset_at": "2026-10-04T00:00:00Z"}
                                for k in ("send", "send_messages", "send_hour")]}]

        def error(action):
            """Keep synthetic machine failures in memory."""
            return subprocess.CompletedProcess([], 1, b"", probe.json.dumps({
                "schema": "amail.machine.v1", "event": "error",
                "data": {"code": "not_found", "http_status": 404, "next_action": action}
            }).encode())

        with patch.object(probe, "amail", side_effect=values), patch.object(probe.subprocess, "run") as run:
            run.return_value = error("stop")
            probe.progressive_surfaces(Path("amail"), {})
            self.assertEqual(run.call_args.args[0][1:3], ["--machine", "send-status"])
            run.return_value = error("retry_later")
            with self.assertRaisesRegex(probe.ProbeFailure, "missing_intent_no_resend"):
                probe.progressive_surfaces(Path("amail"), {})


if __name__ == "__main__":
    unittest.main()
