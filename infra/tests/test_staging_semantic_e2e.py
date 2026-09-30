"""Mock-only tests for the private staging semantic-search oracle."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location(
    "staging_semantic_e2e", Path(__file__).with_name("staging_semantic_e2e.py")
)
assert SPEC and SPEC.loader
SEM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SEM)


class SemanticOracleTests(unittest.TestCase):
    """Distinguish score, filter, pagination and model-contract failures."""

    def setUp(self) -> None:
        """Create two orthogonal private vectors and stable page fixtures."""

        self.query = [1.0] + [0.0] * 255
        self.a = [1.0] + [0.0] * 255
        self.b = [0.0, 1.0] + [0.0] * 254
        self.documents = {
            "a": self.doc(self.a, "2026-09-29T00:00:01Z"),
            "b": self.doc(self.b, "2026-09-29T00:00:00Z"),
        }
        self.pages = [
            {"messages": [self.hit("a", 1.0, "2026-09-29T00:00:01Z")], "next_cursor": "opaque-one"},
            {"messages": [self.hit("b", 0.0, "2026-09-29T00:00:00Z")], "next_cursor": None},
        ]

    @staticmethod
    def doc(vector: list[float], when: str) -> dict:
        """Represent a restricted operator's complete D1 snapshot row."""

        return {
            "vector": vector, "received_at": when,
            "embedding_model": SEM.MODEL, "embedding_dimensions": SEM.DIMENSIONS,
        }

    @staticmethod
    def hit(message_id: str, score: float, when: str) -> dict:
        """Represent a compact HTTP semantic search summary."""

        return {"id": message_id, "score": score, "received_at": when, "read": False}

    def test_exact_pages_accept_complete_two_page_result(self) -> None:
        """Validate scores and cursor chain with the complete private snapshot."""

        SEM.check_exact_pages(self.pages, self.query, self.documents)

    def test_exact_pages_reject_prefix_duplicate_and_wrong_score(self) -> None:
        """No arbitrary top-K prefix or duplicate page may be called exact."""

        for pages in (
            [{"messages": self.pages[0]["messages"], "next_cursor": None}],
            [self.pages[0], {"messages": self.pages[0]["messages"], "next_cursor": None}],
            [self.pages[0], {"messages": [self.hit("b", 0.2, "2026-09-29T00:00:00Z")], "next_cursor": None}],
        ):
            with self.subTest(pages=pages), self.assertRaises(SEM.SemanticProbeError):
                SEM.check_exact_pages(pages, self.query, self.documents)

    def test_cosine_rejects_bad_dimensions_nonfinite_and_zero(self) -> None:
        """Avoid certifying malformed provider or persisted vectors."""

        for vector in ([1.0], [float("nan")] + [0.0] * 255, [0.0] * 256):
            with self.subTest(vector=vector[:1]), self.assertRaises(SEM.SemanticProbeError):
                SEM.cosine(self.query, vector)

    def test_equal_score_uses_time_then_descending_id(self) -> None:
        """Tie-breaking must match the public semantic cursor order."""

        when = "2026-09-29T00:00:01Z"
        docs = {"b": self.doc(self.a, when), "a": self.doc(self.a, when)}
        pages = [{"messages": [self.hit("b", 1.0, when), self.hit("a", 1.0, when)], "next_cursor": None}]
        SEM.check_exact_pages(pages, self.query, docs)
        pages[0]["messages"].reverse()
        with self.assertRaises(SEM.SemanticProbeError):
            SEM.check_exact_pages(pages, self.query, docs)

    def test_wrong_model_never_receives_a_comparable_score(self) -> None:
        """A model migration cannot silently mix embedding spaces."""

        self.documents["a"]["embedding_model"] = "different-model"
        with self.assertRaises(SEM.SemanticProbeError):
            SEM.check_exact_pages(self.pages, self.query, self.documents)

    def test_malformed_private_inputs_keep_fixed_diagnostic_type(self) -> None:
        """Malformed operator snapshots must not surface raw Python exceptions."""

        cases = [
            (self.query, {"a": {"embedding_model": SEM.MODEL, "embedding_dimensions": 256,
                                  "received_at": "2026-09-29T00:00:01Z"}}),
            (self.query, {"a": self.doc(["secret"] + [0.0] * 255, "2026-09-29T00:00:01Z")}),
            (self.query, {"a": self.doc([10 ** 1000] + [0.0] * 255, "2026-09-29T00:00:01Z")}),
            (None, self.documents),
        ]
        for query, documents in cases:
            with self.subTest(case=len(documents)), self.assertRaises(SEM.SemanticProbeError):
                SEM.check_exact_pages(self.pages, query, documents)
        bad_pages = [
            [{"messages": [{"id": ["unhashable"], "score": 1.0,
                             "received_at": "2026-09-29T00:00:01Z"}], "next_cursor": None}],
            [{"messages": ["raw-private-row"], "next_cursor": None}],
            ["raw-private-page"],
        ]
        for pages in bad_pages:
            with self.subTest(pages_type=type(pages[0]).__name__), self.assertRaises(SEM.SemanticProbeError):
                SEM.check_exact_pages(pages, self.query, self.documents)

    def test_cli_search_checks_combined_predicates_without_state_change(self) -> None:
        """The two-mail live helper must demand negative and read controls."""

        nonce = "0123456789abcdef"
        signal = self.hit("a", 0.8, "2026-09-29T00:00:01Z")
        signal["phrase"] = "signal-private"
        distractor = self.hit("b", 0.7, "2026-09-29T00:00:00Z")
        calls = []

        def search(*args: str) -> list[dict]:
            """Return filtered summaries while recording only argument structure."""

            calls.append(args)
            if "--read" in args or "signal-private-absent" in args:
                return []
            if "--body" in args:
                return [signal]
            return [signal, distractor]

        SEM.check_cli_search(search, "fixture@mail-staging.moesegfault.dev", nonce, signal, distractor)
        self.assertEqual(len(calls), 4)
        self.assertTrue(all("--semantic" in args and "--mailbox" in args for args in calls))


if __name__ == "__main__":
    unittest.main()
