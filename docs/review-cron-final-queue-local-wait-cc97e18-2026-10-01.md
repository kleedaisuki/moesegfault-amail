# Independent review: final Cron Queue local wait

Date: 2026-10-01.
Exact candidate: `cc97e182b99481f3d9977e383179b4f0ed7636ce`.
Baseline: merged PR #31 `8ca1815307ae515aa5cacc6a25bb161779bb7be7`.
Independent worktree: `.temp/cron-final-queue-deadline-review`.
Branch: `review/cron-final-queue-deadline-cc97e18`.

## Decision

**GO for exact-source hosted, non-deploying CI. No demonstrated blocking defect.**
High confidence in business-contract preservation; native runtime acceptance is
pending. This does not approve deployment, Cron activation, send-unhold, remote
cancellation guarantees, hard wall-clock deadlines, or complete resource reclamation.

No local project test, build, installation, provider action, or production edit
was performed. Source/docs and locally cached lockfile-matched dependencies were
inspected; public primary platform documentation was retrieved. `git diff --check
8ca1815 cc97e182` passed. Only this independent review artifact is committed.

## Reused knowledge and scope

Selected documents by filename before detailed source inspection: final-diagnostic
implementation note, `review-cron-final-diagnostics-integration-eb15b38-2026-10-01.md`,
and the new local-wait design note. Examined all seven changed files, surrounding
scheduled/collector/deadline/validation code, native fixture, observer, package
script, CI registration, and worker 0.8.7 Queue/Delay, futures-util 0.3.34 select,
wasm-bindgen-futures 0.4.79 and js-sys 0.3.106 Promise bridge implementations.

## Evidence

| Contract | Evidence and assessment |
| --- | --- |
| Final-only transport | `lib.rs:170-180` completes the phase loop and consumes the collector before the only final flush. No business operation is raced or abandoned by this change. |
| Admission unchanged | `maintenance.rs:190-205` captures final observed elapsed plus 10000; existing 115000 business cutoff and first-unit policy remain unchanged. New pure test covers overrun, backward clamping, expired and invalid observations. |
| Immutable application preparation cutoff | `trace.rs:683-696` creates/validates the fixed events, checks remaining time before lookup, and checks again after lookup/batch construction. The injected 11000-ms lookup jump forbids submission rather than granting a fresh allowance. |
| One bounded batch | Existing eight terminal slots plus five presence bits remain invocation-owned and consuming. Whole-buffer schema, <=13 records, <=1024 body bytes and checked <=240000 charge remain unchanged. No retry, split, log fallback, waitUntil, or application continuation is added. |
| Losing future | `trace.rs:697-703` explicitly drops the remaining pinned future. Delay clears an armed timer on early drop; JsFuture late completion is self-contained and memory-safe. Promise rejection is handled by the bridge. Drop is not remote cancellation or proof of non-delivery. |
| Native discriminators | Never-settling acknowledgement requires actual >=9500-ms host elapsed, <20000-ms watchdog, native constructor/method entry, zero forwarding/retry, durable accepted projection and later retention. Committed-held case forwards one actual native batch and observes settlement before local return, then checks healthy next turn, explicit late release, and only a fresh later diagnostic. |
| Positive controls and privacy | `oneBatch` requires real WorkerQueue receiver, one lookup/sendBatch, forwarded and settled counts, exact independent envelope/byte checks, and no business submission after Queue entry. Existing eight-failure/deep-fact cases remain selected; private runtime logs are scanned for sentinels. |
| Hosted registration | Existing `test:maintenance-diagnostics` selects this file; `ci.yml:1628-1630` runs that script. No package/CI edit is needed. |

Async observer forwarding callbacks capture their original stats object. Held
acknowledgements are fixture-only and explicitly released; production has no
module-global policy/stats/diagnostic buffer. Late settlement cannot replay or
contaminate a later invocation's business collector.

## Material limits: do not overclaim

1. **Cooperative timer, not full CPU/wall-clock accounting.** Application record
   construction, charge serialization and Queue lookup precede the last remaining
   check. However worker 0.8.7 `send_batch` performs additional Rust-to-JS/envelope
   serialization in its first poll; `select` polls it before Delay, whose setTimeout
   is armed only on its own first poll. That small fixed synchronous cost is not
   subtracted from the already computed timer duration. Furthermore deployed
   Workers Date.now advances only after I/O, unlike local workerd timers. The
   source has an immutable observed-clock cutoff, not strict accounting of every
   synchronous instruction or an unconditional 10-second wall-clock SLA. Fixed
   thirteen small records and the explicit scheduling caveat make this nonblocking
   for hosted validation; avoid stronger serialization/timing claims.
2. **Waiter drop is not complete bridge reclamation.** Locked js-sys JsFuture
   registers self-contained resolve/reject closures retaining Rc state and a
   waker until settlement; it has no cancellation Drop. A truly never-settling
   Promise can retain that small bridge state for the isolate lifetime. A late
   settlement releases the callbacks safely; it does not resume business work or
   reuse the collector. This is a dependency-level lifetime limitation, not a
   demonstrated production leak rate or cross-invocation diagnostic leak. The
   synthetic never-Promise test establishes liveness, not zero retained memory.

## Required next gates

Hosted CI must execute the reviewed candidate tree (or verify exact Git-tree
equality of its actual PR merge checkout) and pass existing native suites plus
all three added discriminators. Preserve host timing and late-release evidence.
No historical PR #31 green run proves this changed lifetime behavior. Deployment,
serving-sink compatibility and existing privacy/runtime/send gates remain separate.

## Primary references

- [Cloudflare Queue API](https://developers.cloudflare.com/queues/configuration/javascript-apis/): sendBatch resolves after persistence; documented options have no abort contract.
- [Workers performance/timers](https://developers.cloudflare.com/workers/runtime-apis/performance/): deployed Date.now/performance.now advance after I/O; local timers differ.
- [Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/): invocation-owned state and platform bindings.
- Lockfile-matched cached source: worker 0.8.7 `src/queue.rs:647-697`, `src/delay.rs`; futures-util 0.3.34 `src/future/select.rs`; js-sys 0.3.106 `src/futures/mod.rs` JsFuture implementation. Inspected without executing project code.

No novel research-method adoption is needed in this bounded lifetime change;
actual platform ownership and native failure discriminators are the relevant evidence.
