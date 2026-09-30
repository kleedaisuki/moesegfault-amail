"""Synthetic privacy and scope contracts for one historical settings audit GET."""
import contextlib
import io
import json
import os
import re
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import staging_settings_patch_audit as subject

ACCOUNT = "a" * 32
TARGET = f"/accounts/{ACCOUNT}/workers/scripts/amail-mail-staging/script-settings"


def record(uri=TARGET, method="PATCH", status=200, outcome="success"):
    """Use private synthetic fields to detect accidental row or exception output."""
    return {"id": "PRIVATE_RECORD_ID", "account": {"id": ACCOUNT, "name": "PRIVATE"},
        "action": {"time": "2026-09-30T16:16:03Z", "result": outcome},
        "raw": {"method": method, "uri": uri, "status_code": status},
        "actor": {"email": "PRIVATE", "ip_address": "PRIVATE", "token_id": "PRIVATE"},
        "resource": {"request": {"PRIVATE": "PRIVATE"}, "response": {"PRIVATE": "PRIVATE"}}}


def envelope(rows=None):
    """Build one explicitly complete synthetic page without provider fixtures."""
    rows = [record()] if rows is None else rows
    return {"success": True, "errors": [], "result": rows,
            "result_info": {"count": str(len(rows)), "cursor": ""}}


class AuditClassifierTests(unittest.TestCase):
    """Unknown or incomplete evidence cannot authorize historical or live conclusions."""

    def test_unique_success_and_failure_are_provider_outcomes_only(self):
        """Classify known outcome bins, not helper attribution or capture-off state."""
        status, result = subject.classify(envelope(), ACCOUNT)
        self.assertEqual(status, "CLASSIFIED")
        self.assertEqual(result, {"read": "ok", "complete": "yes", "matches": "one",
            "http": "expected_success", "action": "success", "historical": "server_reported_success"})
        for code, http in ((201, "other_success"), (403, "client_error"), (503, "server_error"), (302, "other")):
            outcome = "success" if code == 201 else "failure"
            status, result = subject.classify(envelope([record(status=code, outcome=outcome)]), ACCOUNT)
            self.assertEqual(status, "CLASSIFIED")
            self.assertEqual(result["http"], http)
        status, result = subject.classify(envelope([record(status=403)]), ACCOUNT)
        self.assertEqual(status, "UNVERIFIED")
        self.assertEqual(result["historical"], "unresolved")

    def test_zero_multiple_and_similar_uri_do_not_prove_no_attempt(self):
        """No substring, alternate realm, changed account or query suffix match exists."""
        for uri in (TARGET + "?PRIVATE", TARGET + "/PRIVATE", TARGET.replace("staging", "production"),
                    "/client/v4" + TARGET, "https://api.cloudflare.com/client/v4" + TARGET):
            status, result = subject.classify(envelope([record(uri=uri)]), ACCOUNT)
            self.assertEqual(status, "UNVERIFIED")
            self.assertEqual(result["matches"], "zero")
            self.assertEqual(result["historical"], "unresolved")
        for rows in ([], [record(method="GET")], [record(), record()],
                     [record(), record(status=503, outcome="failure")]):
            status, result = subject.classify(envelope(rows), ACCOUNT)
            self.assertEqual(status, "UNVERIFIED")
            self.assertEqual(result["historical"], "unresolved")
        status, result = subject.classify(envelope([record(), record(status=503, outcome="failure")]), ACCOUNT)
        self.assertEqual(result["http"], "mixed")
        self.assertEqual(result["action"], "mixed")

    def test_pagination_count_scope_and_unknown_shape_fail_closed(self):
        """Never widen, infer exhaustion or classify a malformed partial page."""
        for change in ({"cursor": "PRIVATE"}, {"cursor": None}, {"count": "2"},
                       {"count": 1}, {"count": "01"}, {"next_cursor": "PRIVATE"}):
            data = envelope()
            data["result_info"].update(change)
            status, result = subject.classify(data, ACCOUNT)
            self.assertEqual(status, "UNVERIFIED")
            self.assertEqual(result["complete"], "unverified")
        for removed in ("cursor", "count"):
            data = envelope()
            del data["result_info"][removed]
            self.assertEqual(subject.classify(data, ACCOUNT)[0], "UNVERIFIED")
        for data in ({}, {**envelope(), "success": False}, {**envelope(), "messages": []},
                     {**envelope(), "errors": [{"message": "PRIVATE"}]},
                     envelope([record()] * 101)):
            self.assertEqual(subject.classify(data, ACCOUNT)[0], "UNVERIFIED")
        for change in ({"raw": None}, {"raw": {"method": []}},
                       {"action": {"time": "2026-09-30T16:17:00Z"}},
                       {"account": {"id": "b" * 32}}, {"PRIVATE": "PRIVATE"}):
            data = record()
            data.update(change)
            self.assertEqual(subject.classify(envelope([data]), ACCOUNT)[0], "UNVERIFIED")

    def test_unknown_matching_fields_and_invalid_status_never_escape(self):
        """Unknown statuses/action outcomes are not cast to a known Boolean or class."""
        for value in (None, True, "200", 200.5, float("nan"), float("inf"), 10 ** 1000, 99, 600):
            self.assertIsNone(subject.http_category(value))
            self.assertEqual(subject.classify(envelope([record(status=value)]), ACCOUNT)[0], "UNVERIFIED")
        for outcome in (None, "PRIVATE", [], True):
            self.assertEqual(subject.classify(envelope([record(outcome=outcome)]), ACCOUNT)[0], "UNVERIFIED")
        for timestamp in (subject.SINCE, subject.BEFORE, "PRIVATE", None, "2026-09-30T16:16:60Z"):
            self.assertFalse(subject.in_window(timestamp))

    def test_exact_one_get_scope_size_and_redirect_rejection(self):
        """The reader has no URL/time/cursor override and never follows redirects."""
        response = MagicMock()
        response.status = 200
        response.read.return_value = json.dumps(envelope()).encode()
        response.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = response
        with patch.object(subject, "build_opener", return_value=opener):
            self.assertEqual(subject.read_audit(ACCOUNT, "PRIVATE_TOKEN"), envelope())
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        url = urlsplit(request.full_url)
        self.assertEqual(url.scheme, "https")
        self.assertEqual(url.netloc, "api.cloudflare.com")
        self.assertEqual(url.path, f"/client/v4/accounts/{ACCOUNT}/logs/audit")
        self.assertEqual(parse_qs(url.query), {"since": [subject.SINCE], "before": [subject.BEFORE],
            "limit": ["100"], "direction": ["asc"]})
        self.assertEqual(opener.open.call_args.kwargs, {"timeout": 15})
        response.read.assert_called_once_with(subject.BYTE_LIMIT + 1)
        self.assertIsNone(subject.NoRedirect().redirect_request(None, None, 302, "", {}, "https://PRIVATE"))
        for raw, category in ((b"PRIVATE", "shape"), (b"[]", "shape"),
                              (b"x" * (subject.BYTE_LIMIT + 1), "oversized")):
            response.read.return_value = raw
            with patch.object(subject, "build_opener", return_value=opener), self.assertRaises(subject.AuditReadError) as caught:
                subject.read_audit(ACCOUNT, "PRIVATE_TOKEN")
            self.assertEqual(caught.exception.category, category)
        for error, category in ((HTTPError("PRIVATE", 403, "PRIVATE", {}, None), "denied"),
                                (HTTPError("PRIVATE", 500, "PRIVATE", {}, None), "http_other"),
                                (URLError("PRIVATE"), "transport"), (TimeoutError("PRIVATE"), "transport")):
            opener.open.side_effect = error
            with patch.object(subject, "build_opener", return_value=opener), self.assertRaises(subject.AuditReadError) as caught:
                subject.read_audit(ACCOUNT, "PRIVATE_TOKEN")
            self.assertEqual(caught.exception.category, category)

    def test_main_never_outputs_private_fields_and_enforces_first_attempt(self):
        """Even provider success outputs no URI/status number, actor, payload or attestation."""
        env = {"CLOUDFLARE_ACCOUNT_ID": ACCOUNT, "CLOUDFLARE_API_TOKEN": "PRIVATE_TOKEN",
            "AMAIL_SETTINGS_AUDIT_CONFIRM": subject.CONFIRM, "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/codex/amail-v0.1.0",
            "GITHUB_SHA": "b" * 40}
        out = io.StringIO()
        with patch.dict(os.environ, env, clear=True), patch.object(subject, "read_audit", return_value=envelope()) as reader, \
             contextlib.redirect_stdout(out):
            self.assertEqual(subject.main(), 0)
        reader.assert_called_once()
        self.assertEqual(len(out.getvalue().splitlines()), len(subject.FIELDS) + 1)
        for secret in ("PRIVATE", ACCOUNT, TARGET, "200", "attestation", "Current Version ID"):
            self.assertNotIn(secret, out.getvalue())
        for key, bad in (("GITHUB_RUN_ATTEMPT", "2"), ("GITHUB_REF", "refs/heads/main"),
                         ("GITHUB_EVENT_NAME", "push"), ("AMAIL_SETTINGS_AUDIT_CONFIRM", "PRIVATE")):
            with patch.dict(os.environ, {**env, key: bad}, clear=True), patch.object(subject, "read_audit") as reader, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(subject.main(), 1)
                reader.assert_not_called()
        for failure in (subject.AuditReadError("denied"), ValueError("PRIVATE")):
            out = io.StringIO()
            with patch.dict(os.environ, env, clear=True), patch.object(subject, "read_audit", side_effect=failure), \
                 contextlib.redirect_stdout(out):
                self.assertEqual(subject.main(), 1)
            self.assertNotIn("PRIVATE", out.getvalue())
            self.assertIn("staging_settings_patch_audit=UNVERIFIED", out.getvalue())

    def test_workflow_uses_existing_inputs_and_tests_before_secrets(self):
        """Avoid growing the dispatch schema or exposing credentials during tests."""
        source = (Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = re.split(r"(?m)^  [a-z0-9-]+:\n",
                       source.split("  staging-settings-patch-audit:\n", 1)[1], maxsplit=1)[0]
        self.assertIn("inputs.target == 'staging-settings-patch-audit'", job)
        self.assertIn("environment: staging", job)
        self.assertLess(job.index("test_staging_settings_patch_audit.py"), job.index("secrets.CLOUDFLARE_API_TOKEN"))
        self.assertNotIn("workflow_dispatch:", job)
        self.assertNotIn("wrangler", job)


if __name__ == "__main__":
    unittest.main()
