# ADR: bounded full Mail maintenance on a verified Paid Worker

Date: 2026-10-01. Status: **recommended, not implemented or deployment-approved**.
Source inspected: main `c6f93bf4cadbb58c69027ebc6208d594ca713c80`, including PR #17's address repair. Input review: `.temp/mail-cron-budget-review/docs/mail-cron-budget-review-2026-10-01.md` at review commit `8b361a5`. That review is not assumed to be merged. This decision makes no claim about the actual account subscription, deployed CPU/RSS, or provider quota enforcement.

## Decision in one paragraph

Ship one combined five-minute maintenance handler **only after independently confirming Workers Paid and effective Cron limits**. Keep existing business journals; use an invocation-local **800 submitted-SQL-statement ceiling**, fixed per-phase reservations, accepted outbound **LIMIT 5**, deterministic phase rotation, finite external-fetch timeouts, bounded streaming reads, and cooperative elapsed-time admission. Add a small accepted-index due/claim field for poison-item fairness. Stage chunks invisibly while accepted, then atomically publish the message/ledger/terminal state. Do not tighten the accepted four-million-byte service draft contract, resend mail, or claim that statement counts or a timer constitute a CPU guarantee. If Paid cannot be verified, do not deploy this mode; the Free-compatible alternative below is a different implementation, not an implicit fallback.

## External contracts and existing owners of state

- `send_requests` owns owner-scoped idempotency key + ZIP payload hash + stable message ID, quota charge, provider result, and send state. `accepted` means the provider already accepted; recovery **never calls EMAIL/send**. `unknown/submitting` must not be converted into safe-to-resend work.
- The original `messages/<id>.zip` in R2 is the retained source; `storage_reservations` is its pre-write journal and guards orphan collection. Accepted/unknown/submitting work is already exempt from destructive orphan collection.
- `messages.body_text` stores the first UTF-8-safe <=60,000-byte part. `message_text_chunks` stores later parts at stable indices; readers assemble that existing layout. Keep this representation and all IDs/owner keys.
- `embedding_work` already owns durable lease/retry/quarantine state and owner fairness. Address rows already own due claims and reconciliation markers. Tombstones hide deleted mail immediately; resource deferral must never make it visible again.
- Retain existing success/202/idempotency replay and definitive-rejection behavior. No new client configuration, smaller draft limit, quota re-charge, second provider submission, or user-visible continuation API is introduced by the Paid Cron policy.

Relevant source: `crates/mail-worker/src/{lib.rs,archive.rs,platform.rs,search_jobs.rs,trace.rs}`; migrations `0001`, `0003_storage_budget`, `0004_storage_ledger`, `0007_embedding_work`, `0008_address_reconcile_schedule`; both realms in `crates/mail-worker/wrangler.toml`. The scheduled entry currently fetches D1 independently in each phase, runs all eight phases serially, and has no shared budget. Its current outbound selection has LIMIT 20 without a fair due order.

## Exact accounting contract

A **statement token** is an application-conservative reservation for one top-level SQL statement submitted to D1, not a promise about Cloudflare's undocumented charging internals:

| Operation | Debit immediately before submitting |
| --- | --- |
| prepare / bind / parsing result / metadata inspection | 0 |
| first / all / run / raw execution of one prepared statement | 1, even on error, no rows, conditional no-op, or ambiguous result |
| batch of N prepared statements | N, not 1; charge all N even on rollback/partial provider error |
| retry of a previously submitted call | debit again; never refund failure or timeout |
| multi-row INSERT VALUES with one SQL statement | 1, not number of rows; rows/bytes/SQL duration tracked separately |
| triggers and SQLite-internal work | no extra binding-statement debit; do contribute rows, database CPU, query duration and cost |
| R2 / Queue / external fetch | separate resource counter, not D1 tokens |

Official [D1 limits](https://developers.cloudflare.com/d1/platform/limits/) still list 50 Free / 1,000 Paid queries per invocation, 100 bound parameters, 100,000-byte SQL, 2,000,000-byte value/row, and 30-second individual-query duration. [Workers limits](https://developers.cloudflare.com/workers/platform/limits/) describe newer larger internal-service subrequest limits. Use the stricter D1-specific ceiling pending actual-account evidence; an emulator pass does not settle that discrepancy. No assertion that batching erases per-statement limits is justified. [D1 batch](https://developers.cloudflare.com/d1/worker-api/d1-database/) provides ordered transactional rollback, so it can improve commit correctness and round trips, not our token arithmetic.

Implementation boundary: a private Cron-only `MaintenanceDb` owns the MAIL_DB handle and shared `MaintenanceBudget`. A non-cloneable `StatementPermit`/work reservation authorizes execution before the JS promise is created. Nested helpers receive this handle/permit, never a fresh raw `Env::d1`. Ban raw `exec`/dump in maintenance rather than parse arbitrary SQL to count it. Each phase gets a child reservation; the sum cannot exceed 800. On execution, transfer reserved to spent atomically in local state. On abandoning *unsubmitted* work, release only unused reservation. A failed submitted statement remains spent. This is per-invocation control, **not a durable account quota**.

### Initial fixed reservations

| Phase | Source ceiling after outbound fairness change | Reserved statement tokens |
| --- | ---: | ---: |
| Address repair, existing external allowance | 160 | 170 |
| Accepted outbound, five maximum valid drafts + five due claims | 357 | 360 |
| Semantic retry, including one dependency cooldown | 83 | 90 |
| Storage ledger reconciliation | 1 | 2 |
| Deleted-message cleanup | 61 | 65 |
| Orphan-object cleanup | 61 | 65 |
| Search-job cleanup | 3 | 5 |
| Abuse retention | 3 | 5 |
| Control/future explicitly audited calls | not automatically usable | 8 |
| **Total** | **729** | **800** |

The original five-row proposal is 724 before outbound claims. The additional five successful/failed claim submissions make the chosen source ceiling **729**, not 724. These deliberately loose ceilings do not mean all paths can simultaneously attain every term. No reserve borrowing in the first implementation: unused address allocation must not let outbound steal deletion/indexing opportunities. Future new maintenance statements must fit an explicit amended phase model rather than silently use the 200-token platform gap.

For a parsed valid accepted draft, let `k = text_parts(draft.text).len()-1`. `validate_draft` counts compiled text + sanitized HTML + base64 asset estimate, so compiled text <=4,000,000 bytes. Each nonlast UTF-8 slice is at least 59,997 bytes; therefore `k<=66`, including mixed-width Unicode. Outbound phase setup costs 2; each selected item reserves **1 claim + optional envelope UPDATE (count as 1) + k chunk INSERTs + 3 finalization statements = k+5<=71**. Thus `2 + 5*71 =357`. Reserve 71 before claiming/R2 I/O, then reduce the *unsubmitted* allowance only after parsing proves a smaller k. A malformed old object is not a reason to increase this model: reject/defer safely; no publish or resend.

## Durable exhaustion and index publication

1. Add `send_requests.index_next_attempt_at INTEGER NOT NULL DEFAULT 0` and an index over state/due/created/message ID. Select accepted provider-positive rows due now, **ORDER BY index_next_attempt_at,created_at,message_id LIMIT 5**.
2. One conditional UPDATE claims/rotates each row before expensive R2/parse work, moving its due time to a finite retry slot. The returned new due value can be the claim fence; guard every subsequent staging/finalization statement with accepted state + that fence. A zero-change claim does no work. Claim expiry permits eventual recovery after a terminated isolate. A stale claimant cannot publish after another claim or sent transition.
3. Check stored object size and incrementally cap its read at existing MAX_ZIP before parsing; never buffer an arbitrary stored object and only then apply the cap. Parsing a valid archive keeps existing ZIP/HTML semantics. No repeated parse of twenty drafts in one tick.
4. Envelope repair and idempotent chunk INSERTs remain invisible staging under accepted. Check elapsed-time admission between staged calls. If budget/time ends, retain ZIP, storage reservation, accepted state and any chunks; next claim re-parses the immutable ZIP and safely rewrites deterministic indices. No durable chunk cursor is needed for this chosen Paid path.
5. After all chunks exist, use one **three-statement D1 batch** for message INSERT OR IGNORE, storage-reservation indexed transition, and accepted -> sent. All statements are fenced to the same accepted claim. It costs three tokens and rolls back together on error. A late/ambiguous result is resolved by the existing journal, not by provider resend or deletion.
6. Existing partial message rows from the old implementation must be characterized. In particular, deleted-message GC must **exclude rows whose send journal remains accepted** until recovery has terminalized them. Otherwise a crash after message INSERT but before sent, followed by user delete + GC, can erase the tombstone and let recovery resurrect the message. Keep a tombstoned existing row untouched by INSERT OR IGNORE, terminalize accepted without republishing, then allow GC. Fenced staging must stop after sent, so late workers cannot reinsert chunks after cleanup. This small GC selection change does not add a binding call.
7. Do not voluntarily exit between finalization batch statements or delete a source archive to “release budget.” Validate that every batch predicate is equivalent; a zero-change INSERT with unrelated live row must not authorize the other transitions. No generic blanket catch that converts budget deferral into successful completion.

Privacy retention and cleanup phases have their own reservation. Preserve row-level journals if stopping between idempotent R2 and D1 operations. Exhaustion is `Deferred(Budget/Deadline)`, distinct from dependency error and success; fixed typed counters/diagnostics only, no SQL/provider bodies, owners, addresses, or R2 keys in telemetry.

## Phase scheduling, elapsed time, CPU and dependency timeout

Use existing `ScheduledEvent.scheduledTime` to derive `tick=floor(scheduledTime/300000)`. Rotate the fixed eight-phase order by `tick % 8`. Do not use isolate-global mutable state, wall-clock jitter or a new scheduler service. Each due phase has its fixed statement allocation and a first-pass **15-second soft wall-admission slice**; invocation admission stops at **120 seconds**. These are initial testable policies, not measured performance choices. A phase releases its slot on completion/defer/error; next tick gives a different phase first opportunity. Scheduling must not stop all subsequent phases just because one exhausted its own slice.

External routing/OpenRouter fetches use **10-second per-operation abort deadlines**, bounded by remaining phase/global time. The abort covers header + bounded body-read, redirects are manual, and 3xx is a typed failure rather than follow-up egress. Streaming cap is required for embedding response too. Use workers-rs AbortController + a timer tied to that exact operation; cancel the timer after completion. Existing routing's 20 exchanges are shared across list/fresh GET/DELETE; embedding admits at most 20 initial exchanges. With no automatic redirects, modeled external cap stays 40. Count submitted requests even if aborted.

Bound non-D1 binding work as well: outbound <=5 R2 GETs, deleted GC <=40 R2 DELETEs, orphan GC <=40 R2 DELETEs, so initial R2 submission cap is **85** with no immediate binding retry. Reuse returned object size rather than add unmodeled HEAD calls. Accumulate at most eight fixed phase diagnostics in memory and flush once after phase execution (<=1 Queue batch), instead of awaiting a diagnostic Queue send between phases. Queue failure must not suppress later maintenance. These are separate admission counters: <=800 SQL-statement tokens +85 R2 submissions +1 Queue submission is a conservative **886** internal-operation model, not an assertion about billing or exact batch subrequest charging. Any new binding/retry must enter that model before submission.

D1/R2 binding cancellation is **not** assumed. A promise race that stops awaiting a write does not prove the remote write was canceled. Await an admitted binding operation to its result where possible; if the runtime terminates, recover through its journal. A D1 batch may contain several statements and no claimed whole-batch 30-second bound is justified by the individual-query limit. After an overlong operation returns, stop that phase and service remaining phases only if global admission remains. Phase rotation preserves future opportunities, but cannot guarantee completion in this same tick or an unconditional cleanup SLA under sustained database/provider failure.

Cloudflare [Performance and timers](https://developers.cloudflare.com/workers/runtime-apis/performance/) says Date.now/performance.now advance only after I/O when deployed. Use monotonic elapsed observations at I/O/work boundaries, **never label their difference CPU time**. A timer cannot preempt synchronous Rust ZIP decompression/CSS/DOM work. Paid five-minute Cron currently has a published **30-second CPU allowance**; changing an HTTP cpu_ms limit does not establish a higher short-interval Cron budget. Full-valid draft CPU/RSS and actual invocation cpuTime require hosted/staging evidence. If one allowed draft cannot finish below the platform CPU ceiling, smaller row counts are insufficient: retain acceptance/ZIP and move compilation/projection to a suitable higher-duration execution boundary or reuse a bounded precompiled artifact. Do not reject previously valid input as a shortcut.

Storage-ledger bulk UPDATE and search cleanup currently have fixed statement counts but broad row cardinality. Source admission/daily limits do not establish cheap runtime work. Hosted large-row tests must discriminate whether bounded cardinality sweeps are needed before deployment; a bounded statement wrapper alone is not a database-work bound.

Production practice: [Kubernetes controllers](https://kubernetes.io/docs/concepts/architecture/controller/) separate desired state from repeated reconciliation, matching the existing durable journals. Academic signal: [Anvil, OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/sun-xudong) makes eventual stable reconciliation an explicit liveness property. Here phase/item fairness is an implementable liveness condition, not a formal verification claim. It relies on recurring successful invocations, bounded feasible workload and eventual dependency success; no design creates progress if dependencies never recover.

## Alternative: Free-compatible multi-row writes and continuations

**Important correction to the input review:** 66 *one-row* INSERT calls exceed Free's 50; that does not prove a maximum valid draft inherently requires >50 SQL statements. The existing chunk schema can use a parameterized multi-row VALUES statement with a reused message-ID bind and <=32 chunk tuples:

```sql
-- Illustrative shape only; actual writes need accepted/claim fencing.
INSERT INTO message_text_chunks(message_id,chunk_index,body)
VALUES (?1,?2,?3), (?1,?4,?5) /* ... <=32 rows */
ON CONFLICT(message_id,chunk_index) DO UPDATE SET body=excluded.body;
```

With reusable numbered placeholders this is 1+2*32=65 parameters; even an implementation using three unique parameters per tuple is 96. Both fit 100. SQL text is a small placeholder string; **do not embed body literals or concatenate SQL from mail**. At <=32 pieces, payload bodies total <=1,920,000 bytes (individual rows stay <=60,000), and 66 chunks need **3 statements**, not 66. This aggregate bound is conservative engineering headroom, not a documented D1 per-batch payload requirement. The query-duration/provider-serialization behavior must be measured.

This can be worthwhile for latency on Paid later, but it is **not a Free-safe combined Cron**:
- current address claim + state-clear alone can use 61 statements;
- phase quotas totaling 729 cannot be squeezed under 50 by changing chunk writes;
- 10-ms Free CPU with ZIP/CSS/HTML parsing remains the dominant unproven limit;
- row/byte quotas, trigger costs, R2 operations and lifetime invariants still apply.

If Free becomes a firm requirement, choose separate invocation budgets <=40 statements, phase/per-item partitioning with durable retries, multi-row chunk groups, and fenced invisible projection. A continuation is needed **where a measured valid work item cannot fit the invocation's CPU/statement budget**, not as a matter of arithmetic for every 4-MB body. Record payload/version, chunk count/next committed group, due/lease and terminal publication in a new projection journal; commit progress with each group, publish only after completion. Queue deliveries are hints; D1 remains truth and duplicate/redelivered jobs never submit EMAIL again. Cron must repair missed enqueue and failed/replayed consumption. ZIP/DOM work may still need a different execution boundary or precompiled artifact; repeatedly parsing the same maximum ZIP in Free continuations is not a solution.

Reject this path for initial implementation because it adds durable projection progress, enqueue/repair/consumer topology, and CPU constraints without a demonstrated Free requirement. Paid-first requires tier evidence rather than pretending platform choice is automatic. Multi-row writes remain a compatible optimization, not an excuse to claim current Free feasibility.

## Executable integration order and rollout prerequisites

1. Land private budget/result types and pass the shared handle through **every** scheduled helper; static check no Cron path calls raw D1 or uncounted batch. Keep HTTP/email paths out of this refactor.
2. Add due/claim schema migration, fair LIMIT 5, bounded R2 read, fenced chunk staging/finalization, and accepted-aware GC. Apply the additive migration before new code. Old code ignores due column and remains data-format-compatible, but rollback to old Cron restores the known unbounded resource/race risk; do not present rollback as release-safe. Stop mixed old/new Cron revisions before evaluation.
3. Add phase rotation, per-phase statement reservations, soft admission and bounded/abortable external operations; preserve route ownership/current-state fences. Do not parallelize arbitrary phases just to hide wall latency.
4. Hosted tests below, then one bounded **synthetic-only staging** workload under verified Paid/effective settings and privacy gate, with raw logs/traces still disabled. Observe safe counters/outcomes and platform cpuTime via reviewed metadata-only collection; do not enable context-bearing Logs/Issues for profiling.
5. Only after maximum-valid compilation succeeds with sensible CPU/RSS headroom, actual-account D1 batch/count behavior is demonstrated, poison fairness/deletion tests pass, and old partial accepted rows are addressed may this close the Cron resource gate. It does not close B identity, public outbound, account quota campaign, Issues privacy or final release gates.

### Discriminating GitHub-hosted tests (no local project tests/build)

| Test | Required observation |
| --- | --- |
| Submission accounting | first/all/run charge 1; prepare/bind 0; N-statement batch charges N on success/error/rollback; no-op/failure/retry never refund; exhausted token emits no binding call |
| Reservation isolation | address consumes its full grant; outbound cannot steal semantic/GC; aggregate submitted statements <=800, fail test on any raw bypass |
| Worst valid backlog | five 4,000,000-byte UTF-8-valid service text drafts, address full allowance, twenty embeddings, twenty each GC class and search/abuse work; <=729 modeled statements for these paths, sixth accepted draft preserved |
| Native/service compatibility | native narrower cap unchanged; server-valid >2MiB and exact 4,000,000-byte estimate still admitted; HTML-only compiled estimate and UTF-8 slice boundaries counted correctly |
| Fault at every staging/final step | accepted ZIP/reservation survives; retry does not resend/recharge; exact original bytes/IDs searchable once; final batch failure rolls back all three statements |
| Tombstone and late claimant | delete during accepted projection, GC while accepted, runtime failure after legacy message INSERT, concurrent claims and sent transition; no resurrection, late chunk writes or ownership crossover |
| Poison-item fairness | first five corrupt/missing objects fail/defer, sixth valid accepted row progresses on a later due selection; phase failures do not pin the same five forever |
| Clock/scheduling | frozen CPU-only clock cannot certify CPU safety; slow/aborted first phase does not cancel later eligible phases; eight successive scheduled slots rotate every phase first; no mutable isolate scheduler state |
| Timeout/egress | hung headers and hung chunked body abort; redirects cause no second fetch; declared-length lies/oversized embedding/R2 response bounded; timeout writes never treated as canceled |
| Database-cardinality stress | large storage/search tables use actual deployed SQL shape; collect rows_read/written, SQL duration and backlog progress separately from statement tokens |
| Optional Free discriminator | 66 pieces produce 3 multi-row INSERTs, <=100 params/query, identical chunk bytes; this proves only write arithmetic, never <=10ms CPU or full-Cron Free eligibility |

Measure deployed CPU and wall duration independently, with exact source revision, verified plan/effective settings, synthetic corpus sizes and provider failure schedule. No speedup percentage, CPU millisecond value, remote quota exception, or completed test is claimed by this note.

