"""Offline contracts for the staging-only outbound canary harness.

The hosted CI test suite runs these checks without any network or email send.
"""

from __future__ import annotations

import importlib.util
from email.message import EmailMessage
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


PATH = Path(__file__).with_name("staging_outbound_canary.py")
SPEC = importlib.util.spec_from_file_location("staging_outbound_canary", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def values() -> dict[str, str]:
    """Return synthetic config with no real recipient or credential."""

    return {
        "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
        "CLOUDFLARE_API_TOKEN": "fake",
        "STAGING_E2E_OWNER_SUB": "synthetic-owner",
        "AMAIL_CANARY_RECIPIENT": "probe@example.net",
        "AMAIL_CANARY_IMAP_HOST": "imap.example.net",
        "AMAIL_CANARY_IMAP_USER": "synthetic",
        "AMAIL_CANARY_IMAP_PASSWORD": "fake",
        "AMAIL_CANARY_AUTHSERV_ID": "mx.example.net",
    }


class CanaryTests(unittest.TestCase):
    """Prevent the probe from confusing provider acceptance with delivery."""

    def test_config_requires_external_oracle_and_rejects_internal_recipient(self) -> None:
        """Never spend the one-use grant without the full independent inbox capability."""

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MODULE.ProbeFailure):
                MODULE.config()
        configured = values()
        with patch.dict(os.environ, configured, clear=True):
            self.assertEqual(MODULE.config()["AMAIL_CANARY_RECIPIENT"], "probe@example.net")
        configured["AMAIL_CANARY_RECIPIENT"] = "probe@mail-staging.moesegfault.dev"
        with patch.dict(os.environ, configured, clear=True):
            with self.assertRaisesRegex(MODULE.ProbeFailure, "canary_recipient_not_external"):
                MODULE.config()

    def test_policy_and_grant_must_match_before_send(self) -> None:
        """A global unhold, used grant, wrong digest, or short expiry is a denial."""

        config = values()
        digest = MODULE.hashlib.sha256(b"probe@example.net").hexdigest()
        grant = {
            "canary_owner_iss": MODULE.ISSUER,
            "canary_owner_sub": "synthetic-owner",
            "canary_recipient_sha256": digest,
            "canary_expires_at": 1000,
            "canary_used_by": None,
            "now": 700,
        }
        responses = [[{"state": "held"}], [{"state": "active"}], [grant]]
        with patch.object(MODULE, "d1", side_effect=responses):
            MODULE.preflight(config, "probe@mail-staging.moesegfault.dev")
        for change in ({"canary_used_by": "old"}, {"canary_recipient_sha256": "0" * 64},
                       {"canary_expires_at": 800}):
            with self.subTest(change=change), patch.object(MODULE, "d1", side_effect=[
                [{"state": "held"}], [{"state": "active"}], [{**grant, **change}],
            ]):
                with self.assertRaisesRegex(MODULE.ProbeFailure, "canary_grant_not_ready"):
                    MODULE.preflight(config, "probe@mail-staging.moesegfault.dev")
        with patch.object(MODULE, "d1", return_value=[{"state": "allowed"}]):
            with self.assertRaisesRegex(MODULE.ProbeFailure, "canary_global_not_held"):
                MODULE.preflight(config, "probe@mail-staging.moesegfault.dev")

    def test_hosted_rendezvous_needs_grant_issuance_not_generic_update(self) -> None:
        """Attestation updated_at changes cannot make an old grant fresh."""

        grant = {
            "canary_owner_iss": MODULE.ISSUER,
            "canary_owner_sub": "synthetic-owner",
            "canary_recipient_sha256": MODULE.hashlib.sha256(b"probe@example.net").hexdigest(),
            "canary_expires_at": 2000,
            "canary_used_by": None,
            "case_ref": "amail_canary_12345_1",
            "now": 1050,
        }
        watermark = MODULE.GrantWatermark(8, 2000, "amail_canary_12345_1")
        with patch.object(MODULE, "d1", return_value=[grant]) as d1:
            self.assertFalse(MODULE.grant_ready(values(), after=watermark))
            d1.assert_called_once()
        new_grant = {**grant, "canary_expires_at": 2100}
        with patch.object(MODULE, "d1", side_effect=[[new_grant], []]):
            self.assertFalse(MODULE.grant_ready(values(), after=watermark))
        with patch.object(MODULE, "d1", side_effect=[[new_grant], [{"id": 9}]]):
            self.assertTrue(MODULE.grant_ready(values(), after=watermark))

    def test_grant_watermark_captures_audit_and_expiry_together(self) -> None:
        """The ready marker follows a single atomic staging D1 snapshot."""

        with patch.object(MODULE, "d1", return_value=[{"audit_id": 8, "canary_expires_at": 2000}]) as d1:
            watermark = MODULE.grant_watermark(values(), "12345", "1")
        self.assertEqual(watermark, MODULE.GrantWatermark(8, 2000, "amail_canary_12345_1"))
        self.assertIn("send_release_gate_audit", d1.call_args.args[1])

    def test_provider_202_alone_never_verifies_delivery(self) -> None:
        """An uncorrelated event or a non-delivered outcome is insufficient."""

        config = values()
        request = {"provider_id": "p", "state": "sent", "message_id": "m"}
        with patch.object(MODULE, "d1", side_effect=[[request], [{"n": 1}], [{"kind": "delivered"}]]):
            self.assertTrue(MODULE.feedback_delivered(config, "key", "m"))
        with patch.object(MODULE, "d1", side_effect=[[request], [{"n": 0}], [{"kind": "delivered"}]]):
            self.assertFalse(MODULE.feedback_delivered(config, "key", "m"))
        with patch.object(MODULE, "d1", side_effect=[[request], [{"n": 1}], [{"kind": "deferred"}]]):
            self.assertFalse(MODULE.feedback_delivered(config, "key", "m"))

    def test_accepted_send_must_consume_exact_grant_under_hold(self) -> None:
        """A public unhold or unrelated canary key cannot be called a valid probe."""

        for row in ({"state": "allowed", "canary_used_by": "key"},
                    {"state": "held", "canary_used_by": "other"}):
            with self.subTest(row=row), patch.object(MODULE, "d1", return_value=[row]):
                with self.assertRaisesRegex(MODULE.ProbeFailure, "canary_not_one_use_under_hold"):
                    MODULE.grant_consumed_under_hold(values(), "key")
        with patch.object(MODULE, "d1", return_value=[{"state": "held", "canary_used_by": "key"}]):
            MODULE.grant_consumed_under_hold(values(), "key")

    def test_mime_needs_trusted_authentication_and_assets(self) -> None:
        """A bare subject/body or forged unrelated authserv-id does not pass."""

        nonce = "abc123"
        raw = ("From: probe@mail-staging.moesegfault.dev\r\n"
               "To: probe@example.net\r\nSubject: AMAIL-CANARY-abc123\r\n"
               "Authentication-Results: untrusted.invalid; dkim=pass header.d=mail-staging.moesegfault.dev; "
               "spf=pass; dmarc=pass header.from=mail-staging.moesegfault.dev\r\n"
               "Content-Type: text/plain; charset=utf-8\r\n\r\nSynthetic staging canary abc123\r\n").encode()
        self.assertFalse(MODULE.delivered_mime(raw, "probe@example.net", nonce, "mx.example.net"))

        mail = EmailMessage()
        mail["From"] = "probe@mail-staging.moesegfault.dev"
        mail["To"] = "probe@example.net"
        mail["Subject"] = "AMAIL-CANARY-abc123"
        mail["Authentication-Results"] = (
            "mx.example.net; dkim=pass header.d=mail-staging.moesegfault.dev; "
            "spf=pass; dmarc=pass header.from=mail-staging.moesegfault.dev"
        )
        mail.set_content("Synthetic staging canary abc123")
        mail.add_alternative('<p>abc123</p><img src="cid:canary-pixel">', subtype="html")
        mail.get_payload(1).add_related(
            MODULE.PNG, maintype="image", subtype="png", cid="<canary-pixel>"
        )
        mail.add_attachment(
            MODULE.hashlib.sha256(nonce.encode()).digest(),
            maintype="application", subtype="octet-stream", filename="proof.bin",
        )
        self.assertTrue(MODULE.delivered_mime(mail.as_bytes(), "probe@example.net", nonce, "mx.example.net"))
        # A sender can insert a forged same-ID Authentication-Results field.
        # Its coexistence with the receiver's field must never be accepted.
        mail["Authentication-Results"] = (
            "mx.example.net; dkim=pass header.d=mail-staging.moesegfault.dev; "
            "spf=pass; dmarc=pass header.from=mail-staging.moesegfault.dev"
        )
        self.assertFalse(MODULE.delivered_mime(mail.as_bytes(), "probe@example.net", nonce, "mx.example.net"))

    def test_run_dir_is_fresh_leaf_inside_repository_temp(self) -> None:
        """The first hosted invocation creates its leaf; reuse and escape fail."""

        MODULE.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="outbound-test-", dir=MODULE.TEMP) as parent:
            leaf = Path(parent) / "outbound"
            self.assertEqual(MODULE.create_run_dir(str(leaf)), leaf.resolve())
            self.assertTrue(leaf.is_dir())
            with self.assertRaisesRegex(MODULE.ProbeFailure, "canary_run_dir_invalid"):
                MODULE.create_run_dir(str(leaf))
        with self.assertRaisesRegex(MODULE.ProbeFailure, "path_outside_repository_temp"):
            MODULE.create_run_dir(str(MODULE.TEMP.parent / "outside"))

    def test_d1_refuses_mutation_statement(self) -> None:
        """The canary's operator capability must not become a policy writer."""

        with self.assertRaisesRegex(MODULE.ProbeFailure, "canary_query_not_read_only"):
            MODULE.d1(values(), "UPDATE send_policy SET state='allowed'", [])


if __name__ == "__main__":
    unittest.main()
