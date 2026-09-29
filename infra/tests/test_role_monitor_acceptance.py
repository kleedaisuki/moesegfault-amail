"""Offline contract tests for the private staging role-monitor SMTP harness."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("role_acceptance", ROOT / "workers/role-monitor/acceptance.py")
assert SPEC is not None and SPEC.loader is not None
ACCEPTANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ACCEPTANCE)


class RoleAcceptanceTests(unittest.TestCase):
    """Check the state machine without touching Cloudflare or SMTP."""

    def test_transient_unknown_is_pending_not_failure(self) -> None:
        """A D1 read between insert and forward resolution must be tolerated."""

        states = iter([
            {"n": 1, "unknown_n": 1, "accepted_n": 0, "unalerted_n": 1, "malformed_n": 0},
            {"n": 1, "unknown_n": 0, "accepted_n": 1, "unalerted_n": 1, "malformed_n": 0},
            {"n": 1, "unknown_n": 0, "accepted_n": 1, "unalerted_n": 0, "malformed_n": 0},
        ])
        with (patch.object(ACCEPTANCE, "arrival", side_effect=lambda _: next(states)),
              patch.object(ACCEPTANCE, "row", return_value={"checked_at": 100, "lease_until": 10**15}),
              patch.object(ACCEPTANCE.time, "sleep"),
              patch.object(ACCEPTANCE.time, "time", return_value=100)):
            self.assertEqual(ACCEPTANCE.poll(2, 100), (True, True))

    def test_unknown_is_bounded(self) -> None:
        """Persistently unresolved forwarding is not reported as accepted."""

        state = {"n": 1, "unknown_n": 1, "accepted_n": 0, "unalerted_n": 1, "malformed_n": 0}
        with (patch.object(ACCEPTANCE, "arrival", return_value=state),
              patch.object(ACCEPTANCE.time, "sleep"),
              patch.object(ACCEPTANCE.time, "monotonic", side_effect=[0, 1, 2, 3, 121, 122])):
            with self.assertRaisesRegex(ACCEPTANCE.ProbeError, "role_forward_persistently_unknown"):
                ACCEPTANCE.poll(0, 0)

    def test_cleanup_removes_only_owned_alias_and_checks_standard_rules(self) -> None:
        """Removal/readback must be exact, and recovery marker survives failure."""

        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as temp:
            marker = Path(temp) / "route-open.marker"
            marker.write_text("armed", encoding="ascii")
            before = {"abuse@moesegfault.dev": ("rule", "private-target")}
            with (patch.object(ACCEPTANCE, "MARKER", marker),
                  patch.object(ACCEPTANCE.ROUTE, "remove_if_id", return_value="removed") as remove,
                  patch.object(ACCEPTANCE.ROUTE, "reconcile", side_effect=["absent", "absent"]) as route,
                  patch.object(ACCEPTANCE, "standard_rules", return_value=before),
                  patch.object(ACCEPTANCE.time, "sleep")):
                ACCEPTANCE.cleanup("zone", "token", before, "owned-id")
            remove.assert_called_once_with("zone", "token", "owned-id")
            self.assertEqual([call.args[2] for call in route.call_args_list], ["audit", "audit"])
            self.assertFalse(marker.exists())

    def test_cleanup_failure_preserves_recovery_marker(self) -> None:
        """A route still present cannot be silently converted into a pass."""

        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as temp:
            marker = Path(temp) / "route-open.marker"
            marker.write_text("armed", encoding="ascii")
            with (patch.object(ACCEPTANCE, "MARKER", marker),
                  patch.object(ACCEPTANCE.ROUTE, "remove_if_id", return_value="removed"),
                  patch.object(ACCEPTANCE.ROUTE, "reconcile", side_effect=["enabled"]),
                  patch.object(ACCEPTANCE, "standard_rules", return_value={})):
                with self.assertRaisesRegex(ACCEPTANCE.ProbeError, "route_cleanup_not_absent"):
                    ACCEPTANCE.cleanup("zone", "token", {}, "owned-id")
            self.assertTrue(marker.exists())

    def test_late_route_reappearance_preserves_recovery_marker(self) -> None:
        """An ambiguous create cannot pass on one temporarily absent inventory."""

        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as temp:
            marker = Path(temp) / "route-open.marker"
            marker.write_text("armed", encoding="ascii")
            with (patch.object(ACCEPTANCE, "MARKER", marker),
                  patch.object(ACCEPTANCE.ROUTE, "remove_if_id", return_value="absent"),
                  patch.object(ACCEPTANCE.ROUTE, "reconcile", side_effect=["absent", "enabled"]),
                  patch.object(ACCEPTANCE, "standard_rules", return_value={}),
                  patch.object(ACCEPTANCE.time, "sleep")):
                with self.assertRaisesRegex(ACCEPTANCE.ProbeError, "route_cleanup_late_rule"):
                    ACCEPTANCE.cleanup("zone", "token", {}, "owned-id")
            self.assertTrue(marker.exists())

    def test_unknown_id_never_authorizes_remove(self) -> None:
        """An ambiguous POST timeout must leave a present matching rule untouched."""

        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as temp:
            marker = Path(temp) / "route-open.marker"
            marker.write_text('{"version":1,"route_id":null}\n', encoding="ascii")
            with (patch.object(ACCEPTANCE, "MARKER", marker),
                  patch.object(ACCEPTANCE.ROUTE, "reconcile", return_value="enabled"),
                  patch.object(ACCEPTANCE.ROUTE, "remove_if_id") as remove,
                  patch.object(ACCEPTANCE, "standard_rules", return_value={})):
                with self.assertRaisesRegex(ACCEPTANCE.ProbeError, "route_cleanup_not_absent"):
                    ACCEPTANCE.recover("zone", "token")
            remove.assert_not_called()
            self.assertTrue(marker.exists())

    def test_send_preflight_uses_smtp_token(self) -> None:
        """The audit token need not also carry Email Sending read permission."""

        with (patch.object(sys, "argv", ["acceptance.py", "--confirm-staging-smtp"]),
              patch.dict(os.environ, {"AMAIL_TEST_SMTP_TOKEN": "smtp-token"}),
              patch.object(ACCEPTANCE, "credentials", return_value=("zone", "routing", "account")),
              patch.object(ACCEPTANCE, "preflight", return_value=({}, 0)),
              patch.object(ACCEPTANCE.SMTP, "assert_staging_sender") as sender,
              patch.object(ACCEPTANCE, "arm_marker"),
              patch.object(ACCEPTANCE.ROUTE, "create_owned", side_effect=RuntimeError("ambiguous"))):
            self.assertEqual(ACCEPTANCE.main(), 1)
        sender.assert_called_once_with("zone", "smtp-token")

    def test_read_only_preflight_does_not_require_smtp_token(self) -> None:
        """A read-only audit reports sender readiness as untested."""

        with (patch.object(sys, "argv", ["acceptance.py", "--preflight"]),
              patch.object(ACCEPTANCE, "credentials", return_value=("zone", "routing", "account")),
              patch.object(ACCEPTANCE, "preflight", return_value=({}, 0)),
              patch.object(ACCEPTANCE.SMTP, "assert_staging_sender") as sender):
            self.assertEqual(ACCEPTANCE.main(), 0)
        sender.assert_not_called()

    def test_standard_rule_validation_rejects_worker_action(self) -> None:
        """The harness must never treat a production role cutover as baseline."""

        rows = []
        for name in ACCEPTANCE.ROLES:
            rows.append({
                "id": name, "enabled": True, "source": "api",
                "matchers": [{"type": "literal", "field": "to", "value": name}],
                "actions": [{"type": "worker", "value": ["unexpected"]}],
            })
        with patch.object(ACCEPTANCE.ROUTE, "rules", return_value=rows):
            with self.assertRaisesRegex(ACCEPTANCE.ProbeError, "standard_rule_not_direct_forward"):
                ACCEPTANCE.standard_rules("zone", "token")

    def test_post_timeout_never_infers_ownership_from_matching_rule(self) -> None:
        """A matching rule after a timeout could belong to another writer."""

        with (patch.object(ACCEPTANCE.ROUTE, "rules", return_value=[]),
              patch.object(ACCEPTANCE.ROUTE, "call", return_value=(0, {}))):
            with self.assertRaisesRegex(RuntimeError, "ownership ambiguous"):
                ACCEPTANCE.ROUTE.create_owned("zone", "token")

    def test_successful_create_returns_provider_id(self) -> None:
        """A POST response ID and matching independent inventory bind cleanup."""

        route = {
            "id": "created-id", "name": ACCEPTANCE.ROUTE.NAME, "enabled": True, "source": "api",
            "matchers": [{"type": "literal", "field": "to", "value": ACCEPTANCE.ROUTE.ALIAS}],
            "actions": [{"type": "worker", "value": [ACCEPTANCE.ROUTE.WORKER]}],
        }
        with (patch.object(ACCEPTANCE.ROUTE, "rules", side_effect=[[], [route]]),
              patch.object(ACCEPTANCE.ROUTE, "call", return_value=(201, {
                  "success": True, "result": {"id": "created-id"}}))):
            self.assertEqual(ACCEPTANCE.ROUTE.create_owned("zone", "token"), "created-id")

    def test_replacement_rule_is_not_deleted(self) -> None:
        """A same-shape rule with a new provider ID is not this run's route."""

        replacement = {
            "id": "replacement-id", "name": ACCEPTANCE.ROUTE.NAME,
            "enabled": True, "source": "api",
            "matchers": [{"type": "literal", "field": "to", "value": ACCEPTANCE.ROUTE.ALIAS}],
            "actions": [{"type": "worker", "value": [ACCEPTANCE.ROUTE.WORKER]}],
        }
        with (patch.object(ACCEPTANCE.ROUTE, "rules", return_value=[replacement]),
              patch.object(ACCEPTANCE.ROUTE, "call") as provider):
            with self.assertRaisesRegex(RuntimeError, "ID changed"):
                ACCEPTANCE.ROUTE.remove_if_id("zone", "token", "created-id")
        provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()
