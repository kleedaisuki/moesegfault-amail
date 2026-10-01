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
