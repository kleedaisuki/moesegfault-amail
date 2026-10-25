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
        denied: bytes = json.dumps({"schema": "amail.machine.v1", "event": "error",
            "data": {"code": "mailbox_in_use"}}).encode()
        replies: list[subprocess.CompletedProcess[bytes]] = [
            subprocess.CompletedProcess([], 1, b"", denied),
            subprocess.CompletedProcess([], 0, json.dumps({"address": second, "mode": "write"}).encode(), b""),
        ]
        with patch.object(semantic.mail, "amail", return_value=rows), \
             patch.object(semantic.subprocess, "run", side_effect=replies) as acquire:
            self.assertEqual(semantic.acquire_stable_alias(Path("amail.exe"), {}), second)
            self.assertEqual(acquire.call_count, 2)
            self.assertEqual(acquire.call_args_list[0].args[0],
                ["amail.exe", "--machine", "mailbox", "acquire", first, "--mode", "write"])
            self.assertNotIn("--force", acquire.call_args.args[0])
        with patch.object(semantic.mail, "amail", return_value=[]), \
             patch.object(semantic.subprocess, "run") as acquire:
            with self.assertRaisesRegex(semantic.mail.ProbeFailure, "^semantic_baseline_alias_missing$"):
                semantic.acquire_stable_alias(Path("amail.exe"), {})
            acquire.assert_not_called()

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
