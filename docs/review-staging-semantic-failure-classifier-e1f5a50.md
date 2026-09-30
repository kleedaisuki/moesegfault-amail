# Review: semantic poll-error classifier after run 36677506793

Scope: commit `e1f5a50`, CLI search and API error formatting, Worker search-job
error paths, the hosted harness tests, and the proposed read-only discriminator.
This is a source review, not a local heavy test, deployment, provider query, or
retroactive diagnosis of the failed live run. **Decision: GO for hosted CI of
the diagnostic repair; not a semantic acceptance GO.**

## Verified boundary

`run_search` prints an optional `202` progress line and wraps poll errors as
`search job <UUID>: {ApiFailure}`. `ApiFailure` prints a fixed operation,
HTTP status, code and an opaque correlation ID. The new expression recognizes
that actual poll wrapper and still accepts the unwrapped initial POST error.
It rejects stderr larger than 64 KiB; only a three-digit status and a code
from `SAFE_API_CODES` enter the returned label. The UUID, correlation ID,
semantic query, address, response body and non-allowlisted code are not
interpolated into output. A non-allowlisted code becomes `unknown_code`.
`semantic_cases` retries only `semantic_search_failed_http_503_semantic_index_incomplete`
within its seven-minute deadline, so the new quota, provider, corrupt-index,
resource-limit and unknown-code labels do not create an unsafe retry path.

The added tests exercise a progress line followed by three typed poll errors,
and a non-allowlisted code. Existing tests exercise an unwrapped initial POST
index-incomplete error. They do **not** exercise malformed UUID wrappers,
unrelated operation names, trailing private lines, or oversized stderr. Those
are useful negative tests before trusting the classifier as a general-purpose
diagnostic, but their absence does not block this bounded staging repair: the
harness does not print raw stderr, and the retry predicate is a single fixed
label from its own `amail search` invocation. The parser uses `re.search`, not
a whole-stderr grammar, so a second canonical-looking line could be selected
after unrelated text; this is diagnostic ambiguity, not an observed privacy
leak. If this helper is reused for less-controlled processes, pin expected
operation (`messages.search` or `.poll`) and validate the whole allowable
stderr sequence rather than extending the search expression again.

## What a read-only discriminator can establish

The failed run discarded its CLI stderr and request/job correlation IDs. A
current D1 snapshot cannot reconstruct a completed fast job (the Worker
deletes it) or the exact error from a released/retried poll; message cleanup
also invalidates an index-readiness inference. A current authenticated CLI
query can test the **current** POST/poll path, but neither prove the historical
failure's mechanism nor validate the old two-message AND behavior once those
fixtures are gone. An empty mailbox can at most exercise query preparation,
provider embedding and job machinery; it does not test document embedding.

A time-bounded Worker log aggregate could discriminate whether some
`messages.search` or `messages.search.poll` calls reached the Worker and which
fixed status/code categories occurred in the run window, **if retained logs
actually contain those fields**. It cannot attribute a row to this exact
request merely by window: the current privacy-preserving trace schema has no
principal, query, mailbox, job ID or retained request ID from the failed CLI.
Only an independently established unique candidate count and deployment/time
pin would support a stronger inference, still labelled as an inference.
Provider event aggregates may show provider activity or quota, not the CLI's
precise failure. The proposed query should therefore be explicitly
`unavailable`/`ambiguous` unless source shape, retention, access and candidate
uniqueness are verified without exporting raw rows. No new SMTP is justified
to investigate this historical opaque label.

## Evidence and follow-up

- `infra/tests/staging_mail_e2e.py:182-225,778-805` — bounded classifier and
  exact retry predicate.
- `infra/tests/test_staging_mail_e2e.py:435-515` — original and new cases.
- `crates/amail/src/main.rs:499-559` and `crates/amail/src/api.rs:345-382` —
  emitted progress/wrapped error grammar.
- `crates/mail-worker/src/search_jobs.rs:190-275,350-365,515-560` — typed
  provider/index failures and job lifecycle.
- `docs/staging-semantic-live-failure-36677506793.md` — observed run and
  proposed read-only investigation.

Next: require hosted CI for `e1f5a50`; then prefer a restricted, no-payload
historical log-shape/count query before any fresh semantic request. Do not
report the 36677506793 failure as a confirmed index delay or provider outage.
