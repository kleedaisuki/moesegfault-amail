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
import hashlib
import base64

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


class Response(io.BytesIO):
    """Bounded in-memory API response; never contacts GitHub or a provider."""
    def __init__(self, status, value=b""):
        super().__init__(value if isinstance(value, bytes) else json.dumps(value).encode())
        self.status = status


def encrypted_fixture(metadata, public):
    """Shape-valid synthetic ciphertext for exercising real envelope/provenance checks."""
    header = {"algorithm": "RSA-3072-OAEP-SHA256+A256GCM",
              "fingerprint": hashlib.sha256(base64.b64decode(public)).hexdigest(),
              "nonce": base64.b64encode(bytes(12)).decode(),
              "wrapped_key": base64.b64encode(bytes(384)).decode(), "provenance": metadata}
    return json.dumps({"version": 1, "header": base64.b64encode(json.dumps(header).encode()).decode(),
                       "ciphertext": base64.b64encode(bytes(262144)).decode(),
                       "tag": base64.b64encode(bytes(16)).decode()}).encode()


class OperatorTests(unittest.TestCase):
    """Untrusted input never becomes paths, executable prose or stdout."""

    def test_offline_fixed_enum_boundary(self):
        """Every admitted result is fixed ASCII, never arbitrary provider data."""
        for http in operator.HTTP_BINS:
            for category in operator.OFFLINE_CATEGORIES:
                raw = f"http={http} errors={category}".encode("ascii")
                self.assertEqual(operator.offline_result(raw), raw.decode("ascii"))
        valid = b"http=ok errors=unclassified"
        for raw in (valid + b"\n", b" " + valid, valid + b" PRIVATE", valid + b"\x00",
                    b"errors=unclassified http=ok", b"http=200 errors=unclassified",
                    b"http=ok errors=PRIVATE", b"http=ok errors=\xff", b"x" * 129):
            with self.assertRaises(Exception):
                operator.offline_result(raw)

    def test_offline_child_rejects_extra_stdout_stderr_and_failures(self):
        """Hostile native output and exceptions cannot escape the fixed parent failure."""
        import subprocess
        valid = b"http=ok errors=unclassified"
        outcomes = [subprocess.CompletedProcess([], code, stdout, stderr)
                    for code, stdout, stderr in ((0, valid + b"\nPRIVATE", b""),
                        (0, valid, b"PRIVATE"), (1, valid, b""),
                        (0, b"\xff", b""), (0, b"x" * 129, b""))]
        for outcome in outcomes:
            with patch.object(operator.subprocess, "run", return_value=outcome), self.assertRaises(Exception):
                operator.child("classify-offline", "synthetic", b"CIPHERTEXT")
        with patch.object(operator.subprocess, "run", return_value=subprocess.CompletedProcess([],0,valid,b"")):
            self.assertEqual(operator.child("classify-offline", "synthetic", b"CIPHERTEXT"), valid)
        for failure in (RuntimeError("PRIVATE"), UnicodeError("PRIVATE"), OSError("PRIVATE")):
            with patch.object(operator, "classify_local", side_effect=failure), \
                    patch.object(operator.sys, "argv", ["operator", "classify", "synthetic"]), \
                    contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(operator.main(), 1)
            self.assertEqual(output.getvalue(), "private_provider_operator=UNVERIFIED cleanup=UNVERIFIED\n")
            self.assertEqual(errors.getvalue(), "")

    def test_native_template_freeze_matches_reviewed_public_table(self):
        """Catch changes to frozen literal spelling/order without importing a network entry point."""
        import ast
        import re
        path = Path(operator.__file__).parent
        tree = ast.parse((path / "staging_worker_r2_history_error.py").read_text())
        expected = next(ast.literal_eval(node.value) for node in tree.body
                        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                        and target.id == "TEMPLATES" for target in node.targets))
        native = (path / "private_provider_crypto.ps1").read_text()
        table = native.split("OfflineTemplates = {", 1)[1].split("    };", 1)[0]
        actual = tuple(re.findall(r'\("([a-z_]+)", @"([^"\n]*)"\)', table))
        self.assertEqual(actual, expected)

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
        for phase in ("token", "provenance", "download", "envelope_from_zip", "validate_envelope", "child", "github"):
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

    def test_local_classifier_never_contacts_provider_or_github(self):
        with patch.object(operator, "classify_local", return_value="http=ok errors=unclassified"), \
                patch.object(operator, "github") as network, \
                patch.object(operator.sys, "argv", ["operator", "classify", "session"]), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(operator.main(), 0)
        network.assert_not_called()
        self.assertEqual(output.getvalue(), "private_provider_operator=LOCAL_RETAINED http=ok errors=unclassified delivery=UNVERIFIED\n")

    def test_cleanup_remote_failure_preserves_local_key(self):
        with patch.object(operator, "retire_remote", side_effect=RuntimeError("synthetic")), \
                patch.object(operator, "cleanup") as local, \
                patch.object(operator.sys, "argv", ["operator", "cleanup", "session"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(operator.main(), 1)
        local.assert_not_called()

    def test_late_upload_not_inferred_absent_before_terminal_run(self):
        folder = unittest.mock.MagicMock()
        receipt = folder.__truediv__.return_value
        receipt.exists.return_value = True
        receipt.stat.return_value.st_size = 100
        receipt.read_bytes.return_value = json.dumps({"artifact_id": None, "run_id": "123", "source_sha": "a" * 40}).encode()
        original = {"id": 123, "head_sha": "a" * 40, "head_branch": operator.history.BRANCH,
                    "run_attempt": 1, "event": "workflow_dispatch"}
        for status in ("queued", "in_progress", "waiting", "pending", "requested"):
            with self.subTest(status=status), patch.object(operator, "session_path", return_value=folder), \
                    patch.object(operator, "token", return_value="synthetic"), \
                    patch.object(operator, "github_json", return_value={**original, "status": status}) as api, self.assertRaises(Exception):
                operator.retire_remote("session")
            self.assertEqual(api.call_count, 1)
        # Completed cancellation/failure can be retired after the authenticated,
        # complete artifact listing proves exact absence; no future upload remains.
        for conclusion in ("failure", "cancelled"):
            with self.subTest(conclusion=conclusion), patch.object(operator, "session_path", return_value=folder), \
                    patch.object(operator, "token", return_value="synthetic"), \
                    patch.object(operator, "github_json", side_effect=[{**original, "status": "completed", "conclusion": conclusion},
                                                                           {"total_count": 0, "artifacts": []}]) as api:
                operator.retire_remote("session")
            self.assertEqual(api.call_count, 2)

    def test_authenticated_positive_provenance_and_download_digest(self):
        sha, run_id = "a" * 40, "123"
        data = archive(["capture.enc.json"])
        artifact = {"id": 42, "name": "private-provider-error-123-1", "size_in_bytes": len(data),
                    "expired": False, "created_at": datetime.now(timezone.utc).isoformat(),
                    "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                    "workflow_run": {"id": 123, "head_sha": sha, "head_branch": operator.history.BRANCH}}
        run = {"id": 123, "run_attempt": 1, "head_sha": sha, "head_branch": operator.history.BRANCH,
               "event": "workflow_dispatch", "status": "completed", "conclusion": "success", "path": operator.capture.WORKFLOW}
        job = {"name": operator.JOB, "head_sha": sha, "run_id": 123, "status": "completed", "conclusion": "success"}
        redirect = urllib.error.HTTPError("https://api.github.com", 302, "fixed",
                                          {"Location": "https://synthetic.blob.core.windows.net/archive?synthetic=1"}, None)
        outcomes = [Response(200, run), Response(200, {"total_count": 1, "jobs": [job]}),
                    Response(200, {"total_count": 1, "artifacts": [artifact]}), redirect, Response(200, data)]
        with patch.object(operator.history.OPENER, "open", side_effect=outcomes) as transport, \
                contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()) as stderr:
            proven = operator.provenance(run_id, sha, "SYNTHETIC-TOKEN")
            self.assertEqual(operator.download(proven, "SYNTHETIC-TOKEN"), data)
        self.assertEqual(transport.call_count, 5)
        self.assertTrue(all(call.args[0].get_header("Authorization") == "Bearer SYNTHETIC-TOKEN" for call in transport.call_args_list[:4]))
        self.assertIsNone(transport.call_args_list[4].args[0].get_header("Authorization"))
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), "")

    def test_download_tamper_and_host_fail_closed(self):
        for location, digest, expected_calls in (
                ("https://synthetic.blob.core.windows.net/archive", "0" * 64, 2),
                ("https://evil.invalid/archive", "0" * 64, 1)):
            redirect = urllib.error.HTTPError("https://api.github.com",302,"fixed",{"Location": location},None)
            with self.subTest(calls=expected_calls), patch.object(operator.history.OPENER, "open",
                    side_effect=[redirect, Response(200,b"CIPHERTEXT")]) as transport, self.assertRaises(Exception):
                operator.download({"id":42,"digest":"sha256:"+digest},"SYNTHETIC-TOKEN")
            self.assertEqual(transport.call_count,expected_calls)

    def test_real_cleanup_delete_absence_and_failure_key_retention(self):
        root = Path(operator.__file__).resolve().parents[2] / ".temp"
        root.mkdir(exist_ok=True)
        for delete_status in (204, 403):
            with self.subTest(delete_status=delete_status), tempfile.TemporaryDirectory(dir=root) as name:
                folder = Path(name)
                (folder / "private.pk8").write_bytes(b"SYNTHETIC-NOT-A-KEY")
                operator.record_receipt(folder, {"artifact_id":42,"run_id":"123","source_sha":"a"*40}, first=True)
                run = {"id":123,"head_sha":"a"*40,"head_branch":operator.history.BRANCH,
                       "run_attempt":1,"event":"workflow_dispatch","status":"completed","conclusion":"cancelled"}
                artifact = {"id":42,"name":"private-provider-error-123-1",
                            "workflow_run":{"id":123,"head_sha":"a"*40}}
                deletion = Response(204) if delete_status == 204 else urllib.error.HTTPError("https://api.github.com",403,"fixed",{},None)
                outcomes = [Response(200,run),Response(200,{"total_count":1,"artifacts":[artifact]}),deletion,
                            urllib.error.HTTPError("https://api.github.com",404,"fixed",{},None)]
                with patch.object(operator,"session_path",return_value=folder), patch.object(operator,"token",return_value="SYNTHETIC"), \
                        patch.object(operator.history.OPENER,"open",side_effect=outcomes) as transport, \
                        patch.object(operator.sys,"argv",["operator","cleanup","session"]), contextlib.redirect_stdout(io.StringIO()) as output:
                    result = operator.main()
                if delete_status == 204:
                    self.assertEqual(result,0)
                    self.assertFalse(folder.exists())
                    self.assertEqual(output.getvalue(),"private_provider_operator=CLEANED\n")
                    self.assertEqual(transport.call_count,4)
                else:
                    self.assertEqual(result,1)
                    self.assertTrue((folder / "private.pk8").exists())
                    self.assertEqual(output.getvalue(),"private_provider_operator=UNVERIFIED cleanup=UNVERIFIED\n")
                    self.assertEqual(transport.call_count,3)
                self.assertEqual(transport.call_args_list[2].args[0].get_method(),"DELETE")
                self.assertEqual(transport.call_args_list[2].args[0].full_url,
                                 f"https://api.github.com/repos/{operator.history.REPOSITORY}/actions/artifacts/42")

    def test_real_local_classification_checks_envelope_without_network(self):
        root = Path(operator.__file__).resolve().parents[2] / ".temp"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as name:
            folder = Path(name)
            public = base64.b64encode(b"SYNTHETIC-PUBLIC").decode()
            (folder / "private.pk8").write_bytes(b"SYNTHETIC-NOT-A-KEY")
            (folder / "created.utc").write_text(datetime.now(timezone.utc).isoformat())
            (folder / "public.spki").write_text(public)
            operator.record_receipt(folder,{"artifact_id":42,"run_id":"123","source_sha":"a"*40},first=True)
            metadata = {"source_sha":"a"*40,"capture_run":"123","capture_attempt":"1","original_run":operator.history.RUN,
                        "original_attempt":operator.history.ATTEMPT,"workflow":operator.capture.WORKFLOW,
                        "repository":operator.history.REPOSITORY,"query_sha256":hashlib.sha256(operator.capture.QUERY.encode()).hexdigest()}
            encrypted = encrypted_fixture(metadata,public)
            (folder / "capture.enc.json").write_bytes(encrypted)
            with patch.object(operator,"session_path",return_value=folder), patch.object(operator,"child",return_value=b"http=ok errors=unclassified") as native, \
                    patch.object(operator.history.OPENER,"open") as network, \
                    patch.object(operator.sys,"argv",["operator","classify","session"]),contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(operator.main(),0)
            network.assert_not_called()
            native.assert_called_once_with("classify-offline","session",encrypted)
            self.assertTrue((folder / "private.pk8").exists())
            self.assertEqual(output.getvalue(),"private_provider_operator=LOCAL_RETAINED http=ok errors=unclassified delivery=UNVERIFIED\n")
            # Metadata substitution fails before invoking native decryption.
            bad = encrypted_fixture({**metadata,"source_sha":"b"*40},public)
            (folder / "capture.enc.json").write_bytes(bad)
            with patch.object(operator,"session_path",return_value=folder),patch.object(operator,"child") as native,self.assertRaises(Exception):
                operator.classify_local("session")
            native.assert_not_called()


if __name__ == "__main__":
    unittest.main()
