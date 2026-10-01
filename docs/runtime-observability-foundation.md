# Runtime observability foundation

Status: implementation plan, not native-trace or production privacy acceptance.
Owner priority is infrastructure first; no mailbox campaign or Mail redeploy is
authorized by this document. The overall ledger is infrastructure-foundation.md.

## Known coverage versus desired coverage

Existing code propagates W3C CLI request IDs to authenticated API handling and
emits typed application events through a private Queue to Cloudflare Logs.
That is useful causal correlation, **not** a native Cloudflare trace waterfall
and not proof of observed deployed coverage. Retain compatibility and useful
causality while addressing these concrete debts:

1. CLI events lack an absolute event timestamp. Source events queued to the sink
   likewise cannot distinguish operation time from delivery time. Add optional
   source timestamps and exact operational timing; preserve legacy rows/records
   as unknown time rather than inventing a timestamp.
2. CLI response-body read errors exit before the operation journal records the
   failure. Token acquisition/refresh and local-only operations are also outside
   the present API-request correlation scope. Derive a coverage matrix from
   actual command and dependency boundaries, then test each success/failure path.
3. Send idempotency state shares telemetry.rs and its SQLite initialization.
   Separate diagnostic ownership from durable command-state APIs without
   silently changing old send keys or the existing credential/store layout.
4. Duration/status bucketing unnecessarily hides operational detail. Preserve
   legacy wire fields but add exact timing/status and useful dependency context.
   Body, search, credential, personal identity and private forwarding data remain
   excluded. Infrastructure IDs and static source call sites are not secrets.
5. Account for diagnostic loss/unknown submission and background work, not just
   successful telemetry delivery. Best-effort reporting must not change mail
   behavior or bypass existing durable send/ownership semantics.
6. Control-plane scripts need the same public source/run/stage/request context
   and explicit safe error causes. Do not build a vocabulary of hundreds of
   guessed provider failure codes or hide harmless schema differences.

## Native Cloudflare spans: validate the platform mechanism

Cloudflare's 2026-09-25 update adds getActiveSpan(), startSpan(), recordException()
and setAttributes(). The active-span accessor can return an invocation root and
manual spans can record operational data. These APIs create a plausible path to
native spans through the official Rust/Wasm bridge; do not assume an older Rust
crate exposes every new runtime API or bypass the SDK recovery wrapper.

The current native test runtime is Miniflare 4.20260730.0. It predates that update,
so its old tests alone cannot establish these new APIs' actual behavior. A
separately reviewed runtime pin or a synthetic deployed infrastructure canary is
required. No business-handler rewrite or new JavaScript mail implementation is
needed to evaluate a small platform binding.

Two facts must remain separate:

* Earlier retained-log evidence found an original request-path marker outside
  the allowlisted application event. The existing Queue isolation addresses a
  real enrichment problem; simply enabling all request-facing logging again is
  not field-level privacy.
* The new active-span API permits attributes to be set. Documentation does not
  yet prove that overwriting a root URL field also removes every enriched copy,
  survives runtime finalization, or covers automatic child/exception records.
  Test this directly instead of inferring either universal impossibility or safety.

Next discriminating test: one isolated Rust infrastructure canary with no Mail
DB/R2/Queue, user account, send capability or runtime secret. Supply synthetic
path/query/header/body markers and a known traceparent; annotate only public
attributes, exercise a successful request plus a fixed synthetic failure, and
inspect the complete **canary-only** retained record/trace window. Record actual
native parentage, attributes, error context, runtime/version/source and marker
locations. The test must not expose actual mail or change Mail settings. If root
sanitization does not cover enriched fields, retain the safe event boundary and
use native tracing only on surfaces whose automatic attributes are appropriate.

Do not treat extra harmless platform keys as a privacy failure. Validate our own
event schema strictly, classify protected fields by origin/meaning, and inspect
the whole canary for sensitive markers independently of wrapper shape. The
acceptance target is observable causality with protected fields excluded, not
the absence of all metadata or a perfectly frozen provider schema.

## Compatibility and rollout

Add nullable/optional event fields and in-place SQLite migrations. Historical
clients, queued events, read/search/send contracts and saved send keys continue
to work. Updated sink/schema readers precede enriched producers; do not dual-log
unsafe raw requests as a migration comparison. Source tests and synthetic
infrastructure acceptance precede any separately authorized application rollout.
Keep project Secret management and the existing send hold unchanged.

## Primary evidence

* https://developers.cloudflare.com/changelog/post/2026-09-25-custom-span-apis/
* https://developers.cloudflare.com/workers/observability/traces/custom-spans/
* https://developers.cloudflare.com/workers/observability/traces/spans-and-attributes/
  — fetch/Email/R2/D1 attributes have different privacy origins; inspect each
  relevant surface rather than declaring all operational metadata private.
* https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/
  — native trace and log views are distinct; preserve source/version/time scope.
* docs/mail-trace-privacy-decision.md — historical path-enrichment evidence and
  the current safe-event isolation boundary, not a universal future API verdict.

## Local journal repair (hosted source accepted)

The first bounded implementation retains the legacy upload JSON unchanged:
old Mail servers use deny_unknown_fields, so blindly uploading new attributes
would reject whole batches. New local nullable columns started_at_ms (Unix UTC
milliseconds), elapsed_ms (monotonic), phase and error_kind record the attempt's
actual boundary. Historical rows keep NULL rather than an invented time. The
legacy duration_ms clamp remains only for compatibility; elapsed_ms is exact.
Timestamps/phases are **not yet available remotely**; enriched reader-first wire
rollout and queued producer timestamps are separate remaining work.

Each HTTP attempt starts before credentials, propagates its own traceparent and
consumes one RequestSpan at auth, transport, response-body or full-response
completion. Response-body failures retain the received HTTP status/correlation;
zero status denotes no headers. HTTP error responses are complete exchanges,
not transport failures. JSON interpretation and local command spans remain
outside this attempt span and need their own coverage.

send_state owns legacy send_attempts; auth owns refresh_state; local_store owns
only physical access and private file mode. Keep telemetry.sqlite3 unchanged
for existing processes and saved keys. Journal lock waits are 250 ms, versus
30 seconds for durable state. Diagnostic initialization/record failure reports
safe SQLite codes or I/O kinds on stderr and does not change command results;
normal machine-readable stdout remains unchanged. Explicit telemetry opt-out
skips diagnostic initialization as well as collection/upload. This is diagnostic
ownership isolation, not separate physical storage or crash-state redesign.

Hosted regressions exercise real HTTP complete/error/truncated responses,
request-construction and pre-network auth failures, timestamp/identity equality,
legacy and concurrent additive migrations, unresolved key reuse and concurrent
writers, plus actual CLI process behavior with an unavailable journal and opt-out.
No local project tests/builds and no provider/mail changes accompany this patch.

PR 44 head 46a6cbe9e7dc79242358521d73ab7273aa514095 passed CI 36849720707
and syntax 36849720535. Linux/Windows/macOS each passed 33 unit and 2 actual
CLI-process tests; all three compiler-aware dependency lookups were exact_hit.
Observed scoped workflow duration was 2m01s; platform job durations including
setup were 33s, 105s and 45s. This is not a controlled performance benchmark.
Merged main a0626aae5f79edab85755670902d1df358d91826 preserves the tested tree.

## Queue clock reader upgrade (hosted source accepted)

Mail Event schema v1 gains optional occurred_at_ms, duration_ms and http_status.
The first is the producer's UTC event time, not Queue receipt time. Exact elapsed
milliseconds and status are operational facts, not mail content. Legacy records
remain byte-shape compatible after decoding/re-encoding and retain no fabricated
clock. Integer measurements must survive JavaScript without precision loss;
HTTP status must agree with its legacy class and be an actual HTTP code (zero
only for client attempts that observed no headers). Unknown/personal fields and
existing service/phase combinations are still rejected.

This change upgrades readers only. It does not turn on enriched producers or
redeploy anything. Readers must deploy before producers; retaining schema v1
alone does not make an old strict reader understand optional additions. Hosted
native tests dispatch the actual compiled Queue handler, verify acknowledgements
without guessed delivery sleeps, retain old/new event identity and clocks, and
reject malformed/poisoned records with a positive control. The native file is
assigned to core, raising its required minimum to 105 and total coverage to 154.
Cloudflare's retained-log enrichment/native-span privacy canary remains separate.

Primary native Queue testing mechanism:
https://developers.cloudflare.com/workers/testing/miniflare/migrations/from-v2/
(service binding queue() replaces removed dispatchQueue()).

First reader source check 36850591693 passed Rust/Wasm/unit/build, all three CLI
platforms and seven existing native suites. Core passed its existing 102 tests
but all three new Queue dispatches failed before the sink with a native integer
conversion error. The direct service-binding fixture omitted delivery attempts;
provide an explicit first-attempt integer rather than relying on an obsolete
example's optional default. This is a fixture boundary failure, not evidence that
the sink/schema ran. No partial pass or deployment is accepted; hosted rerun is
required with the complete native message descriptor.

Second source check 36851779508 reached the actual Rust Queue handler after the
attempt descriptor correction (synthetic legacy/enriched output was visible).
The fixture then failed on outdated result-field names: the native response has
retryBatch.retry and retryMessages, not the archived example's retryAll and
explicitRetries. The current workerd API declaration and the pinned Miniflare
4.20260730.0 source confirm that shape. Also capture native console stdout/stderr
with the pinned runtime's handleRuntimeStdio hook; Log.logWithLevel alone captures
Miniflare operational logs, not all Worker console output. Drain both native pipes
after disposal before asserting absence, instead of a guessed delay/global console
patch. This avoids a false-positive poison check or an empty positive-control log.

Primary inspected source (the exact pinned SDK/runtime, not an archived example):
https://github.com/cloudflare/workers-sdk/blob/miniflare%404.20260730.0/packages/miniflare/src/runtime/index.ts
and workerd QueueResponse in https://github.com/cloudflare/workerd/blob/main/src/workerd/api/queue.h.

Third source check 36852863632 accepted the updated Queue response fields and
reached Rust, but the fixture awaited finished() on Miniflare's startup/restart
Transform streams: these are not closed by disposal as assumed. Node correctly
cancelled pending tests rather than silently passing. Replace that guessed stream
lifetime with a test-only subclass of the unchanged SDK bridge: after Rust queue
returns, write a static same-console barrier. Await its actual captured arrival
with a missing-barrier timeout, then inspect the preceding console stream. No
sleep, raw exception, global monkey patch or production-handler change is added.
This is still pending complete hosted acceptance, not a platform privacy claim.

Final reader acceptance: full CI 36853948436, source head
42509113de044fc013a1c51a359286f9859c7812 / merge checkout
7770b4cb0acac48b9145d24813414d53de063eea, passed all 154 native tests, all
CLI platforms, Astro, Rust/Wasm/units and infrastructure/syntax checks. Core's
three sink tests passed with actual acknowledgements, exact legacy/enriched
records, and captured post-Rust console barrier. Merged main
cec8ac2451516e6be6228673176a4048f248976b has the accepted tree. Reader rollout,
producer clocks/remote client failure semantics and the deployed native platform
canary are still pending; do not confuse this acceptance with their completion.
