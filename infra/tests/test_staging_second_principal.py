"""Mock-only contracts for the one-shot hosted B registration path."""

from __future__ import annotations

from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from contextlib import redirect_stdout
import importlib.util
from io import StringIO
import os
from pathlib import Path
import re
import sys
import types
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "staging_second_principal", Path(__file__).with_name("staging_second_principal.py")
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SecondPrincipalTests(unittest.TestCase):
    """Protect the private OTP boundary and non-repeatable registration gate."""

    def test_one_vetted_mime_code(self) -> None:
        """Require exact Identity sender, recipient, fresh date and one text code."""

        message = EmailMessage()
        message["From"] = "moeSegFault Identity <identity@moesegfault.dev>"
        message["To"] = MODULE.ADDRESS
        message["Date"] = format_datetime(datetime.now(timezone.utc))
        message["Subject"] = "moeSegFault 邮箱验证 / Email verification"
        message.set_content(
            "moeSegFault 邮箱验证 / Email verification\n"
            "验证码 / Verification code: 01234567\n"
            f"收件地址 / Address: {MODULE.ADDRESS}\n"
        )
        self.assertEqual(MODULE.verification_code(message.as_bytes()), "01234567")
        message.replace_header("To", MODULE.FIRST)
        with self.assertRaises(MODULE.ProvisionFailure):
            MODULE.verification_code(message.as_bytes())

    def test_contact_query_uses_final_schema_and_no_identifier_output(self) -> None:
        """Read the final Identity table, not the migration's staging table."""

        def fake_request(method, path, token, data, limit=65_536):
            self.assertIn("FROM identifiers i", data.decode())
            self.assertNotIn("identifiers_v3", data.decode())
            return (b'{"success":true,"result":[{"success":true,"results":['
                    b'{"contact":"amail-e2e@moesegfault.dev",'
                    b'"state":"verified","principal":"private-a",'
                    b'"subject":"pairwise-a","username":"amail_e2e_a"}]}]}')

        with patch.object(MODULE, "request", side_effect=fake_request):
            value = MODULE.identity_contacts("a" * 32, "secret")
        self.assertEqual(value[MODULE.FIRST][2], "verified")
        self.assertEqual(value[MODULE.FIRST][3], "amail_e2e_a")

    def test_workflow_is_manual_and_uses_repository_secret_names(self) -> None:
        """No push path may provision a principal or embed B credentials."""

        workflow = (MODULE.ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = workflow.split("  staging-second-principal:\n", 1)[1].split(
            "\n  staging-semantic-query-only:", 1
        )[0]
        self.assertIn("github.event_name == 'workflow_dispatch'", job)
        self.assertIn("inputs.target == 'staging-second-principal'", job)
        self.assertIn("environment: staging", job)
        self.assertIn("secrets.STAGING_E2E_B_USERNAME", job)
        self.assertIn("secrets.STAGING_E2E_B_PASSWORD", job)
        self.assertIn("RUN_STAGING_SECOND_PRINCIPAL_PROVISION", job)
        self.assertIn("RUN_STAGING_SECOND_PRINCIPAL_RECOVER", job)
        self.assertIn("staging-second-principal-recover", job)
        self.assertNotIn("generate_credential", job)

    def test_read_only_workflow_has_no_registration_or_cli_build(self) -> None:
        """The permission discriminator must stop before any mutation."""

        workflow = (MODULE.ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        job = workflow.split("  staging-second-principal-preflight:\n", 1)[1].split(
            "\n  staging-second-principal:", 1
        )[0]
        self.assertIn("github.event_name == 'workflow_dispatch'", job)
        self.assertIn("READ_STAGING_SECOND_PRINCIPAL_PREFLIGHT", job)
        self.assertIn("AMAIL_SECOND_PRINCIPAL_MODE: preflight", job)
        self.assertIn("environment: staging", job)
        self.assertNotIn("cargo build", job)
        self.assertNotIn("--apply", job)
        self.assertNotIn("--remove", job)

    def test_preflight_classifies_only_fixed_contact_states(self) -> None:
        """Keep usernames, principal IDs and mail contacts out of output."""

        a = ("principal-a", "subject-a", "verified", "a_username")
        self.assertEqual(MODULE.classify_contact({MODULE.FIRST: a}, "b_username"), "absent")
        self.assertEqual(MODULE.classify_contact({
            MODULE.FIRST: a,
            MODULE.ADDRESS: ("principal-b", "", "pending", "b_username"),
        }, "b_username"), "pending_same_account")
        self.assertEqual(MODULE.classify_contact({
            MODULE.FIRST: a,
            MODULE.ADDRESS: ("principal-b", "subject-b", "verified", "b_username"),
        }, "b_username"), "verified_same_account")
        for b in (("principal-a", "", "pending", "b_username"),
                  ("principal-b", "", "pending", "other_user")):
            with self.assertRaises(MODULE.ProvisionFailure):
                MODULE.classify_contact({MODULE.FIRST: a, MODULE.ADDRESS: b}, "b_username")

    def test_preflight_emits_only_fixed_label_and_does_not_mutate(self) -> None:
        """Even with protected credentials, this path never invokes execute()."""

        contacts = {MODULE.FIRST: ("principal-a", "subject-a", "verified", "a_username")}
        env = {
            "AMAIL_SECOND_PRINCIPAL_MODE": "preflight",
            "AMAIL_SECOND_PRINCIPAL_CONFIRM": "READ_STAGING_SECOND_PRINCIPAL_PREFLIGHT",
            "STAGING_E2E_B_USERNAME": "b_username",
            "STAGING_E2E_B_PASSWORD": "private-password-not-logged",
        }
        with patch.dict(os.environ, env, clear=True), \
                patch.object(MODULE, "inspect_state", return_value=("account", "token", contacts, set())), \
                patch.object(MODULE, "execute", side_effect=AssertionError("must not mutate")), \
                redirect_stdout(StringIO()) as output:
            self.assertEqual(MODULE.main(), 0)
        self.assertEqual(output.getvalue().strip(), "staging_second_principal_preflight_absent")

    def test_inspection_calls_only_audits_and_read_only_config(self) -> None:
        """A source-level route audit cannot silently become --apply."""

        stub = types.ModuleType("staging_identity_cdp")
        stub.decoded_credential = lambda value: (value["username"], value["password"], value["address"])
        audited: list[str] = []

        def route(action=None, address=None):
            self.assertIsNone(action)
            audited.append(address)
            return "absent"

        stub.route = route
        provider_env = {
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
            "CLOUDFLARE_API_TOKEN": "private-token",
            "CF_EMAIL_ROUTING_TOKEN": "private-route-token",
        }
        with patch.dict(sys.modules, {"staging_identity_cdp": stub}), \
                patch.dict(os.environ, provider_env, clear=True), \
                patch.object(MODULE.subprocess, "run", return_value=types.SimpleNamespace(returncode=0)) as run, \
                patch.object(MODULE, "identity_contacts", return_value={}), \
                patch.object(MODULE, "object_inventory", return_value=set()):
            MODULE.inspect_state("b_username", "protected-password")
        self.assertEqual(audited, [MODULE.ADDRESS, MODULE.FIRST])
        args = run.call_args.args[0]
        self.assertEqual(args[-2:], ["--live", "--deployed"])
        self.assertTrue(str(args[1]).endswith("check_config.py"))

    def test_recovery_refuses_absent_verified_and_wrong_owner(self) -> None:
        """Recovery must never register a replacement for an ambiguous B."""

        a = ("principal-a", "subject-a", "verified", "a_username")
        pending = ("principal-b", "", "pending", "b_username")
        for contacts in (
            {MODULE.FIRST: a},
            {MODULE.FIRST: a, MODULE.ADDRESS: ("principal-b", "subject-b", "verified", "b_username")},
            {MODULE.FIRST: a, MODULE.ADDRESS: ("principal-b", "", "pending", "other_user")},
            {MODULE.FIRST: a, MODULE.ADDRESS: ("principal-a", "", "pending", "b_username")},
        ):
            with self.subTest(contacts=contacts), self.assertRaises(MODULE.ProvisionFailure):
                MODULE.preflight_contacts("recover", contacts, "b_username")
        MODULE.preflight_contacts("recover", {MODULE.FIRST: a, MODULE.ADDRESS: pending},
                                  "b_username")
        with self.assertRaises(MODULE.ProvisionFailure):
            MODULE.preflight_contacts("provision", {MODULE.FIRST: a, MODULE.ADDRESS: pending},
                                      "b_username")

    def test_recovery_uses_exact_account_row_and_closes_route_before_code(self) -> None:
        """The browser path is first-party and has no registration POST."""

        events: list[str] = []

        class FakeBrowser:
            """Record only control operations, never credentials or the OTP."""

            def __init__(self, profile):
                events.append("browser_open")

            def navigate(self, url):
                events.append("navigate_login" if url.endswith("/login") else "navigate_account")

            def wait_dom(self, selector, timeout=45):
                events.append("wait_dom")

            def require_login_origin(self):
                events.append("login_origin")

            def require_account_origin(self):
                events.append("account_origin")

            def fill(self, selector, value):
                events.append("fill_code" if 'name="code"' in selector else "fill_credential")

            def click(self, selector):
                events.append("complete" if "verification-form" in selector else "login")

            def evaluate(self, expression):
                self_test.assertIn(MODULE.ADDRESS, expression)
                self_test.assertIn("r.length!==1", expression)
                events.append("exact_contact_selected")
                return True

            def response(self, predicate, timeout=45):
                count = events.count("response")
                events.append("response")
                return ((200, "login") if count == 0 else
                        (201, "challenge") if count == 1 else (200, "completion"))

            def response_body(self, request_id):
                return {"verification_state": "verified"}

            def close(self):
                events.append("browser_close")

        self_test = self
        stub = types.ModuleType("staging_identity_cdp")
        stub.ACCOUNT_ORIGIN = "https://account-staging.moesegfault.dev"
        stub.LOGIN_ORIGIN = "https://login-staging.moesegfault.dev"
        stub.PASSWORD_AUTH = "/v1/password/authentications"
        stub.VERIFICATION_DONE = re.compile("/v1/me/contacts/.*/completion")
        stub.VERIFICATION_START = re.compile("/v1/me/contacts/.*/verification-transactions")
        stub.Browser = FakeBrowser

        def route(action=None, address=None):
            events.append("route_close" if action == "--remove" else "route_audit")
            return "removed" if action == "--remove" else (
                "absent" if "route_close" in events else "enabled"
            )

        stub.route = route
        with patch.dict(sys.modules, {"staging_identity_cdp": stub}), \
                patch.object(MODULE.time, "sleep"), \
                patch.object(MODULE, "guarded_code", return_value="01234567"):
            MODULE.recover_contact(Path(".temp/recovery-mock"), "b_username", "secret",
                                   "a" * 32, "token", set())
        self.assertLess(events.index("route_close"), events.index("fill_code"))
        self.assertLess(events.index("fill_code"), events.index("complete"))
        self.assertEqual(events[-1], "browser_close")


if __name__ == "__main__":
    unittest.main()
