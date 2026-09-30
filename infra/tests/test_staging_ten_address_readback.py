"""Hosted synthetic complete quota inventories; no provider, CLI or local tests."""

import copy
import hashlib
from pathlib import Path
import tomllib
import unittest
from unittest import mock

import staging_ten_address_readback as target
import staging_ten_address_manifest as manifest
from test_staging_ten_address_manifest import KEY, RUN, GEN, OWNER, plan, row


def raw_rule(address="synthetic@" + manifest.DOMAIN, identity="a" * 32):
    """Represent a complete synthetic provider rule, including unprojected priority."""
    return {"id": identity, "enabled": True, "source": "api", "name": "amail " + address,
            "priority": 1, "matchers": [{"type": "literal", "field": "to", "value": address}],
            "actions": [{"type": "worker", "value": ["amail-inbound-staging"]}]}


def object_row(key):
    """Give synthetic LIST metadata enough provenance to detect same-key replacement."""
    return {"key": key, "size": 42, "etag": "a" * 32,
            "last_modified": "2026-10-01T00:00:00Z"}


def envelope(rows):
    """Return exactly one synthetic D1 success batch."""
    return {"success": True, "result": [{"success": True, "results": rows}]}


class ReaderTests(unittest.TestCase):
    """Check inventory completeness and privacy contracts with injected capabilities."""

    def reader(self, request=None, rules=None):
        """Supply synthetic capabilities; default fixture has no allocation/storage."""
        def empty(method, path, body=None):
            if method == "GET":
                return {"success": True, "result": []}
            return envelope([{"n": 0}] if body["sql"].startswith("SELECT COUNT") else [])
        return target.Readback("a" * 32, "b" * 32, "synthetic-token", "synthetic-routing-token",
                               tuple(plan()["resources"]), request=request or empty,
                               rules=rules or (lambda zone, token: []))

    def test_empty_complete_inventory_and_real_staging_config_binding(self):
        """The fixed database/bucket names match reviewed staging configuration."""
        observed = self.reader().read()
        self.assertEqual(observed.value(), {"rows": {}, "rules": [], "global_count": 0, "objects": {}})
        self.assertTrue(self.reader().storage_empty(tuple(plan()["resources"])))
        config = tomllib.loads((Path(__file__).resolve().parents[2] /
                               "crates/mail-worker/wrangler.toml").read_text())
        stage = config["env"]["staging"]
        self.assertEqual(target.DB, stage["d1_databases"][0]["database_id"])
        self.assertEqual(target.BUCKET, stage["r2_buckets"][0]["bucket_name"])

    def test_capabilities_and_resource_scope_before_request(self):
        """Malformed provider identifiers or production recipients never read."""
        for change in ({"account": "unknown"}, {"zone": "../escape"}, {"token": ""},
                       {"routing_token": ""}, {"resources": ("mail@moesegfault.dev",)},
                       {"resources": ()}):
            args = dict(account="a" * 32, zone="b" * 32, token="secret", routing_token="secret",
                        resources=tuple(plan()["resources"]))
            args.update(change)
            request = mock.Mock()
            with self.assertRaises(manifest.ContractFailure):
                target.Readback(**args, request=request)
            request.assert_not_called()

    def test_normalization_retains_unrelated_forward_drop_and_all_raw_fields(self):
        """Full-zone capacity and raw digest cannot hide forward target/priority drift."""
        owned = raw_rule()
        forward = raw_rule("synthetic@example.test", "b" * 32)
        forward["actions"] = [{"type": "forward", "value": ["private@example.test"]}]
        dropped = raw_rule("discard@example.test", "c" * 32)
        dropped["actions"] = [{"type": "drop"}]
        observed = target.normalize_rules([owned, forward, dropped])
        self.assertEqual(len(observed), 3)
        self.assertEqual(observed[0]["worker"], "amail-inbound-staging")
        self.assertEqual(observed[1]["worker"], "non-worker:forward")
        changed = copy.deepcopy(forward)
        changed["actions"][0]["value"] = ["other@example.test"]
        self.assertNotEqual(target.normalize_rules([forward])[0]["raw_digest"],
                            target.normalize_rules([changed])[0]["raw_digest"])
        changed = copy.deepcopy(owned)
        changed["priority"] = 9
        self.assertNotEqual(target.normalize_rules([owned])[0]["raw_digest"],
                            target.normalize_rules([changed])[0]["raw_digest"])

    def test_unknown_matcher_or_action_never_becomes_free_capacity(self):
        """Wildcard, multiple/non-to and unknown action forms fail closed."""
        changes = [dict(matchers=[]), dict(matchers=[{"type": "all"}]),
                   dict(matchers=raw_rule()["matchers"] * 2),
                   dict(actions=[{"type": "unknown", "value": []}]),
                   dict(actions=raw_rule()["actions"] * 2), dict(enabled="true"),
                   dict(id="../escaped"), dict(actions=[{"type": "drop", "value": ["x"]}])]
        for change in changes:
            value = raw_rule()
            value.update(change)
            with self.assertRaises(manifest.ContractFailure):
                target.normalize_rules([value])
        with self.assertRaises(manifest.ContractFailure):
            target.normalize_rules([raw_rule(), raw_rule()])

    def test_complete_allocation_rows_and_independent_count(self):
        """No projection, duplicate, hidden live row or unrelated retired row passes."""
        address = plan()["allowed"][0]
        value = {"address": address, **row(local_part=address.split("@")[0])}
        rows = target.rows_from_batch([value], 1, (address,))
        self.assertEqual(rows[address], {key: item for key, item in value.items() if key != "address"})
        for batch, count in (([value], 0), ([], 1), ([value, value], 2),
                             ([{"address": address, "state": "active"}], 1),
                             ([dict(value, state="retired")], 0)):
            resources = () if batch == [dict(value, state="retired")] else (address,)
            with self.assertRaises(manifest.ContractFailure):
                target.rows_from_batch(batch, count, resources)

    def test_d1_count_bracket_rejects_concurrent_allocation(self):
        """A changing aggregate cannot authorize a baseline even with empty rows."""
        counts = iter([0, 1])
        def request(method, path, body=None):
            return envelope([{"n": next(counts)}] if body["sql"].startswith("SELECT COUNT") else [])
        with self.assertRaisesRegex(manifest.ContractFailure, "d1_count_drift"):
            self.reader(request=request).read()

    def test_repeated_complete_snapshots_detect_count_preserving_rule_drift(self):
        """Both inventories are exhausted; only a raw priority change distinguishes them."""
        first, second = raw_rule(), raw_rule()
        second["priority"] = 9
        values = iter([[first], [second]])
        with self.assertRaisesRegex(manifest.ContractFailure, "readback_snapshot_drift"):
            self.reader(rules=lambda zone, token: next(values)).read()

    def test_r2_short_nonempty_page_requires_explicit_empty_followup(self):
        """A short provider page is not an absence/completion oracle."""
        calls = []
        pages = iter([[object_row("private/one.zip")], []])
        def request(method, path, body=None):
            calls.append(path)
            return {"success": True, "result": next(pages)}
        observed = self.reader(request=request).objects()
        self.assertEqual(observed, {"private/one.zip": target.digest(object_row("private/one.zip"))})
        self.assertEqual(len(calls), 2)
        self.assertIn("start_after=private%2Fone.zip", calls[-1])

    def test_r2_unknown_truncation_duplicate_or_reordered_keys_fail(self):
        """No implicit final page, duplicate key or unsorted cursor is accepted."""
        pages = [dict(success=True, result=[], result_info={"is_truncated": True}),
                 dict(success=True, result=[object_row("b"), object_row("a")]),
                 dict(success=True, result=[object_row("a"), object_row("a")]),
                 dict(success=True, result=[], result_info={"is_truncated": "false"})]
        for page in pages:
            with self.assertRaises(manifest.ContractFailure):
                self.reader(request=lambda *args, **kwargs: page).objects()

    def test_r2_missing_replacement_metadata_fails_closed(self):
        """The API schema permits omissions, but absence proof cannot rely on them."""
        for field in ("size", "etag", "last_modified"):
            item = object_row("existing.zip")
            del item[field]
            with self.assertRaisesRegex(manifest.ContractFailure, "r2_metadata_unverified"):
                self.reader(request=lambda *args, **kwargs: dict(success=True, result=[item])).objects()

    def test_all_message_directions_and_deleted_rows_are_counted(self):
        """Zero current API-visible mail is weaker than this whole-address aggregate."""
        calls = []
        def request(method, path, body=None):
            calls.append(body)
            return envelope([{"n": 1}])
        reader = self.reader(request=request)
        self.assertFalse(reader.storage_empty(reader.resources))
        self.assertNotIn("deleted_at", calls[0]["sql"])
        self.assertNotIn("direction", calls[0]["sql"])
        self.assertEqual(calls[0]["params"], list(reader.resources))
        with self.assertRaises(manifest.ContractFailure):
            reader.storage_empty(("other@" + manifest.DOMAIN,))

    def test_private_adapter_exception_is_fixed_not_provider_text(self):
        """Captured provider error strings never reach test/harness diagnostics."""
        def failed(*args, **kwargs):
            raise RuntimeError("private provider response")
        with self.assertRaisesRegex(manifest.ContractFailure, "^readback_unverified$"):
            self.reader(request=failed).read()


class StorageBaselineTests(unittest.TestCase):
    """Seal and enforce whole-key metadata baselines without retrieving mail bytes."""

    def test_new_or_replaced_r2_object_rejects_campaign_prefix(self):
        """Orphan objects and same-key replacements cannot be hidden by no D1 messages."""
        baseline = manifest.Snapshot({}, [], 0, {"existing.zip": "a" * 64})
        value = plan(baseline)
        for objects in ({"existing.zip": "a" * 64, "new.zip": "b" * 64},
                        {"existing.zip": "b" * 64}, {}):
            with self.assertRaisesRegex(manifest.ContractFailure, "object_inventory_drift"):
                manifest.assert_prefix(value, manifest.Snapshot({}, [], 0, objects), 0, KEY, RUN, GEN)

    def test_cleanup_refuses_unrelated_storage_changes(self):
        """Exact route cleanup is not a success while the sealed R2 baseline changed."""
        value = plan()
        snapshot = manifest.Snapshot({}, [], 0, {"unrelated.zip": "a" * 64})
        with self.assertRaisesRegex(manifest.ContractFailure, "cleanup_object_drift"):
            manifest.reconcile(value, lambda: snapshot, lambda address: self.fail("unexpected delete"),
                               OWNER, KEY, RUN, GEN)
