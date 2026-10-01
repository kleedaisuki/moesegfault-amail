"""Mock-only realm and credential isolation contracts; no provider, CLI or browser."""

from dataclasses import FrozenInstanceError, replace
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from acceptance_realm import AcceptanceRealm, STAGING

if "websocket" not in sys.modules:
    stub = types.ModuleType("websocket")
    stub.WebSocketException = type("WebSocketException", (Exception,), {})
    stub.create_connection = Mock()
    sys.modules["websocket"] = stub
import staging_identity_cdp as identity
import staging_mail_e2e as mail


def production() -> AcceptanceRealm:
    """Build synthetic production coordinates, never actual provider resources."""
    return AcceptanceRealm(
        name="production", domain="mail.moesegfault.dev", mail_api="https://mail.moesegfault.dev",
        issuer="https://identity.moesegfault.dev", login_origin="https://login.moesegfault.dev",
        account_origin="https://account.moesegfault.dev", client_id="amail-cli",
        ingress="amail-inbound", mail_database_id="00000000-0000-0000-0000-000000000001",
        sending_tag="0" * 32, sender="probe@mail.moesegfault.dev",
    )


class RealmContracts(unittest.TestCase):
    """Preserve staging defaults while forbidding production coordinate fallbacks."""

    def test_coordinates_are_immutable(self) -> None:
        """A selected realm cannot change underneath a running acceptance session."""
        with self.assertRaises(FrozenInstanceError):
            production().domain = "foreign.example"

    def test_production_public_coordinates_are_exactly_pinned(self) -> None:
        """Valid HTTPS syntax is not authorization to send credentials to another host."""
        for name, value in {
            "issuer": "https://identity.foreign.example", "login_origin": "https://login.foreign.example",
            "account_origin": "https://account.foreign.example", "client_id": "foreign-cli",
            "ingress": "foreign-inbound", "sender": "other@mail.moesegfault.dev",
        }.items():
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "^production_coordinate_not_pinned$"):
                replace(production(), **{name: value})
        with self.assertRaisesRegex(ValueError, "^production_coordinate_not_pinned$"):
            replace(production(), domain="mail.foreign.example", mail_api="https://mail.foreign.example",
                    sender="probe@mail.foreign.example")

    def test_production_resources_cannot_reuse_staging(self) -> None:
        """D1 and sending registrations are explicit, distinct realm capabilities."""
        for name in ("mail_database_id", "sending_tag"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "^production_staging_coordinate_forbidden$"):
                replace(production(), **{name: getattr(STAGING, name)})

    def test_malformed_coordinates_fail_closed(self) -> None:
        """Wrong types, ports, userinfo and non-origin URLs are rejected before IO."""
        for name, value in (("login_origin", None), ("issuer", "https://identity.moesegfault.dev:443"),
                            ("issuer", "https://user@identity.moesegfault.dev"),
                            ("account_origin", "https://account.moesegfault.dev/path"),
                            ("mail_database_id", "not-a-uuid")):
            with self.subTest(name=name), self.assertRaises(ValueError):
                replace(production(), **{name: value})

    def test_cli_environment_preserves_default_and_filters_inherited_secrets(self) -> None:
        """The production adapter changes only explicit coordinates, not credential inheritance."""
        with patch.dict(os.environ, {"PATH": "safe", "CF_EMAIL_ROUTING_TOKEN": "secret",
                                    "AMAIL_ISSUER": "https://foreign.example"}, clear=True):
            default = mail.cli_env(Path(".temp/mock-home"))
            explicit = mail.cli_env(Path(".temp/mock-home"), production())
        self.assertEqual(default, STAGING.cli_coordinates(Path(".temp/mock-home")) | {"PATH": "safe"})
        self.assertEqual(explicit["AMAIL_ISSUER"], production().issuer)
        self.assertEqual(explicit["AMAIL_TELEMETRY"], "off")
        self.assertNotIn("CF_EMAIL_ROUTING_TOKEN", explicit)

    def test_native_authorization_is_bound_to_realm(self) -> None:
        """A valid staging PKCE request cannot authorize a production session."""
        realm = production()
        query = {"client_id": realm.client_id, "response_type": "code", "code_challenge_method": "S256",
                 "state": "a" * 43, "nonce": "b" * 43, "code_challenge": "c" * 43,
                 "scope": "openid profile offline_access", "redirect_uri": "http://127.0.0.1:49152/callback"}
        url = realm.issuer + "/oauth/authorize?" + urlencode(query)
        self.assertTrue(identity.valid_authorization_url(url, realm=realm))
        self.assertFalse(identity.valid_authorization_url(url))
        self.assertFalse(identity.valid_authorization_url(url.replace(realm.issuer, STAGING.issuer), realm=realm))

    def test_production_never_loads_staging_credentials(self) -> None:
        """Missing or malformed explicit credentials fail before any browser, path or CLI IO."""
        with patch.object(identity, "load_credential") as load, patch.object(identity, "Browser") as browser:
            for credentials, expected in ((None, None), (None, "synthetic@example.invalid")):
                with self.subTest(credentials=credentials, expected=expected), self.assertRaisesRegex(
                        identity.ProbeError, "^production_explicit_credentials_required$"):
                    identity.native_login(Path(".temp/mock"), Path("amail"), expected,
                                          realm=production(), credentials=credentials)
            for credentials in ((None, "x" * 20, "synthetic@example.invalid"), ("user", None, "a@b"),
                                ("user", "x" * 20), ["user", "x" * 20, "a@b"]):
                with self.subTest(credentials=credentials), self.assertRaisesRegex(
                        identity.ProbeError, "^native_credential_invalid$"):
                    identity.native_login(Path(".temp/mock"), Path("amail"), "synthetic@example.invalid",
                                          realm=production(), credentials=credentials)
        load.assert_not_called()
        browser.assert_not_called()

    def test_browser_refuses_other_realm_before_typing(self) -> None:
        """Production login typing remains guarded even when a redirect reaches staging."""
        browser = object.__new__(identity.Browser)
        browser.realm = production()
        browser.evaluate = Mock(return_value=STAGING.login_origin)
        with self.assertRaisesRegex(identity.ProbeError, "^first_party_origin_mismatch$"):
            browser.require_login_origin()
        browser.evaluate.return_value = production().login_origin
        browser.require_login_origin()

    def test_cleanup_verification_propagates_realm_to_receipt_and_archive(self) -> None:
        """Cleanup must verify the production sender, not silently use staging defaults."""
        realm = production()
        row = {"metadata": {}}
        with patch.object(mail, "amail", return_value=[row]), patch.object(mail, "verify_fixture") as fixture, \
                patch.object(mail, "safe_zip"), patch.object(mail, "verify_archive") as archive, \
                patch.object(mail.tempfile, "TemporaryDirectory") as directory:
            directory.return_value.__enter__.return_value = ".temp/mock-cleanup"
            mail.cleanup_verify(Path("amail"), {}, "alias@" + realm.domain,
                                {"id": {"subject": "subject"}}, {"subject": {}}, realm=realm)
        self.assertIs(fixture.call_args.kwargs["realm"], realm)
        self.assertIs(archive.call_args.kwargs["realm"], realm)

    def test_cleanup_messages_passes_explicit_realm(self) -> None:
        """An empty inventory still verifies against the exact selected realm."""
        realm = production()
        with patch.object(mail, "cleanup_inventory", return_value={}), patch.object(mail, "cleanup_verify") as verify:
            mail.cleanup_messages(Path("amail"), {}, "alias@" + realm.domain, {"one": {}, "two": {}},
                                  True, realm=realm)
        self.assertIs(verify.call_args.kwargs["realm"], realm)

    def test_cleanup_run_passes_explicit_realm(self) -> None:
        """Alias retirement, message cleanup and D1 reconciliation use the same realm."""
        realm = production()
        with patch.object(mail, "amail", return_value=[]), patch.object(mail, "cf_rules", return_value=[]), \
                patch.object(mail, "route_for", return_value=[]), \
                patch.object(mail, "row_snapshot", return_value=("row_absent", "absent", "absent")), \
                patch.object(mail, "cleanup_messages") as cleanup, patch("builtins.print"):
            mail.cleanup_run(Path("amail"), {}, "zone", "token", "alias@" + realm.domain, "nonce", realm=realm)
        self.assertIs(cleanup.call_args.kwargs["realm"], realm)


if __name__ == "__main__":
    unittest.main()
