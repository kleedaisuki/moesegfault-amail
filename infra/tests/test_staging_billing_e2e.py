"""Offline contract checks for the narrow staging browser extension; no network."""

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


FILE = Path(__file__).with_name("staging_billing_e2e.py")
SPEC = importlib.util.spec_from_file_location("staging_billing_e2e", FILE)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class BillingHarnessTests(unittest.TestCase):
    """Reject private/misrouted input before the owned browser can navigate."""

    def test_only_fixed_opaque_staging_authorization_path_is_accepted(self):
        """A URL containing credentials, query capabilities or a foreign host is invalid."""
        good = "https://subscribe-staging.moesegfault.dev/amail/authorize/abcdefghijklmnopqrstuvwxyz012345"
        self.assertEqual(probe.validate_url(good), good)
        for bad in [None, good + "?code=private", good + "#private", good.replace("staging", "production"),
                    good.replace("https://", "http://"), good.replace("https://", "https://user:secret@"),
                    "https://subscribe-staging.moesegfault.dev/amail/authorize/short"]:
            with self.subTest(value=bad), self.assertRaises(probe.BillingProbeError):
                probe.validate_url(bad)

    def test_cli_jsonl_requires_objects_and_bounded_response(self):
        """The two creation projections remain distinct; malformed output is not reflected."""
        self.assertEqual(probe.rows('{"idempotency_key":"fixture"}\n{"state":"pending"}\n'),
                         [{"idempotency_key": "fixture"}, {"state": "pending"}])
        for invalid in ["", "private body", "[]", "null", '"private"', "x" * 65537]:
            with self.assertRaises(probe.BillingProbeError) as error:
                probe.rows(invalid)
            self.assertEqual(str(error.exception), "billing_cli_response_invalid")

    def test_grant_recovery_requires_matching_active_unexpired_subscription(self):
        """Mail projection is irrelevant to the authoritative Billing grant check."""
        grant = {"product_id": "amail", "plan_id": "amail-lite", "status": "active", "current_period_end": 200}
        self.assertFalse(probe.needs_activation({"requires_activation": False, "subscription": grant}, "lite", 100))
        for changed in [{"product_id": "other"}, {"plan_id": "amail-plus"}, {"status": "expired"},
                        {"current_period_end": 100}, {"current_period_end": 99}, {"current_period_end": True}]:
            self.assertTrue(probe.needs_activation({"requires_activation": True, "subscription": grant | changed}, "lite", 100))
        self.assertTrue(probe.needs_activation({"requires_activation": True, "subscription": None}, "lite", 100))
        with self.assertRaises(probe.BillingProbeError):
            probe.needs_activation({"requires_activation": True, "subscription": grant}, "lite", 100)

    def run_recovery(self, mail_plan, existing_grant, code="", *, confirmed_metering=False):
        """Simulate only branch decisions around the real helper, never hosted acceptance."""
        state = {"plan": "free", "grant": existing_grant, "redemptions": 0, "codes_typed": 0, "statuses": 0,
                 "budgets": [], "flushed": False}

        class Browser:
            """Minimal UI observer records whether the helper attempts another redemption."""

            def __init__(self, _profile):
                pass

            def call(self, method, _params, **_kwargs):
                if method == "Runtime.evaluate":
                    subscription = ({"product_id": "amail", "plan_id": "amail-lite", "status": "active",
                                     "current_period_end": 4_000_000_000} if state["grant"] else None)
                    return {"result": {"value": {"requires_activation": not state["grant"], "subscription": subscription}}}
                return {}

            def evaluate(self, expression):
                if expression == "location.origin":
                    return probe.SUBSCRIBE
                if expression == "document.querySelector('#amail-plan').value":
                    return f"amail-{state['plan']}"
                return True

            def fill(self, selector, _value):
                if selector == "#activation-code":
                    state["codes_typed"] += 1
                if selector == "#amail-budget":
                    state["budgets"].append(_value)

            def click(self, selector):
                if selector == "#activation-code + button":
                    state["redemptions"] += 1
                    state["grant"] = True

            def wait_dom(self, _selector, **_kwargs):
                pass

            def close(self):
                pass

        def command(args, **kwargs):
            self.assertNotIn("STAGING_E2E_AMAIL_ACTIVATION_CODE", kwargs["env"])
            self.assertNotIn("STAGING_E2E_AMAIL_ACTIVATION_CODE", os.environ)
            if args[1:3] == ["billing", "status"]:
                state["statuses"] += 1
                plan = mail_plan if state["statuses"] == 1 else "lite"
                output = {"account": {"plan": plan, "currency": "USD", "overage_budget_micros": 0}, "payment_collection_available": False}
            elif args[1:3] == ["billing", "subscribe"]:
                state["plan"] = args[3]
                key = args[-1]
                output = {"session_id": key, "state": "pending",
                          "authorization_url": probe.SUBSCRIBE + "/amail/authorize/abcdefghijklmnopqrstuvwxyz012345"}
            elif args[1:3] == ["billing", "session"]:
                output = {"state": "cancelled" if state["plan"] == "free" else "completed"}
            else:
                if args[1:] == ["_telemetry-flush"]:
                    state["flushed"] = True
                output = {}
            return SimpleNamespace(returncode=0, stdout=json.dumps(output))

        connection = Mock()
        def journal(_sql):
            """Journal context discovery must finish before final telemetry submission."""
            self.assertFalse(state["flushed"])
            return [("0123456789abcdef0123456789abcdef",)]

        connection.execute.side_effect = journal
        identity = SimpleNamespace(Browser=Browser, load_credential=lambda _path: ("synthetic", "synthetic-password", "unused"),
                                   ProbeError=type("ProbeError", (Exception,), {}))
        mail = SimpleNamespace(cli_env=lambda _path: {})
        def meter(*_args, **kwargs):
            """The real metering flow must run before the parent submits its final batch."""
            self.assertFalse(state["flushed"])
            self.assertNotIn("STAGING_E2E_AMAIL_ACTIVATION_CODE", os.environ)
            self.assertIsInstance(kwargs["evidence_started_at_ms"], int)
            return {"trace_ids": ["fedcba9876543210fedcba9876543210"], "budget_restored_micros": 0}

        metering = SimpleNamespace(execute=Mock(side_effect=meter if confirmed_metering else
                                               AssertionError("unconfirmed metering must not run")))
        with patch.dict(os.environ, {"AMAIL_STAGING_BILLING_CONFIRM": probe.CONFIRMATION,
                                     "AMAIL_STAGING_BILLING_PLAN": "lite",
                                     "AMAIL_STAGING_BILLING_TRACE": "true",
                                     "AMAIL_STAGING_BILLING_METERING_CONFIRM":
                                         "RUN_STAGING_BILLING_METERING_V020" if confirmed_metering else "",
                                     "STAGING_E2E_AMAIL_ACTIVATION_CODE": code}, clear=True), \
                patch.dict("sys.modules", {"staging_identity_cdp": identity, "staging_mail_e2e": mail,
                                           "staging_billing_metering": metering}), \
                patch.object(probe.subprocess, "run", side_effect=command), \
                patch.object(probe.sqlite3, "connect", return_value=connection), patch("builtins.print"):
            result = probe.execute(Path("synthetic.exe"), Path("synthetic-home"), Path("synthetic-run"))
            if confirmed_metering:
                metering.execute.assert_called_once()
            else:
                metering.execute.assert_not_called()
            self.assertEqual(state["budgets"], ["0"])
        return state, result

    def test_confirmed_metering_runs_before_final_flush_and_unions_original_traces(self):
        """Optional metering adds its causal IDs without replacing the subscription IDs."""
        state, result = self.run_recovery("lite", True, confirmed_metering=True)
        self.assertTrue(state["flushed"])
        self.assertEqual(result["trace_ids"], ["0123456789abcdef0123456789abcdef",
                                               "fedcba9876543210fedcba9876543210"])
        self.assertEqual(result["metering"]["budget_restored_micros"], 0)

    def test_mail_free_billing_already_redeemed_resumes_without_code(self):
        """A redemption completed before lost approval must not consume a second capability."""
        state, result = self.run_recovery("free", True)
        self.assertEqual((state["codes_typed"], state["redemptions"]), (0, 0))
        self.assertEqual(result["grant_source"], "existing")

    def test_mail_lite_retest_ignores_stale_used_code(self):
        """An already projected Lite grant remains reusable without re-redeeming its old code."""
        state, result = self.run_recovery("lite", True, "synthetic-stale-capability")
        self.assertEqual((state["codes_typed"], state["redemptions"]), (0, 0))
        self.assertEqual(result["grant_source"], "existing")
        state, result = self.run_recovery("lite", True, "old")
        self.assertEqual((state["codes_typed"], state["redemptions"]), (0, 0))
        self.assertEqual(result["grant_source"], "existing")

    def test_first_activation_uses_one_code_once(self):
        """Only an actually missing grant permits one ordinary UI redemption."""
        state, result = self.run_recovery("free", False, "synthetic-fresh-capability")
        self.assertEqual((state["codes_typed"], state["redemptions"]), (1, 1))
        self.assertEqual(result["grant_source"], "redeemed")

    def test_missing_grant_without_code_stops_without_redemption(self):
        """Missing activation material never triggers issuance or a replacement key retry."""
        with self.assertRaises(probe.BillingProbeError) as error:
            self.run_recovery("free", False)
        self.assertEqual(str(error.exception), "billing_legitimate_activation_code_required")

    def test_conflicting_paid_plan_cannot_be_downgraded_by_the_probe(self):
        """A Plus baseline cannot be silently replaced with the requested Lite test plan."""
        with self.assertRaises(probe.BillingProbeError) as error:
            self.run_recovery("plus", True)
        self.assertEqual(str(error.exception), "billing_synthetic_account_plan_conflict")


if __name__ == "__main__":
    unittest.main()
