"""Synthetic contracts for the hosted Worker-created private-object proof."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime
import importlib.util
from io import StringIO
import os
from pathlib import Path
import re
import sys
import types
import unittest
from unittest.mock import patch
import urllib.request

import staging_r2_object_capability as R2


SPEC = importlib.util.spec_from_file_location(
    "staging_worker_created_r2", Path(__file__).with_name("staging_worker_created_r2.py")
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
try:
    SPEC.loader.exec_module(MODULE)
except Exception:
    sys.modules.pop(SPEC.name, None)
    raise


class WorkerCreatedR2Tests(unittest.TestCase):
    """Require route-first cleanup and byte-owned exact object operations."""

    @staticmethod
    def window() -> tuple[datetime, datetime]:
        """Return a bounded synthetic send interval."""

        now = datetime.now(timezone.utc)
        return now - timedelta(minutes=1), now + timedelta(minutes=1)

    @staticmethod
    def mime(value: str = "123", attempt: str = "1") -> bytes:
        """Build one non-OTP MIME with a reproducible test marker."""

        nonce = MODULE.marker(value, attempt)
        message = EmailMessage()
        message["From"] = MODULE.SENDER
        message["To"] = MODULE.FIRST
        message["Subject"] = MODULE.TEMPLATE + nonce
        message["Date"] = format_datetime(datetime.now(timezone.utc))
        message.set_content(MODULE.TEMPLATE + nonce)
        return message.as_bytes()

    def test_strict_mime_accepts_only_exact_run_and_recipient(self) -> None:
        """A foreign or changed object is never an automatic DELETE target."""

        raw = self.mime()
        self.assertTrue(MODULE.synthetic_mail(raw, "123", "1", self.window()))
        self.assertFalse(MODULE.synthetic_mail(raw, "124", "1", self.window()))
        message = EmailMessage()
        message["From"] = MODULE.SENDER
        message["To"] = MODULE.ADDRESS
        message["Subject"] = MODULE.TEMPLATE + MODULE.marker("123", "1")
        message["Date"] = format_datetime(datetime.now(timezone.utc))
        message.set_content(MODULE.TEMPLATE + MODULE.marker("123", "1"))
        self.assertFalse(MODULE.synthetic_mail(message.as_bytes(), "123", "1", self.window()))
        self.assertFalse(MODULE.synthetic_mail(raw, "123", "1", (
            datetime.now(timezone.utc) - timedelta(days=2),
            datetime.now(timezone.utc) - timedelta(days=1))))
        self.assertFalse(MODULE.synthetic_mail(b"private unknown MIME", "123", "1", self.window()))
        duplicate = raw.replace(b"To: " + MODULE.FIRST.encode() + b"\n",
                                b"To: " + MODULE.FIRST.encode() + b"\n"
                                b"To: " + MODULE.FIRST.encode() + b"\n", 1)
        self.assertFalse(MODULE.synthetic_mail(duplicate, "123", "1", self.window()))
        attachment = EmailMessage()
        attachment["From"] = MODULE.SENDER
        attachment["To"] = MODULE.FIRST
        attachment["Subject"] = MODULE.TEMPLATE + MODULE.marker("123", "1")
        attachment["Date"] = format_datetime(datetime.now(timezone.utc))
        attachment.set_content(MODULE.TEMPLATE + MODULE.marker("123", "1"))
        attachment.add_attachment(b"not accepted", maintype="application",
                                  subtype="octet-stream", filename="extra.bin")
        self.assertFalse(MODULE.synthetic_mail(attachment.as_bytes(), "123", "1",
                                                self.window()))

    def test_probe_installs_route_cleanup_before_ambiguous_create(self) -> None:
        """A route API error still invokes exact closure before object cleanup."""

        actions: list[str] = []

        def fake_route(action: str) -> str:
            actions.append(action)
            if action == "apply":
                raise MODULE.ProbeFailure("route_create_unverified")
            return "removed" if action == "remove" else "absent"

        env = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
               "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
               "CLOUDFLARE_API_TOKEN": "private-token",
               "AMAIL_SENDING_GRANT_ATTEST": "ATTEST_ONE_SYNTHETIC_APEX_SEND"}
        contacts = {MODULE.FIRST: ("principal-a", "subject-a", "verified", "a_username")}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE, "audit"), \
                patch.object(MODULE, "identity_contacts", return_value=contacts), \
                patch.object(MODULE, "sender_ready"), \
                patch.object(MODULE, "one_key", return_value=None), \
                patch.object(MODULE, "route", side_effect=fake_route), \
                patch.object(MODULE, "reconcile", return_value=False) as reconcile:
            with self.assertRaises(MODULE.ProbeFailure) as caught:
                MODULE.probe()
        self.assertEqual(str(caught.exception), "route_create_unverified")
        self.assertEqual(actions, ["apply", "remove", "audit"])
        reconcile.assert_not_called()

    def test_probe_closes_route_before_get_delete(self) -> None:
        """The synthetic route may not remain live during object deletion."""

        actions: list[str] = []

        def fake_route(action: str) -> str:
            actions.append(action)
            return {"apply": "created", "audit": "enabled" if "remove" not in actions else "absent",
                    "remove": "removed"}[action]

        env = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
               "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
               "CLOUDFLARE_API_TOKEN": "private-token",
               "AMAIL_SENDING_GRANT_ATTEST": "ATTEST_ONE_SYNTHETIC_APEX_SEND"}
        contacts = {MODULE.FIRST: ("principal-a", "subject-a", "verified", "a_username")}

        def fake_delete(*_args):
            self.assertEqual(actions[-2:], ["remove", "audit"])

        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE, "audit"), \
                patch.object(MODULE, "identity_contacts", return_value=contacts), \
                patch.object(MODULE, "sender_ready"), \
                patch.object(MODULE, "one_key", side_effect=[None, "verification/12345678-1234-4123-8123-123456789abc.eml"]), \
                patch.object(MODULE, "route", side_effect=fake_route), \
                patch.object(MODULE, "send_once", return_value=True), \
                patch.object(MODULE, "delete_owned", side_effect=fake_delete) as deleted, \
                patch.object(MODULE, "reconcile", return_value=False), \
                patch.object(MODULE.time, "sleep"), redirect_stdout(StringIO()) as output:
            MODULE.probe()
        deleted.assert_called_once()
        self.assertIn("staging_worker_created_r2_get_delete_verified", output.getvalue())

    def test_route_settle_or_close_failure_suppresses_send_or_delete(self) -> None:
        """A stale route or failed exact closure cannot become a capability pass."""

        env = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
               "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
               "CLOUDFLARE_API_TOKEN": "private-token",
               "AMAIL_SENDING_GRANT_ATTEST": "ATTEST_ONE_SYNTHETIC_APEX_SEND"}
        contacts = {MODULE.FIRST: ("principal-a", "subject-a", "verified", "a_username")}
        route_states = iter(["created", "enabled", "absent", "removed", "absent"])
        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE, "audit"), \
                patch.object(MODULE, "identity_contacts", return_value=contacts), \
                patch.object(MODULE, "sender_ready"), \
                patch.object(MODULE, "one_key", return_value=None), \
                patch.object(MODULE, "route", side_effect=lambda _action: next(route_states)), \
                patch.object(MODULE, "send_once") as send, \
                patch.object(MODULE, "delete_owned") as delete, \
                patch.object(MODULE.time, "sleep"):
            with self.assertRaises(MODULE.ProbeFailure) as caught:
                MODULE.probe()
        self.assertEqual(str(caught.exception), "route_settle_unverified")
        send.assert_not_called()
        delete.assert_not_called()

        def route_failed(action: str) -> str:
            if action == "remove":
                raise MODULE.ProbeFailure("exact_route_control_failed")
            return "created" if action == "apply" else "enabled"

        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE, "audit"), \
                patch.object(MODULE, "identity_contacts", return_value=contacts), \
                patch.object(MODULE, "sender_ready"), \
                patch.object(MODULE, "one_key", side_effect=[None, "verification/12345678-1234-4123-8123-123456789abc.eml"]), \
                patch.object(MODULE, "route", side_effect=route_failed), \
                patch.object(MODULE, "send_once", return_value=True), \
                patch.object(MODULE, "delete_owned") as delete, \
                patch.object(MODULE.time, "sleep"):
            with self.assertRaises(MODULE.ProbeFailure) as caught:
                MODULE.probe()
        self.assertEqual(str(caught.exception), "route_cleanup_unverified")
        delete.assert_not_called()

    def test_expired_open_route_budget_closes_before_send(self) -> None:
        """Slow creation/readback consumes the mutation budget, not cleanup."""

        env = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
               "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
               "CLOUDFLARE_API_TOKEN": "private-token",
               "AMAIL_SENDING_GRANT_ATTEST": "ATTEST_ONE_SYNTHETIC_APEX_SEND"}
        contacts = {MODULE.FIRST: ("principal-a", "subject-a", "verified", "a_username")}
        actions: list[str] = []

        def fake_route(action: str) -> str:
            actions.append(action)
            return {"apply": "created", "audit": "enabled" if "remove" not in actions else "absent",
                    "remove": "removed"}[action]

        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE, "audit"), \
                patch.object(MODULE, "identity_contacts", return_value=contacts), \
                patch.object(MODULE, "sender_ready"), \
                patch.object(MODULE, "one_key", return_value=None), \
                patch.object(MODULE, "route", side_effect=fake_route), \
                patch.object(MODULE, "send_once") as send, \
                patch.object(MODULE.time, "monotonic", side_effect=[0, 360]), \
                patch.object(MODULE.time, "sleep"):
            with self.assertRaises(MODULE.ProbeFailure) as caught:
                MODULE.probe()
        self.assertEqual(str(caught.exception), "route_window_expired")
        self.assertEqual(actions[-2:], ["remove", "audit"])
        send.assert_not_called()

    def test_recovery_closes_route_before_metadata_and_never_checks_b(self) -> None:
        """Recovery must work even if B credentials or D1 checks are unavailable."""

        actions: list[str] = []

        def close() -> None:
            actions.append("close")

        def metadata(*_args):
            actions.append("metadata")
            return self.window()

        def cleanup(*_args, **_kwargs):
            actions.append("cleanup")
            return True

        env = {"AMAIL_WORKER_R2_PRIOR_RUN_ID": "123",
               "AMAIL_WORKER_R2_PRIOR_RUN_ATTEMPT": "1"}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE, "close_route", side_effect=close), \
                patch.object(MODULE, "prior_window", side_effect=metadata), \
                patch.object(MODULE, "reconcile", side_effect=cleanup), \
                patch.object(MODULE, "one_key", return_value=None), \
                patch.object(MODULE, "route", return_value="absent"), \
                patch.object(MODULE, "identity_contacts", side_effect=AssertionError("no D1")), \
                patch.object(MODULE, "audit", side_effect=AssertionError("no preflight")), \
                redirect_stdout(StringIO()) as output:
            MODULE.recover()
        self.assertEqual(actions, ["close", "metadata", "cleanup"])
        self.assertIn("staging_worker_created_r2_recovered_absent", output.getvalue())

    def test_ambiguous_delete_gets_same_bytes_before_conditional_retry(self) -> None:
        """No blind DELETE repeat; 403 is a definitive stop."""

        key = "verification/12345678-1234-4123-8123-123456789abc.eml"
        calls: list[str] = []
        r2 = sys.modules.get("staging_r2_object_capability")
        self.assertIsNotNone(r2)

        def fake_get(*_args):
            calls.append("GET")
            return ["present", "present", "absent"][calls.count("GET") - 1]

        def fake_delete(*_args):
            calls.append("DELETE")
            if calls.count("DELETE") == 1:
                raise r2.ProbeFailure("r2_outcome_ambiguous")

        with patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                                      "CLOUDFLARE_API_TOKEN": "private-token"}, clear=True), \
                patch.object(MODULE, "get_owned", side_effect=fake_get), \
                patch.object(r2, "delete", side_effect=fake_delete), \
                patch.object(MODULE, "object_inventory", return_value=set()):
            MODULE.delete_owned(key, "123", "1", self.window())
        self.assertEqual(calls, ["GET", "DELETE", "GET", "DELETE", "GET"])

    def test_definite_delete_denial_never_retries(self) -> None:
        """A 403 cannot be turned into another DELETE or a capability pass."""

        key = "verification/12345678-1234-4123-8123-123456789abc.eml"
        with patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                                      "CLOUDFLARE_API_TOKEN": "private-token"}, clear=True), \
                patch.object(MODULE, "get_owned", return_value="present") as get, \
                patch.object(R2, "delete", side_effect=R2.ProbeFailure("r2_delete_denied")) as delete:
            with self.assertRaises(MODULE.ProbeFailure) as caught:
                MODULE.delete_owned(key, "123", "1", self.window())
        self.assertEqual(str(caught.exception), "object_delete_denied")
        self.assertEqual(get.call_count, 1)
        self.assertEqual(delete.call_count, 1)

    def test_whole_probe_does_not_retry_denied_delete_in_finally(self) -> None:
        """The outer cleanup must not turn one definite 403 into a second write."""

        key = "verification/12345678-1234-4123-8123-123456789abc.eml"
        env = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
               "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
               "CLOUDFLARE_API_TOKEN": "private-token",
               "AMAIL_SENDING_GRANT_ATTEST": "ATTEST_ONE_SYNTHETIC_APEX_SEND"}
        contacts = {MODULE.FIRST: ("principal-a", "subject-a", "verified", "a_username")}
        actions: list[str] = []

        def fake_route(action: str) -> str:
            actions.append(action)
            return {"apply": "created", "audit": "enabled" if "remove" not in actions else "absent",
                    "remove": "removed"}[action]

        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE, "audit"), \
                patch.object(MODULE, "identity_contacts", return_value=contacts), \
                patch.object(MODULE, "sender_ready"), \
                patch.object(MODULE, "one_key", side_effect=[None, key, key]), \
                patch.object(MODULE, "route", side_effect=fake_route), \
                patch.object(MODULE, "send_once", return_value=True), \
                patch.object(MODULE, "get_owned", return_value="present"), \
                patch.object(R2, "delete", side_effect=R2.ProbeFailure("r2_delete_denied")) as delete, \
                patch.object(MODULE.time, "sleep"):
            with self.assertRaises(MODULE.ProbeFailure) as caught:
                MODULE.probe()
        self.assertEqual(str(caught.exception), "object_delete_denied_cleanup_unverified")
        self.assertEqual(delete.call_count, 1)
        self.assertEqual(actions[-2:], ["remove", "audit"])

    def test_whole_probe_stops_after_conditional_delete_is_denied(self) -> None:
        """Ambiguous first DELETE permits one readback, not a third after 403."""

        key = "verification/12345678-1234-4123-8123-123456789abc.eml"
        env = {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
               "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
               "CLOUDFLARE_API_TOKEN": "private-token",
               "AMAIL_SENDING_GRANT_ATTEST": "ATTEST_ONE_SYNTHETIC_APEX_SEND"}
        contacts = {MODULE.FIRST: ("principal-a", "subject-a", "verified", "a_username")}

        def fake_route(action: str) -> str:
            return {"apply": "created", "audit": "enabled" if action == "audit"
                    and fake_route.closed is False else "absent", "remove": "removed"}[action]

        fake_route.closed = False

        def route_action(action: str) -> str:
            if action == "remove":
                fake_route.closed = True
            return fake_route(action)

        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE, "audit"), \
                patch.object(MODULE, "identity_contacts", return_value=contacts), \
                patch.object(MODULE, "sender_ready"), \
                patch.object(MODULE, "one_key", side_effect=[None, key, key]), \
                patch.object(MODULE, "route", side_effect=route_action), \
                patch.object(MODULE, "send_once", return_value=True), \
                patch.object(MODULE, "get_owned", return_value="present"), \
                patch.object(R2, "delete", side_effect=[
                    R2.ProbeFailure("r2_outcome_ambiguous"),
                    R2.ProbeFailure("r2_delete_denied")]) as delete, \
                patch.object(MODULE.time, "sleep"):
            with self.assertRaises(MODULE.ProbeFailure) as caught:
                MODULE.probe()
        self.assertEqual(str(caught.exception), "object_delete_denied_cleanup_unverified")
        self.assertEqual(delete.call_count, 2)

    def test_failed_send_is_one_request_and_multiple_objects_fail_closed(self) -> None:
        """A lost sending response cannot trigger a second synthetic message."""

        with patch.object(MODULE, "call", side_effect=R2.ProbeFailure("r2_outcome_ambiguous")) as send:
            self.assertFalse(MODULE.send_once("a" * 32, "private-token", "123", "1"))
        send.assert_called_once()
        with patch.object(MODULE, "call", return_value=(503, b"provider-private-body")) as send:
            self.assertFalse(MODULE.send_once("a" * 32, "private-token", "123", "1"))
        send.assert_called_once()
        with patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                                      "CLOUDFLARE_API_TOKEN": "private-token"}, clear=True), \
                patch.object(MODULE, "request", return_value=(
                    b'{"success":true,"result":[{"key":"one"},{"key":"two"}]}')) as listing:
            with self.assertRaises(MODULE.ProbeFailure) as caught:
                MODULE.one_key()
        self.assertEqual(str(caught.exception), "private_inventory_ambiguous")
        listing.assert_called_once()

    def test_one_key_proves_singleton_with_explicit_empty_next_page(self) -> None:
        """The short-window inventory makes at most two bounded REST calls."""

        key = "verification/12345678-1234-4123-8123-123456789abc.eml"
        pages = [(('{"success":true,"result":[{"key":"' + key + '"}]}').encode()),
                 b'{"success":true,"result":[]}']
        with patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                                      "CLOUDFLARE_API_TOKEN": "private-token"}, clear=True), \
                patch.object(MODULE, "request", side_effect=pages) as listing:
            self.assertEqual(MODULE.one_key(), key)
        self.assertEqual(listing.call_count, 2)
        self.assertIn("start_after=verification%2F", listing.call_args.args[1])

    def test_route_scan_budget_expires_inside_helper_page(self) -> None:
        """A nested page cannot outlive the route action's 45-second budget."""

        def run_helper(module):
            module.reconcile = lambda *_args: urllib.request.urlopen(
                urllib.request.Request("https://api.cloudflare.com/client/v4/test"), timeout=20)

        spec = types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=run_helper))
        env = {"CLOUDFLARE_ZONE_ID": "a" * 32,
               "CF_EMAIL_ROUTING_TOKEN": "private-route-token"}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE.importlib.util, "spec_from_file_location", return_value=spec), \
                patch.object(MODULE.importlib.util, "module_from_spec", return_value=types.SimpleNamespace()), \
                patch.object(MODULE.time, "monotonic", side_effect=[0, 46]), \
                patch.object(MODULE.OPENER, "open", side_effect=AssertionError("must not call provider")):
            with self.assertRaises(MODULE.ProbeFailure) as caught:
                MODULE.route("audit")
        self.assertEqual(str(caught.exception), "exact_route_control_failed")

    def test_get_denial_and_foreign_mime_cannot_reach_delete(self) -> None:
        """The exact candidate must be readable and strictly owned first."""

        key = "verification/12345678-1234-4123-8123-123456789abc.eml"
        env = {"CLOUDFLARE_ACCOUNT_ID": "a" * 32,
               "CLOUDFLARE_API_TOKEN": "private-token"}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE, "call", return_value=(403, b"provider-private-body")):
            with self.assertRaises(MODULE.ProbeFailure) as caught:
                MODULE.get_owned(key, "123", "1", self.window())
        self.assertEqual(str(caught.exception), "object_get_denied")
        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE, "call", return_value=(200, b"foreign-private-body")), \
                patch.object(R2, "delete") as delete:
            with self.assertRaises(MODULE.ProbeFailure) as caught:
                MODULE.delete_owned(key, "123", "1", self.window())
        self.assertEqual(str(caught.exception), "synthetic_mime_mismatch")
        delete.assert_not_called()

    def test_late_inventory_ambiguity_fails_after_route_closed(self) -> None:
        """An extra object in the settle window cannot become a green result."""

        key = "verification/12345678-1234-4123-8123-123456789abc.eml"
        with patch.object(MODULE, "one_key", side_effect=[key, MODULE.ProbeFailure(
                "private_inventory_ambiguous")]), \
                patch.object(MODULE, "delete_owned") as deleted, \
                patch.object(MODULE.time, "sleep"):
            with self.assertRaises(MODULE.ProbeFailure) as caught:
                MODULE.reconcile("123", "1", self.window(), settle=True)
        self.assertEqual(str(caught.exception), "private_inventory_ambiguous")
        deleted.assert_called_once()

    def test_prior_run_requires_correct_job_and_recent_window(self) -> None:
        """Recovery does not accept a guessed run, stale send or another target."""

        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=8)
        end = now - timedelta(minutes=5)
        run = {"id": 123, "run_attempt": 1, "event": "workflow_dispatch",
               "status": "completed", "conclusion": "failure", "head_branch": MODULE.BRANCH,
               "head_sha": "a" * 40,
               "path": ".github/workflows/staging-worker-r2-capability.yml",
               "created_at": start.isoformat(), "updated_at": end.isoformat()}
        valid_job = {"name": MODULE.JOB_NAME, "run_id": 123, "head_sha": "a" * 40,
                     "status": "completed", "conclusion": "failure",
                     "started_at": (start + timedelta(minutes=1)).isoformat(),
                     "completed_at": (end - timedelta(minutes=1)).isoformat(),
                     "steps": [{"name": MODULE.PROBE_STEP_NAME, "status": "completed",
                                "conclusion": "failure",
                                "started_at": (start + timedelta(minutes=2)).isoformat()}]}
        jobs = {"total_count": 1, "jobs": [valid_job]}
        env = {"GITHUB_REPOSITORY": MODULE.REPOSITORY, "GITHUB_RUN_ID": "124",
               "GITHUB_TOKEN": "private-github-token",
               "AMAIL_WORKER_R2_PRIOR_SHA": "a" * 40}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE, "github_json", side_effect=[run, jobs]):
            window = MODULE.prior_window("123", "1")
        self.assertEqual(window[0], start)
        self.assertEqual(window[1], end + timedelta(minutes=10))
        qualified = {**run, "path": ".github/workflows/staging-worker-r2-capability.yml@refs/heads/" + MODULE.BRANCH}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE, "github_json", side_effect=[qualified, jobs]):
            self.assertEqual(MODULE.prior_window("123", "1")[0], start)
        bad_jobs = {"total_count": 1, "jobs": [{"name": "unrelated target",
                                               "status": "completed"}]}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE, "github_json", side_effect=[run, bad_jobs]):
            with self.assertRaises(MODULE.ProbeFailure) as caught:
                MODULE.prior_window("123", "1")
        self.assertEqual(str(caught.exception), "prior_run_job_invalid")
        for bad in (
            {**valid_job, "conclusion": "skipped"},
            {**valid_job, "run_id": 999},
            {**valid_job, "head_sha": "b" * 40},
            {**valid_job, "steps": [{**valid_job["steps"][0], "conclusion": "skipped"}]},
        ):
            with self.subTest(bad=bad), patch.dict(os.environ, env, clear=True), \
                    patch.object(MODULE, "github_json", side_effect=[run, {
                        "total_count": 1, "jobs": [bad]}]):
                with self.assertRaises(MODULE.ProbeFailure):
                    MODULE.prior_window("123", "1")
        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE, "github_json", side_effect=[run, {
                    "total_count": 2, "jobs": [valid_job, valid_job]}]):
            with self.assertRaises(MODULE.ProbeFailure) as caught:
                MODULE.prior_window("123", "1")
        self.assertEqual(str(caught.exception), "prior_run_job_invalid")
        wrong_workflow = {**run, "path": ".github/workflows/other.yml"}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE, "github_json", return_value=wrong_workflow):
            with self.assertRaises(MODULE.ProbeFailure) as caught:
                MODULE.prior_window("123", "1")
        self.assertEqual(str(caught.exception), "prior_run_metadata_invalid")
        stale = {**run, "created_at": (now - timedelta(hours=25)).isoformat()}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE, "github_json", return_value=stale):
            with self.assertRaises(MODULE.ProbeFailure) as caught:
                MODULE.prior_window("123", "1")
        self.assertEqual(str(caught.exception), "prior_run_metadata_invalid")

    def test_recovery_closure_failure_blocks_metadata_and_object_access(self) -> None:
        """An active route is a stop even if prior-run metadata is available."""

        with patch.dict(os.environ, {"AMAIL_WORKER_R2_PRIOR_RUN_ID": "123",
                                      "AMAIL_WORKER_R2_PRIOR_RUN_ATTEMPT": "1"}, clear=True), \
                patch.object(MODULE, "close_route", side_effect=MODULE.ProbeFailure(
                    "route_cleanup_unverified")), \
                patch.object(MODULE, "prior_window") as metadata, \
                patch.object(MODULE, "one_key") as inventory:
            with self.assertRaises(MODULE.ProbeFailure):
                MODULE.recover()
        metadata.assert_not_called()
        inventory.assert_not_called()

    def test_main_prints_only_fixed_labels(self) -> None:
        """Never echo an exception carrying a token, key, address or body."""

        out, err = StringIO(), StringIO()
        with patch.object(MODULE, "execute", side_effect=RuntimeError(
                "private-token verification/secret.eml mail-body")), \
                redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(MODULE.main(), 1)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue().strip(),
                         "staging_worker_created_r2_failed:unexpected_failure")

    def test_manual_workflow_is_guarded_and_tests_before_secrets(self) -> None:
        """Probe and recovery stay dormant, serialized and source-name aligned."""

        workflow = (MODULE.ROOT / ".github/workflows/staging-worker-r2-capability.yml").read_text(
            encoding="utf-8")
        self.assertIn("on:\n  workflow_dispatch:", workflow)
        self.assertNotIn("\n  push:", workflow)
        self.assertNotIn("\n  pull_request:", workflow)
        probe = workflow.split("  staging-worker-r2-probe:\n", 1)[1].split(
            "\n  staging-worker-r2-recover:", 1)[0]
        recovery = workflow.split("  staging-worker-r2-recover:\n", 1)[1]
        self.assertIn("staging-worker-r2-get-delete", workflow)
        self.assertIn("staging-worker-r2-recover", workflow)
        for job, target, mode in ((probe, "staging-worker-r2-get-delete", "probe"),
                                  (recovery, "staging-worker-r2-recover", "recover")):
            with self.subTest(mode=mode):
                self.assertIn("github.event_name == 'workflow_dispatch'", job)
                self.assertIn("inputs.target == '" + target + "'", job)
                self.assertIn("github.ref == 'refs/heads/codex/amail-v0.1.0'", job)
                self.assertIn("runs-on: ubuntu-latest", job)
                self.assertIn("environment: staging", job)
                self.assertIn("group: staging-native-mail-acceptance", job)
                self.assertIn("cancel-in-progress: false", job)
                self.assertIn("CURRENT_ATTEMPT: ${{ github.run_attempt }}", job)
                self.assertIn("AMAIL_WORKER_R2_MODE: " + mode, job)
                self.assertIn("python infra/tests/staging_worker_created_r2.py", job)
                self.assertIn("test_staging_worker_created_r2.py", job)
                self.assertLess(job.index("test_staging_worker_created_r2.py"),
                                job.index("secrets.CLOUDFLARE_API_TOKEN"))
                self.assertEqual(job.count("secrets.CLOUDFLARE_API_TOKEN"), 1)
                self.assertNotIn("STAGING_E2E_B_USERNAME", job)
                self.assertNotIn("STAGING_E2E_B_PASSWORD", job)
                self.assertNotIn("--apply", job)
        self.assertIn("name: " + MODULE.JOB_NAME, probe)
        self.assertIn("- name: " + MODULE.PROBE_STEP_NAME, probe)
        self.assertIn("ATTEST_ONE_SYNTHETIC_APEX_SEND", probe)
        self.assertIn("permissions:\n      contents: read\n      actions: read", recovery)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", recovery)
        self.assertIn("AMAIL_WORKER_R2_PRIOR_SHA: ${{ inputs.worker_r2_prior_sha }}", recovery)
        self.assertNotIn("AMAIL_SENDING_GRANT_ATTEST", recovery)

    def test_dispatch_input_count_stays_within_github_limit(self) -> None:
        """A 26th top-level input invalidates the entire workflow before jobs."""

        for filename, expected in (("ci.yml", 23),
                                   ("staging-worker-r2-capability.yml", 6)):
            with self.subTest(filename=filename):
                workflow = (MODULE.ROOT / ".github/workflows" / filename).read_text(
                    encoding="utf-8")
                dispatch = workflow.split("  workflow_dispatch:\n", 1)[1].split(
                    "\npermissions:", 1)[0]
                names = re.findall(r"^      ([a-z][a-z0-9_]*):$", dispatch, re.MULTILINE)
                self.assertEqual(len(names), expected)
                self.assertEqual(len(names), len(set(names)))
                self.assertLessEqual(len(names), 25)


if __name__ == "__main__":
    unittest.main()
