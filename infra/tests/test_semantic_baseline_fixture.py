"""A semantic-only fixture never retires an owner's existing mailbox or route."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any
import unittest
from unittest.mock import patch

ROOT: Path = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/tests"))
import staging_semantic_e2e as semantic


class BaselineFixtureTests(unittest.TestCase):
    def test_selects_only_owned_active_permanent_aliases_and_never_preempts(self) -> None:
        first: str = "a@mail-staging.moesegfault.dev"
        second: str = "b@mail-staging.moesegfault.dev"
        rows: list[dict[str, Any]] = [
            {"address": second, "kind": "mail", "state": "active", "expires_at": None},
            {"address": first, "kind": "mail", "state": "active", "expires_at": None},
            {"address": "pending@mail-staging.moesegfault.dev", "kind": "mail", "state": "pending"},
            {"address": "temporary@tmpaddr-staging.moesegfault.dev", "kind": "tmpaddr", "state": "active"},
            {"address": "wrong@mail.moesegfault.dev", "kind": "mail", "state": "active"},
        ]
        self.assertEqual(semantic.stable_owned_aliases(rows), [first, second])
        denied: bytes = b"amail: cloud request rejected: mailbox_in_use\r\n"
        replies: list[subprocess.CompletedProcess[bytes]] = [
            subprocess.CompletedProcess([], 1, b"", denied),
            subprocess.CompletedProcess([], 0, json.dumps({"address": second, "mode": "write"}).encode(), b""),
        ]
        with patch.object(semantic.mail, "amail", return_value=rows), \
             patch.object(semantic.subprocess, "run", side_effect=replies) as acquire:
            self.assertEqual(semantic.acquire_stable_alias(Path("amail.exe"), {}), second)
            self.assertEqual(acquire.call_count, 2)
            self.assertEqual(acquire.call_args_list[0].args[0],
                ["amail.exe", "mailbox", "acquire", first, "--mode", "write"])
            self.assertNotIn("--force", acquire.call_args.args[0])
        with patch.object(semantic.mail, "amail", return_value=[]), \
             patch.object(semantic.subprocess, "run") as acquire:
            with self.assertRaisesRegex(semantic.mail.ProbeFailure, "^semantic_baseline_alias_missing$"):
                semantic.acquire_stable_alias(Path("amail.exe"), {})
            acquire.assert_not_called()

    def test_acquire_diagnostics_export_only_closed_codes_and_http_status(self) -> None:
        def record(code: str, status: object = 403) -> bytes:
            return json.dumps({"schema": "amail.machine.v1", "event": "error", "data": {
                "code": code, "details": {"status": status, "private": "secret address"},
                "request_id": "private correlation"}}).encode()

        self.assertEqual(semantic.baseline_acquire_failure(record("profile_request_failed")),
                         "semantic_baseline_acquire_profile_request_failed_http_403")
        self.assertEqual(semantic.baseline_acquire_failure(record("profile_transport_unknown", "private")),
                         "semantic_baseline_acquire_profile_transport_unknown")
        self.assertEqual(semantic.baseline_acquire_failure(record("local_error", True)),
                         "semantic_baseline_acquire_local_error")
        self.assertEqual(semantic.baseline_acquire_failure(record("mailbox_in_use", 409)), "mailbox_in_use")
        self.assertEqual(semantic.baseline_acquire_failure(record("private address")),
                         "semantic_baseline_acquire_unknown_code")
        self.assertEqual(semantic.baseline_acquire_failure(b"private non-JSON address"),
                         "semantic_baseline_acquire_non_json")
        self.assertEqual(semantic.baseline_acquire_failure(b"{}"), "semantic_baseline_acquire_machine_shape")

    def test_plain_acquire_diagnostics_match_only_exact_cli_owned_errors(self) -> None:
        cases: dict[bytes, str] = {
            b"amail: invalid cloud profile response\r\n": "invalid_cloud_profile_response",
            b"amail: cloud lease missing capability\n": "cloud_lease_missing_capability",
            b"amail: cloud lease missing generation": "cloud_lease_missing_generation",
            b"amail: cloud lease missing mode": "cloud_lease_missing_mode",
            b"amail: no active daemon profile": "no_active_daemon_profile",
            b"amail: invalid mailbox lease": "invalid_mailbox_lease",
            b"amail: invalid cloud lease": "invalid_cloud_lease",
            b"amail: cloud request rejected: profile_request_failed": "profile_request_failed",
            b"amail: cloud request rejected: private-address": "plain_unknown",
            b"amail: invalid mailbox lease private-address": "plain_unknown",
            b"private-address\namail: invalid mailbox lease": "plain_unknown",
        }
        for stderr, category in cases.items():
            with self.subTest(category=category):
                self.assertEqual(semantic.baseline_acquire_plain_failure(stderr),
                                 "semantic_baseline_acquire_" + category)
        self.assertEqual(semantic.baseline_acquire_plain_failure(
            b"amail: cloud request rejected: mailbox_in_use\r\n"), "mailbox_in_use")
        self.assertEqual(semantic.baseline_acquire_plain_failure(b"x" * 65_537),
                         "semantic_baseline_acquire_output_invalid")
        inventory: list[dict[str, Any]] = [{"address": "owned@mail-staging.moesegfault.dev",
            "kind": "mail", "state": "active", "expires_at": None}]
        reply: subprocess.CompletedProcess[bytes] = subprocess.CompletedProcess([], 1, b"",
            b"amail: invalid mailbox lease\r\n")
        with patch.object(semantic.mail, "amail", return_value=inventory), \
             patch.object(semantic.subprocess, "run", return_value=reply) as acquire:
            with self.assertRaisesRegex(semantic.mail.ProbeFailure,
                                        "^semantic_baseline_acquire_invalid_mailbox_lease$"):
                semantic.acquire_stable_alias(Path("amail.exe"), {})
            acquire.assert_called_once()
            self.assertNotIn("--machine", acquire.call_args.args[0])

    def test_cleanup_deletes_only_the_known_fixture_and_never_the_baseline(self) -> None:
        with patch.object(semantic.mail, "amail") as cli, patch.object(semantic.mail, "assert_route") as route:
            semantic.cleanup_fixture(Path("amail.exe"), {}, "existing@mail-staging.moesegfault.dev",
                                     "known-new-message", False, lambda action: action())
            cli.assert_called_once_with(Path("amail.exe"), {}, "delete", "known-new-message",
                                        failure="semantic_fixture_delete_failed")
            route.assert_not_called()
            cli.reset_mock()
            semantic.cleanup_fixture(Path("amail.exe"), {}, "existing@mail-staging.moesegfault.dev",
                                     None, False, lambda action: action())
            cli.assert_not_called()
            route.assert_not_called()


if __name__ == "__main__":
    unittest.main()
