"""Mock-only contracts for the one-shot hosted B registration path."""

from __future__ import annotations

from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from contextlib import redirect_stdout
import importlib.util
from io import StringIO
import json
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

    @staticmethod
    def r2_page(keys: list[str], **extra: object) -> bytes:
        """Build only synthetic R2 REST envelopes without private MIME."""

        return json.dumps({"success": True, "result": [{"key": key} for key in keys],
                           **extra}).encode()

    @staticmethod
    def r2_key(number: int) -> str:
        """Produce ordered, well-formed synthetic Worker UUIDv4 keys."""

        return f"verification/{number:08x}-1234-4123-8123-{number:012x}.eml"

    def test_r2_keyset_accepts_empty_and_requires_followup_after_short_page(self) -> None:
        """Missing result_info is normal; only an explicit empty page terminates."""

        empty = self.r2_page([])
        with patch.object(MODULE, "request", return_value=empty) as get:
            self.assertEqual(MODULE.object_inventory("a" * 32, "private-token"), set())
        self.assertEqual(get.call_count, 1)
        self.assertIn("?prefix=verification/&per_page=100", get.call_args.args[1])
        first, second = self.r2_key(1), self.r2_key(2)
        pages = [
            self.r2_page([first], result_info={"is_truncated": False, "cursor": "ignore-me"}),
            self.r2_page([second], result_info={"cursor": "still-ignore"}),
            empty,
        ]
        with patch.object(MODULE, "request", side_effect=pages) as get:
            self.assertEqual(MODULE.object_inventory("a" * 32, "private-token"),
                             {first, second})
        self.assertEqual(get.call_count, 3)
        urls = [call.args[1] for call in get.call_args_list]
        self.assertNotIn("start_after=", urls[0])
        self.assertIn("start_after=verification%2F", urls[1])
        self.assertIn(first.rsplit("/", 1)[1], urls[1])
        self.assertIn(second.rsplit("/", 1)[1], urls[2])
        self.assertTrue(all("cursor=" not in url for url in urls))

    def test_r2_keyset_rejects_duplicate_order_shape_and_page_overlimit(self) -> None:
        """Fail closed on any response that cannot establish ordered coverage."""

        first, second = self.r2_key(1), self.r2_key(2)
        cases = (
            ([self.r2_page([], result_info={"is_truncated": True, "cursor": "more"})],
             "r2_empty_page_truncated"),
            ([self.r2_page([], result_info={"is_truncated": "true"})],
             "r2_result_info_invalid"),
            ([self.r2_page([], result_info=[])], "r2_result_info_invalid"),
            ([self.r2_page([first], result_info=None)], "r2_result_info_invalid"),
            ([self.r2_page([first, first])], "r2_duplicate_key"),
            ([self.r2_page([second, first])], "r2_key_order_invalid"),
            ([self.r2_page([first]), self.r2_page([first])], "r2_duplicate_key"),
            ([self.r2_page([second]), self.r2_page([first])], "r2_key_order_invalid"),
            ([json.dumps({"success": True, "result": {"cursor": "opaque"}}).encode()],
             "r2_result_invalid"),
            ([json.dumps({"success": True, "result": ["bad-entry"]}).encode()],
             "r2_object_entry_invalid"),
            ([self.r2_page(["verification/not-uuid.eml"])], "r2_object_key_invalid"),
            ([self.r2_page([self.r2_key(index) for index in range(101)])],
             "r2_page_size_invalid"),
        )
        for pages, expected in cases:
            with self.subTest(expected=expected), patch.object(MODULE, "request", side_effect=pages):
                with self.assertRaises(MODULE.ProvisionFailure) as caught:
                    MODULE.object_inventory("a" * 32, "private-token")
            self.assertEqual(str(caught.exception), expected)

    def test_r2_keyset_bounds_total_keys_and_pages(self) -> None:
        """Neither endless short pages nor >1000 objects may greenlight mutation."""

        over_limit = [self.r2_page([self.r2_key(index) for index in range(start, start + 100)])
                      for start in range(0, 1000, 100)]
        over_limit.append(self.r2_page([self.r2_key(1000)]))
        with patch.object(MODULE, "request", side_effect=over_limit):
            with self.assertRaises(MODULE.ProvisionFailure) as caught:
                MODULE.object_inventory("a" * 32, "private-token")
        self.assertEqual(str(caught.exception), "r2_inventory_too_large")
        no_end = [self.r2_page([self.r2_key(index)]) for index in range(20)]
        with patch.object(MODULE, "request", side_effect=no_end):
            with self.assertRaises(MODULE.ProvisionFailure) as caught:
                MODULE.object_inventory("a" * 32, "private-token")
        self.assertEqual(str(caught.exception), "r2_page_limit")

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

    def test_private_inbox_failure_labels_are_phase_specific_and_private(self) -> None:
        """Distinguish the checker phase without forwarding captured diagnostics."""

        cases = {
            b"R2 managed-domain read failed: HTTP0\n": "private_r2_managed_transport_failed",
            b"R2 managed-domain read failed: HTTP403\n": "private_r2_managed_read_failed",
            b"R2 managed public domain is enabled or unknown\n":
                "private_r2_managed_policy_failed",
            b"R2 custom-domain read failed: HTTP200\n": "private_r2_custom_read_failed",
            b"R2 custom domains are present or unknown\n": "private_r2_custom_policy_failed",
            b"R2 lifecycle read failed: HTTP0\n": "private_r2_lifecycle_transport_failed",
            b"R2 verification expiry rule is disabled or too long\n":
                "private_r2_lifecycle_policy_failed",
            b"Worker settings readback unavailable: HTTP403\n":
                "private_inbox_settings_read_failed",
            b"Worker bindings differ from reviewed staging configuration\n":
                "private_inbox_bindings_failed",
            b"staging test inbox config is not isolated\n": "private_inbox_source_invalid",
            b"provider private-body/token/address\n": "private_inbox_checker_unclassified",
            b"R2 lifecycle read failed: HTTP403\nprovider private-body":
                "private_inbox_checker_unclassified",
        }
        for raw, expected in cases.items():
            with self.subTest(expected=expected):
                label = MODULE.private_inbox_failure_label(raw)
            self.assertEqual(label, expected)
            self.assertRegex(label, r"\A[a-z][a-z0-9_]+\Z")
            self.assertNotIn("private-body", label)

    def test_private_inbox_checker_failure_stops_before_route_or_d1(self) -> None:
        """A failed private-inbox audit cannot continue toward B mutation."""

        stub = types.ModuleType("staging_identity_cdp")
        stub.decoded_credential = lambda value: None
        stub.route = lambda action=None, address=None: self.fail("route must not run")
        provider_env = {
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
            "CLOUDFLARE_API_TOKEN": "private-token",
            "CF_EMAIL_ROUTING_TOKEN": "private-route-token",
        }
        with patch.dict(sys.modules, {"staging_identity_cdp": stub}), \
                patch.dict(os.environ, provider_env, clear=True), \
                patch.object(MODULE.subprocess, "run", return_value=types.SimpleNamespace(
                    returncode=1, stderr=b"Worker settings readback unavailable: HTTP403\n")), \
                patch.object(MODULE, "identity_contacts", side_effect=AssertionError("D1 must not run")):
            with self.assertRaises(MODULE.ProvisionFailure) as caught:
                MODULE.inspect_state("b_username", "protected-password")
        self.assertEqual(str(caught.exception), "private_inbox_settings_read_failed")
        with patch.dict(sys.modules, {"staging_identity_cdp": stub}), \
                patch.dict(os.environ, provider_env, clear=True), \
                patch.object(MODULE.subprocess, "run", side_effect=MODULE.subprocess.TimeoutExpired(
                    "private-checker", 90)):
            with self.assertRaises(MODULE.ProvisionFailure) as caught:
                MODULE.inspect_state("b_username", "protected-password")
        self.assertEqual(str(caught.exception), "private_inbox_subprocess_failed")

    def test_read_only_permission_failures_identify_d1_or_r2_phase(self) -> None:
        """A denied preflight must identify the capability to repair, not leak replies."""

        stub = types.ModuleType("staging_identity_cdp")
        stub.decoded_credential = lambda value: None
        stub.route = lambda action=None, address=None: "absent"
        provider_env = {
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
            "CLOUDFLARE_API_TOKEN": "private-token",
            "CF_EMAIL_ROUTING_TOKEN": "private-route-token",
        }
        for failed_phase, expected in (("d1", "identity_d1_read_failed"),
                                       ("r2", "private_r2_list_failed")):
            d1 = MODULE.ProvisionFailure("cloudflare_request_failed") if failed_phase == "d1" else {}
            r2 = MODULE.ProvisionFailure("cloudflare_request_failed") if failed_phase == "r2" else set()
            with self.subTest(phase=failed_phase), \
                    patch.dict(sys.modules, {"staging_identity_cdp": stub}), \
                    patch.dict(os.environ, provider_env, clear=True), \
                    patch.object(MODULE.subprocess, "run", return_value=types.SimpleNamespace(returncode=0)), \
                    patch.object(MODULE, "identity_contacts", side_effect=d1 if isinstance(d1, Exception) else None,
                                 return_value=d1 if not isinstance(d1, Exception) else None), \
                    patch.object(MODULE, "object_inventory", side_effect=r2 if isinstance(r2, Exception) else None,
                                 return_value=r2 if not isinstance(r2, Exception) else None):
                with self.assertRaises(MODULE.ProvisionFailure) as caught:
                    MODULE.inspect_state("b_username", "protected-password")
            self.assertEqual(str(caught.exception), expected)

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
