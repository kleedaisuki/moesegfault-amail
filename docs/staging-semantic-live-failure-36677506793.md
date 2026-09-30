# First live semantic-stage failure: exact hosted run 36677506793

Status: **semantic acceptance failed; mechanism unproven**. A later
[empty-mail query-only probe](staging-semantic-query-only-probe.md#first-live-result-2026-09-30)
passed, but does not repair or diagnose this historical two-message failure.
This note records only fixed-label evidence and source-level discriminators. It does not contain
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

## Historical phase-log discriminator: no-go at this boundary

An exact-time Cloudflare Workers Observability query is technically possible:
the repository already has reviewed, bounded, dry, service-filtered readers
for Mail/Role incidents. That is **insufficient for this incident**. The
current Mail `Trace::exit` event records only the closed operation
(`messages_search` or `search_poll`), HTTP status *class*, and a coarse
`error_code` derived from the HTTP status. For example, every HTTP 503 maps to
`service_unavailable`; it does not retain the public API's exact code
(`semantic_index_incomplete`, `semantic_unavailable`, etc.). Unlike Role Cron,
there is no semantic-search phase log. A historical retained event cannot
recover the missing code by parsing its body without violating the logging
privacy boundary, because the API response body is not in the reviewed trace.

The hosted runner deleted its `.temp` CLI home in `finally`, and the harness
suppressed raw CLI output and correlation IDs. Its only public marker has no
request/trace ID. Therefore a service/time-only log query over 06:20–06:26
UTC could at best show a **candidate** search POST/poll and status class,
not establish that it belongs to run 36677506793 or distinguish the typed
cause. This is especially important because the synthetic staging account is
shared across probes. Introducing an account or inferred URL filter into
Workers Observability would still not recover the exact code and risks
handling sensitive metadata. **Do not dispatch a historical Mail phase-log
probe as a root-cause discriminator or weaken the full retained-log privacy
canary for this run.** A bounded read-only D1 query can check current
owner-scoped `search_jobs` and vector counts, but successful cleanup
soft-deletes messages and removes embedding work; fast jobs are deleted after
response. An empty current snapshot cannot prove historical index readiness.

The best non-mail next probe is a **fresh read-only semantic CLI request** on
an already authorized synthetic staging mailbox after the revised classifier
passes hosted CI. Preserve only a fixed POST-versus-poll, status/code label
and duration; suppress the query, result rows, IDs, stderr and correlation
headers. This can distinguish query-provider, quota/job, and local CLI failure
without creating another address or SMTP delivery. If the mailbox is empty,
it only checks query embedding/job machinery, **not** document indexing or
two-message AND behavior; a later deliberate two-fixture acceptance run still
requires its own guarded authorization and cleanup. Repeating SMTP merely to
clarify the opaque first marker would create extra mail and obscure the
failure.

The proposed narrower probe subsequently ran once: [run 36682045842](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36682045842)
reported `empty_query_completed_and_local_cleanup_passed` after a
[100%-serving Worker pin](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36681988920).
It supports query-embedding/job completion on an empty mailbox under the
pinned source, not document-index readiness, lexical AND, semantic score
correctness, or a cause for this earlier failure. See the linked probe note
for exact revision, version, and limitations.

Evidence: [hosted run](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36677506793),
`infra/tests/staging_mail_e2e.py`, `infra/tests/staging_semantic_e2e.py`,
`crates/amail/src/main.rs`, `crates/mail-worker/src/search_jobs.rs`.
