"""Small offline contracts for protected self-send recovery and mutation boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import staging_owned_send as probe


class OwnedSendTests(unittest.TestCase):
    """Use fake subprocesses only; no provider or mail calls are made."""

    def test_grant_failure_reason_never_copies_provider_or_owner_values(self):
        """Known source guards and exception classes are sufficient diagnostics."""
        self.assertEqual(probe.grant_failure_reason(ValueError("staging_canary_owner_unverified")),
                         "owned_send_grant_staging_canary_owner_unverified")
        self.assertEqual(probe.grant_failure_reason(TypeError("private rule value")), "owned_send_grant_shape_unverified")
        self.assertEqual(probe.grant_failure_reason(TimeoutError("private signed URL")), "owned_send_grant_transport_unverified")
        self.assertEqual(probe.grant_failure_reason(ValueError("private recipient")), "owned_send_grant_unverified")

    def test_mapping_observation_is_bounded_and_preserves_original_recovery(self):
        """Record only two booleans, without guessing a global transport identity."""
        self.assertEqual(probe.mapping_observation("id@example", "<id@example>"),
                         {"exactly_equal": False, "anglebracket_normalization_equal": True})
        self.assertEqual(probe.mapping_observation("opaque-provider", "<wire@example>"),
                         {"exactly_equal": False, "anglebracket_normalization_equal": False})
        probe.mail.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=probe.mail.TEMP) as root:
            path = Path(root) / "receipt.json"
            path.write_text(json.dumps({"idempotency_key": "original", "archive_sha256": "digest"}))
            probe.update_recovery(path, {"provider_to_wire_observation": probe.mapping_observation("same", "same")})
            value = json.loads(path.read_text())
            self.assertEqual(value["idempotency_key"], "original")
            self.assertEqual(value["provider_to_wire_observation"],
                             {"exactly_equal": True, "anglebracket_normalization_equal": True})

    def test_unknown_receipt_never_authorizes_replay(self):
        """An unknown server receipt is not a successful send."""
        for state in ("unknown", "submitting", "rejected", None):
            with self.assertRaisesRegex(probe.mail.ProbeFailure, "unresolved_no_resend"):
                probe.accepted({"idempotency_key": "key", "id": "message", "state": state}, "key")
        self.assertEqual(probe.accepted({"idempotency_key": "key", "id": "message", "state": "accepted"}, "key"), "message")

    def test_lost_stdout_keeps_same_intent_and_discards_sensitive_output(self):
        """One timed-out submission must not trigger another subprocess send."""
        with patch.object(probe.subprocess, "run", side_effect=subprocess.TimeoutExpired("private", 90)) as run:
            probe.send_lost_output(Path("native.exe"), {}, "key", Path("intent.zip"))
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["native.exe", "send", "intent.zip", "--idempotency-key", "key"])
        self.assertEqual(run.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["stderr"], subprocess.DEVNULL)

    def test_prepare_persists_native_zip_and_uuid_before_send(self):
        """The intent digest covers the exact native pack output, not a reconstructed ZIP."""
        probe.mail.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=probe.mail.TEMP) as root:
            task = Path(root) / "owned-send"
            def pack(*args):
                Path(args[-1]).write_bytes(b"native-packed-bytes")
                return {"packed": True}
            with patch.object(probe, "one", side_effect=pack):
                key, archive = probe.prepare(Path("native"), {}, task, "self@example.invalid", "unique-title")
            intent = json.loads((task / "intent.json").read_text())
            self.assertEqual(intent["idempotency_key"], key)
            self.assertEqual(intent["archive_sha256"], probe.hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual(str(probe.uuid.UUID(key)), key)
            self.assertNotIn("cc", (task / "draft" / "manifest.toml").read_text())

    def test_original_zip_survives_disposable_task_cleanup(self):
        """An unknown send keeps byte-identical recovery outside the credential run tree."""
        probe.mail.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=probe.mail.TEMP) as outer:
            recovery_root = Path(outer)
            with patch.object(probe.mail, "TEMP", recovery_root):
                with tempfile.TemporaryDirectory(dir=recovery_root) as disposable:
                    archive = Path(disposable) / "intent.zip"
                    archive.write_bytes(b"exact-native-zip-private-content")
                    saved, receipt = probe.preserve_intent(archive, "original-uuid", "a" * 16)
                    self.assertNotEqual(saved.parent, archive.parent)
                    with self.assertRaises(FileExistsError):
                        probe.preserve_intent(archive, "replacement", "a" * 16)
                self.assertFalse(archive.exists())
                self.assertEqual(saved.read_bytes(), b"exact-native-zip-private-content")
                intent = json.loads(receipt.read_text())
                self.assertEqual(intent["idempotency_key"], "original-uuid")
                self.assertEqual(intent["archive"], saved.name)
                self.assertEqual(intent["state"], "unresolved")
                self.assertEqual(intent["archive_sha256"], probe.hashlib.sha256(saved.read_bytes()).hexdigest())

    def test_inventory_refuses_other_task_or_duplicate(self):
        """Cleanup must not broaden its scope beyond exact mailbox/title."""
        base = {"id": "m", "mailbox": "self", "subject": "title", "direction": "inbound"}
        for rows in ([dict(base, subject="other")], [base, base], [{"next_cursor": "private"}]):
            with patch.object(probe.mail, "amail", return_value=rows):
                with self.assertRaises(probe.mail.ProbeFailure):
                    probe.inventory(Path("native"), {}, "self", "title")

    def test_cleanup_retires_even_when_discovery_fails(self):
        """Failed discovery cannot leave the new ingress alias enabled."""
        with patch.object(probe, "retire") as retire, patch.object(probe, "inventory", side_effect=probe.mail.ProbeFailure("offline")):
            with self.assertRaisesRegex(probe.mail.ProbeFailure, "cleanup_messages"):
                probe.cleanup(Path("native"), {}, "zone", "route", "account", "token", "self", "title", None)
        retire.assert_called_once()

    def test_same_key_replay_requires_positive_acceptance_and_preserves_ids(self):
        """Unknown never invokes send; accepted replay uses the original byte archive/key."""
        with patch.object(probe, "one") as cli:
            with self.assertRaisesRegex(probe.mail.ProbeFailure, "unresolved_no_resend"):
                probe.replay_accepted(Path("native"), {}, "key", Path("missing"),
                                      {"idempotency_key": "key", "state": "unknown"}, "provider", "self", "title")
            cli.assert_not_called()
        probe.mail.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=probe.mail.TEMP) as root:
            archive = Path(root) / "intent.zip"
            archive.write_bytes(b"same-native-zip")
            (archive.parent / "intent.json").write_text(json.dumps({"archive_sha256": probe.hashlib.sha256(archive.read_bytes()).hexdigest()}))
            receipt = {"idempotency_key": "key", "state": "accepted", "id": "m"}
            with patch.object(probe, "one", side_effect=[{"state": "accepted", "id": "m"}, receipt]) as cli, \
                 patch.object(probe, "detail", return_value={"metadata": {"provider_id": "provider"}}):
                probe.replay_accepted(Path("native"), {}, "key", archive, receipt, "provider", "self", "title")
            self.assertEqual(cli.call_args_list[0].args[2:], ("send", str(archive), "--idempotency-key", "key"))
            self.assertEqual(cli.call_args_list[1].args[2:], ("send-status", "key", "--local"))

    def test_confirmation_fails_before_any_mutation(self):
        """No optional confirmation means no alias creation or send."""
        with patch.dict(os.environ, {"AMAIL_STAGING_CANARY_CONFIRM": ""}), patch.object(probe.mail, "amail") as cli:
            with self.assertRaisesRegex(probe.mail.ProbeFailure, "confirmation_required"):
                probe.execute(Path("native"), Path("home"), Path("run"), "a" * 16)
            cli.assert_not_called()

    def test_negative_feedback_is_not_retried(self):
        """Real adverse outcomes fail the task instead of triggering another send."""
        with patch.object(probe.time, "monotonic", side_effect=[0, 1]), \
             patch.object(probe, "one", return_value={"id": "m", "outcomes": [{"recipient": "self", "kind": "bounced"}]}) as cli:
            with self.assertRaisesRegex(probe.mail.ProbeFailure, "negative_feedback"):
                probe.verify_feedback(Path("native"), {}, "m", "self")
            self.assertEqual(cli.call_args.args[2:], ("outcomes", "m"))
            cli.assert_called_once()

    def test_feedback_timeout_is_explicit_and_never_sends(self):
        """Absent feedback fails acceptance without implying permission to resend."""
        with patch.object(probe.time, "monotonic", side_effect=[0, 241]), patch.object(probe, "one") as cli:
            with self.assertRaisesRegex(probe.mail.ProbeFailure, "feedback_timeout_no_resend"):
                probe.verify_feedback(Path("native"), {}, "m", "self")
            cli.assert_not_called()


if __name__ == "__main__":
    unittest.main()
