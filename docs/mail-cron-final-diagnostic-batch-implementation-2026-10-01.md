# Cron final diagnostic batch: implementation and acceptance

Date: 2026-10-01. Status: source candidate, not deployed or release approved.

## Baseline and ownership

Isolated worktree: root `.temp/cron-final-diagnostics`, branch
`feat/cron-final-diagnostics`. Initial baseline was main `13b2c284`; the complete
implementation was rebased onto PR #27 merge `59ab7a55f38c4646e08cdf2539176fff2ab4a46d`.
The previously reviewed design is commit
`f525c7aa6a9267c857c63262a11931cbc90a57b0`,
`docs/mail-cron-final-diagnostic-flush-plan-2026-10-01.md` in sibling
`.temp/cron-diagnostic-flush-design`. This slice leaves the independent embedding
HTTP/R2 deadline work to its own PR; collector parameter overlap must be reconciled
there without changing durable failure/deadline cleanup semantics.

## Contract and implementation

`maintenance::MaintenanceDiagnostics` owns eight private terminal outcome slots
and five presence bits, created fresh inside `scheduled()`. An exhaustive phase
identity match decouples slots from rotated dispatch ordering. `finish` classifies
the existing exact SQL-budget/deadline markers, preserves all other phase-specific
failure codes, and records successful no-ops without emitting success events.
`note` accepts only the five reviewed nested condition variants. Neither method
performs I/O, allocates event records, retains error prose or consumes SQL grants.
Repeated nested facts deduplicate, repeated deferrals of different phases do not.
The consuming `into_codes(self)` interface yields no more than 8 + 5 = 13 records.

The address `reconcile_addresses -> repair_address` and embedding
`reindex -> process_embedding -> persist_embedding_failure` chains receive one
explicit mutable collector. Each of the five old immediate Queue emitters becomes
a synchronous note at the same location. In particular quarantine follows its
original work-ledger update and cooldown follows the dependency-ledger update.
SQL statements, claims, attempts, admission, routing timeouts and exact-slot
release behavior from PR #27 remain unchanged. No shared/global collector or
generic asynchronous sink abstraction is introduced.

After all eight phases return or defer, `trace::flush_maintenance` generates the
existing standalone schema, rejects the entire buffer if its count exceeds 13,
any record fails `Event::valid`, serialization fails, or a body exceeds 1024 bytes.
It checks actual UTF-8 JSON body lengths and overflow-safe conservative charge:

```
2 + sum(body_bytes) + max(n - 1, 0) + 4096 + 512*n <= 240000
```

Only a nonempty valid buffer resolves `TRACE_EVENTS`, then submits exactly one
default-JSON native `sendBatch`, awaited once. No splitting, replay/retry, racing,
detachment or console fallback exists. Queue has no abort contract; this final
await can exceed soft headroom and invocation targets. A D1 call already submitted
can also stall: admission is cooperative, not cancellation or a hard wall bound.
This slice prevents diagnostic waiting from serially delaying later maintenance;
it does not pretend to fix arbitrary uncancellable dependency latency.

## Compatibility and sink-before-producer

No new schema vocabulary, sink change or SQL migration is needed. PR #25 already
added both maintenance deferral / `resource_deferred` pairs and the Python mirror.
The serving sink must nevertheless be independently verified to support those
pairs **before** rolling out the producer. Source readiness is not serving evidence.
The foreground `Trace`, warnings, CLI telemetry `[100, 1]` batching, HTTP outcomes,
schemas and accepted projection remain unchanged. Provider writes, deployment,
unhold and PR merge are outside this workstream and were not performed.

## Verification design and current evidence

No project build or tests are run locally. Local actions are source inspection,
Git operations and Rust formatting only. Independent source review must precede
GitHub Actions checks on the exact reviewed commit. Passing a merge-ref PR run is
not substituted for an exact-head manual `target=checks` result.

Hosted pure Rust tests cover exactly thirteen codes after all eight failures and
repeated five conditions, success/no-op and unfinished omission, per-phase
deferral retention, exact closed-marker classification, rotation-independent
identity, duplicate-finish debug assertion, whole-buffer invalid/count rejection,
actual byte charge, the exact aggregate cap and overflow. A literal twelve-field
standalone shape cross-checks Rust serialization against the native fixture.

The non-deploying CI Worker job runs `pnpm test:maintenance-diagnostics` against
the built unchanged production shim. The invocation-only observer wraps real
Miniflare D1/R2/Queue bindings and preserves the Queue constructor (`WorkerQueue`)
and original native receiver. Positive control requires entry/native-forwarded
`sendBatch=1`, `send=0`, fulfilled native result and valid closed records; this
prevents missing-binding/cast-failure zero-send false passes. A dependency-category
tape proves Queue lookup/send follows every business D1/R2 submission. Fixed
stats include codes, byte lengths, aggregate charge and actual native envelope
length, never SQL, binds, message identities or mail/provider bodies.

Native cases cover eight independent phase failures, zero-event success,
all five deep facts with thirty mixed disabled routes and repeated document
quarantines, missing/wrong Queue bindings, synchronous throw, rejected promise,
delayed final Queue completion, durable projection and later retention under
diagnostic failure, fresh rotated invocations, and synthetic 30-second elapsed
D1 failures. The last case is explicitly a logical clock discriminator: four
submitted phases consume 120 seconds of modeled elapsed time, then four later
phases defer without business submissions. It is not remote D1 latency evidence
or a claim that in-flight complete units have a hard 120-second cap.

Synthetic egress permits only routing inventory GET and explicitly selected
embedding error replies. SMTP, Identity, live providers, provider mutations and
foreign egress remain denied. Runtime logs are captured privately and checked
for synthetic mail/body/credential/error sentinels.

## Platform sources

- [Cloudflare Queue JavaScript API](https://developers.cloudflare.com/queues/configuration/javascript-apis/):
  batch producer Promise confirms persistence, exposes no abort parameter.
- [Cloudflare Queue limits](https://developers.cloudflare.com/queues/platform/limits/):
  application charge is deliberately stricter than provider limits/approximate metadata.
- [Cloudflare Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/):
  bindings, invocation-local state and awaited background work.
- [Pinned workers-rs 0.8.7 Queue source](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/queue.rs):
  `WorkerQueue` binding identity and typed native `send_batch` serialization.
- [Pinned worker-sys Queue declarations](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker-sys/src/types/queue.rs):
  caught native synchronous exceptions and Promise-normalized failures.

There is no novel algorithm/research adoption decision in this narrow transport
refactor; the appropriate authority is the existing privacy schema, durable-journal
contract and verified native platform behavior, rather than a speculative telemetry
framework or paper-derived abstraction.
