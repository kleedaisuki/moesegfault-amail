"""Synthetic phased Queue and serving-pin contracts; execute on hosted CI only."""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
sys.path.insert(0, str(ROOT / "crates/mail-worker"))
import ensure_trace_queues as queues
import check_trace_sink_isolation as isolation
import check_role_trace_rollout as rollout
import pin_staging_mail as pin

QUEUE, DLQ = "a" * 32, "b" * 32
SOURCE = "11111111-1111-4111-8111-111111111111"
SINK = "22222222-2222-4222-8222-222222222222"
ROLE = "33333333-3333-4333-8333-333333333333"


def detail(producers: tuple[str, ...] = ("amail-mail-staging",)) -> dict:
    """Use the documented provider attachment/count shape with synthetic IDs."""
    return {"queue_id": QUEUE, "queue_name": "amail-trace-events-staging",
            "settings": {"message_retention_period": 86400},
            "consumers_total_count": 1, "producers_total_count": len(producers),
            "producers": [{"type": "worker", "script": script} for script in producers],
            "consumers": [{"type": "worker", "script_name": "amail-trace-sink-staging",
                           "dead_letter_queue": "amail-trace-dlq-staging", "settings": {
                               "batch_size": 10, "max_wait_time_ms": 1000, "max_retries": 3,
                               "retry_delay": 30, "max_concurrency": 2}}]}


def version(phase: str = "queue-api") -> dict:
    """Translate expected contracts into independent immutable binding resources."""
    bindings = []
    for name, (kind, value) in pin.expected_bindings(phase, QUEUE).items():
        item = {"name": name, "type": kind}
        field = {"d1": "database_id", "r2_bucket": "bucket_name", "plain_text": "text", "queue": "queue_id"}.get(kind)
        if field:
            item[field] = value
        bindings.append(item)
    return {"id": SOURCE, "resources": {"bindings": bindings}}


class PhasedTopologyTests(unittest.TestCase):
    """No topology may adopt unknown, duplicated, missing or cross-realm producers."""

    def validate(self, value: dict, topology: str, phase: str = "readback") -> None:
        """Invoke the real pure validator, not a copied assertion."""
        queues.validate_detail(value, value["queue_name"], QUEUE, "-staging", phase, topology)

    def test_exact_phases_and_order_independence(self) -> None:
        """Phase1 sole API and phase2 exact API/role sets are distinct contracts."""
        self.validate(detail(), "api-only")
        for producers in (("amail-mail-staging", "amail-role-monitor-staging"),
                          ("amail-role-monitor-staging", "amail-mail-staging")):
            self.validate(detail(producers), "api-role")
            with self.assertRaises(ValueError):
                self.validate(detail(producers), "api-only")
        with self.assertRaises(ValueError):
            self.validate(detail(), "api-role")

    def test_missing_extra_duplicate_unknown_and_wrong_realm_denied(self) -> None:
        """Set equality cannot hide duplicate rows or altered producer types."""
        for producers in ((), ("amail-role-monitor-staging",),
                          ("amail-mail-staging", "amail-mail-staging"),
                          ("amail-mail-staging", "amail-role-monitor"),
                          ("amail-mail-staging", "amail-role-monitor-staging", "other")):
            with self.subTest(producers=producers), self.assertRaises(ValueError):
                self.validate(detail(producers), "api-role")
        row = detail(("amail-mail-staging", "amail-role-monitor-staging"))
        for item in (None, {"type": "r2_bucket", "script": "amail-role-monitor-staging"}):
            changed = deepcopy(row)
            changed["producers"][1] = item
            with self.assertRaises(ValueError):
                self.validate(changed, "api-role")
        changed = {**row, "producers_total_count": True}
        with self.assertRaises(ValueError):
            self.validate(changed, "api-role")

    def test_no_phase2_provision_or_recovery_escape(self) -> None:
        """The empty pre-API installation allowance never widens role readback."""
        row = detail(())
        self.validate(row, "api-only", "queues")
        for phase in ("queues", "recover", "readback"):
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                self.validate(row, "api-role", phase)
        with patch.object(queues, "inventory") as read, self.assertRaises(ValueError):
            queues.reconcile("a", "token", "staging", "queues", "api-role")
        read.assert_not_called()

    def test_phase2_cannot_widen_consumer_or_dlq_policy(self) -> None:
        """The new producer set leaves sole consumer, retry and empty DLQ invariant."""
        row = detail(("amail-mail-staging", "amail-role-monitor-staging"))
        changes = [{**row, "consumers": []}, {**row, "consumers": row["consumers"] * 2,
                   "consumers_total_count": 2}, {**row, "queue_id": DLQ}]
        for changed in changes:
            with self.assertRaises(ValueError):
                self.validate(changed, "api-role")
        dlq = {**row, "queue_name": "amail-trace-dlq-staging", "consumers": [], "consumers_total_count": 0}
        with self.assertRaisesRegex(ValueError, "dlq_consumer_unreviewed"):
            self.validate(dlq, "api-role")

    def test_sink_explicit_role_mode_has_no_empty_producer_allowance(self) -> None:
        """Run real sink Queue checks, retaining its historical initial-install mode."""
        dlq = {"queue_id": DLQ, "queue_name": "amail-trace-dlq-staging",
               "settings": {"message_retention_period": 86400}, "consumers": [], "producers": [],
               "consumers_total_count": 0, "producers_total_count": 0}
        for topology, producers, accepted in (
                ("api-only", (), True), ("api-role", (), False),
                ("api-role", ("amail-mail-staging", "amail-role-monitor-staging"), True),
                ("api-only", ("amail-mail-staging", "amail-role-monitor-staging"), False)):
            main = detail(producers)
            with patch.dict(os.environ, {"AMAIL_TRACE_TOPOLOGY": topology,
                            "AMAIL_TRACE_QUEUE_ID": QUEUE, "AMAIL_TRACE_DLQ_ID": DLQ}), \
                    patch.object(queues, "inventory", return_value=[main, dlq]), \
                    patch.object(queues, "request", side_effect=[{"result": main}, {"result": dlq}]):
                if accepted:
                    self.assertTrue(isolation.queue_trigger_exact("c" * 32, "token", "staging", "amail-trace-sink-staging"))
                else:
                    with self.assertRaises(ValueError):
                        isolation.queue_trigger_exact("c" * 32, "token", "staging", "amail-trace-sink-staging")


class QueueServingPinTests(unittest.TestCase):
    """Preserve no-Queue historical attestation while enabling explicit phase1 pins."""

    def test_default_rejects_queue_and_explicit_phase_requires_exact_id(self) -> None:
        """Neither extra Queue adoption nor missing post-rollout capability is accepted."""
        before, after = version("pre-queue"), version()
        self.assertTrue(pin.bindings_match(before, SOURCE))
        self.assertFalse(pin.bindings_match(after, SOURCE))
        self.assertTrue(pin.bindings_match(after, SOURCE, phase="queue-api", queue_id=QUEUE))
        self.assertFalse(pin.bindings_match(before, SOURCE, phase="queue-api", queue_id=QUEUE))
        for value in ("", DLQ):
            if not value:
                with self.assertRaises(ValueError):
                    pin.bindings_match(after, SOURCE, phase="queue-api", queue_id=value)
            else:
                self.assertFalse(pin.bindings_match(after, SOURCE, phase="queue-api", queue_id=value))
        with patch.object(pin, "fetch") as fetch, self.assertRaises(ValueError):
            pin.run("c" * 32, "token", SOURCE, phase="queue-api")
        fetch.assert_not_called()


class RolloutBracketTests(unittest.TestCase):
    """Test the real orchestration with pure transports mocked and no provider calls."""

    def environment(self, phase: str) -> dict:
        """Supply independent synthetic version/resource pins for one transition."""
        return {"CLOUDFLARE_ACCOUNT_ID": "c" * 32, "CLOUDFLARE_API_TOKEN": "token",
                "AMAIL_EXPECTED_WORKER_VERSION": SOURCE, "AMAIL_EXPECTED_TRACE_SINK_VERSION": SINK,
                "AMAIL_EXPECTED_ROLE_WORKER_VERSION": ROLE, "AMAIL_TRACE_QUEUE_ID": QUEUE,
                "AMAIL_TRACE_DLQ_ID": DLQ, "AMAIL_TRACE_TOPOLOGY": "api-only" if phase == "before" else "api-role"}

    def test_transition_brackets_topology_and_all_three_versions(self) -> None:
        """After mode cannot use prior role pins, empty topology or a partial audit."""
        expected = {rollout.API_WORKER: (ROLE, SOURCE), rollout.SINK_WORKER: (ROLE, SINK), rollout.role.WORKER: (SOURCE, ROLE)}
        for phase in ("before", "after"):
            with patch.dict(os.environ, self.environment(phase)), \
                    patch.object(rollout, "serving_pins", return_value=expected) as pins, \
                    patch.object(queues, "reconcile") as topology, \
                    patch.object(rollout.capture, "readback", return_value=version()), \
                    patch.object(rollout.capture, "verify", return_value=True), \
                    patch.object(rollout.role, "audit") as role_audit, \
                    patch.object(rollout, "route_absent") as route:
                rollout.verify(phase)
                self.assertEqual(pins.call_count, 2)
                self.assertEqual(topology.call_count, 2)
                self.assertEqual(topology.call_args.args[-1], self.environment(phase)["AMAIL_TRACE_TOPOLOGY"])
                self.assertEqual(role_audit.call_count, phase == "after")
                self.assertEqual(route.call_count, phase == "before")

    def test_topology_and_missing_pins_fail_before_provider_access(self) -> None:
        """Caller defaults cannot cross the phase boundary or select latest implicitly."""
        for changed in ({"AMAIL_TRACE_TOPOLOGY": "api-only"}, {"AMAIL_EXPECTED_TRACE_SINK_VERSION": ""}):
            with patch.dict(os.environ, {**self.environment("after"), **changed}), \
                    patch.object(rollout, "serving_pins") as read, self.assertRaises(ValueError):
                rollout.verify("after")
            read.assert_not_called()

    def test_absent_route_requires_exact_clean_result(self) -> None:
        """A route inventory error or actual route blocks replacement, without writes."""
        for output, code in (("absent\n", 0), ("present\n", 0), ("absent\n", 1), ("private", 0)):
            with patch.object(rollout.subprocess, "run", return_value=subprocess.CompletedProcess([], code, output, "private")):
                if code == 0 and output == "absent\n":
                    rollout.route_absent()
                else:
                    with self.assertRaises(ValueError):
                        rollout.route_absent()


if __name__ == "__main__":
    unittest.main()
