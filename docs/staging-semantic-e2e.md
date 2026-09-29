# Staging semantic-search verification boundary

Status: prepared assertions, **not deployed evidence**. The independent helper
`infra/tests/staging_semantic_e2e.py` does not send mail, access credentials,
mutate messages, or change a release gate. Its mock-only tests are in
`infra/tests/test_staging_semantic_e2e.py`; the hosted CI owner must run them on
GitHub Actions. Do not present a passing mock test as a deployed search result.

## Small live corpus

After the existing staging SMTP harness has observed its two run-owned messages,
but **before** `mark` or `delete`, call `check_cli_search(search, address, nonce,
signal, distractor)`. The callback must be the harness's captured, JSONL-parsed
CLI search function with raw stderr suppressed. Supply each message's `id`,
`received_at`, and the signal's private `phrase`; do not log arguments or rows.
This checks Qwen-backed semantic execution on two indexed messages, finite
bounded scores, public score/time/ID ordering, mailbox/title/unread predicates,
AND-composition with a unique body phrase, a negative body control, and that
search does not mark mail read. A bounded `semantic_index_incomplete` retry may
be performed by the caller while indexing catches up; do not convert other
provider or index errors into a passing retry. Four semantic searches consume
provider quota, so run only under the manual staging dispatch, never on push.

This is a **small-corpus behavior check**, not proof of exact cosine, exhaustive
retrieval at scale, or cursor pagination. The CLI emits only result JSONL and
does not expose `next_cursor`; a `--limit 1` CLI call alone cannot verify page
continuation. Do not infer semantic relevance quality from these two synthetic
messages: their bodies have no rich semantic contrast.

## Restricted exact-cosine and pagination oracle

`check_exact_pages(pages, query, documents)` requires the raw HTTP pages from
one authenticated staging search, including each opaque `next_cursor`, plus an
**independently complete** authorized/filter-matching D1 snapshot. Each
document record contains the persisted 256-dimensional vector, model slug,
dimension count and API-format UTC timestamp. The query vector must be the
actual 256-dimensional f32 vector persisted in that search job, or a separately
obtained vector using exactly the same OpenRouter route, query input version,
and f32 rounding. A fresh embedding call is not automatically the same vector.
The helper recomputes all cosine scores using f64 accumulation and norms,
checks the complete descending `(score, received_at, id)` sequence, rejects
duplicate or omitted messages, and checks cursor termination/repetition. Its
`1e-5` score tolerance accounts for f32 persistence and serialized scores;
ordering itself is exact against the provided vectors.

The restricted operator must establish that `documents` is the *whole*
matching authorized snapshot, not a convenient prefix. Preserve one mailbox
generation for all pages; mutation should separately produce HTTP 409
`search_cursor_stale`. Raw vectors, query text, message IDs, addresses, D1 rows,
and HTTP bodies must remain in restricted ephemeral memory or repository
`.temp`, never GitHub logs/artifacts. Log only fixed case labels, count,
maximum absolute score error, status/error codes, and a boolean indicating
whether the full snapshot was independently attested. Without that operator
oracle, report exact cosine and cursor pagination as **unverified**.

The source contract is documented in `docs/architecture.md` and
`docs/search-jobs.md`. The distinction matters: exact arithmetic over a
truncated candidate set is still an incorrect exact-search result, while a
complete score order says nothing about whether 256-dimensional Qwen
embeddings capture the user's intended meaning.
