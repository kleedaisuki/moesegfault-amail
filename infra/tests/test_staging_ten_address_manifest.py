"""Synthetic manifest/recovery contracts; no CLI, provider or real crypto I/O."""

from __future__ import annotations

import copy
import hashlib
import hmac
from pathlib import Path
import re
import unittest
from unittest import mock

import staging_ten_address_manifest as target

KEY = "ab" * 32
RUN = "1234567"
GEN = "test-key-v1"
OWNER = "synthetic-b"


def row(state="active", owner=OWNER, saved=None, created=1000, reconcile=0,
        local_part="synthetic", slot=0, next_reconcile_at=0):
    """Construct a normalized synthetic D1 row without real account data."""

    return {"owner_iss": target.ISSUER, "owner_sub": owner, "state": state,
            "created_at": created, "cf_rule_id": saved, "needs_reconcile": reconcile,
            "local_part": local_part, "slot": slot, "next_reconcile_at": next_reconcile_at}


def rule(address, identity="synthetic-rule"):
    """Construct the only exact rule shape eligible for supported deletion."""

    return {"id": identity, "address": address, "enabled": True,
            "source": "api", "name": f"amail {address}", "worker": "amail-ingress-staging"}


def plan(snapshot=None):
    """Build a deterministic fixture; its values are never used with staging."""

    return target.build(KEY, RUN, GEN, OWNER, "a" * 40,
                        "00000000-0000-0000-0000-000000000001", 1000,
                        snapshot or target.Snapshot({}, [], 0))


class SyntheticAEAD:
    """Authentication-only fake for envelope control-flow tests, NOT encryption.

    Production never selects this class. It deliberately provides no privacy;
    hosted AES-GCM integration remains a separate pinned-dependency prerequisite.
    """

    def __init__(self, key):
        """Keep the synthetic test key only in fixture memory."""
        self.key = key

    def encrypt(self, nonce, data, associated):
        """Append a synthetic tag to exercise envelope byte boundaries."""
        return data + hmac.new(self.key, nonce + associated + data, hashlib.sha256).digest()

    def decrypt(self, nonce, data, associated):
        """Reject altered associated data or ciphertext in synthetic contracts."""
        body, tag = data[:-32], data[-32:]
        if not hmac.compare_digest(tag, self.encrypt(nonce, body, associated)[-32:]):
            raise ValueError("synthetic authentication failure")
        return body


class ManifestTests(unittest.TestCase):
    """Exercise fail-closed private plan and exact recovery without side effects."""

    def test_names_fit_worker_and_reconstruct(self):
        """128-bit base32 identities fit even the eleventh prefix."""
        aliases = target.candidates(KEY, RUN)
        self.assertEqual(aliases, target.candidates(KEY, RUN))
        self.assertEqual(len(set(aliases)), 11)
        self.assertTrue(all(len(a.split("@")[0]) <= 32 for a in aliases))
        self.assertTrue(all(re.fullmatch(r"qt[0-9]{1,2}-[a-z2-7]{26}@mail-staging\.moesegfault\.dev", a)
                            for a in aliases))
        self.assertNotEqual(aliases, target.candidates(KEY, "7654321"))
        with self.assertRaisesRegex(target.ContractFailure, "run_coordinates_invalid"):
            target.candidates(KEY, RUN, "2")

    def test_reserved_oracle_matches_source(self):
        """A newly reserved service name cannot escape hosted contract coverage."""
        source = Path(__file__).resolve().parents[2] / "crates/mail-worker/src/lib.rs"
        declaration = source.read_text(encoding="utf-8").split("const RESERVED: &[&str] = &[")[1].split("];", 1)[0]
        self.assertEqual(tuple(re.findall(r'"([a-z-]+)"', declaration)), target.RESERVED)

    def test_canonical_map_deduplicates_variants_not_submissions(self):
        """Raw ADMIN is tested independently but shares the admin baseline."""
        value = plan()
        self.assertIn("ADMIN", value["submissions"])
        self.assertEqual(len(value["resources"]), 36)
        target.validate(value, KEY, RUN, GEN)
        duplicate = copy.deepcopy(value)
        duplicate["resources"].append(duplicate["resources"][0])
        with self.assertRaisesRegex(target.ContractFailure, "manifest_plan_invalid"):
            target.validate(duplicate, KEY, RUN, GEN)

    def test_global_headroom_counts_pending_and_every_owner(self):
        """188 application allocations fail despite zero provider rules."""
        rows = {f"other-{i}@example.test": row("pending", "foreign", created=1) for i in range(187)}
        plan(target.Snapshot(rows, [], 187))
        rows["another@example.test"] = row("deleting", "another", created=1)
        with self.assertRaisesRegex(target.ContractFailure, "global_headroom_missing"):
            plan(target.Snapshot(rows, [], 188))
        with self.assertRaisesRegex(target.ContractFailure, "global_inventory_incomplete"):
            plan(target.Snapshot(rows, [], 0))

    def test_provider_and_owner_gates_independent(self):
        """Provider headroom and B emptiness are independent admission checks."""
        rules = [rule(f"other-{i}@example.test", str(i)) for i in range(189)]
        with self.assertRaisesRegex(target.ContractFailure, "provider_headroom_missing"):
            plan(target.Snapshot({}, rules, 0))
        with self.assertRaisesRegex(target.ContractFailure, "owner_not_empty"):
            plan(target.Snapshot({"existing@example.test": row("provisioning")}, [], 1))

    def test_envelope_readback_and_binding(self):
        """Test protocol authentication with a fake, never claim real encryption."""
        with mock.patch.object(target, "_cipher", side_effect=SyntheticAEAD):
            blob = target.seal(plan(), KEY, RUN, GEN)
            self.assertEqual(target.artifact_readback(blob, blob, "123", KEY, RUN, GEN), plan())
            for altered, run_id, generation in ((blob[:-1] + bytes([blob[-1] ^ 1]), RUN, GEN),
                                                (blob, "7654321", GEN), (blob, RUN, "another-key")):
                with self.assertRaisesRegex(target.ContractFailure, "manifest_authentication_failed"):
                    target.open_manifest(altered, KEY, run_id, generation)
            with self.assertRaisesRegex(target.ContractFailure, "artifact_not_durable"):
                target.artifact_readback(blob, blob, "", KEY, RUN, GEN)
            with self.assertRaisesRegex(target.ContractFailure, "artifact_not_durable"):
                target.artifact_readback(blob, blob[:-1], "123", KEY, RUN, GEN)

    def test_crypto_unavailable_is_not_fallback_cipher(self):
        """Missing dependency stops sealing instead of writing cleartext."""
        with mock.patch.object(target, "_cipher", side_effect=target.ContractFailure("crypto_unavailable")):
            with self.assertRaisesRegex(target.ContractFailure, "crypto_unavailable"):
                target.seal(plan(), KEY, RUN, GEN)

    def live(self, value, count=1):
        """Create the exact prefix of synthetic active rows and rules."""
        aliases = value["allowed"][:count]
        return target.Snapshot({a: row(saved=str(i), local_part=a.split("@")[0], slot=i)
                                for i, a in enumerate(aliases)},
                               [rule(a, str(i)) for i, a in enumerate(aliases)], count)

    def test_prefix_and_external_drift(self):
        """Ten positives do not suffice if another allocation masks quota."""
        value = plan()
        current = self.live(value, 10)
        target.assert_prefix(value, current, 10, KEY, RUN, GEN)
        current.rows["foreign@example.test"] = row("pending", "foreign")
        with self.assertRaisesRegex(target.ContractFailure, "global_or_owner_drift"):
            target.assert_prefix(value, target.Snapshot(current.rows, current.rules, 11), 10, KEY, RUN, GEN)

    def test_recovery_includes_unexpected_reserved_and_eleventh(self):
        """Whole-plan recovery does not depend on acknowledged success ledger."""
        value = plan()
        names = [value["allowed"][10], f"admin@{target.DOMAIN}"]
        current = target.Snapshot({a: row("pending", local_part=a.split("@")[0]) for a in names}, [], 2)
        self.assertEqual(set(target.recovery_actions(value, current, OWNER, KEY, RUN, GEN)), set(names))

    def test_foreign_duplicate_and_saved_rule_block_delete(self):
        """A good rule cannot conceal another rule deleted by the Worker."""
        value = plan()
        current = self.live(value)
        for bad in (rule(value["allowed"][0], "duplicate"), rule("foreign@example.test", "saved-foreign")):
            rows = copy.deepcopy(current.rows)
            if bad["id"] == "saved-foreign":
                rows[value["allowed"][0]]["cf_rule_id"] = "saved-foreign"
            with self.assertRaisesRegex(target.ContractFailure, "recovery_rule_unsafe"):
                target.recovery_actions(value, target.Snapshot(rows, [*current.rules, bad], 1), OWNER, KEY, RUN, GEN)
        current.rows[value["allowed"][0]]["owner_sub"] = "foreign"
        with self.assertRaisesRegex(target.ContractFailure, "recovery_resource_not_owned"):
            target.recovery_actions(value, current, OWNER, KEY, RUN, GEN)

    def test_operational_baseline_is_preserved(self):
        """Preexisting role rule is not a cleanup target."""
        address = f"postmaster@{target.DOMAIN}"
        base = target.Snapshot({}, [rule(address, "operational")], 0)
        value = plan(base)
        self.assertEqual(target.recovery_actions(value, base, OWNER, KEY, RUN, GEN), ())
        with self.assertRaisesRegex(target.ContractFailure, "baseline_resource_changed"):
            target.recovery_actions(value, target.Snapshot({}, [], 0), OWNER, KEY, RUN, GEN)

    def test_cleanup_retains_tombstone_and_does_not_retry_ambiguous(self):
        """Supported delete occurs once and final retired state is accepted."""
        value = plan()
        current = self.live(value)
        retired = target.Snapshot({value["allowed"][0]: row("retired",
                                  local_part=value["allowed"][0].split("@")[0],
                                  next_reconcile_at=-1)}, [], 0)
        read = mock.Mock(side_effect=[current, current, retired])
        delete = mock.Mock()
        target.reconcile(value, read, delete, OWNER, KEY, RUN, GEN)
        delete.assert_called_once_with(value["allowed"][0])
        denied = mock.Mock(side_effect=TimeoutError("synthetic private marker"))
        with self.assertRaisesRegex(target.ContractFailure, "^delete_outcome_ambiguous$"):
            target.reconcile(value, lambda: current, denied, OWNER, KEY, RUN, GEN)
        self.assertEqual(denied.call_count, 1)

    def test_unsettled_tombstone_and_wrong_recovery_owner(self):
        """A retired label alone cannot prove provider reconciliation."""
        value = plan()
        current = target.Snapshot({value["allowed"][0]: row("retired", reconcile=1,
                                  local_part=value["allowed"][0].split("@")[0])}, [], 0)
        with self.assertRaisesRegex(target.ContractFailure, "retirement_unsettled"):
            target.recovery_actions(value, current, OWNER, KEY, RUN, GEN)
        with self.assertRaisesRegex(target.ContractFailure, "recovery_owner_mismatch"):
            target.recovery_actions(value, self.live(value), "foreign", KEY, RUN, GEN)

    def test_callback_failures_and_malformed_state_are_fixed_labels(self):
        """Untrusted adapter text and invalid state containers never escape."""
        read = mock.Mock(side_effect=ValueError("synthetic private marker"))
        delete = mock.Mock()
        with self.assertRaisesRegex(target.ContractFailure, "^snapshot_read_failed$"):
            target.reconcile(plan(), read, delete, OWNER, KEY, RUN, GEN)
        delete.assert_not_called()
        bad = row()
        bad["state"] = []
        with self.assertRaisesRegex(target.ContractFailure, "^row_shape_invalid$"):
            target.Snapshot({"bad@example.test": bad}, [], 1).validate()

    def test_full_row_schema_matches_all_address_migrations(self):
        """Projection must include every actual column, not a convenient subset."""
        root = Path(__file__).resolve().parents[2] / "crates/mail-worker/migrations"
        initial = (root / "0001_initial.sql").read_text(encoding="utf-8")
        table = initial.split("CREATE TABLE IF NOT EXISTS addresses (", 1)[1].split(");", 1)[0]
        columns = set(re.findall(r"^\s*([a-z_]+)\s+(?:TEXT|INTEGER)\b", table, re.MULTILINE))
        for migration in sorted(root.glob("*.sql")):
            columns.update(re.findall(r"ALTER TABLE addresses ADD COLUMN ([a-z_]+)\b",
                                      migration.read_text(encoding="utf-8")))
        self.assertEqual(target.ROW_KEYS | {"address"}, columns)

    def test_local_part_slot_and_schedule_drift_are_not_projected_away(self):
        """Count-preserving unrelated row edits must still stop the quota claim."""
        address = "foreign@example.test"
        base = target.Snapshot({address: row("pending", "foreign", local_part="foreign")}, [], 1)
        value = plan(base)
        for field, replacement in (("local_part", "changed"), ("slot", 1), ("next_reconcile_at", -1)):
            with self.subTest(field=field):
                changed = copy.deepcopy(base.rows)
                changed[address][field] = replacement
                current = target.Snapshot(changed, [], 1)
                with self.assertRaisesRegex(target.ContractFailure, "unrelated_row_drift"):
                    target.assert_prefix(value, current, 0, KEY, RUN, GEN)
                with self.assertRaisesRegex(target.ContractFailure, "cleanup_unrelated_drift"):
                    target.reconcile(value, lambda: current, mock.Mock(), OWNER, KEY, RUN, GEN)

    def test_schedule_and_slot_types_fail_closed(self):
        """Signed schedules are valid; missing fields, bool and out-of-range slots are not."""
        for field, invalid in (("slot", True), ("slot", 10), ("next_reconcile_at", True),
                               ("next_reconcile_at", 2 ** 63), ("local_part", "")):
            bad = row()
            bad[field] = invalid
            with self.subTest(field=field, invalid=invalid):
                with self.assertRaisesRegex(target.ContractFailure, "row_shape_invalid"):
                    target.Snapshot({"bad@example.test": bad}, [], 1).validate()
        incomplete = row()
        del incomplete["next_reconcile_at"]
        with self.assertRaisesRegex(target.ContractFailure, "row_shape_invalid"):
            target.Snapshot({"bad@example.test": incomplete}, [], 1).validate()


if __name__ == "__main__":
    unittest.main()
