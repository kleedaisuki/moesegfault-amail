# Independent review: accepted projection staging ADR

Date: 2026-10-01. Reviewed design-only commit
`500378178cac07e1ae902d6875b554fd5f779cd3` against baseline
`59ab7a55f38c4646e08cdf2539176fff2ab4a46d`.

## Verdict and scope

**GO for the narrow implementation described in the ADR; no substantive design
defect found in the inspected scope.** This is not implementation acceptance,
hosted-test evidence, deployment admission, or a hard Cron-completion guarantee.
The reviewed diff adds one document and changes no executable behavior.

Inspected actual baseline `accepted.rs`, `database.rs`, outbound admission and
repair, text partitioning, draft validation, foreground send/error/idempotency
paths, public visibility guards, migration triggers, previous work-unit and
cutover knowledge, and official public documentation. No project test/build,
provider call, hosted dispatch, push, deployment, or production edit was made.
This review artifact is committed in its own `.temp` worktree.

## Checked contracts

| Area | Evidence and conclusion |
| --- | --- |
| Chunk bound | `lib.rs:validate_draft` caps text plus HTML/assets estimate at 4,000,000 bytes. `text_parts` produces <=60,000-byte UTF-8 pieces; full pieces lose at most three boundary bytes. Thus at most 67 total pieces / 66 additional UPSERTs, including mixed-width text. Eight/group gives nine calls, sizes `[8,8,8,8,8,8,8,8,2]`. |
| Native batch | [D1 binding contract](https://developers.cloudflare.com/d1/worker-api/d1-database/) documents ordered transaction execution and whole-sequence rollback on member failure. Grouping must invoke one actual native batch, not observer-expanded `run()` calls. |
| Budget | `database.rs:Database::batch` checks shared invocation/phase identity and debits the member count before the native promise. Grouping changes round trips, not submitted statement tokens. Normal maximum path including two setup statements is 75 statements / 16 calls. Loose resolution-plus-release envelope is 77 / 18. Excluding setup, worst-case 75 per-item remains compatible with `2+5*75=377 <=380`, under the 800 invocation ceiling. |
| Ownership/concurrency | Each stage statement rechecks exact accepted journal identity, token/lease, reservation and existing-message ownership, and tombstone absence. Final three-member publication remains separate. D1 serialization plus token replacement fences earlier writers; a zero-change stage batch is not terminal authority. No persisted cursor or reused unverified prefix is introduced. |
| Failure/visibility | Earlier committed groups remain hidden: direct reads and search reject exact-owned accepted journals; unpublished chunks lack a visible message. Group failure leaves accepted journal/ZIP/reservation for deterministic full replay. Ambiguous committed returns must not authorize publication. Existing exact-sent resolution and caught-error exact-token release remain authoritative. |
| Triggers/schema | `message_text_chunks` has composite primary key and no production trigger in the inspected migrations. Search/embedding/requeue triggers occur on final message publication, within its transaction. No schema migration is needed for grouping. This does not waive migration 0010's existing unfenced-to-fenced quiescent cutover obligations. |
| HTTP compatibility | Shared grouping affects foreground staging too, but changes only invisible rollback granularity. Foreground adapter has no maintenance admission budget; accepted/sent same-key replay and 202 contract remain unchanged. Fresh send still maps projection failure to fixed 503 `send_index_pending`; no provider resend or recharge is added. |

## Timing claims: accepted only as conditional bounds

[D1 limits](https://developers.cloudflare.com/d1/platform/limits/) footnote 4
explicitly applies 30 seconds to the entire batch call; 100 parameters applies
per statement, not across the group. However that service/API limit is not
independent proof of end-to-end Workers binding settlement through transport,
queueing, or transparent retries. The ADR explicitly identifies this inference
as an assumption, so its arithmetic is not a false hard guarantee.

With settlement assumption `D=30s`, staging is `9D=270s`, normal setup plus one
item is `16D=480s`, and loose late-failure envelope is `18D=540s`. Additional
outbound items are admitted only while elapsed <=55s and the 15-second slice
remains open; one must not multiply the slow full-item envelope by five.
The ADR's `55+540+30+30=655s` also assumes successful original archive GET/body
within 30 seconds and aggregate invocation CPU within 30 seconds. It is neither
a baseline R2 deadline nor a whole-Cron bound.

[Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
separate short-Cron CPU allowance from 900-second wall lifetime. Native R2 GET
and persistence-confirming final Queue awaits have no admitted cancellation or
settlement guarantee here. Their residual uncertainty cannot be covered by
nominal diagnostic headroom. Eight genuinely 14-second SQL executions would
exceed a batch's service envelope and fail; grouping removes network round-trip
amplification, not database work or all liveness failures.

## Required implementation evidence, not defects in this design

- Keep every guard/UPSERT unchanged, one timestamp per group, <=8 prepared
  statements live, no empty native batch, exact result count and success checks.
- Preserve N-token observer accounting and actual transaction rollback. Run the
  ADR's real native failure, ambiguous-return, token-loss, DELETE, UTF-8/max-text,
  HTTP replay and continuation discriminators on exact integrated hosted source.
- <=480,000 body bytes/group is a payload bound, **not** an RSS bound. JS strings,
  Wasm allocations, binding serialization, retained ZIP/draft and concurrent
  foreground work share isolate resources; Workers documents 128 MB per isolate,
  including JS and Wasm, not per invocation. Maximum workload measurements must
  separate binding wall latency from D1 `meta.duration`, and retain CPU/memory
  admission as independent gates.
- Deployment remains separately gated on effective account/runtime contracts,
  exact serving/privacy/sink/schema pins and authorized observations. Data-safe
  rollback to fenced serial staging reopens latency infeasibility; it is not
  liveness-safe rollback merely because no migration was added.

The ADR's research comparisons are appropriately scoped: [Beldi (OSDI 2020)](https://www.usenix.org/conference/osdi20/presentation/zhang-haoran)
motivates durable transactional progress, and [Anvil (OSDI 2024)](https://www.usenix.org/conference/osdi24/presentation/sun-xudong)
distinguishes reconciliation liveness from safety. Neither establishes provider
timing or formally verifies this implementation. Native grouping is a coherent
smaller first experiment; generation-scoped resumability remains a separate
design if measured healthy groups cannot complete.
