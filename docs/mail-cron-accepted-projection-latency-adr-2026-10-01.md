# ADR: bounded accepted-projection staging round trips

Date: 2026-10-01. Status: **recommended design, not implemented, hosted-tested,
deployed, or release-approved**. Inspected baseline: merged PR #27 main
`59ab7a55f38c4646e08cdf2539176fff2ab4a46d`. Isolated worktree:
`.temp/accepted-projection-latency-bound`.

Only this English artifact is written. No production code, project test/build,
provider request/mutation, workflow dispatch, push, or deployment is performed.
Official public documentation was retrieved on the date above. The concurrent
R2/embedding and final-diagnostics owners supplied their bounded-body and
uncancellable-binding contracts; their candidates are not baseline acceptance.

## 1. Decision

Replace the serial per-chunk `run()` loop in shared `accepted::stage` with
**ordered native D1 batches of at most eight existing fenced UPSERT statements**.
Keep stale-index cleanup as its own fenced statement and publication as the
existing separate three-statement transaction. Do not create a durable cursor,
projection-generation schema, cancellation race, new retry loop, smaller draft
contract, or parallel writer pool.

At the service-valid maximum of 66 additional chunks, staging becomes nine
native binding calls instead of 66. Each batch still spends its member count
under the existing private D1 adapter. Construct only the current group; use
one lease-time snapshot for its members and preserve every existing predicate.
No soft elapsed-time check interrupts an admitted successful projector.

This removes a demonstrated **round-trip amplification** mechanism, not all
ways a Cron can exceed its lifetime. A hard whole-Cron wall-time or universal
eventual-completion claim remains unjustified: native R2 GET and final Queue
publication have no admitted hard settlement bound, and D1 service limits are
not separately documented end-to-end binding-delivery SLAs.

## 2. Evidence and the exact gap

The [whole-unit implementation](mail-cron-work-unit-admission-implementation-2026-10-01.md)
correctly removed our voluntary 15-second prefix cutoff, but explicitly records
`66 * 14s = 924s`: a legal per-call delay can make chunk staging alone exceed
Cron's 900-second wall lifetime. The 20-minute lease protects correctness after
termination; it cannot extend the invocation or make a restarted prefix finish.
The existing 66-by-300-ms hosted fixture discriminates the old voluntary cutoff,
not the platform-lifetime counterexample.

Current [D1 limits](https://developers.cloudflare.com/d1/platform/limits/) list
30 seconds for query duration and explicitly extend that limit to the **entire
batch call** in footnote 4. They also retain 1,000 Paid queries/invocation,
100 parameters/query, 100,000-byte SQL, and 2,000,000-byte value/row limits.
These are product limits, not proof of this account's effective configuration.
The [D1 batch contract](https://developers.cloudflare.com/d1/worker-api/d1-database/)
provides ordered execution, one transaction, rollback on failure, and reduced
network round trips. It does not parallelize member SQL or exempt statements
from limits. This makes bounded groups a supported platform mechanism rather
than an application-invented transaction protocol.

[Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
separate five-minute Cron's 30-second Paid CPU allowance from its 15-minute
wall lifetime; waiting on I/O is not Worker CPU. Keep CPU/RSS and effective-plan
admission independent of SQL-call arithmetic.

## 3. Data/state model and invariant preservation

| Owner | Existing invariant | Effect of grouping |
| --- | --- | --- |
| `send_requests` | Exact owner, idempotency key, payload hash, provider ID and `accepted` state authorize projection | Every member retains the exact guard; no inferred provider resend |
| Projection token/lease | Only the live opaque token may write; reclaim fences old HTTP/Cron projectors | Unchanged token and lease, checked inside every SQL statement; group uses one timestamp snapshot |
| Immutable R2 ZIP | Original bytes/hash plus exact owned reservation authorize reconstructed content | Read/hash/parse/validation occur before staging, unchanged |
| `message_text_chunks` | Deterministic UTF-8 parts at stable indices; staged accepted rows are publicly invisible | Same bytes, indices, primary key and UPSERT expression; one group commits all or none |
| `messages` | Existing tombstone/read state survive; accepted legacy rows stay hidden until completion | Every group retains `NOT EXISTS` tombstone predicate; publication unchanged |
| Storage reservation | Retained protection until message/ledger/journal publication commits | No early `indexed`, recharge, reservation removal or orphan-GC exemption weakening |
| Publication transaction | Exact completeness plus message/ledger/sent commit together | Separate final three-member batch, existing exact-sent resolution retained |
| Due fairness/budgets | Exact due CAS precedes archive I/O; five items and fixed 380/800 grants | Unchanged due ownership and maximum statement admission; batch(N) spends N |

Representative interaction:

```text
phase entry -> 2 setup calls -> exact due CAS -> bounded valid original ZIP
  -> optional restricted-envelope update -> exact projection lease claim
  -> fenced stale-index cleanup
  -> batch chunks [1..8] -> [9..16] -> ... -> [65..66]
  -> existing atomic message + indexed ledger + sent publication
  -> exact-sent resolution only when required
```

The lease is acquired after archive validation in the current call graph. Lease
expiry remains a retry window, not an HTTP lifetime assumption. With successful
bounded groups the SQL-after-claim envelope is comfortably below 20 minutes.
An old fenced revision and a new grouped revision can coexist: both respect
the same token and per-statement guard. Do not extend this claim to pre-0010
unfenced revisions; their [quiescent cutover contract](accepted-projection-cutover-contract-2026-10-01.md)
still applies.

Migration inspection (`0001`, `0005`, `0007`, `0010`) finds no production trigger
on `message_text_chunks`. Existing message search revision, embedding INSERT and
accepted-body requeue triggers still run only inside final publication; their
effects roll back with its transaction. Preserve those triggers unchanged.
Statement tokens count top-level submissions, not trigger-expanded `meta.changes`;
the existing final exact-journal authority and DELETE `RETURNING` remain intact.

## 4. Concrete bounds, with assumptions exposed

Let `k <= 66`, `b = ceil(k/8)` (zero when k is zero), and `D` be a conservative
bound on settlement of one submitted native D1 call. The documented **service
duration envelope** is 30 seconds. Applying it as `D = 30s` requires the explicit
assumption that binding transport/queueing/transparent retries do not extend
settlement beyond that envelope. No local fake clock proves this assumption.

| Path component | SQL statements | Awaited D1 calls |
| --- | ---: | ---: |
| Phase setup | 2 | 2 |
| Due CAS | 1 | 1 |
| Optional envelope update, conservatively present | 1 | 1 |
| Projection claim | 1 | 1 |
| Stale-index cleanup | 1 | 1 |
| Staging | k | b |
| Final publication | 3 | 1 |
| Exact-sent resolution, conservatively present | 1 | 1 |
| Caught-error exact-token release, conservatively present | 1 | 1 |
| **Conservative setup + one attempt** | **k + 11 <= 77** | **b + 9 <= 18** |

The final two calls are a loose late-path envelope, not an assertion that every
successful attempt takes both. A normal maximum-item publication takes
`b + 7 = 16` calls and `k + 9 = 75` statements including setup. One item's
existing 75-statement admission excludes the two phase setup statements; the
five-item phase bound stays `2 + 5*75 = 377 <= 380`, and the invocation ceiling
stays 800. There is no automatic retry or refund.

Thus, conditionally on `D = 30s`:

- Maximum staging service envelope: `9 * 30s = 270s`, versus `66 * 30s = 1980s`.
- Normal setup + one maximum item: `16 * 30s = 480s`.
- Conservative setup + one attempt including late resolution/release:
  `18 * 30s = 540s`.
- Outbound phase enters at invocation elapsed `E <= 55s`. If successful archive
  GET plus body fits the concurrent owner's original **30-second** read envelope,
  and aggregate invocation CPU fits **30 seconds**, the conservative attempt
  completes by `55 + 540 + 30 + 30 = 655s`. Normal publication yields 595s.
  Both are below 900s, with at least 245s conditional margin in the loose model.

For a later admitted item, entry remains at elapsed <=55s and the already-paid
setup costs can be conservatively counted again without weakening the bound.
If setup itself consumes the 15-second soft slice, only the entitled first
item runs. If all calls are fast, the existing five-item cap/statement grants
apply; this ADR does not multiply a per-item slow bound by five despite the
additional-unit admission rule.

**Important limitation:** these are conditional accepted-attempt bounds, not a
hard 655-second whole-Cron claim. PR #29's archive cutoff starts before GET but
GET is still awaited if it does not settle; late return cancels the body without
reading. The final diagnostics owner has one persistence-confirming Queue await
and explicitly no cancellation/deadline guarantee. Neither wait may be replaced
by an invented five-second diagnostic allowance. Other cleanup phases also
retain their own complete-unit/native-binding obligations.

**Success versus bounded failure:** eight statements that each genuinely need
14 seconds of database execution do not magically finish in 30 seconds; that
batch must fail/timeout under the documented contract. Batching fixes repeated
network-call latency and caps this attempt's admitted waits; successful completion
still requires each group to fit the service envelope. This is an actionable
measurement distinction, not a reason to assert unconditional liveness.

## 5. Why eight, and rejected alternatives

Each unchanged chunk statement has 12 bound parameters and <=60,000 body bytes.
Eight statements therefore hold <=480,000 body bytes per prepared group, with
bounded SQL/identity overhead. The 100-parameter limit applies per statement,
not the batch. Retain bound values rather than interpolate text into SQL. The
5-MiB compressed ZIP cap and four-million-byte valid compiled-content contract
are unchanged; grouping adds bounded JS/Wasm conversion allocations rather than
buffering all 66 bound statements at once.

| Option | Benefit | Material cost / reason not chosen now |
| --- | --- | --- |
| **8 unchanged statements/group** | Nine stage calls; bounded transient payload; reuses guards, adapter and transaction support | Every group must fit 30-second service duration; small new allocation/locking profile requires measurement |
| All 66 chunks in one batch | One stage round trip, strongest grouping | Nearly 4 MB chunk bindings plus copies; one large transaction/rollback unit and 30-second execution envelope; needless dominant-case pressure |
| 4/group | Smaller transient payload | 17 stage calls; conservative total 26 calls/780s D1 alone, then entry/R2/CPU leaves only 5s margin to 900s under the same assumptions |
| Multi-row INSERT with 8 rows | One statement/group, fewer tokens; fits common guard +16 row parameters | New SQL shape and accounting proof; conflict/guards must be reverified; no need to reduce already-fitting 800 budget to solve RTT amplification |
| Parallel native calls | Potentially overlaps network waits | D1 is single-threaded per database; <=6 connections and harder statement/fence ordering; does not provide a simple serial bound |
| Durable resumable cursor | Can guarantee persisted progress across sufficiently short successful turns | Needs compiler/generation fingerprint, atomic cursor advancement, restart/reset rules, lease handoff, per-generation stale chunk cleanup, no mixed-generation publication and old-writer coexistence proof |
| Queue/Workflow per accepted item | Different invocation scheduling and retry primitives | Another operational contract/ownership boundary; does not by itself fix per-step D1 serialization, archive validation, or cancellation |

A cursor storing only `next_chunk` is unsafe: compiler revisions can map the
same immutable ZIP to different parts, and current completeness checks indices,
not per-chunk hashes. Continuing a partial previous-generation body could publish
a mixed result. If measured small groups cannot finish despite healthy available
dependencies, introduce a generation-scoped progress model as a **separate ADR**:
identify immutable source plus compiler/chunk version, commit group+cursor together,
restart on version change, and gate final publication against the exact generation.
Do not casually add one column and reuse old prefix contents.

The systems-research comparison is [Beldi, OSDI 2020](https://www.usenix.org/conference/osdi20/presentation/zhang-haoran):
durable logs and transactions make stateful serverless execution fault-tolerant.
Here the journal already supplies durable authority; a resumable progress protocol
is justified only when one bounded projector remains infeasible. That is a
conceptual connection, not a claim Beldi proves Cloudflare timing or drop-in
compatibility. The mature platform batch API is the smaller first experiment.
More recent [Anvil, OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/sun-xudong)
distinguishes reconciliation liveness from safety under concurrency/asynchrony.
That supports making recurring selection, successful dependency windows and
per-group feasibility explicit; this ADR is not a formal Anvil verification.

## 6. Failure, concurrency, and regression risks

1. Build a Vec only for the current <=8 statements; invoke existing `db.batch`.
   Require result length equal to group length and all `success` flags. Do not
   interpret individual equal-value UPSERT change counts as progress authority.
2. On native rejection/failed member, return the existing fixed pending error;
   existing exact-token release is budgeted. Earlier committed groups remain
   invisible. Retry rebuilds **all** chunks under a fresh lease from the verified
   ZIP, not only an inferred saved prefix.
3. An ambiguous batch return does not authorize publication. Replay is safe under
   deterministic UPSERTs and the lease fence. No within-invocation auto retry,
   promise abandonment, compensation DELETE, or provider send is added.
4. DELETE serializes before or after a group transaction. All group predicates
   still reject a surviving tombstone; the final transaction preserves tombstones.
   No visibility or terminal-state publication is moved into stage groups.
5. A group takes a common `now()` snapshot; lease expiry during a submitted group
   is handled like the existing final batch snapshot. Reclaim and D1 writes are
   serialized; a new token makes later old groups no-ops. Stage no-ops are not
   terminal success: final guards/exact-sent resolution remain authoritative.
6. Measure added parameter serialization CPU, peak live JS/Wasm memory and longer
   write-lock occupancy. <=480k body bytes is not a 480k RSS guarantee. Do not
   claim batching reduces total database rows, hashing, ZIP/DOM work or trigger CPU.
7. Preserve the existing foreground projector's wire/error/idempotency behavior.
   The shared helper intentionally groups HTTP too, avoiding two staging engines;
   full-batch rollback changes only invisible internal partial progress.

## 7. Executable implementation and migration slices

1. **Focused source change:** document `STAGE_BATCH_CHUNKS = 8` and factor short
   prepare-group / validate-results helpers inside `accepted.rs`. Keep fence SQL,
   stale cleanup, publication, leases, schema, public APIs and all grant constants
   unchanged. Common bindings use one group-time snapshot. Add rustdoc contracts
   in English; no test-policy knob enters production.
2. **Observer/test change:** extend the existing hosted native observer to retain
   statement SQL/args metadata for batch members, not just a native weak mapping.
   Recognize stage batches separately from final publication. Debit/report every
   submitted member; then execute **one actual native batch**, never substitute
   separate `run()` calls that destroy transaction semantics.
3. **Focused hosted CI:** retain default 96 cases, integrity/race suites, budget,
   liveness, routing and concurrent R2/embedding discriminators. Execute exact
   combined source, not a predecessor with the old serial helper.
4. **Source acceptance:** independent review of all unchanged SQL guards and exact
   native submission accounting, then nondeploying exact-head CI. This document
   itself does not authorize push, dispatch or implementation.
5. **Operational admission remains separate:** effective Paid/short-Cron CPU,
   privacy/sink/schema/serving pins and supported maximum workload observations.
   No new migration is needed. New and old **fenced** versions share all data.
   Rollback to the previous fenced serial helper is data-safe but reopens the
   latency gap; keep Cron paused if rollback loses runtime feasibility. Never
   roll back to an unfenced revision under the guise of schema compatibility.

After design review, assign **one narrow implementation owner**, preferably the
existing accepted-projection integrity owner, only `accepted.rs` plus its native
liveness observer/tests. Keep concurrent `lib.rs`, archive deadlines and Queue
collector edits with their current owners. Integrate once before exact-head CI;
do not run two independent accepted-stage implementations.

## 8. Hosted discriminatory tests and measurements

All runtime tests use unchanged built Rust/Wasm, fresh native Miniflare/workerd
D1/R2, globally held synthetic canary insertion, expired grants and strict local
egress; no EMAIL/Identity/OpenRouter/provider mutation. Setup/readback must bypass
the invocation observer. Source-only fixtures do not establish remote Paid limits.

| Discriminator | Mechanism | Required observation |
| --- | --- | --- |
| Maximum valid text and exact statement budget | Real 4,000,000-byte text; observe all batch submissions | 66 member UPSERTs in sizes `[8,8,8,8,8,8,8,8,2]`; <=9 staging calls; byte-exact independent reconstruction and one sent transition; N-token batch accounting |
| Group boundary / UTF-8 | k=0,1,7,8,9,65,66 and mixed-width maximum-valid content | No empty batch; correct final partial group and stable byte-safe indices; identical read/search/API output |
| Real wall-time continuation, retained old oracle | Before each real group, delay by `300ms * members`, not per-call constant | >=19.8s genuine timer delay for maximum item; all 66 writes/publication; second due CAS and R2 GET untouched; later retention cleanup completes |
| Network RTT amplification | One real 2s delay per native staging call; optionally one dedicated 14s/call focused job | Exactly9 stage calls / at least18s (or126s) real added wait, not66 /132s (or924s); exact first item; no second admission; late phases denied when cutoff crossed |
| Cutoff during successful group continuation | Add logical+116s after fifth successful8-member native group (chunk40) | Remaining26 member writes and publication finish; zero new business admission, due CAS or R2 GET; observer counts members rather than expecting26 native calls |
| Group rollback | Test-only native trigger aborts e.g. member4 of group3 | Actual native batch leaves no group3 members committed; previous groups remain hidden; journal accepted/ZIP/reservation retained; later due retry rewrites all and publishes exact text |
| Ambiguous committed return | Execute native group, then reject observer response | No early sent/visible message; lease/error release is fenced; next due retry rebuilds exact content without resend/recharge |
| Losing token while still accepted | Pause old writer between native groups, expire/reclaim in native D1, keep new writer before final commit, resume old group | Old group no-op under replaced token even before sent; no mixed-generation publication; new writer completes |
| DELETE and existing terminal replay | Pause between groups; real owner DELETE + journal-safe GC; resume writer | Exact tombstone retained/terminalized safely; no resurrection; unchanged owner/foreign/repeated DELETE results and same-key HTTP202 |
| Maximum original R2 stream | Concurrent owner's66-by300ms ZIP stream plus grouped projector | Existing19.8s successful archive stream, actual five-MiB caps/hash/parse guard, exact publication; no fresh per-group archive GET or deadline reset |

For transaction rollback tests, inject failure only in the isolated synthetic
database; never disable production guards/triggers or manually mark accepted
rows sent to force setup through. Observer result shape failures and budget
denial must be included without refundable tokens or hidden raw binding escapes.

Production-supported envelope measurement requires a separately authorized hosted
realm observation of maximum valid archives, closed diagnostics and exact pins.
Record native binding-call wall duration separately from D1 `meta.duration`, batch
member count/payload bytes, aggregate Worker CPU and peak memory where supported.
Do not output SQL, IDs, owners, ZIP bodies, envelopes, hashes or raw provider errors.
Fast D1 execution with slow call latency supports batching; consistently slow SQL
approaching the group limit supports investigating smaller transactional progress
units. Remote measurement is pending, not substituted by emulator timers.

## 9. Acceptance boundary

Adopt grouping if hosted exact-source tests preserve every invariant and a
supported maximum-item workload fits measured CPU/memory and group duration.
The contribution is nine bounded-size staging calls with unchanged statement
and journal semantics. Unconditional Cron completion, plan verification, R2 GET
settlement, final Queue settlement and the service-to-binding duration inference
remain separate evidence obligations. Do not reopen voluntary per-chunk cutoffs
or weaken no-resend/DELETE safety to create an apparent liveness pass.
