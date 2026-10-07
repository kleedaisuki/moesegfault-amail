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
        currency = "USD"

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
                     "links": {"events": "/v1/events", "send_receipt": "/v1/sends/{idempotency_key}", "billing": "/v1/billing"},
                     "billing": {"plan": "free", "period_start": 1, "period_end": 2,
                                 "outbound": {"meter": "outbound_recipients", "included": 100, "accepted": 0, "reserved": 0, "remaining_included": 100},
                                 "overage": {"enabled": False, "currency": currency, "budget_micros": 0, "accrued_micros": 0, "reserved_micros": 0, "remaining_budget_micros": 0}},
                     "quotas": [{"kind": k, "used": 0, "limit": limit, "remaining": limit, "reset_at": "2026-10-04T00:00:00Z"}
                                for k, limit in (("send_minute", 2), ("send_global", 10_000))]}]

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
            # Historical CNY remains readable elsewhere, not acceptable as current USD status.
            currency = "CNY"
            run.return_value = error("stop")
            with self.assertRaisesRegex(probe.ProbeFailure, "sending_status_overage_budget"):
                probe.progressive_surfaces(Path("amail"), {})


class SearchRestartContractTests(unittest.TestCase):
    """Exercise generation races without weakening search oracles or replaying writes."""

    @staticmethod
    def stale(code="search_job_stale", *, stdout=b"", operation="messages.search.poll"):
        """Build the exact safe CLI failure grammar observed in hosted acceptance."""
        return subprocess.CompletedProcess([], 1, stdout, (
            f"amail: mail API {operation} failed: HTTP 409 Conflict, code={code}, "
            "correlation_id=123e4567-e89b-42d3-a456-426614174000\n"
        ).encode())

    def test_stale_restarts_identical_fresh_search_and_returns_only_complete_page(self):
        """Every predicate survives the restart and only the successful page is exposed."""
        args = ("search", "--mailbox", "owned@example.test", "--title", "^Signal$",
                "--regex", "--meta", "message_id=<receipt@example.test>", "--unread")
        success = subprocess.CompletedProcess([], 0, b'{"id":"current","subject":"Signal"}\n', b"")
        for code in ("search_job_stale", "search_cursor_stale"):
            with self.subTest(code=code), patch.object(probe.subprocess, "run", side_effect=[
                    self.stale(code), success]) as run, patch.object(probe.time, "sleep") as sleep:
                values = probe.amail(Path("amail"), {}, *args, failure="search_test_failed")
                self.assertEqual(values, [{"id": "current", "subject": "Signal"}])
                self.assertEqual(run.call_count, 2)
                self.assertEqual(run.call_args_list[0], run.call_args_list[1])
                self.assertEqual(run.call_args.args[0], ["amail", *args])
                sleep.assert_called_once_with(2)

    def test_stale_restarts_are_bounded_and_never_accept_missing_results(self):
        """Persistent mutation must fail rather than passing a positive or negative oracle."""
        with patch.object(probe.subprocess, "run", return_value=self.stale()) as run, \
                patch.object(probe.time, "sleep") as sleep:
            with self.assertRaisesRegex(probe.ProbeFailure, "search_test_failed_http_409_search_job_stale"):
                probe.amail(Path("amail"), {}, "search", "--title", "Signal", failure="search_test_failed")
            self.assertEqual(run.call_count, 3)
            self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 5])

    def test_pages_resume_mutations_and_other_conflicts_never_restart(self):
        """Recovery cannot mix snapshots, replay sends, or swallow unrelated HTTP 409."""
        for args, failure in [
            (("search", "--cursor", "old-page"), self.stale()),
            (("search", "--cursor=old-page"), self.stale()),
            (("search", "--resume", "old-job"), self.stale()),
            (("search", "--resume=old-job"), self.stale()),
            (("send", "draft.zip", "--idempotency-key", "original-key"), self.stale()),
            (("search",), self.stale("send_outcome_unknown")),
            (("search",), self.stale(operation="messages.send")),
            (("search",), self.stale(stdout=b'{"id":"partial"}\n')),
            (("search",), subprocess.CompletedProcess([], 1, b"", b"private unknown failure")),
        ]:
            with self.subTest(args=args, stderr=failure.stderr), \
                    patch.object(probe.subprocess, "run", return_value=failure) as run, \
                    patch.object(probe.time, "sleep") as sleep:
                with self.assertRaises(probe.ProbeFailure):
                    probe.amail(Path("amail"), {}, *args, failure="search_test_failed")
                run.assert_called_once()
                sleep.assert_not_called()

    def test_search_stale_grammar_rejects_mixed_or_unknown_diagnostics(self):
        """Only a full typed search failure, including wrapped poll errors, is recoverable."""
        original = self.stale().stderr
        wrapped = original.replace(b"amail: ", b"amail: search job 123e4567-e89b-42d3-a456-426614174000: ", 1)
        self.assertTrue(probe.restartable_search_error(wrapped))
        for value in (original + b"private extra text", b"untrusted prefix\n" + original,
                      original.replace(b"409 Conflict", b"503 Unavailable"),
                      original.replace(b"search_job_stale", b"search_job_expired")):
            self.assertFalse(probe.restartable_search_error(value))


if __name__ == "__main__":
    unittest.main()
