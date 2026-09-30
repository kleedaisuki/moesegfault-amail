# First live semantic-stage failure: exact hosted run 36677506793

Status: **semantic acceptance failed; mechanism unproven**. This note records
only fixed-label evidence and source-level discriminators. It does not contain
the staging address, message IDs, query text, ZIP, token, mail body, or raw CLI
output.

## Observed boundary

The manual `staging-e2e` dispatch at commit `da86b13` ran on 2026-09-30
06:17:50–06:26:26 UTC. The hosted Windows job
`109765573879` reached native login, exact literal route, two SMTP submissions,
and owner-scoped ZIP/asset verification before entering the opt-in semantic
stage. Its first public failure marker was
`staging_hosted_e2e_failed:mail_semantic_search_failed`; the harness also
reported `address_add_primary:semantic_search_failed` and
`address_add_cleanup:none`. The run is **not** a semantic pass, and route
retirement is not evidence that the semantic request succeeded. Preserve this
failed run rather than silently replacing it with another SMTP run.

The exact marker comes from `semantic_cases` in
`infra/tests/staging_mail_e2e.py`. `semantic_cases` retries only the exact
`semantic_search_failed_http_503_semantic_index_incomplete` label. The plain
`semantic_search_failed` marker says a CLI process returned nonzero and its
stderr did not match the harness's closed parser. It is **not** evidence of
provider failure, indexing delay, quota, or search correctness. Its distinct
timeout, process-start, JSONL and semantic-assertion labels were not reported.

## Source-level diagnostic blind spot

The CLI's `run_search` can print a `202` polling notice, then wrap a failed
poll as `amail: search job <UUID>: mail API messages.search.poll failed: HTTP
...`. The previous harness classifier recognized only a line beginning
`amail: mail API ...`; therefore a typed poll error—including the one index
delay for which the harness is meant to wait—could collapse to the observed
plain marker. An initial POST error could also be a non-allowlisted code, or
the CLI could fail locally. We cannot reconstruct which happened from the
retained fixed labels. The CLI's default `--wait-seconds 900` exceeds the
harness's 90-second subprocess timeout, but that timeout has its own fixed
label and was not observed in this run.

The classifier now accepts only an optional canonical UUID poll prefix and
an allowlisted Worker status/code pair, never the job ID or correlation ID.
Hosted synthetic tests cover a prior `202` line, typed index/provider/quota
poll errors, and an unknown code. This is **future diagnostic repair**, not a
retroactive claim about the live run.

## Smallest next discriminator without new SMTP

First examine a restricted, exact-time Worker application-log or provider
event aggregate for the 06:20–06:26 UTC window. Constrain it to the staging
mail Worker and only the synthetic test principal/run; return fixed counts of
`messages.search` versus `messages.search.poll` invocation status and known
error-code categories, plus whether the request reached the Worker. Do not
export raw URL, request, response, address, query, subject, IDs, or log row.
If the observability product cannot scope those fields safely, report
`unavailable`, not an invented diagnosis. A bounded read-only D1 query can
separately check owner-scoped `search_jobs` state and `embedding_work`/vector
counts, but successful test cleanup soft-deletes messages and removes embedding
work, while fast semantic jobs are deleted after response, so a *current*
empty D1 snapshot cannot prove historical index readiness.

After this classifier passes hosted CI, a fresh **read-only** semantic CLI
request on an existing authorized synthetic mailbox can distinguish initial
POST from poll and typed error from local failure, provided the test account
and corpus are deliberately selected and no content is printed. An empty
mailbox only tests query embedding and job machinery, **not** document
indexing or two-message AND behavior. Repeating SMTP merely to clarify an
opaque marker would create extra mail and obscure the first failure.

Evidence: [hosted run](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36677506793),
`infra/tests/staging_mail_e2e.py`, `infra/tests/staging_semantic_e2e.py`,
`crates/amail/src/main.rs`, `crates/mail-worker/src/search_jobs.rs`.
