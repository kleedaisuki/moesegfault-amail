# Accepted staging: bounded native transactions

## Scope and implementation

Base: `848c214a16adebec16d88eaf338bacf65dd7b083`. This implements the
[reviewed latency ADR](mail-cron-accepted-projection-latency-adr-2026-10-01.md),
not a new mail, schema, resumable-cursor or scheduling contract.

`accepted.rs` prepares at most eight consecutive additional text chunks and
submits one native `Database.batch` per group. Each unchanged statement retains
the full journal token, owner, immutable archive/provider, reservation, and
tombstone predicate. One clock snapshot is bound across a group, then refreshed
for the next group. The existing adapter debits every member before native
submission; rejected, rolled-back and no-op members are not refunded.

The group result must contain exactly one successful result per submitted
member. A rejected promise, short result array or unsuccessful result stops this
attempt before final publication. It does not cause an immediate retry. Existing
exact-token release and durable due scheduling handle recovery. Neither direct
nor trigger-expanded change counts establish staging progress. Final publication
remains the separate atomic message/indexed-ledger/sent transaction, with its
existing exact-sent resolution. DELETE uses the existing owner/live RETURNING
predicate; no HTTP response, idempotency key, ZIP or migration contract changes.

| Bound | Before | After |
| --- | ---: | ---: |
| Maximum additional UTF-8 chunks | 66 | 66 |
| Staging SQL statement tokens | 66 | 66 |
| Sequential native staging calls | 66 | 9 |
| Body bytes held in one prepared group | 60,000 | <=480,000 |
| Bound parameters per statement | 12 | 12 |
| Five maximum items, healthy whole-Cron top-level SQL | 379 | 379 |
| Same fixture, native individual calls | 364 | 34 |
| Same fixture, native batches / member statements | 5 / 15 | 50 / 345 |

The five-item count includes 45 staging batches (330 members) plus five final
publication batches (15 members). These are application/native submission
counts, not SQLite trigger-expanded row-change counts or a new platform quota.
The 800 invocation and 380 outbound grants remain unchanged.

## Native test evidence design

All fixtures use the real built Rust/Wasm Worker, native workerd D1 and R2, full
migrations, and local-only synthetic network destinations. Accepted seed rows
consume the production one-use held-canary trigger and immediately expire that
grant; global sending stays held. No email provider is called. Setup/readback
uses native bindings outside the observer.

The new `accepted-stage-observer.mjs` unwraps observed statements and invokes
exactly one native `batch` for each production submission; it never substitutes
individual runs. Its statistics expose only counts, indices, byte sizes and
same-clock booleans. The unique `accepted-stage-batch.test.mjs` contains nine
tests covering:

- Maximum decimal-four-million-byte ASCII and mixed-width UTF-8 bodies, exact
  reconstruction, ordered indices, nine groups `[8,8,8,8,8,8,8,8,2]`, no chunk
  `.run()`, and replay without another staging write or reservation mutation.
- Additional-chunk boundaries `0,1,7,8,9,65,66`, including no empty transaction.
- A native trigger failure on chunk 20: the complete third group rolls back,
  chunks 1..16 survive invisibly, and a fresh due/lease retry completes exactly.
- A promise rejection, truncated result or `success=false` returned **after**
  native group-three commit: 24 invisible chunks survive, but no sent/live row
  is published before a fresh retry.
- Two concurrent native Cron writers: pause old token after group one, explicitly
  expire its lease, let a new token stage all groups and pause before publication.
  Resume the old writer while the journal is still accepted under the new token.
  A fixture-only marker in chunk nine proves old-token writes are no-ops, and
  old publication/release cannot change the new token. Restore the marker before
  releasing the legitimately prepared final transaction, then verify exact body.
  This marker is an isolation discriminator, not a claim that production accepts
  arbitrary out-of-band edits to its database.
- Public authenticated DELETE during grouped legacy repair: hidden accepted row,
  foreign/repeated 404, first owner 204 with persisted tombstone, no resurrection,
  and eventual native GC of message/chunks/archive.

Existing HTTP/Cron race tests continue to cover accepted HTTP 202/replay and
DELETE. Existing maintenance liveness tests now inspect native group membership
and maintain per-member cutoff accounting. Their real 66*300ms slow-member test
still represents 19.8 seconds; a new nine*2s native-call test discriminates
round-trip amplification while retaining later cleanup. Neither artificial delay
is a production benchmark. The existing whole-Cron native counter still asserts
379 statements, now with the call/member breakdown above.

## Validation and adoption boundary

Only static `rustfmt`, `node --check`, and scoped Git whitespace checks are run
locally. No build, project tests, package installation, provider access, deploy,
policy release or Cron resume is performed. Initial source/test candidate
`2c67564bf6cdddca3c63261c0dd082d0e7b90cb6` received independent source GO in
[its review](review-accepted-stage-batching-2026-10-01.md). After PR29 and PR31
merged, the implementation was rebased onto
`8ca1815307ae515aa5cacc6a25bb161779bb7be7`; `test:accepted-stage` and its
non-deploying native Worker CI step now register the nine new cases separately
from the default suite. Existing Routing, embedding, liveness and final diagnostic
focused suites remain registered. Exact integrated source/test review and hosted
evidence are still pending; registration is not a claim of successful execution.

Native D1 batch has ordered transactional semantics and the documented 30-second
duration applies to the entire batch, not each member. Successful completion
requires each group to fit that envelope. Nine calls reduce repeated binding
round trips but do not prove account-level CPU, latency, transport settlement,
memory or full-Cron wall-time admission. Paid staging/production measurement of
maximum valid ASCII/UTF-8 drafts remains required before live rollout. The
original source cutover and held-Cron constraints remain in force.

Primary references: [D1 database API](https://developers.cloudflare.com/d1/worker-api/d1-database/),
[D1 limits](https://developers.cloudflare.com/d1/platform/limits/), and the ADR's
explicit conditional-latency derivation. Research alternatives and measurement
assumptions are preserved in the ADR rather than expanded into unrelated cursor
or parallel-call machinery here.
