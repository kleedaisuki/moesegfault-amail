# Independent review: native D1 actual-submission observer

Date: 2026-10-01. Candidate: `a4a2faa`, relative to `7037952`.
Review worktree: `.temp/cron-d1-observer-review`.

## Decision

**GO for exact-SHA GitHub-hosted CI execution.** No substantive blocking defect
found in the test-only observer or the 379-statement fixture expectation.
This is source-based approval to execute the fixture, not a hosted-pass claim,
production rollout approval, or proof of remote account quotas/resources.

## Evidence

- Inspected relevant document filenames first, then reused the prior maintenance
  accounting and counter-fixture reviews. Read the complete changed test modules,
  scheduled call graph, private database adapter, accepted projector, ZIP parser,
  text validation/splitting, relevant migrations, and hosted test discovery.
- `maintenance-counter-observer.mjs` wraps the environment passed to the imported
  unchanged Worker. The actual lockfile pins **worker/worker-sys 0.8.7**; CI
  installs **worker-build 0.8.5**. Inspected those exact locally cached dependency
  sources (and official upstream source). D1 environment acquisition checks the
  constructor name, which the proxy forwards unchanged. Generated scheduled
  handlers use `this.env`, so inherited scheduled execution sees the wrapped
  MAIL_DB. No production Worker modification or alternative Rust handler exists.
- `prepare` and every returned `bind` value retain proxy coverage without spending
  counters. `first/all/run` each increment immediately before the native executor
  invocation and call it with its original native receiver and arguments. Returned
  promises/results/errors are untouched. Native internal calls therefore do not
  recursively enter the proxy or double count convenience-method internals.
- Batch validates all members before native submission, unwraps their exact native
  statements via WeakMap, adds N statements once, and calls native batch once.
  It does not emulate batch with N individual calls, alter SQL/binds, or replace
  native transaction/results. workers-rs constructs a JavaScript Array of the
  original prepared JS objects, matching the observer's identity validation.
- No reachable built-Worker bypass was found: all current MAIL_DB acquisition is
  through the wrapped environment and all four executor paths are covered.
  Unsupported property/method access increments `unsupported` and throws; the
  exact-zero assertion exposes even caught unsupported calls. This is coverage
  of the current cooperative Worker call graph, not a security membrane against
  deliberately hostile prototype/reflection access or a different DB binding.
- Fixture setup/migrations/seeding and readback use `mf.getBindings()` native
  handles outside the Worker wrapper. Initial stats must be exactly zero. The
  stats fetch returns only fixed numeric fields and does no Rust/D1 work. Each
  fixture creates/disposes a new Miniflare instance; counters are module-local
  across the stats and scheduled requests in that isolated fixture, not general
  per-invocation telemetry. Multiple ticks would accumulate, appropriately.

## Independently derived expected count

| Phase | Submitted statements | Reason in this fixture |
| --- | ---: | --- |
| Addresses | 2 | Empty initial and second repair selections; empty inventory |
| Outbound | 367 | 2 setup + 5 * (due 1 + envelope 1 + claim 1 + stale-chunk cleanup 1 + chunks 66 + publication batch 3) |
| Embeddings | 1 | Dependency read exits on seeded one-day cooldown |
| Storage | 1 | Reservation reconciliation UPDATE |
| Deleted | 1 | Empty tombstone selection |
| Orphans | 1 | Fresh reservations excluded by one-hour age predicate |
| Search | 3 | Unconditional cleanup submissions, even with no rows |
| Abuse | 3 | Envelope, event, and recipient cleanup submissions |
| Total | **379** | **364 individual + 15 batch statements in 5 batches** |

The independent stored ZIP has two valid entries and a 4,000,000-byte ASCII body:
67 pieces of at most 60,000 bytes, with 66 additional chunk writes. It satisfies
5 MiB archive / 12 MiB expanded caps and the inclusive 4,000,000-byte draft estimate
(no HTML/assets). Its immutable archive hash, owner/journal identity, and ledger
byte count agree. Twenty reservations total about 80 MB, below the 1 GiB mailbox
cap. Fresh accepted journals have due=0 and lease=0; only five are selected. The
chunk trigger is extra lower-bound content evidence, not counted application SQL.
The old provider-event readback independently proves a later maintenance effect.

## Validation limits and next gate

Performed source/dependency/document inspection and `git diff --check` only. No
local project tests/builds, provider actions, push, deployment, CPU/RSS measurement,
or runtime proxy/Miniflare verification. Exact-SHA hosted CI must establish native
binding interoperability, isolate lifecycle, elapsed runtime and all assertions.
A total-count oracle cannot attribute canceling per-phase regressions or prove all
error/rollback paths; these are scope limits, not defects in this focused fixture.

Official contracts checked: [D1 database/batch](https://developers.cloudflare.com/d1/worker-api/d1-database/),
[prepared statements](https://developers.cloudflare.com/d1/worker-api/prepared-statements/),
[workers-rs 0.8.7 D1](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/d1/mod.rs),
[worker-build 0.8.5 handler generation](https://github.com/cloudflare/workers-rs/blob/v0.8.5/worker-build/src/main.rs),
and [Workers production practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/).
Module-global synthetic observation is intentionally isolated; production
invocation accounting remains invocation-owned. No new academic claim is made.
