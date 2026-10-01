"""Credential-free hosted source/topology/rollback contracts for the Mail split."""
from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import check_mail_maintenance as maintenance
import ensure_trace_queues as queues
import mail_split_transition as state

VERSION = "11111111-1111-4111-8111-111111111111"
QUEUE = "a" * 32


def queue_detail(suffix: str) -> dict:
    """Use the complete existing provider-shape ownership and retention contract."""
    return {"queue_id": QUEUE, "queue_name": "amail-trace-events" + suffix,
            "settings": {"message_retention_period": 86400, "delivery_delay": 0, "delivery_paused": False},
            "producers_total_count": 2, "consumers_total_count": 1,
            "producers": [{"type": "worker", "script": "amail-mail" + suffix},
                          {"type": "worker", "script": "amail-mail-maintenance" + suffix}],
            "consumers": [{"type": "worker", "script_name": "amail-trace-sink" + suffix,
                           "dead_letter_queue": "amail-trace-dlq" + suffix,
                           "settings": {"batch_size": 10, "max_wait_time_ms": 1000, "max_retries": 3,
                                        "retry_delay": 30, "max_concurrency": 2}}]}


class ScheduledOnlySourceTests(unittest.TestCase):
    """Tracked paused truth, exact capability ownership and closed migration edges."""

    def test_explicit_realm_configs_and_no_inbound_callers(self):
        """API forever empty; maintenance source initial cadence is paused in each realm."""
        for realm in maintenance.REALMS:
            self.assertEqual(maintenance.api_config(realm)["triggers"], {"crons": []})
            selected = maintenance.maintenance_config(realm)
            self.assertEqual(selected["triggers"], {"crons": []})
            expected = maintenance.expected_bindings(realm, QUEUE)
            self.assertEqual({name for name, (kind, _) in expected.items() if kind == "secret_text"}, set(maintenance.SECRETS))
            self.assertEqual(expected["VERSION_METADATA"], ("version_metadata", None))
            for name in ("EMAIL", "OFFICIAL_EMAIL", "INGRESS_SECRET", "IDENTITY_ISSUER", "MAIL_DOMAIN", "ROLE_MONITOR"):
                self.assertNotIn(name, expected)
            with self.assertRaises(ValueError):
                maintenance.maintenance_config(realm, active=True)
        maintenance.reject_inbound_bindings()

    def test_no_omitted_or_dual_trigger_acceptance(self):
        """Empty means explicitly complete, never absent/null or hidden extra schedules."""
        self.assertTrue(maintenance.schedules_match({"schedules": []}))
        self.assertTrue(maintenance.schedules_match({"schedules": [{"cron": maintenance.CADENCE[0]}]}, maintenance.CADENCE))
        for value in ({}, {"schedules": None}, {"schedules": [] , "cursor": "hidden"},
                      {"schedules": [{"cron": maintenance.CADENCE[0]}]},
                      {"schedules": [{"cron": maintenance.CADENCE[0]}] * 2},
                      {"schedules": [{"cron": maintenance.CADENCE[0], "unknown": True}]}):
            self.assertFalse(maintenance.schedules_match(value))

    def test_immutable_handler_no_named_entrypoint_or_inherited_fetch(self):
        """Binding match alone cannot certify a scheduled-only application surface."""
        good = {"id": VERSION, "resources": {"script": {"handlers": ["scheduled"], "named_handlers": []}}}
        self.assertTrue(maintenance.entry_surface_match(good, VERSION, "scheduled"))
        for script in ({"handlers": ["scheduled", "fetch"]}, {"handlers": ["fetch"]},
                       {"handlers": ["scheduled"], "named_handlers": ["Admin"]}, {}):
            self.assertFalse(maintenance.entry_surface_match({"id": VERSION, "resources": {"script": script}}, VERSION, "scheduled"))
        self.assertFalse(maintenance.entry_surface_match(good, "other", "scheduled"))

    def test_exact_two_producer_graph_not_arbitrary_additional_producers(self):
        """Keep API producer, same realm, sink, retention, counts and complete inventory."""
        for suffix in ("", "-staging"):
            good = queue_detail(suffix)
            args = (good["queue_name"], QUEUE, suffix, "readback", "api-scheduled")
            queues.validate_detail(good, *args)
            wrong_sets = (["amail-mail" + suffix], ["amail-mail-maintenance" + suffix],
                          ["amail-mail" + suffix, "amail-role-monitor" + suffix],
                          ["amail-mail" + suffix, "amail-mail-maintenance" + ("" if suffix else "-staging")],
                          ["amail-mail" + suffix] * 2,
                          ["amail-mail" + suffix, "amail-mail-maintenance" + suffix, "unknown"])
            for names in wrong_sets:
                changed = deepcopy(good)
                changed["producers"] = [{"type": "worker", "script": name} for name in names]
                changed["producers_total_count"] = len(names)
                with self.subTest(names=names), self.assertRaises(ValueError):
                    queues.validate_detail(changed, *args)
            changed = deepcopy(good)
            changed["producers_total_count"] = 1
            with self.assertRaises(ValueError):
                queues.validate_detail(changed, *args)
            for phase in ("queues", "recover"):
                with self.assertRaisesRegex(ValueError, "topology_unreviewed"):
                    queues.validate_detail(good, good["queue_name"], QUEUE, suffix, phase, "api-scheduled")
            with self.assertRaises(ValueError):
                queues.validate_detail(good, good["queue_name"], QUEUE, suffix, "readback")

    def test_split_write_never_provisions_queue(self):
        """Split ownership is readback-only even if resources are missing."""
        with patch.object(queues, "inventory") as read, patch.object(queues, "request") as write:
            for phase in ("queues", "recover"):
                with self.assertRaises(ValueError):
                    queues.reconcile("a", "token", "production", phase, "api-scheduled")
        read.assert_not_called()
        write.assert_not_called()

    def test_normal_rollback_cannot_restore_old_schedule_or_legacy_state(self):
        """Only paused/active normal replacement; transition plans never restore API Cron."""
        for realm in maintenance.REALMS:
            for selected in (state.State.PAUSED, state.State.ACTIVE):
                for owner in ("api", "sink", "maintenance"):
                    plan = state.normal_replacement(realm, selected.value, owner)
                    self.assertEqual(plan.successor, selected)
                    self.assertIsNone(plan.script)
                    self.assertIsNone(plan.crons)
                    self.assertEqual(plan.topology, "api-scheduled")
            for selected in (state.State.LEGACY_PINNED, state.State.LEGACY_RECOVERY, state.State.PREPARED,
                             state.State.OLD_DRAINING, state.State.NEW_DRAINING):
                with self.assertRaises(ValueError):
                    state.normal_replacement(realm, selected.value, "api")
            pause = state.transition(realm, state.State.ACTIVE, "pause")
            self.assertEqual(pause.crons, ())
            self.assertEqual(pause.successor, state.State.NEW_DRAINING)
            with self.assertRaises(ValueError):
                state.transition(realm, state.State.NEW_DRAINING, "activate", admission="production-first-fenced-bootstrap")
            with self.assertRaises(ValueError):
                state.transition(realm, state.State.PAUSED, "activate")


if __name__ == "__main__":
    unittest.main()
