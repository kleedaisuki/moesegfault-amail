"""Offline controlled-metering admission and real-ledger comparison contracts."""

import importlib.util
from itertools import count
import os
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch


FILE = Path(__file__).with_name("staging_billing_metering.py")
SPEC = importlib.util.spec_from_file_location("staging_billing_metering", FILE)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)
BILLING_SPEC = importlib.util.spec_from_file_location("metering_billing_fixture", FILE.with_name("staging_billing_e2e.py"))
billing = importlib.util.module_from_spec(BILLING_SPEC)
BILLING_SPEC.loader.exec_module(billing)


def account():
    """Return an independent empty Lite/zero-budget acceptance fixture."""
    return {"plan": "lite", "currency": "USD", "included_addresses": 3, "grandfathered_addresses": 0,
            "address_count": 0, "overage_budget_micros": 0, "period_start": 100,
            "storage_bytes": 0, "included_storage_bytes": 2_000_000_000, "outbound_reserved": 0, "accrued_micros": 0, "reserved_micros": 0,
            "period_end": int(time.time()) + 86400, "valid_until": int(time.time()) + 86400}


def event():
    """One actual-address-second liability fixture, not production usage seeding."""
    return {"event_id": "synthetic-event", "billing_owner_id": "a" * 64,
            "meter": "address_seconds", "currency": "USD", "quantity": 7, "amount_micros": 7,
            "occurred_at": int(time.time()), "period_start": 100,
            "period_end": int(time.time()) + 86400, "delivered_at": int(time.time()),
            "origin_traceparent": "00-0123456789abcdef0123456789abcdef-abcdef0123456789-01"}


def usage():
    """Authoritative usage totals must remain pending settlement, never paid."""
    return {"owner_id": "a" * 64, "currency": "USD", "period_start": 100, "amount_micros": 7, "events_count": 1,
            "overage_budget_micros": 0, "settlement_status": "pending_settlement"}


class MeteringTests(unittest.TestCase):
    """Keep mutations behind explicit consent and reject missing positive delivery evidence."""

    def test_every_confirmation_is_required_before_any_provider_or_browser_action(self):
        """No optional budget is granted by an omitted flag, Free plan or trace-disabled run."""
        valid = {"AMAIL_STAGING_BILLING_METERING_CONFIRM": probe.CONFIRMATION,
                 "AMAIL_STAGING_BILLING_CONFIRM": "RUN_STAGING_BILLING_V020",
                 "AMAIL_STAGING_BILLING_PLAN": "lite", "AMAIL_STAGING_BILLING_TRACE": "true"}
        for key, wrong in [("AMAIL_STAGING_BILLING_METERING_CONFIRM", ""),
                           ("AMAIL_STAGING_BILLING_METERING_CONFIRM", "wrong"),
                           ("AMAIL_STAGING_BILLING_CONFIRM", ""),
                           ("AMAIL_STAGING_BILLING_PLAN", "free"),
                           ("AMAIL_STAGING_BILLING_TRACE", "false")]:
            with patch.dict(os.environ, valid | {key: wrong}, clear=True), \
                    patch.object(probe, "d1_read") as read:
                with self.assertRaises(probe.MeteringError) as error:
                    probe.execute(Path("unused"), Path("unused"), Path("unused"))
                self.assertEqual(str(error.exception), "metering_confirmation_required")
                read.assert_not_called()

    def test_admission_requires_empty_lite_zero_budget_and_four_slots(self):
        """Existing allocations, grandfather rights or near expiry are not this fixture."""
        probe.preflight(account(), [], 194, 196)
        for changed in [{"plan": "free"}, {"currency": "CNY"}, {"included_addresses": 5}, {"grandfathered_addresses": 1},
                        {"address_count": 1}, {"overage_budget_micros": 1},
                        {"valid_until": int(time.time()) + 30}, {"storage_bytes": 2_000_000_001},
                        {"outbound_reserved": 1}, {"accrued_micros": 1}, {"reserved_micros": 1}]:
            with self.assertRaises(probe.MeteringError):
                probe.preflight(account() | changed, [], 194, 196)
        for owned, registered, provider in [([{}], 194, 196), ([], 195, 196), ([], 194, 197)]:
            with self.assertRaises(probe.MeteringError):
                probe.preflight(account(), owned, registered, provider)

    def test_sql_transport_refuses_mutations_before_credentials_or_network(self):
        """No arbitrary read/write query can be slipped into the provider adapter."""
        with patch.dict("sys.modules", {"acceptance_realm": SimpleNamespace(STAGING=SimpleNamespace()),
                                       "staging_trace_witness": SimpleNamespace(USER_AGENT="synthetic")}), \
                patch.object(probe, "read_json") as read:
            for sql in ["UPDATE resource_outbox SET delivered_at=1", "SELECT * FROM messages", "DELETE FROM addresses"]:
                with self.assertRaises(probe.MeteringError):
                    probe.d1_read(sql, [])
            read.assert_not_called()

    def test_delivered_pending_totals_prove_positive_small_liability(self):
        """Local event, delivered marker and Billing amount/count must agree."""
        result = probe.verify_delivery([event()], usage(), int(time.time()) - 10, 100)
        self.assertEqual(result["amount_micros"], 7)
        self.assertEqual(result["budget_restored_micros"], 0)
        self.assertFalse(result["payment_collection_verified"])
        self.assertNotIn("billing_owner_id", result)
        self.assertNotIn("event_id", result)
        for changed in [{"currency": "CNY"}, {"delivered_at": None}, {"amount_micros": 0}, {"amount_micros": 10_001},
                        {"quantity": 0}, {"period_start": 101}, {"origin_traceparent": None}]:
            with self.assertRaises(probe.MeteringError):
                probe.verify_delivery([event() | changed], usage(), int(time.time()) - 10, 100)
        for changed in [{"currency": "CNY"}, {"amount_micros": 8}, {"amount_micros": 7.0}, {"events_count": 2},
                        {"owner_id": "b" * 64}, {"overage_budget_micros": 500_000},
                        {"settlement_status": "paid"}]:
            with self.assertRaises(probe.MeteringError):
                probe.verify_delivery([event()], usage() | changed, int(time.time()) - 10, 100)

    def test_currency_partition_is_explicit_and_legacy_totals_are_immutable(self):
        """A USD charge cannot be accepted as CNY, or alter the old six-event ledger."""
        self.assertIn("currency='USD'", probe.EVENT_SQL)
        legacy = usage() | {"currency": "CNY", "amount_micros": 22, "events_count": 6}
        probe.verify_legacy_usage(legacy, "a" * 64, 100)
        for changed in [{"currency": "USD"}, {"amount_micros": 23}, {"events_count": 7},
                        {"owner_id": "b" * 64}, {"period_start": 101}, {"settlement_status": "paid"}]:
            with self.assertRaises(probe.MeteringError):
                probe.verify_legacy_usage(legacy | changed, "a" * 64, 100)
        requests = []
        with patch.dict("sys.modules", {"staging_trace_witness": SimpleNamespace(USER_AGENT="synthetic")}), \
                patch.dict(os.environ, {"BILLING_SERVICE_KEY": "synthetic"}), \
                patch.object(probe, "read_json", side_effect=lambda request: requests.append(request.full_url) or {}):
            probe.usage_read("a" * 64, 100)
            probe.usage_read("a" * 64, 100, "CNY")
            with self.assertRaises(probe.MeteringError):
                probe.usage_read("a" * 64, 100, "EUR")
        self.assertTrue(requests[0].endswith("period_start=100&currency=USD"))
        self.assertTrue(requests[1].endswith("period_start=100&currency=CNY"))

    def run_workflow(self, *, fail_action=False, fail_cleanup=False, fail_restore=False,
                     evidence_age_seconds=0):
        """Exercise the real helper with controlled transport/UI failures, not providers."""
        state = {"addresses": {}, "budget": 0, "budgets": [], "actions": [], "event_reads": 0}

        class Browser:
            """Record UI-selected caps while normal helper ordering remains in control."""

            def __init__(self, _path):
                pass

            def call(self, method, _params, **_kwargs):
                if method == "Runtime.evaluate":
                    return {"result": {"value": {"requires_activation": False, "subscription": {
                        "product_id": "amail", "plan_id": "amail-lite", "status": "active",
                        "current_period_end": int(time.time()) + 86400}}}}
                return {}

            def evaluate(self, expression):
                if expression == "location.origin":
                    return "https://subscribe-staging.moesegfault.dev"
                if expression == "document.querySelector('#amail-plan').value":
                    return "amail-lite"
                return True

            def fill(self, selector, value):
                if selector == "#amail-budget":
                    if value == "0" and fail_restore:
                        raise RuntimeError("synthetic restore failure")
                    state["budget"] = 500_000 if value == "0.50" else 0
                    state["budgets"].append(state["budget"])

            def click(self, _selector):
                pass

            def close(self):
                pass

        def cli(_binary, _environment, *args, **_kwargs):
            state["actions"].append(args[:2])
            if args[:2] == ("billing", "status"):
                return [{"account": account() | {"overage_budget_micros": state["budget"]}}]
            if args[:2] == ("billing", "manage"):
                return [{"state": "pending", "session_id": args[-1], "authorization_url":
                         "https://subscribe-staging.moesegfault.dev/amail/authorize/abcdefghijklmnopqrstuvwxyz012345"}]
            if args[:2] == ("billing", "session"):
                return [{"state": "completed"}]
            if args[:2] == ("address", "list"):
                return list(state["addresses"].values())
            if args[:2] == ("address", "add"):
                self.assertEqual(state["budget"], 500_000)
                address = args[2] + "@mail-staging.moesegfault.dev"
                state["addresses"][address] = {"address": address, "state": "active"}
                if fail_action and len(state["addresses"]) == 2:
                    raise RuntimeError("synthetic lost creation ACK")
                return [state["addresses"][address]]
            if args[:2] == ("address", "delete"):
                if fail_cleanup:
                    raise RuntimeError("synthetic retirement failure")
                del state["addresses"][args[2]]
                return []
            return []

        def read(sql, _params):
            if sql == probe.CAPACITY_SQL:
                return [{"n": 0}]
            if sql == probe.OWNER_SQL:
                return [{"owner_iss": "https://identity-staging.moesegfault.dev", "owner_sub": "synthetic", "n": 4}]
            self.assertEqual(state["addresses"], {})
            self.assertEqual(state["budget"], 0)
            state["event_reads"] += 1
            return [event()]

        identity = SimpleNamespace(Browser=Browser, load_credential=lambda _path: ("synthetic", "synthetic-password", "unused"),
                                   ProbeError=type("ProbeError", (Exception,), {}))
        mail = SimpleNamespace(cli_env=lambda _path: {}, amail=cli, cf_rules=lambda *_args: [])
        with patch.dict(os.environ, {"AMAIL_STAGING_BILLING_METERING_CONFIRM": probe.CONFIRMATION,
                                     "AMAIL_STAGING_BILLING_CONFIRM": "RUN_STAGING_BILLING_V020",
                                     "AMAIL_STAGING_BILLING_PLAN": "lite", "AMAIL_STAGING_BILLING_TRACE": "true",
                                     "BILLING_SERVICE_KEY": "synthetic"}, clear=True), \
                patch.dict("sys.modules", {"staging_identity_cdp": identity, "staging_mail_e2e": mail,
                                           "staging_billing_e2e": billing}), \
                patch.object(probe, "d1_read", side_effect=read), \
                patch.object(probe, "usage_read", side_effect=lambda _owner, _period, currency="USD":
                    usage() if currency == "USD" else usage() | {"currency": "CNY", "amount_micros": 22, "events_count": 6}), \
                patch.object(probe.time, "sleep"), \
                patch.object(probe.time, "monotonic", side_effect=count()), patch("builtins.print"):
            try:
                result = probe.execute(Path("synthetic.exe"), Path("home"), Path("run"),
                                       evidence_started_at_ms=int((time.time() - evidence_age_seconds) * 1000))
            except probe.MeteringError as error:
                result = str(error)
        return state, result

    def test_workflow_simulation_cleans_four_addresses_and_restores_budget_before_wait(self):
        """The normal flow closes stock and consent before any delivery polling."""
        state, result = self.run_workflow()
        self.assertEqual(state["budgets"], [500_000, 0])
        self.assertEqual(state["addresses"], {})
        self.assertEqual(state["actions"].count(("address", "add")), 4)
        self.assertEqual(state["actions"].count(("address", "delete")), 4)
        self.assertEqual(result["addresses_created_and_retired"], 4)


    def test_lost_creation_ack_still_retires_task_owned_addresses_and_restores_zero(self):
        """A partial creation failure is not permission to create replacement addresses."""
        state, result = self.run_workflow(fail_action=True)
        self.assertEqual(result, "metering_cli_failed")
        self.assertEqual(state["addresses"], {})
        self.assertEqual(state["budget"], 0)
        self.assertEqual(state["actions"].count(("address", "add")), 2)
        self.assertEqual(state["actions"].count(("address", "delete")), 2)
        self.assertEqual(state["event_reads"], 0)

    def test_delivery_stops_before_network_and_parent_flush_exhaust_evidence_window(self):
        """A late arrival still closes stock/consent but does not start another read."""
        state, result = self.run_workflow(evidence_age_seconds=750)
        self.assertEqual(result, "metering_delivery_timeout")
        self.assertEqual(state["addresses"], {})
        self.assertEqual(state["budget"], 0)
        self.assertEqual(state["event_reads"], 0)

    def test_cleanup_and_restore_failures_cannot_be_reported_as_success(self):
        """Both independent recovery failures remain visible through fixed safe labels."""
        for cleanup, restore, expected in [
                (True, False, "metering_cleanup_failed"),
                (False, True, "metering_restore_failed"),
                (True, True, "metering_cleanup_and_restore_failed")]:
            state, result = self.run_workflow(fail_cleanup=cleanup, fail_restore=restore)
            self.assertEqual(result, expected)
            self.assertEqual(state["event_reads"], 0)
            if not restore:
                self.assertEqual(state["budget"], 0)
            if not cleanup:
                self.assertEqual(state["addresses"], {})


if __name__ == "__main__":
    unittest.main()
