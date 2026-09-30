# Staging semantic-search verification boundary

Status: **bounded live staging acceptance for two documents and two pages**.
The [guarded run 36719116852](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36719116852)
at `17abe25`, after [100%-serving Mail Worker pin 36713072636](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36713072636)
to version `8f05fd3f-3c7d-4dad-9c79-2a67f87b1583`, passed native PKCE,
two SMTP submissions, ZIP retrieval, basic two-message semantic search,
search/read/delete, and exact route retirement with primary/cleanup `none`.
Its v5 origin-vector oracle reported
`semantic_exact_cosine_verified:max_abs_error=0.00000000:count=2:order=true:origin_vector=true`.
This verifies exact scores and order for the complete two-document snapshot
across two `limit=1` pages, not tie ordering, three pages, live tamper
rejection, large-mailbox behavior, or production. The earlier bounded
[v4 attempt 36699356379](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36699356379)
at `11127a8` passed native PKCE, two real SMTP fixtures, ZIP, and the basic
two-message semantic behavior check. Its separate exact-cosine phase stopped
before the first CLI page because independently repeated OpenRouter query
vectors disagreed at `f32` bits (`query_vector_unstable`). The exact route was
retired and cleanup reported `none`. Thus this run supports the small-corpus
behavior result but **not** v4 cursor/two-page or exact-score acceptance; the
precondition failure does not diagnose the Worker's cosine arithmetic. See
[the protected oracle](staging-exact-cosine-oracle.md) for the evidence boundary.
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
switch for a semantic dispatch: `gh workflow run ci.yml --ref codex/amail-v0.1.0
-f target=staging-e2e -f confirm=RUN_STAGING_E2E -f semantic=true`. The
`semantic` workflow input is a default-off boolean. A successful optional run
prints `staging_hosted_native_login_inbound_and_semantic_verified`; the basic
run instead prints `staging_hosted_native_login_and_inbound_mail_verified` and
does **not** attest semantic search. No extra address or SMTP submission
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
actual 256-dimensional `f32` vector used on page 1. The current v5 cursor
refers to a completed, owner-bound origin job from which the restricted
operator reads that vector privately; it does not depend on an independently
repeated OpenRouter embedding. The earlier v4 approach could not safely
assume a fresh embedding was identical, as the guarded v4 attempt above
demonstrated. Never add a public vector-returning endpoint just for a test.
The [protected oracle](staging-exact-cosine-oracle.md) documents the current
origin-vector procedure and historical v4 alternatives.
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
whether the full snapshot was independently attested. The successful run above
attests only its two-document/two-page fixture; without an equivalent operator
oracle for another scope, report that scope as **unverified**.

The source contract is documented in `docs/architecture.md` and
`docs/search-jobs.md`. The distinction matters: exact arithmetic over a
truncated candidate set is still an incorrect exact-search result, while a
complete score order says nothing about whether 256-dimensional Qwen
embeddings capture the user's intended meaning.
