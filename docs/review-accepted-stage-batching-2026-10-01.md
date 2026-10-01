# Independent review: accepted staging native D1 batching

Date: 2026-10-01. Candidate: `2c67564bf6cdddca3c63261c0dd082d0e7b90cb6`.
Base: `848c214a16adebec16d88eaf338bacf65dd7b083`.
Review worktree: `.temp/accepted-stage-batching-review`.

## Decision

**GO for coordinated source integration and exact integrated hosted CI. No
substantive defect found in the inspected change. NO-GO for claiming runtime
acceptance, deployment, public sending, or Cron resumption from this review.**
The new suite is deliberately not registered yet; that is an integration task,
not a hidden passing test or a source blocker under the agreed staged scope.
Integrate after PR #29 merges, register the new suite, and retain the existing
liveness, statement-budget, HTTP/race, R2/archive and embedding coverage on the
actual combined head before merge/runtime acceptance.

No production code was modified. No local project build, test, installation,
provider call, hosted dispatch, push or deployment was performed. Only source
inspection, public primary documentation retrieval and `git diff --check`
(candidate against base, successful) were performed. The nine new tests below
are evaluated for their discrimination by source, not reported as executed.

## Knowledge and inspection scope

Started from the relevant filenames, then read the staging latency ADR,
independent ADR review, accepted integrity contract, cutover contract and the
candidate implementation note. Inspected the complete production diff,
`accepted.rs`, private `database.rs`, `lib.rs` outbound due admission/repair,
foreground publication/error handling and UTF-8 partitioner; both new JavaScript
modules; existing liveness observer/tests, budget expectation and package/CI
entry points. Existing published integrity evidence is historical, not evidence
for this candidate. The concurrent PR #29 implementation is outside this review.

## Production contract assessment

| Contract | Evidence and assessment |
| --- | --- |
| Data/indices | `accepted.rs:116-144` uses the current group's offset `8*ordinal+1`, at most eight consecutive parts, with indices matching the old enumerated loop. `lib.rs:1287` always returns at least one part, even for empty text, so `parts[1..]` cannot panic on valid internal input. No empty group is submitted. UTF-8 byte-safe partitioning is unchanged. |
| Fence | The INSERT/UPSERT SQL, stale-index DELETE and all journal/ownership/tombstone predicates are unchanged. Each member still binds the exact owner, key, hash, provider, reservation bytes, opaque token and lease timestamp. `stage_group` takes one snapshot for the group and refreshes it for each next group. No prior SELECT substitutes for in-statement authority. |
| Native transaction | `accepted.rs:119` submits one actual `Database.batch`. The official native contract gives ordered execution and whole-sequence rollback on member failure. Earlier groups may remain committed but publicly invisible. Grouping introduces no durable cursor or mixed-prefix continuation: a fresh holder still rewrites all expected chunks. |
| Return validation | `validate_stage` at line 150 requires exact result cardinality and every success flag. Promise rejection, shortened array or false flag exits before final publication. Equal-value/no-op `changes` is intentionally not used as progress authority. An ambiguous committed stage result cannot mark sent. |
| Recovery | Existing `publish` catches the error and best-effort releases only its exact token; failure/termination falls back to the unchanged 20-minute expiry. No auto retry, token refund, compensation deletion, resend, quota charge or new archive GET is added. A replaced token makes old writes and release no-ops. |
| Publication/DELETE | Final message + indexed reservation + sent transition remains a separate three-member transaction with exact completeness and exact-sent resolution. Tombstones/read state and deletion RETURNING semantics are unchanged. A tombstone arriving between groups blocks later staging but can terminalize through the existing publication path. Accepted-aware GC continues to retain deletion intent until terminalization. |
| Resource admission | `database.rs:136-155` checks admission identity and debits N members before the native promise. The grouping path cannot escape the capability wrapper. The unchanged 75-statement per-item admission, `2+5*75=377 <=380` outbound grant and 800 invocation ceiling still apply, including error/release envelopes. All-no-op/rollback/error submissions still cost tokens. |
| HTTP/ZIP compatibility | Shared HTTP and Cron publication means both use the same grouping engine. Original ZIP hash/parse/validation precede Cron claim; HTTP retains its existing accepted response and fixed 503 projection-error mapping, same-key replay and no-resend behavior. No migration, public API, ZIP/hash commitment or idempotency contract changes. |

The change increases bounded transient statement/string materialization, not the
maximum draft contract. Eight members carry at most 480,000 body bytes and twelve
parameters per statement. That bound is not peak JS/Wasm memory, serialization
CPU or account-level performance evidence.

## Native observer and nine new discriminators

`accepted-stage-observer.mjs:39-63` retains the bound native statement, SQL and
args in a WeakMap, classifies homogeneous staging groups, records every submitted
member, and calls `target.batch` once with the unwrapped native statements.
It never simulates a transaction using individual `run()` calls. Fixture setup
and readback bypass the observer; fault policy is test-only and no production
switch is introduced. Statistics returned by the observer contain counts, index
ranges, byte sizes and a same-clock boolean, not mail text or identity bindings.

| Test location | What its assertions discriminate |
| --- | --- |
| `accepted-stage-batch.test.mjs:118` | Four-million-byte ASCII text, exact independent ordered reconstruction, nine `[8,8,8,8,8,8,8,8,2]` groups, correct endpoints, common clock, <=480k bindings and zero chunk runs. Later Cron replay submits no new stage and preserves ledger bytes/state. This is Cron replay, not a replacement for existing HTTP idempotency tests. |
| Line 134 | Additional chunk counts 0,1,7,8,9,65,66 exercise no empty batch and partial/full boundaries rather than only the maximum shape. |
| Line 142 | Exactly 4,000,000 UTF-8 bytes of mixed 3-byte/4-byte characters, with byte-exact independent reconstruction and expected group sizes. Tests byte-safe splits, not merely JS character count. |
| Line 149 | Native trigger aborts chunk 20 in group three. Expected persisted indices are exactly 1..16, distinguishing real whole-group rollback from sequential runs that leak 17..19. No message publishes; ZIP survives; dropping the fault and a fresh due attempt completes exact content. |
| Lines 162-172, three cases | Native third group commits before rejection, short array or false success return. Exactly 24 chunks survive but no message/sent transition occurs. Subsequent fresh retry reconstructs the exact body. This is deliberately ambiguous application-visible completion, not a falsely claimed rollback. |
| Line 174 | Old writer pauses after group one. Lease/due are expired, new token writes the whole body and pauses before final publication. Old writer resumes while new journal is still accepted. Marker at index nine would be overwritten by an unfenced old UPSERT; its survival plus unchanged new token/no visible message discriminates token authority independently of terminal sent. The marker is restored before legitimate publication; test does not claim completeness validates arbitrary database corruption. |
| Line 206 | Real authenticated hidden-row GET/foreign DELETE/repeated DELETE 404 and owner DELETE 204 while grouped legacy repair is paused. Tombstone survives old continuation, then actual later GC removes message/chunks/ZIP. This preserves the real trigger-sensitive public deletion contract rather than directly faking deletion. |

The observer's global stage ordinal is intentional for the stale-token case:
old group one occupies ordinal one; the new writer's groups then advance the
ordinal before its first publication barrier; old continuation cannot reacquire
the after-stage-one barrier. Deferred releases in `finally` prevent a failed
assertion from permanently retaining those test barriers.

## Existing liveness and counter updates

- `maintenance-budget.test.mjs:18` still asserts exactly 379 top-level statements.
  Five maximum items change 330 serial chunk runs into 45 stage batches; add five
  final batches: 34 individual calls, 50 batches, 345 members; `34+345=379`.
  No accounting limit was weakened to accommodate batching.
- Liveness observer now retains member metadata and executes one native batch.
  Its successful-group accounting adds member count, not one per call. Existing
  genuine `66*300ms=19.8s` delayed-member workload remains intact; after chunk 40,
  the cutoff assertion demands exactly 26 continuation members and no new phase.
- The new nine-by-two-second delay case requires >=18s genuine elapsed time,
  exact publication, only the first due CAS/R2 read, nine groups and later cleanup.
  With the previous serial stage path it has no matching batch evidence and
  cannot pass solely by observing elapsed time. This is an RTT mechanism
  discriminator, not production latency/CPU/memory measurement.

## External contract and research calibration

Retrieved primary public references on the review date:

- [Cloudflare D1 database API](https://developers.cloudflare.com/d1/worker-api/d1-database/):
  native batch preserves ordered transactional execution, ordered results and
  rollback on member failure; reducing round trips does not parallelize SQL.
- [Cloudflare D1 limits](https://developers.cloudflare.com/d1/platform/limits/):
  the 30-second duration applies to the entire batch; parameter limits are per
  statement. Eight expensive SQL operations still must fit the group envelope.
- [Cloudflare Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/):
  native bindings and awaited operations are consistent with this implementation.
  The code adds no background promise abandonment or REST escape.
- [Anvil, OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/sun-xudong):
  reconciliation liveness requires explicit reasoning about eventual progress,
  not only safe concurrent state transitions. It supports the ADR's separation
  of safety and successful-dependency-window assumptions, not a formal proof of
  this Worker or a reason to add a cursor now.

Nine bounded calls repair repeated network-round-trip amplification. They do
not prove that R2 GET or final Queue publication settles, that D1's service limit
is an end-to-end binding SLA, or that this account's CPU/memory fits. The ADR
correctly labels the 655-second arithmetic conditional. Native maximum ASCII
and mixed-width payload CPU/memory and whole-group latency still require
separately authorized measurement before live runtime admission. A rollback to
the previous fenced serial helper is data-safe but reopens the liveness gap;
rollback to an unfenced writer remains prohibited by the old cutover contract.

## Required next action

After PR #29 merges, integrate this exact candidate with its tests and register
`accepted-stage-batch.test.mjs` in package/CI execution. Run exact-head hosted
Rust/Wasm + native workerd CI, including the maintained budget/liveness and
HTTP/delete/race suites plus concurrent R2/embedding coverage. Record the actual
case selection, counts, immutable head and outcomes. Resolve any failures without
weakening no-resend, token, tombstone, rollback or N-token assertions. Until that
evidence exists, this is source GO only, not runtime GO.
