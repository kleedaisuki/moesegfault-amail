"""Hosted predecessor bracket, missing-proof and no-replay recovery policy tests."""

from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "deploy"))
import mail_lifecycle_guard as lifecycle
from test_mail_lifecycle_receipt import DEPLOYMENT, VERSION, fixture


def receipt(state="paused"):
    """Build an inert validated observation with explicit unknown old-work verdict."""
    value = fixture(state=state)
    if state in ("new-draining", "old-draining"):
        value.update(predecessor_run="122", stop={
            "script": lifecycle.script_name("staging", maintenance=state == "new-draining"),
            "acknowledged_at": "2026-10-01T09:59:00Z"})
    return lifecycle.Receipt(json.dumps(value), 456)


def readback(value):
    """Return the existing graph verifier's exact pinned tuple shape."""
    graph = deepcopy(value.value["graph"])
    graph["pins"] = {name: (pin["deployment"], pin["version"]) for name, pin in graph["pins"].items()}
    return graph


class MailLifecycleGuardTests(unittest.TestCase):
    """An exact serving pin is necessary but not old invocation completion."""

    def test_pause_and_hold_preserve_draining_unknown_old_work(self):
        """Stop planning never becomes active or old-work-ended from an empty read."""
        for state, operation, expected in (("active", "pause", "new-draining"),
                                           ("new-draining", "hold", "paused")):
            predecessor = receipt(state)
            with patch.object(lifecycle.graph, "verify", return_value=readback(predecessor)) as verify:
                plan = lifecycle.guard(predecessor, operation)
            self.assertEqual(plan.successor.value, expected)
            self.assertIn(plan.crons, ((), None))
            verify.assert_called_once()
            self.assertEqual(predecessor.value["drain"], {"status": "UNVERIFIED"})

    def test_activation_and_code_rollback_missing_verifiers_fail_before_provider_reads(self):
        """No elapsed-time or success self-attestation shortcut invokes a writer/reader."""
        for operation, reason in (("activate", "old_work_end_verifier_unavailable"),
                                  ("rollback-maintenance", "code_compatibility_verifier_unavailable"),
                                  ("replace-api", "code_compatibility_verifier_unavailable")):
            with patch.object(lifecycle.graph, "verify") as verify:
                with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, reason):
                    lifecycle.guard(receipt(), operation)
            verify.assert_not_called()

    def test_failed_or_changed_deployment_read_never_means_predecessor_absent(self):
        """Same version with a changed deployment still constitutes graph drift."""
        predecessor = receipt("active")
        changed = readback(predecessor)
        name = next(iter(changed["pins"]))
        changed["pins"][name] = (VERSION, VERSION)
        with patch.object(lifecycle.graph, "verify", return_value=changed), self.assertRaises(ValueError):
            lifecycle.guard(predecessor, "pause")
        with patch.object(lifecycle.graph, "verify", side_effect=ValueError("provider_read_failed")), self.assertRaises(ValueError):
            lifecycle.guard(predecessor, "pause")

    def test_coordinate_scope_is_restored_on_read_failure(self):
        """A failed bracket cannot leave later operations targeting admitted temporary pins."""
        with patch.dict(os.environ, {"AMAIL_TRACE_QUEUE_ID": "original"}, clear=True):
            with self.assertRaises(ValueError), lifecycle.coordinates(receipt()):
                self.assertEqual(os.environ["AMAIL_TRACE_QUEUE_ID"], "a" * 32)
                raise ValueError("synthetic_failure")
            self.assertEqual(dict(os.environ), {"AMAIL_TRACE_QUEUE_ID": "original"})

    def test_recovery_recognizes_exact_graphs_but_never_replays_write(self):
        """Classify one full read, not the failed submit's presumed remote outcome."""
        predecessor, successor = receipt("active"), receipt("new-draining")
        for actual, expected in ((predecessor.value["graph"], lifecycle.Recovery.PREDECESSOR),
                                 (successor.value["graph"], lifecycle.Recovery.SUCCESSOR)):
            read = Mock(return_value=actual)
            result = lifecycle.recovery(predecessor, "pause", read)
            self.assertEqual(result.outcome, expected)
            self.assertFalse(result.may_replay_write)
            read.assert_called_once()
        unknown = deepcopy(successor.value["graph"])
        unknown["pins"][next(iter(unknown["pins"]))]["deployment"] = VERSION
        self.assertEqual(lifecycle.recovery(predecessor, "pause", Mock(return_value=unknown)).outcome,
                         lifecycle.Recovery.UNRESOLVED)

    def test_failed_missing_or_malformed_recovery_read_is_not_a_safe_outcome(self):
        """Neither HTTP failure nor empty/missing fields classify write-not-applied."""
        predecessor, successor = receipt("active"), receipt("new-draining")
        for actual in (None, {}, {"pins": {}}):
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                lifecycle.recovery(predecessor, "pause", Mock(return_value=actual))
        read = Mock(side_effect=ValueError("read_failed"))
        with self.assertRaises(ValueError):
            lifecycle.recovery(predecessor, "pause", read)
        read.assert_called_once()


if __name__ == "__main__":
    unittest.main()
