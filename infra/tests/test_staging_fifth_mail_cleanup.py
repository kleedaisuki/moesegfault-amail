"""Synthetic fail-closed contract tests for the fifth-mail cleanup guard."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import staging_fifth_mail_cleanup as cleanup


MAILBOX = "e2e-0123456789abcdef@mail-staging.moesegfault.dev"
SUBJECT = "AMAIL-E2E-0123456789abcdef-Signal"


class CleanupGuardTests(unittest.TestCase):
    """Check exact inventory and get gates without contacting any service."""

    def test_inventory_exhausts_pages_and_rejects_unrelated_mail(self) -> None:
        """A cursor page is mandatory and an unexpected row is never ignored."""

        row = {"id": "known_1", "mailbox": MAILBOX, "direction": "inbound", "subject": SUBJECT}
        with patch.object(cleanup, "search_page", side_effect=[
            (0, [row, {"next_cursor": "opaque"}], b""), (0, [], b"")
        ]) as search:
            self.assertEqual(cleanup.inventory(Path("amail"), {}, MAILBOX), {"known_1": row})
            self.assertEqual(search.call_count, 2)
        with patch.object(cleanup, "search_page", return_value=(0, [
            {**row, "mailbox": "other@mail-staging.moesegfault.dev"}
        ], b"")):
            with self.assertRaises(cleanup.CleanupFailure):
                cleanup.inventory(Path("amail"), {}, MAILBOX)

    def test_stale_read_restarts_from_first_page(self) -> None:
        """A stale cursor discards all partial results and retries only a read."""

        row = {"id": "known_1", "mailbox": MAILBOX, "direction": "inbound", "subject": SUBJECT}
        with patch.object(cleanup, "search_page", side_effect=[
            (0, [row, {"next_cursor": "old"}], b""),
            (1, [], b"amail: mail API search failed: HTTP 409 Conflict, code=search_cursor_stale\n"),
            (0, [row], b""),
        ]) as search, patch.object(cleanup.time, "sleep"):
            self.assertEqual(cleanup.inventory(Path("amail"), {}, MAILBOX), {"known_1": row})
            self.assertNotIn("--cursor", search.call_args_list[-1].args[2])

    def test_get_requires_exact_message_id_and_mime(self) -> None:
        """Subject and sender equality alone cannot authorize deletion."""

        row = {"id": "known_1", "mailbox": MAILBOX, "direction": "inbound",
               "subject": SUBJECT, "from": cleanup.SENDER, "to": [MAILBOX],
               "has_text": True, "has_html": True, "has_attachments": True,
               "attachment_count": 2,
               "metadata": {"message_id": "<amail-e2e-0123456789abcdef-signal@mail-staging.moesegfault.dev>"}}
        with patch.object(cleanup, "success", return_value=[row]):
            cleanup.verify_row(Path("amail"), {}, "known_1", MAILBOX, SUBJECT, True)
        with patch.object(cleanup, "success", return_value=[{**row, "metadata": {"message_id": "spoof"}}]):
            with self.assertRaises(cleanup.CleanupFailure):
                cleanup.verify_row(Path("amail"), {}, "known_1", MAILBOX, SUBJECT, True)

    def test_control_refuses_extra_mail_and_duplicate_fixture(self) -> None:
        """Only the exact two historical rows, active or deleted, are acceptable."""

        row = {"address_state": "retired", "needs_reconcile": 0, "owner_expected": 1,
               "signal_active": 1, "signal_deleted": 0, "distractor_active": 1,
               "distractor_deleted": 0, "inbound_active": 2, "other_inbound_active": 0,
               "other_inbound_deleted": 0, "outbound_active": 0, "outbound_deleted": 0,
               "embedding_pending": 0, "embedding_quarantined": 0}
        with patch.object(cleanup, "rules", return_value=[]), \
             patch.object(cleanup, "aggregate", return_value=row):
            cleanup.control("account", "token", "route", MAILBOX, 2)
            row["other_inbound_deleted"] = 1
            with self.assertRaises(cleanup.CleanupFailure):
                cleanup.control("account", "token", "route", MAILBOX, 2)
            row["other_inbound_deleted"] = 0
            row["signal_deleted"] = 1
            with self.assertRaises(cleanup.CleanupFailure):
                cleanup.control("account", "token", "route", MAILBOX, 2)

    def test_delete_accepts_only_cli_empty_204_render(self) -> None:
        """Deletion output is parsed separately from JSONL search and get rows."""

        with patch.object(cleanup.subprocess, "run", return_value=SimpleNamespace(
            returncode=0, stdout=b'{"ok":true}\n', stderr=b"")) as run:
            self.assertTrue(cleanup.delete_once(Path("amail"), {}, "known_1"))
            self.assertEqual(run.call_count, 1)
        with patch.object(cleanup.subprocess, "run", return_value=SimpleNamespace(
            returncode=0, stdout=b"null\n", stderr=b"")):
            self.assertFalse(cleanup.delete_once(Path("amail"), {}, "known_1"))

    def test_final_control_allows_cron_purge_only_after_mutation(self) -> None:
        """Physical purge may erase a soft-deleted row before final readback."""

        row = {"address_state": "retired", "needs_reconcile": 0, "owner_expected": 1,
               "signal_active": 0, "signal_deleted": 0, "distractor_active": 0,
               "distractor_deleted": 1, "inbound_active": 0, "other_inbound_active": 0,
               "other_inbound_deleted": 0, "outbound_active": 0, "outbound_deleted": 0,
               "embedding_pending": 0, "embedding_quarantined": 0}
        with patch.object(cleanup, "rules", return_value=[]), \
             patch.object(cleanup, "aggregate", return_value=row):
            with self.assertRaises(cleanup.CleanupFailure):
                cleanup.control("account", "token", "route", MAILBOX, 0)
            cleanup.control("account", "token", "route", MAILBOX, 0, allow_purge=True)


if __name__ == "__main__":
    unittest.main()
