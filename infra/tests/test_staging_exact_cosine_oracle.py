"""Synthetic-only tests for the restricted staging exact-cosine operator."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import staging_exact_cosine_oracle as oracle


OWNER = (oracle.ISSUER, "synthetic-sub")
ADDRESS = "e2e-0123456789abcdef@mail-staging.moesegfault.dev"
NONCE = "0123456789abcdef"
IDS = ("signal", "distractor")


class ExactCosineTests(unittest.TestCase):
    """Reject malformed snapshots, cursor substitution and wrong scores."""

    def setUp(self) -> None:
        """Build an orthogonal two-vector fixture with discriminating scores."""

        self.query = [1.0] + [0.0] * 255
        self.documents = {
            IDS[0]: {"vector": self.query, "received_at": "2026-09-30T00:00:01.000Z",
                     "embedding_model": oracle.MODEL, "embedding_dimensions": 256},
            IDS[1]: {"vector": [0.0, 1.0] + [0.0] * 254,
                     "received_at": "2026-09-30T00:00:00.000Z",
                     "embedding_model": oracle.MODEL, "embedding_dimensions": 256},
        }
        binding = oracle.query_hash(OWNER, ADDRESS, NONCE)
        self.cursor = base64.urlsafe_b64encode(json.dumps({
            "version": 5, "hash": binding, "generation": 7,
            "vector_commitment": oracle.commitment(binding, self.query),
            "origin_job_id": "12345678-1234-1234-1234-123456789abc",
            "cursor_mac": "a" * 64,
        }).encode()).decode().rstrip("=")
        self.pages = [
            {"messages": [{"id": IDS[0], "score": 1.0, "read": False,
                            "mailbox": ADDRESS, "direction": "inbound",
                            "subject": f"AMAIL-E2E-{NONCE}-Signal",
                            "received_at": self.documents[IDS[0]]["received_at"]}],
             "next_cursor": self.cursor},
            {"messages": [{"id": IDS[1], "score": 0.0, "read": False,
                            "mailbox": ADDRESS, "direction": "inbound",
                            "subject": f"AMAIL-E2E-{NONCE}-Distractor",
                            "received_at": self.documents[IDS[1]]["received_at"]}],
             "next_cursor": None},
        ]

    def verify(self, pages=None, vectors=None, snapshots=None, generations=None):
        """Run the real pure oracle with only deterministic external adapters."""

        pages = self.pages if pages is None else pages
        vectors = [self.query, self.query] if vectors is None else vectors
        snapshots = [self.documents, self.documents] if snapshots is None else snapshots
        generations = [7, 7] if generations is None else generations

        def read(_, __, sql, params):
            """Return only the owner identity; snapshot/count are mocked below."""

            self.assertEqual(sql, oracle.OWNER_SQL)
            self.assertEqual(params, [ADDRESS])
            return [{"owner_iss": OWNER[0], "owner_sub": OWNER[1]}]

        with patch.object(oracle, "d1_rows", side_effect=read), \
             patch.object(oracle, "generation", side_effect=generations), \
             patch.object(oracle, "snapshot", side_effect=snapshots), \
             patch.object(oracle, "origin_vector", side_effect=vectors) as origin, \
             patch.object(oracle, "cli_page", side_effect=pages) as cli:
            error = oracle.verify("f" * 32, "private", "amail", {}, ADDRESS, NONCE, IDS)
            self.assertEqual(cli.call_count, 2)
            self.assertEqual(origin.call_count, 2)
            self.assertIsNone(cli.call_args_list[0].args[-1])
            self.assertEqual(cli.call_args_list[1].args[-1], self.cursor)
            return error

    def test_matching_commitment_and_two_pages_attest_exact_cosine(self) -> None:
        """The positive mock requires both pages and reports zero score error."""

        self.assertEqual(self.verify(), 0.0)

    def test_changed_origin_vector_invalidates_snapshot(self) -> None:
        """The origin vector cannot change while two pages are checked."""

        changed = self.query.copy()
        changed[1] = oracle.f32(0.1)
        with self.assertRaisesRegex(oracle.OracleError, "^oracle_snapshot_changed$"):
            self.verify(vectors=[self.query, changed])
        signed_zero = self.query.copy()
        signed_zero[1] = -0.0
        with self.assertRaisesRegex(oracle.OracleError, "^oracle_snapshot_changed$"):
            self.verify(vectors=[self.query, signed_zero])

    def test_cursor_binds_actual_vector_generation_and_filter(self) -> None:
        """Tampered commitments, generation and filter hash fail before page two."""

        for field, replacement in (("vector_commitment", "0" * 64), ("generation", 8),
                                   ("hash", "0" * 64), ("origin_job_id", "invalid"),
                                   ("cursor_mac", "invalid")):
            with self.subTest(field=field):
                raw = json.loads(base64.urlsafe_b64decode(self.cursor + "=" * (-len(self.cursor) % 4)))
                raw[field] = replacement
                cursor = base64.urlsafe_b64encode(json.dumps(raw).encode()).decode().rstrip("=")
                pages = [dict(self.pages[0], next_cursor=cursor), self.pages[1]]
                with self.assertRaises(oracle.OracleError):
                    self.verify(pages=pages)

    def test_wrong_score_or_second_page_fails(self) -> None:
        """A score mismatch or a missing second result is not an exact oracle."""

        bad_score = [self.pages[0], {"messages": [dict(self.pages[1]["messages"][0], score=0.1)],
                                     "next_cursor": None}]
        missing = [self.pages[0], {"messages": [], "next_cursor": None}]
        for pages in (bad_score, missing):
            with self.subTest(pages=len(pages[1]["messages"])), self.assertRaises(oracle.OracleError):
                self.verify(pages=pages)

    def test_provider_drift_cannot_be_mistaken_for_origin_vector_scoring(self) -> None:
        """A second-page score computed from orthogonal q2 fails against D1 q1."""

        # The live oracle does not call the provider. Its independent reference
        # is the f32 vector retained by the first completed search job.
        q2_score = 1.0
        page_two = dict(self.pages[1], messages=[dict(
            self.pages[1]["messages"][0], score=q2_score)])
        with self.assertRaisesRegex(oracle.OracleError, "^semantic_cosine_mismatch$"):
            self.verify(pages=[self.pages[0], page_two])

    def test_generation_change_rejects_a_cross_epoch_comparison(self) -> None:
        """A concurrent mailbox mutation invalidates even otherwise exact pages."""

        with self.assertRaisesRegex(oracle.OracleError, "^oracle_snapshot_changed$"):
            self.verify(generations=[7, 8])

    def test_exact_ties_use_time_then_id_not_provider_arrival_order(self) -> None:
        """The shared independent rank checker requires deterministic tie order."""

        query = self.query
        docs = {
            "older": {"vector": query, "received_at": "2026-09-30T00:00:00.000Z",
                      "embedding_model": oracle.MODEL, "embedding_dimensions": 256},
            "newer-a": {"vector": query, "received_at": "2026-09-30T00:00:01.000Z",
                        "embedding_model": oracle.MODEL, "embedding_dimensions": 256},
            "newer-b": {"vector": query, "received_at": "2026-09-30T00:00:01.000Z",
                        "embedding_model": oracle.MODEL, "embedding_dimensions": 256},
        }
        order = ["newer-b", "newer-a", "older"]
        pages = [{"messages": [{"id": ident, "score": 1.0,
                                 "received_at": docs[ident]["received_at"]}],
                  "next_cursor": f"opaque-{number}" if number < 2 else None}
                 for number, ident in enumerate(order)]
        oracle.check_exact_pages(pages, query, docs)
        inverted = [pages[1], pages[0], pages[2]]
        with self.assertRaisesRegex(oracle.SemanticProbeError, "^semantic_rank_mismatch$"):
            oracle.check_exact_pages(inverted, query, docs)

    def test_near_tie_uses_exact_score_before_newer_timestamp(self) -> None:
        """A score gap below display tolerance still controls cursor rank order."""

        almost = [1.0, oracle.f32(0.001)] + [0.0] * 254
        docs = {
            "best-older": {"vector": self.query,
                           "received_at": "2026-09-30T00:00:00.000Z",
                           "embedding_model": oracle.MODEL, "embedding_dimensions": 256},
            "almost-newer": {"vector": almost,
                             "received_at": "2026-09-30T00:00:01.000Z",
                             "embedding_model": oracle.MODEL, "embedding_dimensions": 256},
        }
        gap = 1.0 - oracle.cosine(self.query, almost)
        self.assertGreater(gap, 0)
        self.assertLess(gap, oracle.SCORE_TOLERANCE)
        pages = [{"messages": [{"id": ident,
                                 "score": oracle.cosine(self.query, docs[ident]["vector"]),
                                 "received_at": docs[ident]["received_at"]}],
                  "next_cursor": "opaque" if index == 0 else None}
                 for index, ident in enumerate(("best-older", "almost-newer"))]
        oracle.check_exact_pages(pages, self.query, docs)
        with self.assertRaisesRegex(oracle.SemanticProbeError, "^semantic_rank_mismatch$"):
            oracle.check_exact_pages([pages[1] | {"next_cursor": "opaque"},
                                      pages[0] | {"next_cursor": None}], self.query, docs)

    def test_generation_or_vector_mutation_fails(self) -> None:
        """A changed D1 vector after search invalidates the entire comparison."""

        changed = {key: dict(value) for key, value in self.documents.items()}
        changed[IDS[0]]["vector"] = [0.0, 1.0] + [0.0] * 254
        with self.assertRaisesRegex(oracle.OracleError, "^oracle_snapshot_changed$"):
            self.verify(snapshots=[self.documents, changed])

    def test_f32_rounding_and_invalid_vectors(self) -> None:
        """Round once like Rust; reject nonfinite, zero, and wrong dimensions."""

        self.assertEqual(oracle.f32(0.1), 0.10000000149011612)
        for value in ([0.0] * 256, [1.0], [float("nan")] + [0.0] * 255):
            with self.assertRaises(oracle.OracleError):
                oracle.validate_vector(value)

    def test_snapshot_enforces_complete_owner_and_model_metadata(self) -> None:
        """D1 cannot silently return a prefix or a mixed-model row."""

        base = {"id": IDS[0], "address": ADDRESS, "direction": "inbound",
                "received_at": 1_780_185_601_000, "is_read": 0,
                "embedding_json": json.dumps(self.query), "embedding_model": oracle.MODEL,
                "embedding_dimensions": 256, "embedding_input_version": 1}
        other = dict(base, id=IDS[1])
        def read(_, __, sql, params):
            """Supply deterministic count/vector data for one snapshot."""

            return [{"n": 2}] if sql == oracle.COUNT_SQL else [base, other]

        with patch.object(oracle, "d1_rows", side_effect=read):
            self.assertEqual(set(oracle.snapshot("f" * 32, "private", OWNER, ADDRESS, IDS)), set(IDS))
        with patch.object(oracle, "d1_rows", side_effect=lambda *a: [{"n": 3}]):
            with self.assertRaisesRegex(oracle.OracleError, "^oracle_owner_inventory_changed$"):
                oracle.snapshot("f" * 32, "private", OWNER, ADDRESS, IDS)
        wrong = dict(other, embedding_input_version=2)
        with patch.object(oracle, "d1_rows", side_effect=lambda _, __, sql, params:
                          [{"n": 2}] if sql == oracle.COUNT_SQL else [base, wrong]):
            with self.assertRaisesRegex(oracle.OracleError, "^oracle_vector_metadata$"):
                oracle.snapshot("f" * 32, "private", OWNER, ADDRESS, IDS)

    def test_origin_read_selects_vector_without_signing_key(self) -> None:
        """The restricted SELECT never exposes a reusable cursor MAC key."""

        origin_id, digest = oracle.cursor_origin(self.cursor, oracle.query_hash(
            OWNER, ADDRESS, NONCE), 7)
        row = {"id": origin_id, "state": "done", "expires_at": 4_000_000_000_000,
               "origin_job_id": origin_id,
               "is_origin": 1, "query_input_version": 1,
               "query_model": oracle.MODEL, "vector_commitment": digest,
               "query_vector_json": json.dumps(self.query)}

        def read(_, __, sql, params):
            """Assert the real query projection and owner predicate."""

            self.assertEqual(sql, oracle.ORIGIN_SQL)
            self.assertEqual(params, [origin_id, *OWNER])
            self.assertNotIn("cursor_key", sql)
            return [row]

        with patch.object(oracle, "d1_rows", side_effect=read):
            self.assertEqual(oracle.origin_vector("f" * 32, "private", OWNER,
                                                  origin_id, digest), self.query)
        for changed in ({"state": "running"}, {"is_origin": 0},
                        {"query_model": "other"}, {"query_input_version": 2},
                        {"expires_at": 0}, {"query_vector_json": "[]"}):
            with self.subTest(changed=changed), patch.object(
                    oracle, "d1_rows", return_value=[dict(row, **changed)]):
                with self.assertRaises(oracle.OracleError):
                    oracle.origin_vector("f" * 32, "private", OWNER, origin_id, digest)

    def test_missing_foreign_origin_is_not_a_vector_oracle(self) -> None:
        """The owner-scoped D1 read fails closed when it returns no origin row."""

        origin_id, digest = oracle.cursor_origin(self.cursor, oracle.query_hash(
            OWNER, ADDRESS, NONCE), 7)
        foreign_owner = (OWNER[0], "different-account")

        def read(_, __, sql, params):
            """Model D1 enforcing the exact owner predicate for a foreign user."""

            self.assertEqual(sql, oracle.ORIGIN_SQL)
            self.assertEqual(params, [origin_id, *foreign_owner])
            return []

        with patch.object(oracle, "d1_rows", side_effect=read):
            with self.assertRaisesRegex(oracle.OracleError, "^oracle_vector_unavailable$"):
                oracle.origin_vector("f" * 32, "private", foreign_owner, origin_id, digest)

    def test_native_cli_cursor_record_is_captured_privately(self) -> None:
        """A JSONL cursor record is part of the native product contract."""

        first = self.pages[0]
        output = (json.dumps(first["messages"][0]) + "\n"
                  + json.dumps({"next_cursor": self.cursor}) + "\n").encode()
        proc = subprocess.CompletedProcess([], 0, output, b"")
        with patch.object(oracle.subprocess, "run", return_value=proc) as run:
            self.assertEqual(oracle.cli_page("amail", {}, ADDRESS, NONCE, None), first)
            self.assertEqual(run.call_args.kwargs["env"], {})
        malformed = subprocess.CompletedProcess([], 0, output + b'{"id":"extra"}\n', b"")
        with patch.object(oracle.subprocess, "run", return_value=malformed):
            with self.assertRaisesRegex(oracle.OracleError, "^oracle_cli_page_shape$"):
                oracle.cli_page("amail", {}, ADDRESS, NONCE, None)


if __name__ == "__main__":
    unittest.main()
