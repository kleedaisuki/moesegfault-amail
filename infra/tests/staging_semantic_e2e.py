"""Private staging semantic-search assertions; never print mail or embeddings.

Call ``check_cli_search`` before the inbound harness marks or deletes its two
run-owned messages. ``check_exact_pages`` is a separate, restricted operator
oracle: it needs the exact query vector used by the Worker, persisted document
vectors, and raw HTTP pages. CLI JSONL alone cannot expose a cursor or prove
that every eligible vector was scored. Neither function sends mail or changes
mail state.
"""

from __future__ import annotations

import math
import re
from typing import Callable, Mapping, Sequence


MODEL = "qwen/qwen3-embedding-8b"
DIMENSIONS = 256
SCORE_TOLERANCE = 1e-5


class SemanticProbeError(Exception):
    """A fixed diagnostic label that contains no private input."""


def require(condition: bool, label: str) -> None:
    """Fail without reflecting a message, vector, or provider response."""

    if not condition:
        raise SemanticProbeError(label)


def finite_number(value: object) -> bool:
    """Reject malformed or unrepresentable JSON-like numeric fields safely."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def cosine(query: Sequence[float], document: Sequence[float]) -> float:
    """Mirror Worker f32-persisted, f64-accumulated exact cosine semantics."""

    require(isinstance(query, (list, tuple)) and isinstance(document, (list, tuple)), "semantic_vector_shape")
    require(len(query) == len(document) == DIMENSIONS, "semantic_vector_dimensions")
    require(
        all(finite_number(x) for x in (*query, *document)),
        "semantic_vector_nonfinite",
    )
    dot = sum(float(a) * float(b) for a, b in zip(query, document))
    qnorm = sum(float(a) * float(a) for a in query)
    dnorm = sum(float(b) * float(b) for b in document)
    denominator = math.sqrt(qnorm * dnorm)
    require(math.isfinite(denominator) and denominator > 0, "semantic_vector_zero_norm")
    return max(-1.0, min(1.0, dot / denominator))


def rank(row: Mapping[str, object]) -> tuple[float, str, str]:
    """Return the public descending score/time/ID tuple after shape checks."""

    score = row.get("score")
    when = row.get("received_at")
    message_id = row.get("id")
    require(finite_number(score), "semantic_score_invalid")
    require(isinstance(when, str) and bool(when), "semantic_time_invalid")
    require(isinstance(message_id, str) and bool(message_id), "semantic_id_invalid")
    return float(score), when, message_id


def check_cli_search(
    search: Callable[..., list[dict]], address: str, nonce: str,
    signal: Mapping[str, object], distractor: Mapping[str, object],
) -> None:
    """Check live provider/index/AND/read behavior on two run-owned messages.

    ``search`` accepts CLI arguments and returns parsed JSONL rows, without
    forwarding raw stderr. The caller must run before marking or deletion and
    must keep the generated query and address out of logs. This small corpus
    proves neither global exactness nor cursor behavior.
    """

    require(isinstance(nonce, str) and bool(re.fullmatch(r"[a-f0-9]{16}", nonce)), "semantic_nonce_invalid")
    require(isinstance(signal, Mapping) and isinstance(distractor, Mapping), "semantic_fixture_invalid")
    signal_id, distractor_id = signal.get("id"), distractor.get("id")
    phrase = signal.get("phrase")
    require(
        isinstance(signal_id, str) and isinstance(distractor_id, str)
        and signal_id != distractor_id and isinstance(phrase, str) and bool(phrase),
        "semantic_fixture_invalid",
    )
    ids = {signal_id, distractor_id}
    title = f"^AMAIL-E2E-{nonce}-(Signal|Distractor)$"
    query = "synthetic staging notification"
    common = ("--mailbox", address, "--title", title, "--regex", "--semantic", query)
    values = search(*common, "--unread", "--limit", "100")
    rows = values
    require(len(rows) == 2 and all(isinstance(row.get("id"), str) for row in rows), "semantic_fixture_missing")
    require({row["id"] for row in rows} == ids, "semantic_fixture_missing")
    require(all(row.get("read") is False for row in rows), "semantic_search_changed_read")
    scores = [rank(row) for row in rows]
    require(scores == sorted(scores, reverse=True), "semantic_order_invalid")
    require(all(-1 <= item[0] <= 1 for item in scores), "semantic_score_range")

    signal_only = search(*common, "--body", phrase, "--unread", "--limit", "100")
    require([row.get("id") for row in signal_only] == [signal_id], "semantic_and_positive")
    absent = search(*common, "--body", phrase + "-absent", "--unread", "--limit", "100")
    require(not absent, "semantic_and_negative")
    read_only = search(*common, "--read", "--limit", "100")
    require(not read_only, "semantic_read_filter_invalid")


def check_exact_pages(
    pages: Sequence[Mapping[str, object]], query: Sequence[float],
    documents: Mapping[str, Mapping[str, object]],
) -> None:
    """Independently compare complete private HTTP pages with exact cosine.

    ``documents`` must be the *entire authorized, filter-matching snapshot*,
    each with ``vector``, ``received_at``, ``embedding_model`` and
    ``embedding_dimensions``. ``query`` must be the precise vector persisted
    in the search job (or independently obtained with identical provider,
    input version and f32 rounding). No API response alone proves corpus
    completeness; the restricted operator must attest that input separately.
    """

    require(isinstance(pages, (list, tuple)) and bool(pages), "semantic_pages_missing")
    require(isinstance(documents, Mapping), "semantic_documents_shape")
    expected = []
    for message_id, row in documents.items():
        require(isinstance(row, Mapping), "semantic_document_shape")
        require(row.get("embedding_model") == MODEL, "semantic_model_mismatch")
        require(row.get("embedding_dimensions") == DIMENSIONS, "semantic_dimensions_mismatch")
        require(isinstance(message_id, str) and isinstance(row.get("received_at"), str), "semantic_fixture_invalid")
        expected.append((cosine(query, row.get("vector")), row["received_at"], message_id))
    expected.sort(reverse=True)
    actual = []
    seen_cursors = set()
    for number, page in enumerate(pages):
        require(isinstance(page, Mapping), "semantic_page_shape")
        rows = page.get("messages")
        require(isinstance(rows, list) and all(isinstance(row, Mapping) for row in rows), "semantic_page_shape")
        cursor = page.get("next_cursor")
        require(cursor is None if number == len(pages) - 1 else isinstance(cursor, str) and bool(cursor), "semantic_cursor_chain")
        if cursor is not None:
            require(cursor not in seen_cursors, "semantic_cursor_repeated")
            seen_cursors.add(cursor)
        for row in rows:
            rank(row)
        actual.extend(rows)
    require(len(actual) == len(expected), "semantic_page_completeness")
    require(len({row.get("id") for row in actual}) == len(actual), "semantic_page_duplicate")
    for row, (score, when, message_id) in zip(actual, expected):
        require(row.get("id") == message_id and row.get("received_at") == when, "semantic_rank_mismatch")
        require(abs(rank(row)[0] - score) <= SCORE_TOLERANCE, "semantic_cosine_mismatch")
