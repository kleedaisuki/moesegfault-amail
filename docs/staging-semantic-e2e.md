# Staging semantic-search verification boundary

Status: integrated as an **opt-in hosted stage**, **not deployed evidence**.
The independent helper `infra/tests/staging_semantic_e2e.py` does not send mail,
access credentials, mutate messages, or change a release gate. Its mock-only
tests are in `infra/tests/test_staging_semantic_e2e.py`; hosted integration
tests are in `test_staging_mail_e2e.py` and `test_staging_hosted_e2e.py`. The
GitHub Actions infrastructure job discovers all three under `infra/tests`.
Do not present a passing mock test as a deployed search result.

## Small live corpus

The existing staging SMTP harness calls `check_cli_search` on its **same two
run-owned deliveries**, after ordinary search and before `mark`/`delete`, only
when `--check-semantic` is selected. The hosted wrapper translates the explicit
`AMAIL_STAGING_SEMANTIC_E2E=1` environment switch into that flag; an absent
switch preserves the base inbound gate. The workflow must explicitly pass the
switch for a semantic dispatch; merely running today's basic `staging-e2e`
target does **not** attest semantic search. No extra address or SMTP submission
is made for this stage. The callback captures JSONL and suppresses raw stderr,
passing only the existing message IDs, timestamps and private phrase in memory.

Document embedding is asynchronous via the mail API's five-minute Cron. The
stage retries only `HTTP 503 semantic_index_incomplete` for up to seven minutes
in 30-second intervals, then fails with a fixed `semantic_index_timeout` label.
Provider, auth, quota, malformed-result and other index errors are not retried.
The stage runs four semantic queries **after** indexing; their provider calls
consume quota, so enable it only under a confirmed manual staging dispatch.
The stage checks Qwen-backed semantic execution on two indexed messages, finite
bounded scores, public score/time/ID ordering, mailbox/title/unread predicates,
AND-composition with a unique body phrase, a negative body control, and that
search does not mark mail read.

This is a **small-corpus behavior check**, not proof of exact cosine, exhaustive
retrieval at scale, or cursor pagination. This helper strips the CLI cursor
record and receives only result JSONL rows; a `--limit 1` CLI call alone cannot
verify page continuation. Do not infer semantic relevance quality from these
two synthetic messages: their bodies have no rich semantic contrast.

## Restricted exact-cosine and pagination oracle

`check_exact_pages(pages, query, documents)` requires the raw HTTP pages from
one authenticated staging search, including each opaque `next_cursor`, plus an
**independently complete** authorized/filter-matching D1 snapshot. Each
document record contains the persisted 256-dimensional vector, model slug,
dimension count and API-format UTC timestamp. The query vector must be the
actual 256-dimensional f32 vector persisted in that search job, or a separately
obtained vector using exactly the same OpenRouter route, query input version,
and f32 rounding. A fresh embedding call is not automatically the same vector.
The fast two-message POST deletes its transient search job, so this vector is
not available from the CLI probe. Use a separate restricted fixture that
forces a durable job and capture its query vector while it is running; never
add a public vector-returning endpoint just for a test.
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
