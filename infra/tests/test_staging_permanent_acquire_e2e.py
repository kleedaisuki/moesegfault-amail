"""Keep permanent-acquire acceptance limited to its existing owned fixture."""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any
import unittest
from unittest.mock import patch

ROOT: Path = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/tests"))
import staging_permanent_acquire_e2e as probe


class PermanentAcquireProbeTests(unittest.TestCase):
    def test_baseline_requires_exact_active_owned_permanent_empty_generation(self) -> None:
        address: str = "semantic-example@mail-staging.moesegfault.dev"
        valid: dict[str, Any] = {"address": address, "kind": "mail", "state": "active",
            "generation": "", "expires_at": None}
        probe.require_baseline([valid], address)
        for changed in ({"address": "other@mail-staging.moesegfault.dev"}, {"kind": "tmpaddr"},
                        {"state": "pending"}, {"generation": "temporary-generation"}, {"expires_at": 123}):
            with self.subTest(changed=changed), self.assertRaisesRegex(probe.mail.ProbeFailure,
                    "^permanent_acquire_managed_baseline_missing$"):
                probe.require_baseline([{**valid, **changed}], address)

    def test_actual_acquire_release_path_and_capability_redaction(self) -> None:
        binary: Path = Path("amail.exe")
        address: str = "semantic-example@mail-staging.moesegfault.dev"
        calls: list[tuple[str, ...]] = []

        def cli(_binary: Path, _env: dict[str, str], *args: str, failure: str) -> list[dict[str, Any]]:
            calls.append(args)
            return ([{"released": True}] if args[1] == "release" else
                    [{"address": address, "generation": "", "mode": args[-1]}])

        with patch.object(probe.mail, "amail", side_effect=cli):
            probe.lease_journey(binary, {}, address)
        self.assertEqual(calls, [("mailbox", "acquire", address, "--mode", "read"),
            ("mailbox", "acquire", address, "--mode", "read"),
            ("mailbox", "acquire", address, "--mode", "write"), ("mailbox", "release", address),
            ("mailbox", "acquire", address, "--mode", "read"), ("mailbox", "release", address)])
        for token in ("lease_token", "session_token"):
            with self.subTest(token=token), patch.object(probe.mail, "amail", return_value=[{token: "private"}]):
                with self.assertRaisesRegex(probe.mail.ProbeFailure,
                        "^permanent_acquire_private_capability_in_stdout$"):
                    probe.one(binary, {}, "mailbox", "acquire", address, "--mode", "read")


if __name__ == "__main__":
    unittest.main()
