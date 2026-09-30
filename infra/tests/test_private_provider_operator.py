"""Offline provenance/ZIP/confidentiality contracts; no real keys or provider access."""
import contextlib
import io
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import urllib.error

import private_provider_operator as operator


def archive(names):
    """Create encrypted-looking synthetic ZIP bytes only in memory."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as file:
        for name in names:
            entry = zipfile.ZipInfo(name)
            entry.external_attr = (stat.S_IFREG | 0o600) << 16
            file.writestr(entry, b"ENCRYPTED")
    return buffer.getvalue()


class OperatorTests(unittest.TestCase):
    """Untrusted input never becomes paths, executable prose or stdout."""

    def test_exact_zip_member(self):
        self.assertEqual(operator.envelope_from_zip(archive(["capture.enc.json"])), b"ENCRYPTED")

    def test_zip_extra_traversal_absolute_rejected(self):
        for names in (["../capture.enc.json"], ["/capture.enc.json"], ["capture.enc.json", "extra"], []):
            with self.subTest(names=names), self.assertRaises(Exception):
                operator.envelope_from_zip(archive(names))

    def test_zip_symlink_rejected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as file:
            entry = zipfile.ZipInfo("capture.enc.json")
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            file.writestr(entry, "PRIVATE")
        with self.assertRaises(Exception):
            operator.envelope_from_zip(buffer.getvalue())

    def test_paths_and_ci_keygen_refused(self):
        for session in ("../key", "C:\\key", "", "a/b", "UPPER"):
            with self.subTest(session=session), self.assertRaises(Exception):
                operator.session_path(session)
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), self.assertRaises(Exception):
            operator.session_path("valid-session")

    def test_unclassified_failure_not_printed(self):
        output = io.StringIO()
        with patch.object(operator.sys, "argv", ["operator", "inspect", "test", "1", "a" * 40]), \
                patch.object(operator, "inspect", side_effect=RuntimeError("TOKEN\nMAIL")), contextlib.redirect_stdout(output):
            self.assertEqual(operator.main(), 1)
        self.assertEqual(output.getvalue(), "private_provider_operator=UNVERIFIED cleanup=UNVERIFIED\n")

    def test_provenance_source_rejected_before_archive(self):
        run = {"id": 1, "run_attempt": 2}
        with patch.object(operator, "github_json", return_value=run) as api, self.assertRaises(Exception):
            operator.provenance("1", "a" * 40, "synthetic")
        self.assertEqual(api.call_count, 1)

    def test_child_never_inherits_credentials(self):
        import subprocess
        result = subprocess.CompletedProcess([], 0, b"unclassified", b"")
        with patch.dict(os.environ, {"GITHUB_TOKEN": "SECRET", "CF_OBSERVABILITY_TOKEN": "SECRET"}), \
                patch.object(operator.subprocess, "run", return_value=result) as execute:
            self.assertEqual(operator.child("classify", "session", b"CIPHERTEXT"), b"unclassified")
        env = execute.call_args.kwargs["env"]
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("CF_OBSERVABILITY_TOKEN", env)
        self.assertEqual(execute.call_args.kwargs["input"], b"CIPHERTEXT")

    def test_interruption_preserves_key_and_recoverable_coordinates(self):
        # All experiment files stay inside repository-root .temp, on hosted CI.
        root = Path(operator.__file__).resolve().parents[2] / ".temp"
        root.mkdir(exist_ok=True)
        for phase in ("token", "provenance", "download", "envelope_from_zip", "validate_envelope", "child", "github", "cleanup"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory(dir=root) as folder_name:
                folder = Path(folder_name)
                (folder / "private.pk8").write_bytes(b"SYNTHETIC-NOT-A-KEY")
                (folder / "public.spki").write_text("synthetic-public")
                (folder / "created.utc").write_text(datetime.now(timezone.utc).isoformat())
                with contextlib.ExitStack() as stack:
                    stack.enter_context(patch.object(operator, "session_path", return_value=folder))
                    replacements = {"token": "synthetic", "provenance": {"id": 42}, "download": b"ZIP",
                                    "envelope_from_zip": b"ENCRYPTED", "child": b"unclassified",
                                    "github": (204, b""), "cleanup": None}
                    for name, value in replacements.items():
                        side_effect = RuntimeError("PRIVATE") if name == phase else None
                        if name == "github" and phase != "github":
                            side_effect = [(204, b""), urllib.error.HTTPError("https://api.github.com",404,"fixed",{},None)]
                        stack.enter_context(patch.object(operator, name, side_effect=side_effect, return_value=value))
                    stack.enter_context(patch.object(operator.capture, "validate_envelope",
                        side_effect=RuntimeError("PRIVATE") if phase == "validate_envelope" else None))
                    with self.assertRaises(Exception):
                        operator.inspect("session", "123", "a" * 40)
                state = json.loads((folder / "receipt.json").read_text())
                self.assertEqual(state["run_id"], "123")
                self.assertEqual(state["source_sha"], "a" * 40)
                self.assertEqual(state["artifact_id"], None if phase in ("token", "provenance") else 42)
                self.assertTrue((folder / "private.pk8").exists())

    def test_uninspected_key_cleanup_refuses_uncertain_remote_state(self):
        folder = unittest.mock.MagicMock()
        receipt = folder.__truediv__.return_value
        receipt.exists.return_value = False
        with patch.object(operator, "session_path", return_value=folder), self.assertRaises(Exception):
            operator.retire_remote("session")

    def test_receipt_replace_failure_keeps_previous_coordinates(self):
        root = Path(operator.__file__).resolve().parents[2] / ".temp"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as folder_name:
            folder = Path(folder_name)
            original = {"artifact_id": None, "run_id": "123", "source_sha": "a" * 40}
            operator.record_receipt(folder, original, first=True)
            with patch.object(operator.os, "replace", side_effect=OSError("synthetic")), self.assertRaises(Exception):
                operator.record_receipt(folder, {**original, "artifact_id": 42})
            self.assertEqual(json.loads((folder / "receipt.json").read_text()), original)
            self.assertEqual(json.loads((folder / "receipt.next.json").read_text())["artifact_id"], 42)


if __name__ == "__main__":
    unittest.main()
