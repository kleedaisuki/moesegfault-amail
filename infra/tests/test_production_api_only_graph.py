"""Direct-only graph source contracts, authored for hosted execution only."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import check_production_role_graph as graph
import pin_staging_mail as pin
import prepare_production_graph as prepare

VERSION = "11111111-1111-4111-8111-111111111111"
SINK_VERSION = "22222222-2222-4222-8222-222222222222"
ENVIRONMENT = {
    "GITHUB_REF": "refs/heads/main",
    "AMAIL_PRODUCTION_GRAPH_FREEZE": "FREEZE_PRODUCTION_GRAPH_WRITERS",
    "AMAIL_PRODUCTION_GRAPH_CONFIRM": "RUN_PRODUCTION_API_ONLY_MAINTENANCE",
    "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
    "CLOUDFLARE_API_TOKEN": "synthetic",
    "AMAIL_TRACE_QUEUE_ID": "b" * 32,
    "AMAIL_TRACE_DLQ_ID": "c" * 32,
    "AMAIL_EXPECTED_WORKER_VERSION": VERSION,
    "AMAIL_EXPECTED_TRACE_SINK_VERSION": SINK_VERSION,
    "AMAIL_TRACE_TOPOLOGY": "api-only",
}


def api_version() -> dict:
    """Derive provider-shaped immutable bindings from reviewed production config."""
    rows = []
    fields = {"d1": "database_id", "r2_bucket": "bucket_name", "plain_text": "text", "queue": "queue_id"}
    expected = pin.expected_bindings("queue-api", ENVIRONMENT["AMAIL_TRACE_QUEUE_ID"], realm="production")
    for name, (kind, value) in expected.items():
        row = {"name": name, "type": kind}
        if kind in fields:
            row[fields[kind]] = value
        if name == "OFFICIAL_EMAIL":
            row["allowed_sender_addresses"] = ["mail@moesegfault.dev"]
        rows.append(row)
    return {"id": VERSION, "resources": {"bindings": rows}}


@contextmanager
def accepted_graph():
    """Patch only transports and independent guards; keep real binding comparison."""
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, ENVIRONMENT, clear=True))
        mocks = {}
        replacements = {
            "held_send": None,
            "serving": {graph.API: (VERSION, VERSION), graph.SINK: (SINK_VERSION, SINK_VERSION)},
            "forward_snapshot": {str(index): {"id": str(index)} for index in range(4)},
            "role_absent": None,
        }
        for name, value in replacements.items():
            mocks[name] = stack.enter_context(patch.object(graph, name, return_value=value))
        mocks["queues"] = stack.enter_context(patch.object(graph.queues, "reconcile"))
        mocks["readback"] = stack.enter_context(patch.object(graph.capture, "readback", return_value=api_version()))
        mocks["privacy"] = stack.enter_context(patch.object(graph.capture, "verify", return_value=True))
        mocks["storage"] = stack.enter_context(patch.object(graph, "storage", side_effect=AssertionError("role storage must not be read")))
        mocks["role_capabilities"] = stack.enter_context(patch.object(graph, "role_capabilities", side_effect=AssertionError("role version must not be read")))
        yield mocks


class ApiOnlyGraphTests(unittest.TestCase):
    """The single active graph rejects legacy dependencies instead of ignoring drift."""

    def test_maintenance_and_post_bootstrap_share_exact_contract(self):
        """Only API/sink pins, exact Queue ownership, privacy and held forwards are used."""
        with accepted_graph() as mocks:
            graph.verify("api-only", "replacement")
            self.assertEqual(mocks["queues"].call_count, 2)
            for call in mocks["queues"].call_args_list:
                self.assertEqual(call.args[2:], ("production", "readback", "api-only"))
            self.assertEqual(mocks["role_absent"].call_count, 2)
            self.assertEqual(mocks["held_send"].call_count, 2)
            self.assertEqual(mocks["privacy"].call_args_list[0].kwargs, {})
            self.assertEqual(mocks["privacy"].call_args_list[1].kwargs, {"sink": True})
            mocks["storage"].assert_not_called()
            mocks["role_capabilities"].assert_not_called()

    def test_api_and_sink_capture_remain_independent(self):
        """A safe graph cannot replace either independent current-resource privacy proof."""
        for replies in ([False], [True, False]):
            with accepted_graph() as mocks:
                mocks["privacy"].side_effect = replies
                with self.assertRaises(ValueError):
                    graph.verify("api-only", "replacement")

    def test_role_state_and_wrong_pins_fail_before_provider_access(self):
        """No dormant lease or role pin may be auto-adopted as the direct graph."""
        mutations = {
            "AMAIL_TRACE_TOPOLOGY": "api-role",
            "AMAIL_EXPECTED_ROLE_WORKER_VERSION": VERSION,
            "AMAIL_ROLE_ROUTED_COUNT": "1",
            "AMAIL_EXPECTED_WORKER_VERSION": "missing",
            "AMAIL_EXPECTED_TRACE_SINK_VERSION": "missing",
            "AMAIL_TRACE_DLQ_ID": ENVIRONMENT["AMAIL_TRACE_QUEUE_ID"],
        }
        for name, value in mutations.items():
            with accepted_graph() as mocks, patch.dict(os.environ, {name: value}), self.assertRaises(ValueError):
                graph.verify("api-only", "replacement")
            mocks["serving"].assert_not_called()

    def test_extra_role_binding_and_wrong_mail_database_fail_closed(self):
        """Resource identity remains exact after removing the old indexed prerequisite."""
        extra = api_version()
        extra["resources"]["bindings"].append({"name": "ROLE_MONITOR", "type": "d1", "database_id": SINK_VERSION})
        wrong = api_version()
        next(row for row in wrong["resources"]["bindings"] if row["name"] == "MAIL_DB")["database_id"] = SINK_VERSION
        for value in (extra, wrong):
            with accepted_graph() as mocks:
                mocks["readback"].return_value = value
                with self.assertRaises(ValueError):
                    graph.verify("api-only", "replacement")

    def test_queue_role_absence_hold_and_forward_drift_all_deny(self):
        """Failed remote proof and mutations bracketed across checks are not acceptance."""
        for name in ("queues", "role_absent", "held_send"):
            with accepted_graph() as mocks:
                mocks[name].side_effect = ValueError("synthetic_unverified")
                with self.assertRaises(ValueError):
                    graph.verify("api-only", "replacement")
        for name in ("serving", "forward_snapshot"):
            with accepted_graph() as mocks:
                mocks[name].side_effect = [mocks[name].return_value, {}]
                with self.assertRaises(ValueError):
                    graph.verify("api-only", "replacement")

    def test_direct_graph_rejects_role_migration_flags(self):
        """Role bootstrap/replacement lifecycle is never an implicit direct state."""
        with accepted_graph() as mocks:
            with self.assertRaises(ValueError):
                graph.verify("api-only", "first-bootstrap")
            with self.assertRaises(ValueError):
                graph.verify("api-only", "replacement", migrated=True)
            mocks["serving"].assert_not_called()


class PreparationTests(unittest.TestCase):
    """An explicit held api-only maintenance path does not replay first provisioning."""

    def test_direct_maintenance_has_no_role_storage_dependency(self):
        """Writer freeze and phase confirmation lead to the same strict direct checker."""
        with patch.dict(os.environ, ENVIRONMENT, clear=True), patch.object(prepare, "verify") as verify:
            prepare.prepare("api-only-maintenance")
        verify.assert_called_once_with("api-only", "replacement")

    def test_old_role_maintenance_confirmation_is_not_accepted(self):
        """Old dispatch inputs cannot silently weaken the selected direct-only release."""
        with patch.dict(os.environ, ENVIRONMENT, clear=True), patch.object(prepare.role, "api_get") as provider:
            with self.assertRaises(ValueError):
                prepare.prepare("api-role-maintenance")
        provider.assert_not_called()

    def test_bootstrap_reads_only_mail_policy_and_preserves_forward_snapshot(self):
        """No pristine isolated D1 or role lease is required by API-only first deploy."""
        environment = dict(ENVIRONMENT, AMAIL_PRODUCTION_GRAPH_CONFIRM="RUN_PRODUCTION_API_ONLY_BOOTSTRAP")
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, environment, clear=True))
            held = stack.enter_context(patch.object(prepare, "held_send"))
            stack.enter_context(patch.object(prepare.role, "api_get", return_value=[]))
            snapshot = stack.enter_context(patch.object(prepare, "forward_snapshot", return_value={"synthetic": {}}))
            stack.enter_context(patch.object(prepare, "role_absent"))
            storage = stack.enter_context(patch.object(graph, "storage", side_effect=AssertionError("no role D1")))
            prepare.prepare("bootstrap")
            held.assert_called_once()
            self.assertEqual(snapshot.call_count, 2)
            storage.assert_not_called()


class ResourceConfigTests(unittest.TestCase):
    """Reviewed Mail resource names, not array positions, establish binding identity."""

    def test_single_mail_d1_uses_adopted_production_and_unchanged_staging_identity(self):
        """Production points to the actual owned scope; staging remains untouched."""
        identities = {
            "production": "d9be9bb4-5a73-4223-85d6-b04763e6f03b",
            "staging": "74f35f95-42ce-482c-86e6-dffbdd35cbbe",
        }
        for realm, database in identities.items():
            expected = pin.expected_bindings("queue-api", ENVIRONMENT["AMAIL_TRACE_QUEUE_ID"], realm=realm)
            self.assertEqual({name: value for name, (kind, value) in expected.items() if kind == "d1"},
                             {"MAIL_DB": database})
            self.assertNotIn("ROLE_MONITOR", expected)

    def test_named_single_mail_resources_and_config_drift(self):
        """Missing/extra/duplicate/renamed D1 or R2 entries fail without provider reads."""
        good = {"d1_databases": [{"binding": "MAIL_DB", "database_id": VERSION}],
                "r2_buckets": [{"binding": "MAIL_BODIES", "bucket_name": "synthetic-bodies"}]}
        self.assertEqual(pin.mail_resources(good), (VERSION, "synthetic-bodies"))
        bad = []
        for collection in ("d1_databases", "r2_buckets"):
            missing, duplicate, renamed = deepcopy(good), deepcopy(good), deepcopy(good)
            missing[collection] = []
            duplicate[collection] *= 2
            renamed[collection][0]["binding"] = "ROLE_MONITOR"
            bad.extend((missing, duplicate, renamed))
        malformed = deepcopy(good)
        malformed["d1_databases"][0]["database_id"] = "not-a-database-id"
        bad.append(malformed)
        for value in bad:
            with self.assertRaises(ValueError):
                pin.mail_resources(value)


if __name__ == "__main__":
    unittest.main()
