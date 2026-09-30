"""Synthetic fail-closed contract tests for the fifth-mail cleanup guard."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
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

    def test_get_reports_fixed_field_mismatches_without_weakening_gate(self) -> None:
        """Every strict predicate has a fixed label and never embeds its value."""

        row = {"id": "known_1", "mailbox": MAILBOX, "direction": "inbound",
               "subject": SUBJECT, "from": cleanup.SENDER, "to": [MAILBOX],
               "has_text": True, "has_html": True, "has_attachments": True,
               "attachment_count": 2,
               "received_at": "2026-09-29T15:20:00Z",
               "metadata": {"message_id": "<provider-123@mx.cloudflare.net>"}}
        with patch.object(cleanup, "success", return_value=[row]):
            self.assertEqual(cleanup.verify_row(Path("amail"), {}, "known_1", MAILBOX, SUBJECT, True), row)
        cases = (
            ("id", "other", "fixture_get_id_mismatch"),
            ("mailbox", "other", "fixture_get_mailbox_mismatch"),
            ("direction", "outbound", "fixture_get_direction_mismatch"),
            ("subject", "other", "fixture_get_subject_mismatch"),
            ("from", "other", "fixture_get_from_mismatch"),
            ("to", ["other"], "fixture_get_to_mismatch"),
            ("has_text", False, "fixture_get_text_mismatch"),
            ("has_html", False, "fixture_get_html_mismatch"),
            ("has_attachments", False, "fixture_get_attachments_mismatch"),
            ("attachment_count", 1, "fixture_get_attachment_count_mismatch"),
            ("metadata", "other", "fixture_get_metadata_shape_mismatch"),
            ("metadata", {"message_id": "other"}, "fixture_get_message_id_mismatch"),
            ("received_at", None, "fixture_get_received_at_mismatch"),
        )
        for field, value, label in cases:
            with self.subTest(field=field, label=label), \
                 patch.object(cleanup, "success", return_value=[{**row, field: value}]):
                with self.assertRaisesRegex(cleanup.CleanupFailure, f"^{label}$"):
                    cleanup.verify_row(Path("amail"), {}, "known_1", MAILBOX, SUBJECT, True)

    def test_get_distractor_requires_plain_text_shape(self) -> None:
        """The second fixture has no HTML or attachments, even if the first does."""

        subject = SUBJECT.replace("Signal", "Distractor")
        row = {"id": "known_2", "mailbox": MAILBOX, "direction": "inbound",
               "subject": subject, "from": cleanup.SENDER, "to": [MAILBOX],
               "has_text": True, "has_html": False, "has_attachments": False,
               "attachment_count": 0,
               "received_at": "2026-09-29T15:20:00Z",
               "metadata": {"message_id": "<provider-456@mx.cloudflare.net>"}}
        with patch.object(cleanup, "success", return_value=[row]):
            cleanup.verify_row(Path("amail"), {}, "known_2", MAILBOX, subject, False)
        with patch.object(cleanup, "success", return_value=[{**row, "has_html": True}]):
            with self.assertRaisesRegex(cleanup.CleanupFailure, "^fixture_get_html_mismatch$"):
                cleanup.verify_row(Path("amail"), {}, "known_2", MAILBOX, subject, False)

    def test_archive_corrobates_both_fixtures_before_delete(self) -> None:
        """Native CLI ZIP output must match exact manifest, text, MIME, and asset shape."""

        cleanup.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cleanup.TEMP) as directory:
            root = Path(directory)
            for signal in (True, False):
                with self.subTest(signal=signal):
                    suffix = "signal" if signal else "distractor"
                    subject = SUBJECT if signal else SUBJECT.replace("Signal", "Distractor")
                    phrase = ("NebulaInvariant-" if signal else "HarborOpposite-") + "0123456789abcdef"
                    msg_id = "known_1" if signal else "known_2"
                    delivered = "<provider-123@mx.cloudflare.net>"
                    row = {"received_at": "2026-09-29T15:20:00Z",
                           "metadata": {"message_id": delivered}}
                    archive = root / f"{suffix}.zip"
                    archive.write_bytes(b"synthetic")
                    dest = root / suffix
                    dest.mkdir()
                    (dest / "body.txt").write_text(phrase, encoding="utf-8")
                    manifest = (f'version = 1\nid = "{msg_id}"\ndirection = "inbound"\n'
                                f'from = "{cleanup.SENDER}"\nto = ["{MAILBOX}"]\n'
                                f'subject = "{subject}"\nreceived_at = "{row["received_at"]}"\n'
                                f'message_id = "{delivered}"\n')
                    if signal:
                        assets = dest / "assets"
                        assets.mkdir()
                        (dest / "body.html").write_text(
                            f'<p>{phrase}</p><img src="cid:chart-0123456789abcdef">', encoding="utf-8")
                        (assets / "1-chart.png").write_bytes(cleanup.PNG)
                        (assets / "2-payload.bin").write_bytes(b"x" * 73)
                        manifest += ('\n[[assets]]\npath = "assets/1-chart.png"\n'
                                     'content_type = "image/png"\ndisposition = "inline"\n'
                                     'cid = "chart-0123456789abcdef"\nfilename = "chart.png"\n'
                                     '\n[[assets]]\npath = "assets/2-payload.bin"\n'
                                     'content_type = "application/octet-stream"\n'
                                     'disposition = "attachment"\nfilename = "payload.bin"\n')
                    (dest / "manifest.toml").write_text(manifest, encoding="utf-8")
                    outputs = [[{"id": msg_id, "path": str(archive), "unpacked": False}],
                               [{"path": str(dest), "unpacked": True}]]
                    with patch.object(cleanup, "success", side_effect=outputs) as cli:
                        cleanup.verify_archive(Path("amail"), {}, root, msg_id,
                                               MAILBOX, subject, signal, row)
                        self.assertEqual([call.args[2] for call in cli.call_args_list],
                                         ["read", "unpack"])
                    manifest_path = dest / "manifest.toml"
                    manifest_path.write_text(manifest.replace(f'id = "{msg_id}"',
                                                              'id = "wrong"'), encoding="utf-8")
                    with patch.object(cleanup, "success", side_effect=outputs):
                        with self.assertRaisesRegex(cleanup.CleanupFailure,
                                                    "^fixture_archive_manifest_mismatch$"):
                            cleanup.verify_archive(Path("amail"), {}, root, msg_id,
                                                   MAILBOX, subject, signal, row)
                    manifest_path.write_text(manifest, encoding="utf-8")
                    if signal:
                        html_path = dest / "body.html"
                        html_path.write_text(f'<p>{phrase}</p><img onerror="alert(1)" '
                                             'src="cid:chart-0123456789abcdef">', encoding="utf-8")
                        with patch.object(cleanup, "success", side_effect=outputs):
                            with self.assertRaisesRegex(cleanup.CleanupFailure,
                                                        "^fixture_archive_html_mismatch$"):
                                cleanup.verify_archive(Path("amail"), {}, root, msg_id,
                                                       MAILBOX, subject, signal, row)
                        html_path.write_text(f'<p>{phrase}</p><img '
                                             'src="cid:chart-0123456789abcdef">', encoding="utf-8")
                        asset_path = dest / "assets/2-payload.bin"
                        asset_path.write_bytes(b"x" * 72)
                        with patch.object(cleanup, "success", side_effect=outputs):
                            with self.assertRaisesRegex(cleanup.CleanupFailure,
                                                        "^fixture_archive_attachment_mismatch$"):
                                cleanup.verify_archive(Path("amail"), {}, root, msg_id,
                                                       MAILBOX, subject, signal, row)
                        asset_path.write_bytes(b"x" * 73)
                    (dest / "body.txt").write_text("wrong", encoding="utf-8")
                    with patch.object(cleanup, "success", side_effect=outputs):
                        with self.assertRaisesRegex(cleanup.CleanupFailure,
                                                    "^fixture_archive_body_mismatch$"):
                            cleanup.verify_archive(Path("amail"), {}, root, msg_id,
                                                   MAILBOX, subject, signal, row)

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
