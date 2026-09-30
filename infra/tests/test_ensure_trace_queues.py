"""Synthetic contracts for bounded private trace Queue deployment, executed in CI."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("trace_queues", Path(__file__).parents[1] / "deploy/ensure_trace_queues.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def queue(name):
    """Build explicit provider-shape fixtures, not permissive Wrangler output."""
    return {"queue_name": name, "queue_id": ("b" if "dlq" in name else "a") * 32, "settings": {
        "message_retention_period": 86400, "delivery_delay": 0, "delivery_paused": False}}


class TraceQueueTests(unittest.TestCase):
    """Protect no-purge provisioning, strict ownership and bounded inventory."""

    def test_retention_and_paused_drift(self):
        """Existing queue drift fails rather than silently updating settings."""
        row = queue("amail-trace-events-staging")
        self.assertTrue(MODULE.bounded_queue(row))
        for field, bad in [("message_retention_period", 345600), ("delivery_paused", True), ("delivery_delay", 10)]:
            with self.subTest(field=field):
                changed = {**row, "settings": {**row["settings"], field: bad}}
                self.assertFalse(MODULE.bounded_queue(changed))

    def test_duplicate_name_rejected(self):
        """Never select an arbitrary resource when provider identity is ambiguous."""
        with self.assertRaisesRegex(ValueError, "queue_ambiguous"):
            MODULE.exact_queue([queue("x"), queue("x")], "x")

    def test_inventory_requires_complete_pages(self):
        """Absence is meaningful only after all declared pages were read."""
        replies = [{"result": [queue("a")], "result_info": {"page": 1, "total_pages": 2}},
                   {"result": [queue("b")], "result_info": {"page": 2, "total_pages": 2}}]
        with patch.object(MODULE, "request", side_effect=replies) as call:
            self.assertEqual(len(MODULE.inventory("a", "t")), 2)
            self.assertEqual(call.call_count, 2)
        with patch.object(MODULE, "request", return_value={"result": [], "result_info": {"page": 1}}):
            with self.assertRaisesRegex(ValueError, "inventory_shape"):
                MODULE.inventory("a", "t")

    def test_post_timeout_not_retried(self):
        """An ambiguous create is reconciled by a later operator run, never repeated here."""
        with patch.object(MODULE, "inventory", return_value=[]), patch.object(
                MODULE, "request", side_effect=ValueError("provider_unavailable")) as call:
            with self.assertRaisesRegex(ValueError, "provider_unavailable"):
                MODULE.reconcile("a", "t", "staging", "queues")
            self.assertEqual(call.call_count, 1)

    def test_existing_queue_requires_reviewed_id(self):
        """A same-name empty resource is not sufficient provenance for adoption."""
        with patch.object(MODULE, "inventory", return_value=[queue("amail-trace-dlq-staging")]), patch.dict(
                MODULE.os.environ, {}, clear=True), patch.object(MODULE, "request") as call:
            with self.assertRaisesRegex(ValueError, "existing_queue_ownership_unverified"):
                MODULE.reconcile("a", "t", "staging", "queues")
            call.assert_not_called()

    def test_peer_conflict_prevents_any_creation(self):
        """An absent DLQ cannot be created before an existing main queue is authorized."""
        with patch.object(MODULE, "inventory", return_value=[queue("amail-trace-events-staging")]), patch.dict(
                MODULE.os.environ, {}, clear=True), patch.object(MODULE, "request") as call:
            with self.assertRaisesRegex(ValueError, "existing_queue_ownership_unverified"):
                MODULE.reconcile("a", "t", "staging", "queues")
            call.assert_not_called()

    def test_create_identity_must_survive_readback(self):
        """A successful POST identity cannot be replaced by a same-name resource."""
        dlq, main = queue("amail-trace-dlq-staging"), queue("amail-trace-events-staging")
        changed = {**main, "queue_id": "c" * 32}
        with patch.object(MODULE, "inventory", side_effect=[[], [dlq, changed]]), patch.object(
                MODULE, "request", side_effect=[{"result": dlq}, {"result": main}, {"result": {
                    **dlq, "consumers": [], "producers": [], "consumers_total_count": 0, "producers_total_count": 0}}]):
            with self.assertRaisesRegex(ValueError, "queue_settings_drift"):
                MODULE.reconcile("a", "t", "staging", "queues")

    def test_readback_requires_exact_owner(self):
        """Extra consumers/producers, bad DLQ and wrong retry settings are rejected."""
        dlq, main = queue("amail-trace-dlq-staging"), queue("amail-trace-events-staging")
        safe = {**main, "consumers_total_count": 1, "producers_total_count": 1, "consumers": [{"type": "worker", "script_name": "amail-trace-sink-staging",
                "dead_letter_queue": "amail-trace-dlq-staging", "settings": {
                    "batch_size": 10, "max_wait_time_ms": 1000, "max_retries": 3,
                    "retry_delay": 30, "max_concurrency": 2}}],
                "producers": [{"type": "worker", "script": "amail-mail-staging"}]}
        for detail, fails in [(safe, False), ({**safe, "producers": []}, True),
                              ({**safe, "consumers": []}, True),
                              ({**safe, "queue_id": "b" * 32}, True),
                              ({**safe, "producers_total_count": 2}, True)]:
            with self.subTest(fails=fails), patch.dict(MODULE.os.environ, {"AMAIL_TRACE_QUEUE_ID": "a" * 32, "AMAIL_TRACE_DLQ_ID": "b" * 32}), patch.object(MODULE, "inventory", return_value=[dlq, main]), patch.object(
                    MODULE, "request", side_effect=[{"result": {**dlq, "consumers": [], "producers": [], "consumers_total_count": 0, "producers_total_count": 0}}, {"result": detail}]):
                if fails:
                    with self.assertRaises(ValueError):
                        MODULE.reconcile("a", "t", "staging", "readback")
                else:
                    MODULE.reconcile("a", "t", "staging", "readback")


if __name__ == "__main__":
    unittest.main()
