# Cron final Queue local-wait deadline

Date: 2026-10-01. Status: source candidate; independent review and hosted evidence pending.
Baseline: merged main `8ca1815307ae515aa5cacc6a25bb161779bb7be7` (PR #31).
Isolated worktree: root `.temp/cron-final-queue-deadline`; branch
`feat/cron-final-queue-deadline`.

## Retrieved knowledge and narrow scope

Selected existing notes by filename before investigation: the final-diagnostic
implementation and its two independent reviews, design commit `f525c7a` in
`.temp/cron-diagnostic-flush-design`, PR #29 embedding/R2 deadlines and the accepted
projection latency ADR. PR #31 already verified one native Queue batch after all
business phases; its unbounded final await was an explicitly documented remaining
gap. The original design prohibited racing/dropping that waiter. This task changes
**only that reviewed best-effort transport-wait policy**, not its privacy or
durable-business contracts.

No changes to accepted staging, R2 GET/body, embedding HTTP, business admission,
SQL, schema, public API/CLI, foreground Trace or Queue submission/consumer retry
policy are introduced. `package.json` and `ci.yml` remain owned by the concurrent
accepted-staging workstream and are not edited: the existing
`test:maintenance-diagnostics` script already selects this file and runs in CI.

## Decision: immutable ten-second tail, not a new business cutoff

After all eight business phases return/defer, the scheduled handler captures
`MaintenanceTurn::diagnostic_deadline()` once on the same clamped invocation clock.
Its cutoff is `observed_final_elapsed + 10000ms`. Application serialization,
whole-buffer validation and binding lookup are checked against that same observed
cutoff; they do not grant a fresh per-call allowance. This is not strict charging
of every synchronous instruction: deployed Date.now advances after I/O, and the
pinned workers-rs native serializer executes in the send future's first poll
before `select` polls/arms Delay. That fixed synchronous cost can extend actual
wall time beyond the computed timer duration; the cooperative limit below applies.
The deadline is intentionally independent of the expired 115-second business
admission cutoff. An already admitted complete projection may finish much later;
granting diagnostics a short tail must not reopen business admission.

`trace::flush_maintenance` preserves all existing validation: up to thirteen
records, closed standalone schema, actual body bytes <=1024 and overflow-checked
batch charge <=240000. An empty/invalid buffer returns without Queue access.
An expired/invalid tail also abandons the buffer. After binding lookup and batch
construction, the remaining immutable allowance initializes one `worker::Delay`.
The function races one pinned native `send_batch` future against that timer:

| First ready result | Local action | Business effect |
| --- | --- | --- |
| Native success | Drop timer; return | None; native persistence confirmation observed |
| Native synchronous error / Promise rejection | Drop timer; return silently | None; delivery must not be assumed safe to retry |
| Local timer | Drop native waiter; return silently | None; delivery unknown, not canceled |

The function emits no new timeout record, returns no repair failure, performs no
retry/replay/split, registers no `waitUntil`, and starts no detached/background
continuation. Its consuming collector and existing one-call site retain at most
one native batch attempt per invocation. The last awaited operation cannot undo
already committed projection/retention or skip a later business phase because all
business work precedes transport.

## What this proves and what it does not

The Queue producer API exposes no AbortSignal or native cancellation method.
Dropping workers-rs' Rust `JsFuture` waiter is not cancellation of its JavaScript
Promise, service request, persistence or delivery. A remote write may already
have committed; its response may resolve later or be discarded by runtime
termination. Do not replay this batch or claim a timeout proves non-delivery.
No consumer deduplication/transactionality change is made.

`JsFuture` installs JavaScript response callbacks and Rust waker state. Dropping
the waiting Rust future does not necessarily unregister those callbacks; they
may remain live until Promise settlement or runtime teardown, and a late result
may wake an already-completed task. No bounded lifetime or elimination of that
native callback state is claimed. The consuming collector is not retained or
replayed by application continuation code; the hosted late-acknowledgement probe
checks that completion cannot produce a second batch or contaminate new turns.

This is a cooperative **local waiting policy**, not a literal real-time ten-second
guarantee under event-loop/CPU starvation. Timer scheduling, finite synchronous
serialization and runtime scheduling latency remain assumptions. The bounded
thirteen-record payload makes serialization work fixed/small, not zero. Native
D1 work and other complete units retain their existing envelopes/uncertainties;
the full Cron duration, actual CPU/Paid-tier fit, remote Queue SLA and deployed
behavior remain separate evidence obligations.

## Native hosted discriminators

Extend the already registered unchanged-Wasm diagnostics suite. It retains actual
Miniflare `queueProducers`, the native `WorkerQueue` constructor/prototype/receiver,
and mandatory normal forwarded/settled positive control. Injection replaces the
returned Promise at that exact binding-method boundary, never a fake plain Queue
object. It is synthetic transport-wait evidence, not remote Queue latency.

1. **Never-settling method result:** native binding lookup/cast and method entry
   occur once, but the injected Promise never resolves and is not forwarded.
   Real ten-second waiting must end with scheduled `outcome=ok`, one entry, zero
   retries, accepted projection `sent`, byte-exact text and later retention already
   committed. Host watchdog at twenty seconds makes the pre-fix implementation
   fail cleanly instead of leaving a whole CI job stuck.
2. **Write committed, acknowledgement held:** forward exactly one real native
   `sendBatch`, immediately observe its native successful result, but hold the
   returned acknowledgement Promise through the local timeout. This positively
   discriminates delivery ambiguity: timeout does not undo the native write.
   Next healthy invocation must produce zero diagnostic records/batches; explicitly
   release the old acknowledgement, then another failed phase must emit only its
   new code with one batch, never replay old facts.
3. **Absolute cutoff consumed during lookup:** synthetic eleven-second clock jump
   during Queue binding access must result in zero method submissions. This
   rejects a fresh per-call allowance after serialization/lookup.

Observer asynchronous callbacks retain their original invocation evidence object
rather than writing global current stats. This prevents a test-observer race from
masquerading as a production collector leak. Synthetic runtime logs remain private
and scanned for body/credential/address/error sentinels; D1/R2-before-Queue tape
and real native body/envelope byte checks remain unchanged.

Pure Rust coverage establishes immutable tail cutoff after business overrun,
backward-clock clamping, invalid-clock fail-closed behavior and no business
admission reopening. Existing thirteen-record/schema/charge cases remain selected.

## Verification and deployment gates

No local project tests/builds/install/provider writes are performed. Local static
checks are Rust formatting, JavaScript syntax and diff whitespace only. Independent
source review must precede hosted non-deploying CI. Automatic PR CI can establish
exact reviewed-source acceptance only after checking actual merge checkout SHA
and complete Git-tree equality to the reviewed candidate; `run.headSha` alone is
not proof of checkout. Avoid duplicate manual CI when the automatic run covers
the same exact source tree.

There is no new sink vocabulary/binary requirement. Before any eventual producer
rollout, independently verify serving sink acceptance of both existing maintenance
deferral/resource-deferred pairs and preserve sink-before-producer, privacy,
runtime-tier/CPU, held sending and release gates. Source and synthetic success
are not deployment, Cron activation or send-unhold authorization.

## Primary platform grounding

- [Queue JavaScript API](https://developers.cloudflare.com/queues/configuration/javascript-apis/):
  producer persistence-confirming Promise and no exposed abort option.
- [Scheduled handler](https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/):
  scheduled Promise ownership; no additional `waitUntil` task is required here.
- [Pinned workers-rs Queue](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/queue.rs):
  native typed batch serialization, `WorkerQueue` binding identity and awaited JsFuture.
- [Pinned workers-rs Delay](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/delay.rs):
  native setTimeout-backed future and timer clearing on early drop.
- [Workers timers/performance](https://developers.cloudflare.com/workers/runtime-apis/performance/):
  deployed observed clocks advance after I/O; local workerd clocks differ.

This narrow change adopts the mature platform's existing local timer/Promise
ownership mechanisms. It needs native failure/lifetime discrimination, not a
new telemetry framework or speculative research abstraction.
