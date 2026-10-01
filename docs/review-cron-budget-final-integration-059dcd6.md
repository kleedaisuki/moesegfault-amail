# Final pre-hosted review: integrated maintenance budget candidate

Date: 2026-10-01.
Exact candidate: `059dcd624eb6dcfe295f8f6f07e8e9d644747a63`.
Integrated main base: `73874d6a5d40ac542abefb0a9b88af99bbf28573`.
Review worktree: `.temp/cron-budget-final-integration-review`.

## Decision

**GO for exact-SHA GitHub-hosted source CI.** No substantive merge/base
integration defect was found. This is not deployment approval, a hosted-pass
claim, account Paid verification, or completion of the full maintenance ADR.
Confidence is high for the inspected source integration; runtime behavior remains
subject to executing the exact candidate on the hosted runner.

## Scope and method

Inspected relevant document names first, then the maintenance ADR, implementation
record, accepted cutover contract and prior scoped source reviews. Inspected the
complete 22-file diff against main, surrounding scheduled/foreground call graph,
accepted projector, fixture seeding, default workerd discovery, shared trace
schema, sink implementation and deployment workflow dependencies. Reused the
prior independent accounting/due, native R2 and native D1-observer reviews instead
of representing them as fresh runtime results. No project test/build, provider
request/mutation, push or deployment was performed. Only source inspection and
an isolated documentation worktree/commit were used.

## Integration evidence

- Git merge-base is the exact main base above; the candidate working tree was
  clean. Main's held-canary fixture admission remains intact: each synthetic
  accepted insert consumes its exact one-use grant while global policy remains
  held, asserts the consumed key, and expires the grant before scheduled work.
  Unexpected external requests remain rejected. No production policy relaxation
  or alternative migration is introduced by the observer fixtures.
- Main's owner-message deletion correction survives the adapter conversion:
  `delete_message` uses the atomic owner/deleted-state UPDATE with `RETURNING id`
  and returned-row presence. It does not restore trigger-sensitive aggregate
  change-count admission or add a racy existence lookup. The shared HTTP/Cron
  projection fences and legacy tombstone preservation are retained.
- Only `database.rs` acquires MAIL_DB in the Mail Worker; the sole foreground
  constructor caller is the existing foreground `db` helper. Scheduled dispatch
  passes its phase handle through all eight phases, including the fresh desired
  state read preceding routing DELETE. Adapter execution debits every first/all/
  run and each batch member before native submission; grant denial does not
  borrow or refund. Shared foreground helper conversions otherwise forward the
  established binding behavior.
- Migration 0011 is additive and defaults existing accepted rows due immediately.
  Selection skips live projection leases; the exact observed due-slot UPDATE
  uses RETURNING before content work. Existing projection authority remains the
  opaque journal lease, not the due slot. Retry fixtures explicitly reset due
  state when modeling expiry, so they do not assume an immediate second tick.
- `package.json` explicitly selects both `maintenance-budget.test.mjs` and
  `r2-archive-read.test.mjs`, alongside all existing selected suites. The hosted
  Worker job builds the production shim and executes this script via `pnpm test`.
  Observer entrypoints import the production shim and use the shared ESM/Wasm
  module rules; they are test-only and independently scoped.
- The maintenance test asserts initial actual-observer counters are all zero,
  then exactly **379 statements, 364 individual executors, 5 batch calls and 15
  batch members**, with zero unsupported calls. Fixture setup/readback uses the
  unwrapped native binding. It separately checks 330 inserted chunks, five sent /
  fifteen retained accepted journals, and later retention cleanup. This is a real
  native-call assertion, not an assertion on application permits or trigger work.
  Its expected count is still a source hypothesis until hosted execution.
- Native R2 rejection tests retain the original archive/accepted state and require
  a following healthy item to complete. They assert the metadata/single/total
  cases read zero/one/two chunks, cancel exactly once and never use arrayBuffer.
  The production reader checks native chunk length before copying into Wasm,
  normalizes body acquisition failures, and does not introduce HEAD/GET retries.

## Trace upgrade and truthful scope

The new diagnostic/error pair is closed to standalone maintenance in both Rust
and the active Python safe sink mirror; negative fixtures reject dependency-pair
mismatch and request/phase misuse. The Queue sink builds against the same shared
schema. An old sink acknowledges invalid records, hence would silently drop the
new pair. The implementation record explicitly requires updated sink deployment
and verification before enabling producers; existing staging/production producer
deployment jobs depend on their corresponding sink jobs. This source ordering is
not evidence that any deployed sink has actually been upgraded.

The implementation record correctly distinguishes historical PR22 validation
from this rebased budget candidate, keeps prior immutable review hashes, and
calls the 379 expectation a hypothesis. It explicitly leaves phase rotation,
wall/dependency deadlines, single Queue flush, maximum-valid archive CPU/RSS,
account tier and full rollout/drain admission unresolved. Existing accepted
cutover documents still require old unfenced work drain and Cron-paused ordering;
a schema addition does not prove old/new runtime cooperation. These remain
release blockers, not reasons to block bounded hosted source testing.

References reused: `mail-cron-budget-architecture-decision-2026-10-01.md`,
`accepted-projection-cutover-contract-2026-10-01.md`,
`review-mail-maintenance-accounting-source-2026-10-01.md`,
`review-native-r2-archive-cap-7037952.md`, and
`review-cron-native-d1-observer-a4a2faa.md`.
