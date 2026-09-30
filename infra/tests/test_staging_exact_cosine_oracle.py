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
    """Reject malformed snapshots, drift, cursor substitution and wrong scores."""

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
            "version": 4, "hash": binding, "generation": 7,
            "vector_commitment": oracle.commitment(binding, self.query),
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

    def verify(self, pages=None, vectors=None, snapshots=None):
        """Run the real pure oracle with only deterministic external adapters."""

        pages = self.pages if pages is None else pages
        vectors = [self.query, self.query] if vectors is None else vectors
        snapshots = [self.documents, self.documents] if snapshots is None else snapshots

        def read(_, __, sql, params):
            """Return only the owner identity; snapshot/count are mocked below."""

            self.assertEqual(sql, oracle.OWNER_SQL)
            self.assertEqual(params, [ADDRESS])
            return [{"owner_iss": OWNER[0], "owner_sub": OWNER[1]}]

        with patch.object(oracle, "d1_rows", side_effect=read), \
             patch.object(oracle, "generation", side_effect=[7, 7]), \
             patch.object(oracle, "snapshot", side_effect=snapshots), \
             patch.object(oracle, "provider_vector", side_effect=vectors), \
             patch.object(oracle, "cli_page", side_effect=pages) as cli:
            error = oracle.verify("f" * 32, "private", "private", "amail", {}, ADDRESS, NONCE, IDS)
            self.assertEqual(cli.call_count, 2)
            self.assertIsNone(cli.call_args_list[0].args[-1])
            self.assertEqual(cli.call_args_list[1].args[-1], self.cursor)
            return error

    def test_matching_commitment_and_two_pages_attest_exact_cosine(self) -> None:
        """The positive mock requires both pages and reports zero score error."""

        self.assertEqual(self.verify(), 0.0)

    def test_changed_provider_vector_never_scores(self) -> None:
        """A single changed rounded coordinate is not a score tolerance."""

        changed = self.query.copy()
        changed[1] = oracle.f32(0.1)
        with self.assertRaisesRegex(oracle.OracleError, "^query_vector_unstable$"):
            self.verify(vectors=[self.query, changed])
        signed_zero = self.query.copy()
        signed_zero[1] = -0.0
        with self.assertRaisesRegex(oracle.OracleError, "^query_vector_unstable$"):
            self.verify(vectors=[self.query, signed_zero])

    def test_cursor_binds_actual_vector_generation_and_filter(self) -> None:
        """Tampered commitments, generation and filter hash fail before page two."""

        for field, replacement in (("vector_commitment", "0" * 64), ("generation", 8),
                                   ("hash", "0" * 64)):
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
