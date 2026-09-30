"""Synthetic confidentiality, bounds, provenance and exact-path contracts."""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

import private_provider_capture as capture


class ProjectionTests(unittest.TestCase):
    """Provider prose is confidential data, not an output or command."""

    def test_unknown_fields_preserved_and_data_dropped(self):
        payload = {"data": {"private": "MAIL"}, "errors": [{"message": "TOKEN\nmalicious", "unknown": {"x": 1}}], "headers": "COOKIE"}
        result = json.loads(capture.project(200, json.dumps(payload).encode()))
        self.assertEqual(result, {"http_status": 200, "errors": payload["errors"]})

    def test_invalid_projection(self):
        for raw in (b'{}', b'{"errors":[]}', b'{"errors":1,"errors":2}', b'NaN', b'<html>', b'x' * 131073):
            with self.subTest(raw_length=len(raw)), self.assertRaises(Exception):
                capture.project(200, raw)

    def test_expanded_projection_bound(self):
        with self.assertRaises(Exception):
            capture.project(200, json.dumps({"errors": "\u00e9" * 40000}, ensure_ascii=False).encode())

    def test_child_output_and_credentials_suppressed(self):
        result = subprocess.CompletedProcess([], 1, b'TOKEN', b'MAIL')
        with patch.dict(os.environ, {"CF_OBSERVABILITY_TOKEN": "PRIVATE", "GITHUB_TOKEN": "PRIVATE"}), \
                patch.object(capture.subprocess, "run", return_value=result) as child:
            with self.assertRaises(Exception):
                capture.encrypt(b'PRIVATE', {}, 'public')
            args, kwargs = child.call_args
            self.assertEqual(kwargs["input"], b'PRIVATE')
            self.assertNotIn("CF_OBSERVABILITY_TOKEN", kwargs["env"])
            self.assertNotIn("GITHUB_TOKEN", kwargs["env"])
            self.assertNotIn("PRIVATE", str(args))

    def test_main_never_outputs_exception(self):
        output = io.StringIO()
        with patch.object(capture, "run", side_effect=RuntimeError("TOKEN\nMAIL")), \
                patch.object(capture.sys, "argv", ["capture"]), contextlib.redirect_stdout(output):
            self.assertEqual(capture.main(), 1)
        self.assertEqual(output.getvalue(), "private_provider_capture=UNVERIFIED\n")

    def test_unreviewed_source_no_provider_read(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(capture.history.OPENER, "open") as provider:
            with self.assertRaises(Exception):
                capture.run()
            provider.assert_not_called()

    def test_one_post_original_window_exact_projection(self):
        sha = "a" * 40
        env = {"PRIVATE_CAPTURE_CONFIRM": capture.CONFIRM, "GITHUB_RUN_ATTEMPT": "1",
               "GITHUB_REPOSITORY": capture.history.REPOSITORY,
               "GITHUB_REF": "refs/heads/" + capture.history.BRANCH,
               "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": sha,
               "PRIVATE_CAPTURE_REVIEWED_SHA": sha, "PRIVATE_CAPTURE_PUBLIC_KEY": "public",
               "GITHUB_RUN_ID": "123", "CF_ZONE_ID": "b" * 32,
               "CF_OBSERVABILITY_TOKEN": "SYNTHETIC_TOKEN", "GITHUB_TOKEN": "synthetic"}
        class Response(io.BytesIO):
            """Synthetic HTTP response never contacts Cloudflare."""
            status = 200
        output = io.BytesIO()
        class File:
            """Anonymous ciphertext-only destination fixture."""
            def exists(self):
                return False
            def open(self, mode):
                self.mode = mode
                return contextlib.nullcontext(output)
        file = File()
        time = datetime(2026, 9, 30, tzinfo=timezone.utc)
        response = Response(b'{"data":{"secret":"MAIL"},"errors":[{"message":"TOKEN"}]}')
        with patch.dict(os.environ, env, clear=True), \
                patch.object(capture, "destination", return_value=file), \
                patch.object(capture, "encrypt", return_value=b'CIPHERTEXT') as crypto, \
                patch.object(capture.history, "historical_window", return_value=(time, time)), \
                patch.object(capture.history.OPENER, "open", return_value=response) as provider:
            capture.run()
        provider.assert_called_once()
        request = provider.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data)["query"], capture.QUERY)
        self.assertEqual(crypto.call_count, 2)
        self.assertEqual(json.loads(crypto.call_args.args[0]), {"http_status": 200, "errors": [{"message": "TOKEN"}]})
        self.assertEqual(crypto.call_args.args[1]["workflow"], ".github/workflows/ci.yml")
        self.assertEqual(file.mode, "xb")
        self.assertEqual(output.getvalue(), b'CIPHERTEXT')

    def test_ciphertext_component_shape_rejection(self):
        # Malformed ciphertext never reaches disk even if a child claims success.
        for raw in (b'{}', b'{"version":1,"version":1}', b'TOKEN', b'x' * 400001):
            with self.subTest(length=len(raw)), self.assertRaises(Exception):
                capture.validate_envelope(raw, {}, "public")

    def test_cleanup_exact_file_only(self):
        class ExactFile:
            """In-memory deletion fixture, no local experiment directory."""
            def __init__(self):
                self.removed = False
            def unlink(self, *, missing_ok):
                self.removed = missing_ok
            def exists(self):
                return not self.removed
        file = ExactFile()
        with patch.object(capture, "destination", return_value=file), patch.object(capture.sys, "argv", ["capture", "cleanup"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(capture.main(), 0)
        self.assertTrue(file.removed)


class HostedCryptoTests(unittest.TestCase):
    """Native .NET interoperation on hosted Linux and Windows only."""

    @unittest.skipUnless(os.environ.get("PRIVATE_CAPTURE_SYNTHETIC_HOSTED") == "1", "hosted crypto lane only")
    def test_native_crypto(self):
        result = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File", str(Path(capture.__file__).with_name("private_provider_crypto.ps1")), "-Mode", "synthetic"], capture_output=True, timeout=60, check=False)
        self.assertEqual(result.returncode, 0, "fixed native crypto failure")
        self.assertEqual(result.stdout.strip(), b'private_capture_crypto=PASS')
        self.assertEqual(result.stderr, b'')


if __name__ == "__main__":
    unittest.main()
