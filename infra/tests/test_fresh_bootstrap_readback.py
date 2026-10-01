"""Hosted synthetic provider proves NEW storage and full immutable/mutable bracket."""

from copy import deepcopy
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import fresh_bootstrap_readback as readback
from fresh_bootstrap_contract import Epoch, Scope

VERSION = "11111111-1111-4111-8111-111111111111"
DEPLOYMENT = "22222222-2222-4222-8222-222222222222"
DATABASE = "33333333-3333-4333-8333-333333333333"
QUEUE, DLQ = "a" * 32, "b" * 32


def fixture_scope():
    """Use valid synthetic operational identities, never original production stores."""
    return Scope(Epoch("c" * 40, "123", 456, "d" * 64, "1.98.1"), DATABASE,
                 "2026-10-01T10:00:00Z", "2026-10-01T10:00:01Z")


def binding_rows(expected):
    """Build exact immutable provider resources from existing source predicates."""
    result = []
    fields = {"d1": "database_id", "r2_bucket": "bucket_name", "queue": "queue_id", "plain_text": "text"}
    for name, (kind, target) in expected.items():
        row = {"name": name, "type": kind}
        if kind in fields:
            row[fields[kind]] = target
        if name == "OFFICIAL_EMAIL":
            row["allowed_sender_addresses"] = ["mail@moesegfault.dev"]
        result.append(row)
    return result


def settings(sink=False):
    """Model three independent capture switches, not just top-level sampling."""
    return {"logpush": False, "tail_consumers": [], "observability": {
        "enabled": sink, "head_sampling_rate": 1.0, "redact_query_string": True,
        "logs": {"enabled": sink, "invocation_logs": False},
        "traces": {"enabled": False}, "issues": {"enabled": False}}}


class Provider:
    """Bounded in-memory transport; SQLite is the synthetic hosted D1 data plane."""

    def __init__(self):
        """Compile complete migrations into memory only on the hosted test runner."""
        self.account = "e" * 32
        self.scope = fixture_scope()
        self.calls, self.data = [], {}
        self.database = sqlite3.connect(":memory:")
        self.database.row_factory = sqlite3.Row
        files = sorted(readback.MIGRATIONS.glob("*.sql"))
        for file in files:
            self.database.executescript(file.read_text(encoding="utf-8"))
        self.database.execute("CREATE TABLE d1_migrations(id INTEGER PRIMARY KEY,name TEXT)")
        self.database.executemany("INSERT INTO d1_migrations(name) VALUES (?)", [(file.name,) for file in files])
        self.pins = {script: VERSION for script in readback.scripts("production")}
        for script in self.pins:
            self.add_script(script)
        self.data[self.base + "/workers/domains"] = [{"id": "f" * 32, "service": readback.API,
            "hostname": "mail.moesegfault.dev", "zone_id": readback.forwards.ZONE}]
        self.data[self.base + "/queues"] = [{"queue_id": QUEUE, "queue_name": "amail-trace-events"},
                                             {"queue_id": DLQ, "queue_name": "amail-trace-dlq"}]
        self.data["zones?account.id=" + self.account + "&type=full,partial,secondary,internal&per_page=50&page=1"] = [
            {"id": readback.forwards.ZONE, "account": {"id": self.account}}]
        self.data[f"zones/{readback.forwards.ZONE}/workers/routes"] = []
        self.add_queue(QUEUE, "amail-trace-events", True)
        self.add_queue(DLQ, "amail-trace-dlq", False)

    @property
    def base(self):
        """All synthetic D1 and Worker reads remain in the one selected account."""
        return "accounts/" + self.account

    def add_script(self, script):
        """Populate independent exact immutable and current-resource representations."""
        path = f"{self.base}/workers/scripts/{script}"
        if script == readback.SINK:
            expected, handler = {}, "queue"
        else:
            expected = (readback.expected_bindings("queue-api", QUEUE, realm="production")
                        if script == readback.API else readback.maintenance.expected_bindings("production", QUEUE))
            expected.update({"MAIL_DB": ("d1", self.scope.database), "MAIL_BODIES": ("r2_bucket", self.scope.bucket)})
            handler = "fetch" if script == readback.API else "scheduled"
        self.data[path + "/versions/" + VERSION] = {"id": VERSION, "resources": {
            "bindings": binding_rows(expected), "script": {"handlers": [handler], "named_handlers": []}}}
        self.data[path + "/deployments?per_page=1&page=1"] = {"deployments": [{"id": DEPLOYMENT,
            "strategy": "percentage", "versions": [{"version_id": VERSION, "percentage": 100}]}]}
        self.data[path + "/settings"] = settings(script == readback.SINK)
        self.data[path + "/script-settings"] = settings(script == readback.SINK)
        self.data[f"{self.base}/workers/workers/{script}"] = {"id": "fixture", "name": script, **settings(script == readback.SINK)}
        self.data[path + "/subdomain"] = {"enabled": False, "previews_enabled": False}
        self.data[path + "/schedules"] = {"schedules": []}

    def add_queue(self, identity, name, main):
        """Exact strict API+maintenance producer pair with a bounded private sink."""
        consumers = [{"type": "worker", "script_name": readback.SINK, "dead_letter_queue": "amail-trace-dlq",
                      "settings": {"batch_size": 10, "max_wait_time_ms": 1000, "max_retries": 3,
                                   "retry_delay": 30, "max_concurrency": 2}}] if main else []
        producers = [{"type": "worker", "script": name} for name in (readback.API, readback.MAINTENANCE)] if main else []
        self.data[self.base + "/queues/" + identity] = {"queue_id": identity, "queue_name": name,
            "settings": {"message_retention_period": readback.queues.RETENTION}, "consumers": consumers,
            "producers": producers, "consumers_total_count": len(consumers), "producers_total_count": len(producers)}

    def get(self, path):
        """Return independent successful data; every read is retained for assertions."""
        self.calls.append(("GET", path, None))
        return deepcopy(self.data[path])

    def envelope(self, method, path, body=None):
        """Permit only exact source SELECT/PRAGMA; no actual account request exists."""
        self.calls.append((method, path, deepcopy(body)))
        if method == "POST":
            if path != self.base + "/d1/database/" + self.scope.database + "/query":
                raise AssertionError("wrong database queried")
            rows = [dict(row) for row in self.database.execute(body["sql"]).fetchall()]
            return {"success": True, "result": [{"success": True, "results": rows}]}
        rows = deepcopy(self.data[path])
        value = {"success": True, "result": rows}
        if path.startswith("zones?"):
            value["result_info"] = {"page": 1, "per_page": 50, "count": len(rows), "total_count": len(rows), "total_pages": 1}
        return value

    def r2_empty(self, bucket):
        """Mock a complete successful whole-bucket metadata inspection, never a write."""
        self.calls.append(("R2_METADATA", bucket, None))
        return bucket == self.scope.bucket


class FreshReadbackTests(unittest.TestCase):
    """Hostile reads cannot become held, private, exact graph or absence proof."""

    def setUp(self):
        """No remote forwarding call occurs in synthetic tests."""
        self.provider = Provider()
        self.forward_patch = patch.object(readback, "forward_snapshot", return_value={"fixture": "unchanged"})
        self.forward_patch.start()
        self.addCleanup(self.forward_patch.stop)
        self.addCleanup(self.provider.database.close)

    def verify(self):
        """Exercise the material full graph integration, not a predicate-only stub."""
        return readback.verify(self.provider.scope, self.provider.pins, QUEUE, DLQ, self.provider)

    def reader_fixture(self):
        """Install only the fixed sink with one consumer and zero producers."""
        self.provider.data[self.provider.base + "/workers/domains"] = []
        queue = self.provider.data[self.provider.base + "/queues/" + QUEUE]
        queue["producers"], queue["producers_total_count"] = [], 0

    def test_reader_first_exact_sink_before_any_producer(self):
        """A binding alone is not a deployed compatible reader/privacy proof."""
        self.reader_fixture()
        readback.verify_sink_reader(self.provider.scope, VERSION, QUEUE, DLQ, self.provider)
        self.assertFalse(any(call[0] == "POST" for call in self.provider.calls))
        paths = [call[1] for call in self.provider.calls]
        self.assertTrue(any("/versions/" + VERSION in path for path in paths))
        self.assertEqual(sum("deployments?" in path for path in paths), 2)

    def test_sdk_named_exports_are_replacement_input_not_isolation_success(self):
        """The actual old module can be replaced, never signed off as a queue-only target."""
        self.reader_fixture()
        version = self.provider.data[self.provider.base + "/workers/scripts/" + readback.SINK + "/versions/" + VERSION]
        version["resources"]["script"]["named_handlers"] = [
            {"name": name, "handlers": ["class"]}
            for name in ("ContainerStartupOptions", "MinifyConfig", "R2Range")]
        readback.verify_sink_replacement(self.provider.scope, VERSION, QUEUE, DLQ, self.provider)
        with self.assertRaisesRegex(ValueError, "fresh_capabilities_unverified"):
            readback.verify_sink_reader(self.provider.scope, VERSION, QUEUE, DLQ, self.provider)
        version["resources"]["bindings"] = [{"name": "unexpected", "type": "secret_text"}]
        with self.assertRaisesRegex(ValueError, "fresh_sink_replacement_precondition_unverified"):
            readback.verify_sink_replacement(self.provider.scope, VERSION, QUEUE, DLQ, self.provider)

    def test_reader_first_refuses_absent_consumer_existing_producer_or_public_sink(self):
        """Provisioning allowances cannot admit an uninstalled/unsafe reader."""
        self.reader_fixture()
        path = self.provider.base + "/queues/" + QUEUE
        baseline = deepcopy(self.provider.data[path])
        for field, rows, count_field in (("consumers", [], "consumers_total_count"),
                                        ("producers", [{"type": "worker", "script": readback.API}], "producers_total_count")):
            self.provider.data[path][field] = rows
            self.provider.data[path][count_field] = len(rows)
            with self.subTest(field=field), self.assertRaises(ValueError):
                readback.verify_sink_reader(self.provider.scope, VERSION, QUEUE, DLQ, self.provider)
            self.provider.data[path] = deepcopy(baseline)
        self.provider.data[self.provider.base + "/workers/domains"] = [{
            "id": "f" * 32, "service": readback.SINK, "hostname": "sink.invalid", "zone_id": readback.forwards.ZONE}]
        with self.assertRaisesRegex(ValueError, "fresh_public_domain_unverified"):
            readback.verify_sink_reader(self.provider.scope, VERSION, QUEUE, DLQ, self.provider)

    def test_reader_first_refuses_handler_and_independent_issues_drift(self):
        """Capture and immutable handler are independent pre-producer checks."""
        self.reader_fixture()
        worker = self.provider.data[self.provider.base + "/workers/workers/" + readback.SINK]
        worker["observability"]["issues"]["enabled"] = True
        with self.assertRaisesRegex(ValueError, "fresh_capture_or_surface_unverified"):
            readback.verify_sink_reader(self.provider.scope, VERSION, QUEUE, DLQ, self.provider)
        worker["observability"]["issues"]["enabled"] = False
        version = self.provider.data[self.provider.base + "/workers/scripts/" + readback.SINK + "/versions/" + VERSION]
        version["resources"]["script"]["handlers"] = ["queue", "fetch"]
        with self.assertRaisesRegex(ValueError, "fresh_capabilities_unverified"):
            readback.verify_sink_reader(self.provider.scope, VERSION, QUEUE, DLQ, self.provider)

    def test_graph_witness_constructor_is_not_public_success_admission(self):
        """JSON-only callers cannot accidentally manufacture the private witness."""
        with self.assertRaisesRegex(ValueError, "fresh_successful_readback_required"):
            readback.VerifiedGraph({}, self.provider.scope, QUEUE, DLQ)


    def test_complete_graph_queries_only_new_database_and_preserves_normal_targets(self):
        """Resource substitution is local; v1/normal desired source remains unchanged."""
        before = readback.expected_bindings("queue-api", QUEUE, realm="production")
        graph = self.verify()
        self.assertEqual(set(graph), {"pins", "api_crons", "maintenance_crons", "topology"})
        self.assertEqual(graph["pins"][readback.API], {"deployment": DEPLOYMENT, "version": VERSION})
        self.assertEqual(before, readback.expected_bindings("queue-api", QUEUE, realm="production"))
        posts = [call for call in self.provider.calls if call[0] == "POST"]
        self.assertGreater(len(posts), 20)
        self.assertTrue(all(DATABASE in call[1] for call in posts))
        self.assertTrue(all(call[2]["sql"].startswith(("SELECT ", "PRAGMA ")) for call in posts))
        self.assertEqual(len([call for call in self.provider.calls if call[0] == "R2_METADATA"]), 2)

    def test_new_database_hold_not_old_target(self):
        """A genuinely allowed fresh DB fails even if the original DB could be held."""
        original = self.provider.envelope
        def allowed(method, path, body=None):
            """Model a hostile provider population without violating SQLite triggers."""
            value = original(method, path, body)
            if body and body["sql"] == "SELECT scope,owner_iss,owner_sub,state FROM send_policy":
                value["result"][0]["results"][0]["state"] = "allowed"
            return value
        with patch.object(self.provider, "envelope", side_effect=allowed):
            with self.assertRaisesRegex(ValueError, "fresh_send_hold_unverified"):
                self.verify()

    def test_full_schema_and_all_table_population_required(self):
        """Zero messages alone cannot hide retained projection/contact state."""
        self.provider.database.execute("CREATE TABLE unexpected(id TEXT)")
        with self.assertRaisesRegex(ValueError, "schema_objects_unverified"):
            self.verify()

    def test_retained_nonmessage_table_fails_fresh_population(self):
        """Every application table is checked, not only mail/address/journal counts."""
        self.provider.database.execute("INSERT INTO recipient_blocks VALUES ('issuer','subject','fixture.invalid','operator',NULL,1)")
        with self.assertRaisesRegex(ValueError, "fresh_population_unverified"):
            self.verify()

    def test_every_worker_independent_capture_and_handler(self):
        """No API privacy result substitutes for maintenance or sink Issues."""
        for script in self.provider.pins:
            path = f"{self.provider.base}/workers/workers/{script}"
            old = deepcopy(self.provider.data[path])
            for field in ("issues", "traces"):
                self.provider.data[path]["observability"][field]["enabled"] = True
                with self.subTest(script=script, capture=field), self.assertRaises(ValueError):
                    self.verify()
                self.provider.data[path] = deepcopy(old)
        path = f"{self.provider.base}/workers/scripts/{readback.MAINTENANCE}/versions/{VERSION}"
        self.provider.data[path]["resources"]["script"]["handlers"] = ["fetch", "scheduled"]
        with self.assertRaisesRegex(ValueError, "fresh_capabilities_unverified"):
            self.verify()

    def test_strict_producers_and_empty_dlq(self):
        """Bootstrap cannot inherit sink-install's empty-producer allowance."""
        row = self.provider.data[self.provider.base + "/queues/" + QUEUE]
        row["producers"], row["producers_total_count"] = [], 0
        with self.assertRaisesRegex(ValueError, "producer_drift"):
            self.verify()

    def test_same_version_new_deployment_fails_bracket(self):
        """Deployment replacement is a change even when compiled version is identical."""
        original = self.provider.get
        counts = {}
        def changed(path):
            """Return a different deployment only on the final graph bracket."""
            value = original(path)
            if "deployments?" in path:
                counts[path] = counts.get(path, 0) + 1
                if counts[path] > 1:
                    value["deployments"][0]["id"] = DATABASE
            return value
        with patch.object(self.provider, "get", side_effect=changed), self.assertRaisesRegex(ValueError, "fresh_graph_changed"):
            self.verify()

    def test_failed_or_nonempty_r2_read_never_absence(self):
        """Empty proof requires literal true from the complete metadata adapter."""
        for result in (False, None, 0):
            with patch.object(self.provider, "r2_empty", return_value=result), self.assertRaisesRegex(ValueError, "fresh_r2_empty_unverified"):
                self.verify()

    def test_api_exact_ingress_and_private_sibling_surfaces(self):
        """First paused source keeps API host while forbidding sibling public exposure."""
        path = self.provider.base + "/workers/domains"
        self.provider.data[path][0]["hostname"] = "wrong.invalid"
        with self.assertRaisesRegex(ValueError, "fresh_public_domain_unverified"):
            self.verify()


class CaptureOffTests(unittest.TestCase):
    """Guard settings-only writes on exact owned versions; never contact a provider."""

    def setUp(self):
        """Reuse exact role/immutable fixtures, adding only current writable fields."""
        self.provider = Provider()
        self.addCleanup(self.provider.database.close)
        self.provider.token = "PRIVATE_TOKEN"
        self.records = []
        for script in (readback.API, readback.MAINTENANCE):
            current = self.provider.data[f"{self.provider.base}/workers/workers/{script}"]
            current.update({"tags": ["PRIVATE_TAG"], "subdomain": {"enabled": False, "previews_enabled": False},
                            "references": {"PRIVATE": []}, "updated_on": "before"})
            current["observability"]["issues"] = {"enabled": True}

    def execute(self, script=readback.API, *, patch_action=None):
        """Require intent before a synthetic single PATCH, then perform separate GETs."""
        expected = (readback.expected_bindings("queue-api", QUEUE, realm="production") if script == readback.API
                    else readback.maintenance.expected_bindings("production", QUEUE))
        expected.update({"MAIL_DB": ("d1", DATABASE), "MAIL_BODIES": ("r2_bucket", self.provider.scope.bucket)})
        def record(state, **facts):
            """Keep closed private journal coordinates in memory for assertions."""
            self.records.append({"state": state, **facts})
        def submit(account, token, identity, body):
            """Simulate only a current-resource PATCH while preserving the response state."""
            self.assertEqual(len(self.records), 1)
            self.assertEqual(self.records[0], {"state": "intent", "version": VERSION, "worker_id": "fixture"})
            self.assertEqual(account, self.provider.account)
            self.assertEqual(identity, "fixture")
            self.assertEqual(body["name"], script)
            if patch_action is not None:
                return patch_action(body)
            current = self.provider.data[f"{self.provider.base}/workers/workers/{script}"]
            current["observability"] = deepcopy(body["observability"])
            current["updated_on"] = "after"
            return {"id": identity, "name": script}
        with patch.object(readback, "patch_worker", side_effect=submit) as writer:
            result = readback.capture_off(self.provider, script, VERSION, expected_bindings=expected,
                                         reviewed=settings()["observability"], record=record)
        return result, writer

    def test_api_and_maintenance_correct_only_issues_with_exact_pins(self):
        """Both owned roles retain immutable deployment, storage and non-capture state."""
        for script in (readback.API, readback.MAINTENANCE):
            self.records.clear()
            path = f"{self.provider.base}/workers/workers/{script}"
            snapshot = readback.unaffected(self.provider.data[path])
            result, writer = self.execute(script)
            self.assertEqual(result, "applied")
            self.assertEqual(writer.call_count, 1)
            self.assertEqual(self.provider.data[path]["observability"]["issues"], {"enabled": False})
            self.assertEqual(readback.unaffected(self.provider.data[path]), snapshot)
            self.assertEqual([row["state"] for row in self.records], ["intent", "observed"])

    def test_positive_already_off_skips_patch_and_journal_write(self):
        """A strict positive no-op still brackets immutable capabilities and serving pin."""
        path = f"{self.provider.base}/workers/workers/{readback.API}"
        self.provider.data[path]["observability"]["issues"] = {"enabled": False}
        result, writer = self.execute()
        self.assertEqual(result, "unchanged")
        writer.assert_not_called()
        self.assertEqual(self.records, [])

    def test_live_default_off_and_normalized_inactive_preferences_need_no_patch(self):
        """Actual post-PATCH wire defaults are off, not a demand for another identical write."""
        policy = {"enabled": False, "head_sampling_rate": 1, "redact_query_string": False,
                  "logs": {"enabled": False, "head_sampling_rate": 1, "invocation_logs": True,
                           "persist": True, "destinations": []},
                  "traces": {"enabled": False, "head_sampling_rate": 1, "persist": True, "destinations": []}}
        for script in (readback.API, readback.MAINTENANCE):
            path = f"{self.provider.base}/workers/workers/{script}"
            self.provider.data[path]["observability"] = deepcopy(policy)
            with patch.object(readback, "projection") as project:
                result, writer = self.execute(script)
            self.assertEqual(result, "unchanged")
            project.assert_not_called()
            writer.assert_not_called()
            self.assertEqual(self.records, [])
        path = f"{self.provider.base}/workers/workers/{readback.API}"
        self.provider.data[path]["observability"]["issues"] = {"enabled": True}
        def normalize(body):
            """Model the real successful PATCH followed by default-normalized independent GET."""
            self.provider.data[path]["observability"] = deepcopy(policy)
            return {"id": "fixture", "name": readback.API}
        result, writer = self.execute(patch_action=normalize)
        self.assertEqual(result, "applied")
        writer.assert_called_once()
        self.assertEqual([row["state"] for row in self.records], ["intent", "observed"])

    def test_active_other_capture_or_wrong_bindings_refuses_before_write(self):
        """Only explicit Issues capture may be corrected; other capture or drift refuses."""
        path = f"{self.provider.base}/workers/workers/{readback.API}"
        original = deepcopy(self.provider.data[path])
        for section in (None, "logs", "traces"):
            current = self.provider.data[path]
            target = current["observability"] if section is None else current["observability"][section]
            target["enabled"] = True
            with self.subTest(section=section), self.assertRaises(ValueError):
                self.execute()
            self.assertEqual(self.records, [])
            self.provider.data[path] = deepcopy(original)
        version = self.provider.data[f"{self.provider.base}/workers/scripts/{readback.API}/versions/{VERSION}"]
        version["resources"]["bindings"].append({"name": "EXTRA", "type": "secret_text"})
        with self.assertRaisesRegex(ValueError, "fresh_capture_capabilities_unverified"):
            self.execute()
        self.assertEqual(self.records, [])

    def test_failed_patch_retains_intent_and_never_retries(self):
        """An ambiguous transport exception cannot be reinterpreted as capture-off."""
        action = Mock(side_effect=ValueError("PRIVATE_PROVIDER_BODY"))
        with self.assertRaises(ValueError):
            self.execute(patch_action=action)
        action.assert_called_once()
        self.assertEqual([row["state"] for row in self.records], ["intent"])

    def test_patch_reply_or_unchanged_current_state_is_not_readback_proof(self):
        """Identity mismatch and retained active Issues after a response both fail."""
        for response in ({"id": "other", "name": readback.API}, {"id": "fixture", "name": readback.API}):
            self.records.clear()
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.execute(patch_action=lambda body: response)
            self.assertEqual([row["state"] for row in self.records], ["intent"])

    def test_unaffected_state_drift_after_patch_refuses(self):
        """A valid new Issues flag cannot hide changes to references, tags or previews."""
        def drift(body):
            """Model an unrelated provider mutation during the correction."""
            current = self.provider.data[f"{self.provider.base}/workers/workers/{readback.API}"]
            current["observability"] = deepcopy(body["observability"])
            current["tags"] = []
            return {"id": "fixture", "name": readback.API}
        with self.assertRaisesRegex(ValueError, "fresh_capture_readback_unverified"):
            self.execute(patch_action=drift)
        self.assertEqual([row["state"] for row in self.records], ["intent"])

    def test_same_version_different_deployment_refuses_final_bracket(self):
        """Serving deployment identity is protected independently of immutable version."""
        original = self.provider.get
        count = 0
        def drift(path):
            """Keep pre-write pins stable and replace the final deployment only."""
            nonlocal count
            value = original(path)
            if "deployments?" in path:
                count += 1
                if count == 3:
                    value["deployments"][0]["id"] = DATABASE
            return value
        with patch.object(self.provider, "get", side_effect=drift), self.assertRaisesRegex(ValueError, "fresh_capture_serving_changed"):
            self.execute()
        self.assertEqual([row["state"] for row in self.records], ["intent"])


if __name__ == "__main__":
    unittest.main()
