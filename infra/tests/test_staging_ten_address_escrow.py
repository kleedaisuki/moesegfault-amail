"""Hosted synthetic encrypted D1 escrow contracts; never live/migrate/run locally."""

import base64
import json
import sqlite3
import unittest
from unittest import mock

import staging_ten_address_escrow as target
import staging_ten_address_manifest as manifest
from test_staging_ten_address_manifest import KEY, RUN, GEN, plan, SyntheticAEAD


def maximum_plan():
    """Fill a valid object baseline to the exact existing manifest plaintext limit."""
    value = plan()
    objects = value["baseline"]["objects"]
    remaining = manifest.LIMIT - len(manifest.canonical(value))
    digest = "a" * 64
    index = 0
    while remaining > 1900:
        key = f"synthetic-object-{index:04d}-" + "x" * 900
        cost = len(manifest.canonical({key: digest})) - 2 + bool(objects)
        objects[key] = digest
        remaining -= cost
        index += 1
    for prefix, amount in (("synthetic-final-a-", remaining // 2),
                           ("synthetic-final-b-", remaining - remaining // 2)):
        cost = len(manifest.canonical({prefix: digest})) - 2 + 1
        key = prefix + "x" * (amount - cost)
        if not 1 <= len(key) <= 1024 or amount < cost:
            raise AssertionError("synthetic maximum-size fixture invalid")
        objects[key] = digest
    if len(manifest.canonical(value)) != manifest.LIMIT:
        raise AssertionError("synthetic maximum-size fixture length invalid")
    return value


class Database:
    """Host-only in-memory SQLite operations schema; no provider or repository file DB."""

    def __init__(self):
        """Apply isolated test DDL only in memory on GitHub's synthetic test runner."""
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(target.MIGRATION.read_text(encoding="utf-8-sig"))
        self.calls = []
        self.ambiguous = None

    def query(self, sql, params):
        """Model exact query result and optional transport failure AFTER a committed write."""
        self.calls.append((sql, params))
        before = self.db.total_changes
        cursor = self.db.execute(sql, params)
        rows = [dict(row) for row in cursor.fetchall()]
        self.db.commit()
        changes = self.db.total_changes - before
        if self.ambiguous == sql:
            self.ambiguous = None
            raise TimeoutError("synthetic private provider response")
        return target.Result(rows, changes)


class EscrowTests(unittest.TestCase):
    """Exercise real SQLite invariants with synthetic authenticated envelopes only."""

    def setUp(self):
        """Replace crypto for contracts, not a substitute for the separate real cipher CI."""
        self.crypto = mock.patch.object(manifest, "_cipher", SyntheticAEAD)
        self.crypto.start(); self.addCleanup(self.crypto.stop)
        self.world = Database(); self.addCleanup(self.world.db.close)
        self.client = target.Escrow("a" * 32, "synthetic-token", query=self.world.query)
        self.blob = manifest.seal(plan(), KEY, RUN, GEN)

    def prepare(self):
        """Insert authenticated synthetic data and attach a separately assumed valid ID."""
        row = self.client.put(self.blob, KEY, RUN, GEN)
        self.client.attach(RUN, KEY, GEN, "123", self.blob)
        return row

    def test_complete_insert_once_seal_readback_and_one_time_arm(self):
        """Only known changes=1 plus authenticated stable readback produces Arm."""
        self.prepare()
        row, blob = self.client.read(RUN, KEY, GEN)
        self.assertEqual(blob, self.blob); self.assertEqual(row["state"], "sealed")
        self.assertEqual(self.client.put(self.blob, KEY, RUN, GEN)["state"], "sealed")
        permit = self.client.arm(RUN, KEY, GEN, "123", self.blob)
        self.assertEqual(permit.original_run, RUN)
        self.assertEqual(permit.envelope_sha, target.hash_bytes(self.blob))
        self.assertEqual(self.client.read(RUN, KEY, GEN)[0]["state"], "armed")
        before = len(self.world.calls)
        with self.assertRaisesRegex(manifest.ContractFailure, "escrow_arm_not_available"):
            self.client.arm(RUN, KEY, GEN, "123", self.blob)
        self.assertNotIn(target.SQL["arm"], [sql for sql, params in self.world.calls[before:]])

    def test_ciphertext_only_public_coordinates_no_key_or_plain_owner(self):
        """Bound SQL payloads contain only public metadata or authenticated ciphertext."""
        self.prepare()
        payload = repr(self.world.calls)
        for private in (KEY, plan()["owner_sub"], plan()["provenance"]["verified_username"], *plan()["allowed"]):
            # SyntheticAEAD is intentionally plaintext+tag, but its bytes reach SQL only
            # through base64; no decoded private field or key is a bound metadata value.
            self.assertNotIn(private, payload)
        self.assertTrue(all(len(sql.encode()) < 4096 and len(params) <= 100 for sql, params in self.world.calls))
        self.assertTrue(all(len(str(params[-1])) <= 87_384 for sql, params in self.world.calls if sql == target.SQL["part_create"]))
        self.assertFalse(any("DELETE" in sql or "addresses" in sql or "messages" in sql for sql, params in self.world.calls))

    def test_ambiguous_arm_remains_armed_without_permit_or_replay(self):
        """A committed but lost response is not repaired by reading back armed state."""
        self.prepare()
        self.world.ambiguous = target.SQL["arm"]
        with self.assertRaisesRegex(manifest.ContractFailure, "escrow_query_unverified"):
            self.client.arm(RUN, KEY, GEN, "123", self.blob)
        self.assertEqual(self.client.read(RUN, KEY, GEN)[0]["state"], "armed")
        with self.assertRaisesRegex(manifest.ContractFailure, "escrow_arm_not_available"):
            self.client.arm(RUN, KEY, GEN, "123", self.blob)
        self.assertEqual(sum(sql == target.SQL["arm"] for sql, params in self.world.calls), 1)

    def test_zero_change_arm_response_never_authorizes(self):
        """Even an apparent readback candidate cannot replace current transition acknowledgement."""
        self.prepare()
        original = self.client._query
        def changed(sql, params):
            result = original(sql, params)
            return target.Result(result.rows, 0) if sql == target.SQL["arm"] else result
        self.client._query = changed
        with self.assertRaisesRegex(manifest.ContractFailure, "escrow_arm_ack_unverified"):
            self.client.arm(RUN, KEY, GEN, "123", self.blob)
        self.assertEqual(self.client.read(RUN, KEY, GEN)[0]["state"], "armed")

    def test_competing_arm_has_only_one_known_transition(self):
        """Interleave a competing caller after sealed readback but before the UPDATE."""
        self.prepare()
        winner = []
        competitor = target.Escrow("a" * 32, "synthetic-token", query=self.world.query)
        original = self.client._query
        def competing(sql, params):
            if sql == target.SQL["arm"] and not winner:
                winner.append(competitor.arm(RUN, KEY, GEN, "123", self.blob))
            return original(sql, params)
        self.client._query = competing
        with self.assertRaisesRegex(manifest.ContractFailure, "escrow_arm_ack_unverified"):
            self.client.arm(RUN, KEY, GEN, "123", self.blob)
        self.assertEqual(len(winner), 1)
        self.assertEqual(self.client.read(RUN, KEY, GEN)[0]["state"], "armed")
        self.assertEqual(sum(sql == target.SQL["arm"] for sql, params in self.world.calls), 2)

    def test_lost_create_chunk_and_seal_responses_stop_without_retry(self):
        """Committed preparation loss preserves exact data but supplies no arm authority."""
        for operation in ("create", "part_create", "seal"):
            with self.subTest(operation=operation):
                world = Database()
                try:
                    client = target.Escrow("a" * 32, "synthetic-token", query=world.query)
                    world.ambiguous = target.SQL[operation]
                    with self.assertRaisesRegex(manifest.ContractFailure, "escrow_query_unverified"):
                        client.put(self.blob, KEY, RUN, GEN)
                    self.assertEqual(sum(sql == target.SQL[operation] for sql, params in world.calls), 1)
                    self.assertFalse(any(sql == target.SQL["arm"] for sql, params in world.calls))
                    parent = client.parent(RUN)
                    self.assertEqual(parent["state"], "sealed" if operation == "seal" else "writing")
                    self.assertIsNone(parent["armed_at"])
                    # A separately initiated durability operation may finish matching
                    # preparation; it cannot synthesize or replay an arm result.
                    self.assertEqual(client.put(self.blob, KEY, RUN, GEN)["state"], "sealed")
                    self.assertEqual(client.read(RUN, KEY, GEN)[1], self.blob)
                    self.assertFalse(any(sql == target.SQL["arm"] for sql, params in world.calls))
                finally:
                    world.db.close()

    def test_maximum_valid_manifest_roundtrips_all_31_chunks(self):
        """Exercise actual 2MB plaintext serialization, all chunk INSERTs and repeat reads."""
        blob = manifest.seal(maximum_plan(), KEY, RUN, GEN)
        self.assertGreater(len(blob), manifest.LIMIT)
        self.assertLessEqual(len(blob), target.MAX_ENVELOPE)
        row = self.client.put(blob, KEY, RUN, GEN)
        self.assertEqual(row["chunk_count"], 31)
        self.client.attach(RUN, KEY, GEN, "123", blob)
        self.client.arm(RUN, KEY, GEN, "123", blob)
        self.assertEqual(self.client.read(RUN, KEY, GEN)[1], blob)
        inserts = [params for sql, params in self.world.calls if sql == target.SQL["part_create"]]
        self.assertEqual([params[1] for params in inserts], list(range(31)))
        self.assertTrue(all(len(params[-1]) <= 87_384 for params in inserts))
        self.assertEqual(sum(params[2] for params in inserts), len(blob))

    def test_different_ciphertext_or_artifact_never_overwrites(self):
        """Existing coordinates are not a namespace for replacement content."""
        self.prepare()
        other = manifest.seal(plan(), KEY, RUN, GEN)
        with self.assertRaisesRegex(manifest.ContractFailure, "escrow_binding_mismatch"):
            self.client.put(other, KEY, RUN, GEN)
        with self.assertRaisesRegex(manifest.ContractFailure, "escrow_artifact_unverified"):
            self.client.attach(RUN, KEY, GEN, "456", self.blob)
        self.assertEqual(self.client.read(RUN, KEY, GEN)[1], self.blob)

    def test_partial_insert_retained_and_second_envelope_blocked(self):
        """Incomplete preparation reserves the outstanding slot; failure cannot hide it."""
        _, values = target.binding(self.blob, KEY, RUN, GEN)
        self.world.query(target.SQL["create"], values)
        with self.assertRaisesRegex(manifest.ContractFailure, "escrow_chunks_incomplete"):
            self.client.read(RUN, KEY, GEN)
        second = list(values); second[0] = "7654321"
        with self.assertRaises(sqlite3.IntegrityError):
            self.world.query(target.SQL["create"], tuple(second))
        self.assertEqual(self.client.parent(RUN)["state"], "writing")
        self.client.put(self.blob, KEY, RUN, GEN)

    def test_chunk_collision_gap_extra_and_phase_are_rejected(self):
        """The parent fixes every index/size and disallows chunk edits after seal."""
        _, values = target.binding(self.blob, KEY, RUN, GEN)
        self.world.query(target.SQL["create"], values)
        index = 0
        wrong = bytes([self.blob[0] ^ 1]) + self.blob[1:]
        self.world.query(target.SQL["part_create"], (RUN,index,len(wrong),target.hash_bytes(wrong),base64.b64encode(wrong).decode()))
        with self.assertRaisesRegex(manifest.ContractFailure, "escrow_chunk_collision"):
            self.client.put(self.blob, KEY, RUN, GEN)
        with self.assertRaises(sqlite3.IntegrityError):
            self.world.query(target.SQL["part_create"], (RUN,30,1,target.hash_bytes(b"x"),base64.b64encode(b"x").decode()))
        with self.assertRaises(sqlite3.IntegrityError):
            self.world.db.execute(f"UPDATE {target.PARTS} SET chunk_sha=? WHERE original_run=?", ("a"*64,RUN))
        with self.assertRaises(sqlite3.IntegrityError):
            self.world.db.execute(f"DELETE FROM {target.PARTS} WHERE original_run=?", (RUN,))

    def test_schema_change_does_not_become_name_only_approval(self):
        """Missing/added trigger or malformed actual result blocks every write."""
        self.world.db.execute("DROP TRIGGER staging_acceptance_chunk_admission")
        with self.assertRaisesRegex(manifest.ContractFailure, "escrow_schema_unverified"):
            self.client.put(self.blob, KEY, RUN, GEN)
        self.assertEqual(self.world.db.execute(f"SELECT COUNT(*) FROM {target.PARENT}").fetchone()[0], 0)

    def test_server_metadata_boolean_and_oversized_response_are_rejected(self):
        """Typed integer/count contracts are not Python bool equality shortcuts."""
        self.prepare()
        original = self.client._query
        def boolean(sql, params):
            result = original(sql, params)
            if sql == target.SQL["parent"]:
                result.rows[0]["attempt"] = True
            return result
        self.client._query = boolean
        with self.assertRaisesRegex(manifest.ContractFailure, "escrow_parent_unverified"):
            self.client.read(RUN, KEY, GEN)
        self.client._query = lambda *args: target.Result([{"private": "x" * target.MAX_RESPONSE}], 0)
        with self.assertRaisesRegex(manifest.ContractFailure, "escrow_response_unverified"):
            self.client.schema()

    def test_wrong_key_generation_or_coordinates_never_writes(self):
        """The operations adapter never creates an unauthenticated baseline."""
        for key, run, generation in (("cd"*32,RUN,GEN), (KEY,"7654321",GEN), (KEY,RUN,"other")):
            with self.assertRaises(manifest.ContractFailure):
                self.client.put(self.blob,key,run,generation)
        self.assertFalse(any(sql == target.SQL["create"] for sql, params in self.world.calls))

    def terminal(self):
        """Model only the private SQL contract, NOT real independent recovery attestation."""
        self.prepare()
        self.client.arm(RUN,KEY,GEN,"123",self.blob)
        return self.client._finalize(RUN,KEY,GEN,"7654321","b"*40,self.blob)

    def test_terminal_receipt_is_atomic_bound_immutable_and_purge_only(self):
        """Full public receipt and state commit together; permanent parent survives purge."""
        receipt = self.terminal()
        self.assertEqual(receipt["state"],"cleanup_verified")
        self.assertEqual(receipt["cleanup_receipt_sha"],self.client._receipt(receipt))
        self.assertEqual(receipt["cleanup_verifier_run"],"7654321")
        self.assertEqual(receipt["cleanup_check_set"],target.CHECK_SET)
        self.assertEqual(self.client.read(RUN,KEY,GEN)[1],self.blob)
        with self.assertRaises(sqlite3.IntegrityError):
            self.world.db.execute(f"UPDATE {target.PARENT} SET cleanup_verifier_sha=? WHERE original_run=?",("c"*40,RUN))
        with self.assertRaises(sqlite3.IntegrityError):
            self.world.db.execute(f"UPDATE {target.PARENT} SET armed_at=armed_at+1 WHERE original_run=?",(RUN,))
        self.client._purge(RUN,KEY,GEN,self.blob)
        self.assertEqual(self.world.query(target.SQL["aggregate"],(RUN,)).rows,[{"n":0,"bytes":0}])
        self.assertEqual(self.client.parent(RUN),receipt)
        with self.assertRaises(sqlite3.IntegrityError):
            self.world.db.execute(f"DELETE FROM {target.PARENT} WHERE original_run=?",(RUN,))
        with self.assertRaisesRegex(manifest.ContractFailure,"escrow_state_not_preparable"):
            self.client.put(self.blob,KEY,RUN,GEN)

    def test_lost_terminal_response_keeps_ciphertext_and_never_purges(self):
        """A persisted receipt does not turn lost acknowledgement into an automatic purge."""
        self.prepare()
        self.world.ambiguous = target.SQL["receipt"]
        with self.assertRaisesRegex(manifest.ContractFailure,"escrow_query_unverified"):
            self.client._finalize(RUN,KEY,GEN,"7654321","b"*40,self.blob)
        row,blob = self.client.read(RUN,KEY,GEN)
        self.assertEqual(row["state"],"cleanup_verified")
        self.assertEqual(blob,self.blob)
        self.assertFalse(any(sql == target.SQL["purge"] for sql,params in self.world.calls))
        with self.assertRaisesRegex(manifest.ContractFailure,"escrow_receipt_not_available"):
            self.client._finalize(RUN,KEY,GEN,"7654321","b"*40,self.blob)
        self.assertEqual(sum(sql == target.SQL["receipt"] for sql,params in self.world.calls),1)

    def test_competing_terminal_receipt_loser_cannot_purge_or_replace(self):
        """Only the current known winner returns a terminal response; a loser stops."""
        self.prepare()
        winner = []
        competitor = target.Escrow("a"*32,"synthetic-token",query=self.world.query)
        original = self.client._query
        def competing(sql,params):
            if sql == target.SQL["receipt"] and not winner:
                winner.append(competitor._finalize(RUN,KEY,GEN,"8765432","c"*40,self.blob))
            return original(sql,params)
        self.client._query = competing
        with self.assertRaisesRegex(manifest.ContractFailure,"escrow_receipt_ack_unverified"):
            self.client._finalize(RUN,KEY,GEN,"7654321","b"*40,self.blob)
        self.assertEqual(self.client.parent(RUN)["cleanup_verifier_run"],"8765432")
        self.assertEqual(len(winner),1)
        self.assertEqual(self.client.read(RUN,KEY,GEN)[1],self.blob)
        self.assertFalse(any(sql == target.SQL["purge"] for sql,params in self.world.calls))

    def test_attach_interleaved_before_receipt_does_not_commit_stale_digest(self):
        """A changed artifact relation fails CAS before any terminal metadata is written."""
        self.client.put(self.blob,KEY,RUN,GEN)
        original = self.client._query
        competitor = target.Escrow("a"*32,"synthetic-token",query=self.world.query)
        def attaching(sql,params):
            if sql == target.SQL["receipt"]:
                competitor.attach(RUN,KEY,GEN,"123",self.blob)
            return original(sql,params)
        self.client._query = attaching
        with self.assertRaisesRegex(manifest.ContractFailure,"escrow_receipt_ack_unverified"):
            self.client._finalize(RUN,KEY,GEN,"7654321","b"*40,self.blob)
        row,blob = self.client.read(RUN,KEY,GEN)
        self.assertEqual(row["state"],"sealed")
        self.assertEqual(row["artifact_id"],"123")
        self.assertIsNone(row["cleanup_receipt_sha"])
        self.assertIsNone(row["cleanup_verifier_run"])
        self.assertEqual(blob,self.blob)

    def test_arm_interleaved_before_receipt_does_not_commit_stale_digest(self):
        """State and arm timestamp are part of the same receipt CAS observation."""
        self.prepare()
        original = self.client._query
        competitor = target.Escrow("a"*32,"synthetic-token",query=self.world.query)
        def arming(sql,params):
            if sql == target.SQL["receipt"]:
                competitor.arm(RUN,KEY,GEN,"123",self.blob)
            return original(sql,params)
        self.client._query = arming
        with self.assertRaisesRegex(manifest.ContractFailure,"escrow_receipt_ack_unverified"):
            self.client._finalize(RUN,KEY,GEN,"7654321","b"*40,self.blob)
        row,blob = self.client.read(RUN,KEY,GEN)
        self.assertEqual(row["state"],"armed")
        self.assertIsNotNone(row["armed_at"])
        self.assertIsNone(row["cleanup_receipt_sha"])
        self.assertIsNone(row["cleanup_verified_at"])
        self.assertEqual(blob,self.blob)

    def test_purge_requires_receipt_and_stops_on_ambiguous_chunk_delete(self):
        """Partial logical purge resumes only as an explicit separate private invocation."""
        blob = manifest.seal(maximum_plan(),KEY,RUN,GEN)
        self.client.put(blob,KEY,RUN,GEN)
        self.client.attach(RUN,KEY,GEN,"123",blob)
        with self.assertRaisesRegex(manifest.ContractFailure,"escrow_receipt_unverified"):
            self.client._purge(RUN,KEY,GEN,blob)
        self.client._finalize(RUN,KEY,GEN,"7654321","b"*40,blob)
        self.world.ambiguous = target.SQL["purge"]
        with self.assertRaisesRegex(manifest.ContractFailure,"escrow_query_unverified"):
            self.client._purge(RUN,KEY,GEN,blob)
        self.assertEqual(sum(sql == target.SQL["purge"] for sql,params in self.world.calls),1)
        self.assertEqual(self.world.query(target.SQL["aggregate"],(RUN,)).rows[0]["n"],30)
        receipt = self.client.parent(RUN)
        self.client._purge(RUN,KEY,GEN,blob)
        self.assertEqual(self.client.parent(RUN),receipt)
        self.assertEqual(self.world.query(target.SQL["aggregate"],(RUN,)).rows,[{"n":0,"bytes":0}])
        # The committed-but-lost index is observed absent, never DELETE-replayed.
        indexes = [params[1] for sql,params in self.world.calls if sql == target.SQL["purge"]]
        self.assertEqual(indexes,list(range(31)))

    def test_unverified_receipt_or_foreign_blob_preserves_ciphertext(self):
        """A changed verifier relation or envelope cannot grant even private purge."""
        self.terminal()
        different = manifest.seal(plan(),KEY,RUN,GEN)
        with self.assertRaisesRegex(manifest.ContractFailure,"escrow_binding_mismatch"):
            self.client._purge(RUN,KEY,GEN,different)
        original = self.client._query
        def forged(sql,params):
            result = original(sql,params)
            if sql == target.SQL["parent"]:
                result.rows[0]["cleanup_receipt_sha"] = "a"*64
            return result
        self.client._query = forged
        with self.assertRaisesRegex(manifest.ContractFailure,"escrow_receipt_unverified"):
            self.client._purge(RUN,KEY,GEN,self.blob)
        self.assertFalse(any(sql == target.SQL["purge"] for sql,params in self.world.calls))


class BoundaryTests(unittest.TestCase):
    """Exercise exact maximum sizes/budget using synthetic bounded bytes/DDL only."""

    def test_maximum_envelope_chunks_and_response_fit(self):
        """The last slice and base64 expansion stay within D1/app response bounds."""
        length = target.MAX_ENVELOPE
        chunks = [min(target.CHUNK,length-index*target.CHUNK) for index in range((length+target.CHUNK-1)//target.CHUNK)]
        self.assertEqual(len(chunks), 31)
        self.assertEqual(sum(chunks), length)
        self.assertLessEqual(max(((size+2)//3)*4 for size in chunks), 87_384)
        self.assertLess(87_384 + 4096, target.MAX_RESPONSE)
        self.assertTrue(all(len(sql.encode()) < 4096 for sql in target.SQL.values()))

    def test_real_http_contract_rejects_missing_or_malformed_changes(self):
        """The REST adapter never treats absent, boolean or string counters as one ACK."""
        client = target.Escrow("a" * 32, "synthetic-token")
        for meta in (None, {}, {"changes": None}, {"changes": True},
                     {"changes": "1"}, {"changes": -1}, {"changes": 1.0}):
            with self.subTest(meta=meta):
                result = {"success": True, "results": [], "meta": meta}
                payload = json.dumps({"success": True, "result": [result]}).encode()
                with mock.patch.object(target, "request", return_value=payload) as request:
                    with self.assertRaisesRegex(manifest.ContractFailure, "escrow_response_unverified"):
                        client._http(target.SQL["arm"], (RUN,"a"*64,"123"))
                self.assertEqual(request.call_count, 1)
        payload = json.dumps({"success": True, "result": [
            {"success": True, "results": [], "meta": {"changes": 1}}]}).encode()
        with mock.patch.object(target, "request", return_value=payload):
            self.assertEqual(client._http(target.SQL["arm"], (RUN,"a"*64,"123")).changes, 1)

    def test_budget_includes_verified_nonpurged_ciphertext(self):
        """A terminal state flag cannot remove retained chunks from reserved accounting."""
        world = Database()
        self.addCleanup(world.db.close)
        blob = b"synthetic"
        size = target.MAX_ENVELOPE
        count = 31
        reserved = ((size+2)//3)*4 + count*1028 + 4096
        for number in range(1,7):
            run = str(number)
            values = (run,1,manifest.REPOSITORY,target.RECOVERY_WORKFLOW,"a"*40,2,GEN,"b"*64,size,count,reserved)
            world.query(target.SQL["create"], values)
            raw = b"x" * target.CHUNK
            world.query(target.SQL["part_create"], (run,0,len(raw),target.hash_bytes(raw),base64.b64encode(raw).decode()))
            world.db.execute(f"UPDATE {target.PARENT} SET state='cleanup_verified',cleanup_verified_at=unixepoch(),cleanup_receipt_sha=?,cleanup_verifier_run='123',cleanup_verifier_sha=?,cleanup_check_set=? WHERE original_run=?", ("c"*64,"d"*40,target.CHECK_SET,run))
            world.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            world.query(target.SQL["create"], ("7",1,manifest.REPOSITORY,target.RECOVERY_WORKFLOW,"a"*40,2,GEN,"b"*64,size,count,reserved))
        self.assertEqual(world.db.execute(f"SELECT COUNT(*) FROM {target.PARENT}").fetchone()[0], 6)
