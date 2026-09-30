"""Synthetic contracts for bounded private trace Queue deployment, executed in CI."""

import importlib.util
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("trace_queues", Path(__file__).parents[1] / "deploy/ensure_trace_queues.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def queue(name):
    """Build explicit provider-shape fixtures, not permissive Wrangler output."""
    return {"queue_name": name, "queue_id": ("b" * 32 if "dlq" in name else "a" * 32 if name.startswith("amail-trace-events") else hashlib.sha256(name.encode()).hexdigest()[:32]), "settings": {
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

    def test_inventory_documented_single_page(self):
        """The endpoint has no page/per_page parameters and optional response metadata."""
        for info in (None, {}, {"page": 1, "per_page": 20, "count": 2, "total_count": 2, "total_pages": 1}):
            reply = {"result": [queue("a"), queue("b")]}
            if info is not None:
                reply["result_info"] = info
            with self.subTest(info=info), patch.object(MODULE, "request", return_value=reply) as call:
                self.assertEqual(len(MODULE.inventory("a", "t")), 2)
                self.assertEqual(call.call_args.args[2], "queues")
                self.assertEqual(call.call_count, 1)

    def test_inventory_denies_counts_and_duplicate_identity(self):
        """No count mismatch, omitted page or duplicate queue can attest exclusivity."""
        safe = {"result": [queue("only")], "result_info": {
            "page": 1, "per_page": 100, "count": 1, "total_count": 1, "total_pages": 1}}
        bad = [{**safe, "result_info": {**safe["result_info"], "count": 0}},
               {**safe, "result_info": {**safe["result_info"], "total_count": 2}},
               {**safe, "result": [queue("only"), queue("only")], "result_info": {
                   **safe["result_info"], "count": 2, "total_count": 2}}]
        for payload in bad:
            with self.subTest(payload=payload), patch.object(MODULE, "request", return_value=payload):
                with self.assertRaises(ValueError):
                    MODULE.inventory("a", "t")
        empty = {"result": [], "result_info": {"page": 1, "per_page": 100,
                 "count": 0, "total_count": 0, "total_pages": 0}}
        with patch.object(MODULE, "request", return_value=empty):
            self.assertEqual(MODULE.inventory("a", "t"), [])

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

    def test_existing_attachment_conflict_prevents_peer_creation(self):
        """Reviewed identity is insufficient if the existing queue has a foreign consumer."""
        main = queue("amail-trace-events-staging")
        bad = {**main, "consumers": [{"type": "http_pull"}], "producers": [],
               "consumers_total_count": 1, "producers_total_count": 0}
        with patch.object(MODULE, "inventory", return_value=[main]), patch.dict(MODULE.os.environ,
                {"AMAIL_TRACE_QUEUE_ID": "a" * 32}), patch.object(MODULE, "request", return_value={"result": bad}) as call:
            with self.assertRaisesRegex(ValueError, "consumer_drift"):
                MODULE.reconcile("a", "t", "staging", "queues")
            self.assertEqual(call.call_count, 1)
            self.assertEqual(call.call_args.args[2], "queues/" + "a" * 32)

    def test_only_new_identity_can_be_configured(self):
        """Documented create then PATCH targets exactly the fresh provider identity."""
        dlq = queue("amail-trace-dlq-staging")
        with patch.object(MODULE, "inventory", return_value=[]), patch.object(MODULE, "request",
                side_effect=[{"result": dlq}, {"result": {**dlq, "queue_id": "f" * 32}}]) as call:
            with self.assertRaisesRegex(ValueError, "created_queue_settings_unverified"):
                MODULE.reconcile("a", "t", "staging", "queues")
            self.assertEqual(call.call_args_list[0].args[3], {"queue_name": "amail-trace-dlq-staging"})
            self.assertEqual(call.call_args_list[1].args[2], "queues/" + "b" * 32)
            self.assertEqual(call.call_args_list[1].kwargs["method"], "PATCH")

    def test_create_identity_must_survive_readback(self):
        """A successful POST identity cannot be replaced by a same-name resource."""
        dlq, main = queue("amail-trace-dlq-staging"), queue("amail-trace-events-staging")
        changed = {**main, "queue_id": "c" * 32}
        with patch.object(MODULE, "inventory", side_effect=[[], [dlq, changed]]), patch.object(
                MODULE, "request", side_effect=[{"result": dlq}, {"result": dlq}, {"result": main}, {"result": main}, {"result": {
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
