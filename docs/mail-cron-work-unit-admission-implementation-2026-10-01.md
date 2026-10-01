# Mail Cron work-unit admission: first nondeploying liveness slice

Date: 2026-10-01. Base: main `cb50b35e1672e33a503e423c125016235f81386c`.
Status: source candidate; hosted results and review are recorded below when available.
No deployment, provider mutation, Cron enablement, send unhold, or release approval.

## Scope and contracts

This first slice separates **admission of another complete work unit** from
execution of an already admitted accepted projection. The private invocation
clock uses observed nondecreasing Date deltas, not the scheduled timestamp.
Its 115-second new-work cutoff and 15-second additional-item slices are policy
hypotheses, not binding cancellation, CPU measurement, or a hard 120-second bound.
Outbound and addresses require 60 seconds of nominal headroom at phase entry,
before setup SQL. The first entitlement covers setup and one complete item;
slow setup cannot permanently deny that first item. Later outbound admissions
need both an unexpired slice and the same global headroom.

Accepted due CAS remains immediately before archive I/O, after the unchanged
75-statement whole-item allowance. A noncloneable permit moves into the complete
repair function; there are no elapsed checks in accepted chunk writes, final
publication, terminal resolution, or genuine failure release. Every submission
still uses PR #23's unchanged D1 adapter, 800 ceiling, and fixed phase grants.
The opaque PR #22 lease, content fences, exact due slot, immutable ZIP/hash,
atomic publication, retained reservations, and no-resend/no-recharge rules remain.

Deleted and orphan cleanup admit before a whole existing journal-safe sequence,
including the read checking protected send states; statement headroom is checked
before destruction. Embeddings admit before claim and finish persistence/retry
under the existing lease even if the clock passes the slice. This slice changes
no foreground embedding timeout, API, CLI limit, schema layout, or migrations.

## Deterministic rotation and its limit

For the configured five-minute schedule, start is
`floor(event.schedule() / 300000) mod 8`; all eight phase identities rotate once.
The locked workers-rs 0.8.7 accessor is `ScheduledEvent::schedule()`, not
`scheduled_time()`. Duplicate and delayed deliveries preserve the intended slot;
invocation elapsed starts when the handler actually enters. Grants follow phase
identity, never position. There is no persistent scheduler state or extra SQL.

Every phase receives first opportunity across eight consecutive **delivered**
configured slots, not a 40-minute completion SLA. Delivering only slots congruent
modulo eight gives the same first phase forever. Schedule changes/second Cron
need an explicit formula revision; this source does not solve arbitrary misses.

## Deliberately separate follow-ups

- Addresses retain the existing complete finite claim/inventory/repair batch as
  one compound phase in this slice. Safe per-address time deferral must reserve
  counted exact-slot release writes for previously claimed but unattempted rows;
  implement it together with complete-inventory plus first-repair entitlement.
- Complete routing header/body and inventory deadlines, Cron-only 10-second
  embedding exchanges, and timed native R2 reader cleanup remain unimplemented.
  Native binding GET/write cancellation is not assumed.
- The new closed `MaintenanceDeadlineDeferred` / `ResourceDeferred` diagnostic
  pair is synchronized with the active Python sink mirror and restricted to
  standalone maintenance. Older sinks acknowledge/drop unknown enum variants:
  update/verify the sink before new producers. Existing pairs remain valid.
- Scheduled diagnostic delivery still follows the established immediate behavior.
  A separate small slice must collect all five nested conditions plus phase
  outcomes and flush one byte-guarded Queue batch. Queue waits remain unbounded
  here and can consume admission time; do not present this PR as full liveness.

Eventual accepted completion still requires a feasible full item, dependency
success, durable lease survival, and recurring due selection. At 66 roundtrips
of 14 seconds, chunks alone need 924 seconds, beyond Cron's published 900-second
wall lifetime. Complete permits fix our own prefix cutoff, not platform exit.
If real maximum-item latency exceeds headroom, investigate bounded transactional
staging batches separately. CPU/RSS fit and applicable effective Paid/Cron limits
remain independent release gates; no timer or hosted fixture certifies them.

## Verification discipline

Local actions are limited to source inspection, rustfmt, Node syntax checks,
Python AST parsing, and whitespace/diff review. Runtime tests/builds execute only
in nondeploying GitHub-hosted source CI. Synthetic fixtures use fresh D1/R2,
production held-canary insertion rules, globally held outbound, strict local
egress stubs, and no EMAIL binding. Setup/readback do not pollute invocation
counters. The real 66 x 300-ms native chunk delay must finish exact complete text,
deny a second due CAS/R2 after the slice, and still service later cleanup.

References: [accounting implementation](mail-maintenance-accounting-implementation-2026-10-01.md),
[maintenance ADR](mail-cron-budget-architecture-decision-2026-10-01.md),
[scheduled contract](https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/),
[clock semantics](https://developers.cloudflare.com/workers/runtime-apis/performance/),
[production practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/),
[Anvil, OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/sun-xudong).
The controller/liveness analogy motivates explicit recurring-progress assumptions;
it is not a formal proof of this implementation.

## First hosted result and order-sensitive fixture correction

PR #25 head `048ce10f17d45d56947a233d70836adc8dbebaa5`,
[CI run 36811279260](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36811279260),
attempt 1: all three CLI platforms, infrastructure, site and workflow syntax
checks passed. Worker Rust units and Wasm compilation/bundling passed. Existing
built-workerd boundary tests passed **95/96**; the new focused liveness step was
skipped because the preceding default suite failed, not tested successfully.

The sole failure was the hidden accepted legacy tombstone case at its assertion
that one immediate Cron turn physically removed the archive. Rotation can place
deleted cleanup before outbound terminalization. Accepted-aware GC must then
retain the ZIP and tombstone; after outbound terminalizes the deletion, another
real GC turn can reclaim it. Restoring fixed production order would defeat the
new scheduler, and deleting the archive earlier would violate journal safety.

The test-only correction explicitly chooses slot residue four (Deleted first)
after its existing fixture-only persisted due expiry. That first real turn must
terminalize to sent, retain the exact tombstone, and still retain the ZIP because
GC preceded terminalization. The following existing real turn must physically
remove it. Owner/foreign/repeated DELETE and old HTTP no-resurrection/no-recharge
assertions are unchanged. A narrow independent fixture review precedes rerun.
Raw failed logs are retained only in worktree `.temp/ci-36811279260-failed.log`;
this source correction is not yet new hosted-pass evidence.

## Final hosted source acceptance

PR #25 head `9aadfd1d7aafdb4ed491e069d0f37928a51711ef`:

- [CI run 36812091255](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36812091255),
  attempt 1, **success**, 2026-10-01 03:47:00 to 03:53:32 UTC.
- [Workflow syntax run 36812090952](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36812090952),
  **success**. Seven source checks were green: macOS/Linux/Windows CLI,
  infrastructure, site, Rust Worker/Wasm, and workflow syntax.
- Actions checked out PR merge revision
  `3b66d616650b5b2e55087b971c8b78f129990e39`, merging the exact head into then-current
  main `47d391615e671722c7f01bb7cf8963987f6150f9`. Do not call it a deployment
  or confuse this merge ref with either public branch's revision.
- Existing default built-workerd tests: **96/96**, zero failures. The corrected
  owner/hidden-accepted/rotated-GC/resumed-HTTP workflow passed without weakening
  deletion, journal or no-resurrection assertions.
- Focused native liveness suite: **5/5**, zero failures, suite TAP duration
  **27,024.268877 ms**. The 66 x 300-ms case TAP duration was **21,609.349357 ms**;
  this includes fixture setup/teardown, not an independently reported handler
  duration. Its internal real invocation wall assertion was >=19,800 ms.
  Terminal sent, byte-exact four-million-character text, untouched second due
  CAS/R2 read, and later retention cleanup all passed.
- The other passing discriminators were the +116-second jump after chunk 40,
  +16-second slow setup first entitlement, <60-second outbound headroom denial
  before setup/CAS/R2, and eight scheduled-slot orders with duplicate/delayed/
  skipped-event determinism. These logical offsets are policy fixtures, not
  proof that a real 116-second workload fits platform CPU or lifetime limits.
- Worker Rust unit suite: **62/62**, including the new pure admission tests;
  trace-schema contract suite: **8/8**. Other existing Worker contract/build
  steps completed successfully as required by the full hosted job.

Independent source review and fixture review are committed in the PR. The latter
retains the original R2 constructor P1, its 74e1db4 correction/re-review, and the
narrow review of the order-sensitive nine-line fixture correction before rerun.
Raw successful Worker logs are retained at worktree
`.temp/ci-36812091255-worker.log`; failed predecessor logs remain separate.

This final evidence update is initially a **local documentation-only follow-up**,
not pushed into the already validated PR head. It reports the exact tested source,
not a new untested source SHA. No local project runtime test/build, deployment,
provider mutation, Cron enablement or unhold was performed. All separate provider,
address-unit, diagnostic Queue, plan, CPU/RSS and release gates above remain.
