"""Offline provenance/ZIP/confidentiality contracts; no real keys or provider access."""
import contextlib
import io
import json
import os
import stat
import unittest
from unittest.mock import patch
import zipfile

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


if __name__ == "__main__":
    unittest.main()
