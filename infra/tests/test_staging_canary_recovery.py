"""Offline contracts for deterministic, read-only outbound reconciliation."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).parent))
import staging_canary_recovery as recovery
import staging_outbound_canary as canary


SECRET = "a1" * 32


class RecoveryTests(unittest.TestCase):
    """Prove ambiguous sends remain attributable after ephemeral cleanup."""

    def test_material_is_stable_domain_separated_and_run_bound(self) -> None:
        """A protected key and public coordinates recreate one exact attempt."""

        key, nonce = recovery.material("12345", "1", SECRET)
        self.assertEqual((key, nonce), recovery.material("12345", "1", SECRET))
        self.assertNotEqual(key, recovery.material("12345", "2", SECRET)[0])
        self.assertNotEqual(nonce, recovery.material("12346", "1", SECRET)[1])
        self.assertEqual(len(nonce), 32)
        with self.assertRaisesRegex(recovery.RecoveryError, "recovery_key_invalid"):
            recovery.material("12345", "1", "short")
        with self.assertRaisesRegex(recovery.RecoveryError, "run_coordinates_invalid"):
            recovery.material("0", "1", SECRET)

    def test_uncertain_send_key_recoverable_without_replay(self) -> None:
        """A failed CLI send uses the recomputable key, not a transient UUID."""

        from argparse import Namespace
        from unittest.mock import MagicMock

        key, nonce = recovery.material("12345", "1", SECRET)
        home = MagicMock()
        home.is_dir.return_value = True
        binary = MagicMock()
        binary.is_file.return_value = True
        run_dir = Path("private")
        draft_path = run_dir / "draft"
        args = Namespace(confirm_staging=True, home="private-home", amail="amail.exe",
                         run_dir="private-outbound", sender="probe@mail-staging.moesegfault.dev")
        with patch.dict(os.environ, {
            "GITHUB_ACTIONS": "true", "GITHUB_RUN_ID": "12345", "GITHUB_RUN_ATTEMPT": "1",
            "AMAIL_STAGING_CANARY_RECOVERY_KEY": SECRET,
        }, clear=True), patch.object(canary.os, "name", "nt"), \
                patch.object(canary, "inside_temp", side_effect=[home, binary]), \
                patch.object(canary, "config", return_value={"AMAIL_CANARY_RECIPIENT": "probe@example.net"}), \
                patch.object(canary, "cli_env", return_value={}), \
                patch.object(canary, "privacy_ready"), patch.object(canary, "inbox_ready"), \
                patch.object(canary, "preflight"), \
                patch.object(canary, "create_run_dir", return_value=run_dir), \
                patch.object(canary, "make_draft", return_value=(draft_path, "unused")) as draft, \
                patch.object(canary, "amail", side_effect=[
                    [{"authenticated": True}], [{"packed": True}],
                    canary.ProbeFailure("canary_send_uncertain"),
                ]) as amail:
            with self.assertRaisesRegex(canary.ProbeFailure, "canary_send_uncertain"):
                canary.execute(args)
        self.assertEqual(draft.call_args.args[3], nonce)
        self.assertEqual(amail.call_args_list[2].args[-1], key)
        self.assertEqual(amail.call_count, 3)

    def test_recovery_reads_exact_request_and_grant_without_mutation(self) -> None:
        """An uncertain provider state is classified, not automatically replayed."""

        with patch.dict(os.environ, {
            "AMAIL_STAGING_CANARY_RECOVERY_KEY": SECRET,
            "STAGING_E2E_OWNER_SUB": "synthetic-owner",
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
            "CLOUDFLARE_API_TOKEN": "fake-read-token",
        }, clear=True):
            d1 = Mock(side_effect=[
                [{"state": "held"}],
                [{"state": "unknown", "provider_id": None, "message_id": "opaque"}],
                [{"canary_used_by": recovery.material("12345", "1", SECRET)[0]}],
            ])
            self.assertEqual(
                recovery.inspect("12345", "1", read_d1=d1),
                "request_unknown_grant_consumed_provider_id_absent_delivered_event_absent",
            )
        self.assertEqual(d1.call_count, 3)
        self.assertTrue(all(call.args[1].startswith("SELECT ") for call in d1.call_args_list))


if __name__ == "__main__":
    unittest.main()
