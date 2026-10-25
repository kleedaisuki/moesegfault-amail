"""The focused reuse fixture uses only the existing protected staging ingress."""
from __future__ import annotations

from email.message import EmailMessage
from email.policy import SMTP
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

ROOT: Path = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/tests"))
import staging_semantic_e2e as semantic


class PrivateIngressTests(unittest.TestCase):
    address: str = "semantic-0123456789abcdef@tmpaddr-staging.moesegfault.dev"
    secret: str = "synthetic-private-key-" + "a" * 32

    def message(self) -> EmailMessage:
        message: EmailMessage = EmailMessage()
        message["To"] = self.address
        message["From"] = "synthetic@example.invalid"
        message["Subject"] = "Synthetic reuse fixture"
        message.set_content("Synthetic harbor notification only.\n")
        return message

    def test_exact_origin_secret_envelope_and_bounded_typed_receipt(self) -> None:
        message: EmailMessage = self.message()
        ident: str = "12345678-1234-1234-1234-123456789abc"
        response: MagicMock = MagicMock(status=201)
        response.read.return_value = json.dumps({"id": ident,
            "request_id": "12345678-1234-1234-1234-123456789abd"}).encode()
        response.__enter__.return_value = response
        with patch.object(semantic.urllib.request, "build_opener") as builder:
            builder.return_value.open.return_value = response
            self.assertEqual(semantic.private_ingress_fixture(message, self.address, self.secret), ident)
            builder.assert_called_once_with(semantic.mail.RejectRedirect)
            request = builder.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, semantic.PRIVATE_INGRESS)
            self.assertEqual(request.get_method(), "POST")
            self.assertEqual(request.data, message.as_bytes(policy=SMTP))
            headers: dict[str, str] = {key.lower(): value for key, value in request.header_items()}
            self.assertEqual(headers["x-amail-ingress-secret"], self.secret)
            self.assertEqual(headers["x-amail-envelope-to"], self.address)
            self.assertEqual(headers["content-type"], "message/rfc822")
            response.read.assert_called_once_with(16_385)
            self.assertIsNone(semantic.mail.RejectRedirect().redirect_request(
                request, None, 307, "redirect", {}, "https://foreign.invalid/collect"))

    def test_redirect_http_error_and_invalid_success_are_not_retried_or_reflected(self) -> None:
        for status_code in (307, 308, 500):
            body: MagicMock = MagicMock()
            body.read.return_value = b"must-not-log synthetic@example.invalid secret"
            error: urllib.error.HTTPError = urllib.error.HTTPError(
                semantic.PRIVATE_INGRESS, status_code, "private provider prose", {}, body)
            with self.subTest(status=status_code), patch.object(semantic.urllib.request, "build_opener") as builder:
                builder.return_value.open.side_effect = error
                with self.assertRaises(semantic.mail.ProbeFailure) as raised:
                    semantic.private_ingress_fixture(self.message(), self.address, self.secret)
                self.assertEqual(str(raised.exception), f"semantic_fixture_ingress_http_{status_code}")
                builder.return_value.open.assert_called_once()
                body.read.assert_not_called()
        for raw in (b"not-json private provider prose", b"x" * 16_385,
                    b'{"id":"not-a-uuid","request_id":"not-a-uuid"}'):
            response: MagicMock = MagicMock(status=201)
            response.read.return_value = raw
            response.__enter__.return_value = response
            with self.subTest(raw_size=len(raw)), patch.object(semantic.urllib.request, "build_opener") as builder:
                builder.return_value.open.return_value = response
                with self.assertRaisesRegex(semantic.mail.ProbeFailure, "^semantic_fixture_ingress_receipt_invalid$"):
                    semantic.private_ingress_fixture(self.message(), self.address, self.secret)
                builder.return_value.open.assert_called_once()


if __name__ == "__main__":
    unittest.main()
