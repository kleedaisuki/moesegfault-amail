# Cron embedding and retained R2 deadline implementation

Date: 2026-10-01. Base: merged PR #27 main
`59ab7a55f38c4646e08cdf2539176fff2ab4a46d`. Status: source implementation and
hosted-only discriminators; independent source review and exact-SHA hosted runtime
validation pending. Not deployment/release approval or production timing evidence.
Worktree: `.temp/cron-embedding-r2-deadlines`.

## Reused contract and focused decision

Reuse PR #27's invocation-local clamped clock and immutable `ExternalDeadline`.
Do not add an independent clock, durable cursor, provider mutation, SQL chunk
cutoff, new diagnostic content, or foreground transport default. The existing
full admitted accepted projector and statement accounting remain unchanged.

| Boundary | Absolute policy | Failure semantics |
| --- | --- | --- |
| Foreground embedding | Existing 30-second headers-plus-body race | Existing `provider_transient` timeout and provider classes; existing awaited reader cleanup |
| Cron embedding | min(10 seconds, original 115-second invocation cutoff remainder) covering headers and bounded body | Typed `CronEmbeddingFailure::Deferred`, exact-token lease release; no attempts/cooldown/quarantine update |
| Retained R2 GET plus body | min(30 seconds from **before GET**, original phase-entry+60-second allowance, 115-second invocation cutoff) | Uncancelable GET is still awaited; late returned body canceled before first read; pending body read canceled on deadline; accepted journal/archive retained |
| Successful accepted SQL projection | Complete admitted sequence, no time check between chunks | Existing lease/fences, budget, genuine dependency failure only |
| Native Cron cancellation cleanup | Synchronous `cancel()` initiation, release lock, native Promise rejection bookkeeping | Never await an arbitrary cancel promise after a deadline |

R2 deliberately uses **30 seconds**, not the design sketch's ten-second body
hypothesis. Sixty-six valid native body chunks at 300 ms require 19.8 seconds;
a ten-second policy would deterministically reject that healthy stream on every
retry. The new test uses the actual immutable ZIP in 66 native chunks with real
platform timers and independently reconstructs all indexed text after publication.
The separate existing 66 slow UPSERT fixture must also keep passing. These are two
different latency boundaries: R2 reading can genuinely fail before projection;
once the admitted SQL projector starts, this policy never truncates its success.

The thirty-second retained-read cutoff is a release hypothesis, not evidence that
all supported archives or dependencies finish within it. A healthy stream exceeding
thirty seconds can still remain accepted indefinitely. If that latency is material,
increase the demonstrated supported envelope or introduce structural staging/progress;
do not add a timeout per native chunk or hide the failed discriminator.

## Data ownership and state invariants

- `PhaseTurn::archive_deadline()` borrows the existing invocation and shares the
  original outbound setup/first-unit sixty-second entitlement. Copies never
  restart the clock. `repair_accepted` clips it once before native GET.
- `PhaseTurn::embedding_deadline()` carries the original invocation cutoff.
  Cron's exchange timer encompasses headers and body; it does not restart after
  header receipt or each body chunk.
- Cron's native embedding reader is owned outside the raced exchange future.
  Dropping the timed-out future does not lose the exact reader needed for cleanup.
  Foreground continues using the existing body helper and timeout classification.
- Policy denial after a claimed embedding releases `lease_until`/`lease_token`
  only under the exact opaque token. The release goes through the unchanged D1
  adapter and consumes the existing ninety-statement grant. Durable attempts,
  due time, provider code and shared dependency cooldown remain unchanged.
- Ordinary provider failures (including 429) retain existing retry/backoff policy.
  Policy expiration is not provider-failure evidence. A timeout does **not** prove
  OpenRouter stopped computing or that no billable provider work occurred.
- R2 metadata/actual-byte caps remain five MiB, checked before native-array copies.
  Missing, malformed and oversize archives remain durable accepted work. Deadline
  errors propagate as the closed maintenance deferral marker, not generic failure.
- Native `cancel()` initiation is not a guarantee of cancellation fulfillment or
  remote-source stopping. Its returned promise can be pending/rejected without
  retaining Cron. No new Rust detached cleanup task or provider request is spawned.

## Acceptance evidence required

All fixtures exercise the unchanged generated Rust/Wasm shim via a test-only native
observer in fresh Miniflare/workerd realms, with strict synthetic egress. No live
provider, Identity, SMTP, deployment, or sending-unhold action is involved.

1. Existing foreground embedding fixtures: valid exact-64-KiB result, malformed
   inputs, redirects, over-cap native reader cancellation, real thirty-second
   header/body stalls and privacy sentinels.
2. New Cron embedding fixtures: real ten-second header/body stalls, exact native
   signal abort, pending-reader cancellation, unchanged attempts/cooldown, later
   cleanup liveness, pre-transfer expired deadline with zero provider exchanges,
   seven-second remaining global allowance without restarting ten seconds, valid
   normalized 256D persistence, and unchanged ordinary 429 retry classification.
3. Retained R2: real 66x300-ms valid body completion, real pending-read thirty-second
   timeout with retained archive/journal and untouched following due item, a late
   GET with no first body read, a never-settling cancellation promise that cannot
   block following healthy work, plus all existing metadata/chunk/total caps.
4. Existing complete-item liveness suite: 66x300-ms UPSERT success, setup entitlement,
   cutoff during chunk 40, phase fairness and exact SQL accounting remain unchanged.

Performed locally: source inspection, Rust formatting, JavaScript parse-only
`node --check`, Git whitespace inspection. No local project build, runtime test,
provider mutation, deployment or unhold was performed. Exact-SHA hosted CI is
required **after independent source review**; source checks are not runtime success.

## Scope limitations and next discriminator

This is not a hard 120-second invocation guarantee. Native R2 GET, D1 calls, CPU
ZIP/DOM/hash work and successful complete projection cannot be preempted by these
stream deadlines. A submitted binding is never raced and abandoned as if canceled.
The policy prevents a late GET from buying a fresh body allowance once it returns.
The next evidence-driven structural step is batching or durable progress only if
measured complete-item feasibility fails; it is not justified merely by adding a
stopwatch. Beldi's durable serverless execution offers a research comparison, not
a drop-in cancellation capability for these existing native bindings.

## Primary-source references

- [Cloudflare Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/): bounded streaming, request-local ownership and native bindings rather than REST.
- [R2 Workers API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/): native `get` options/body boundary; no claim of an AbortSignal for GET.
- [Native reader contract](https://developers.cloudflare.com/workers/runtime-apis/streams/readablestreamdefaultreader/): `cancel()` returns a Promise for the associated native stream.
- [AWS timeout/retry production guidance](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/): timeout selection must follow a supported latency envelope, and timeout does not imply remote side effects did not occur.
- [Beldi, OSDI 2020](https://www.usenix.org/conference/osdi20/presentation/zhang-haoran): durable execution/state primitives are the structural alternative when an ephemeral invocation boundary is insufficient.
- Existing `docs/embedding-cancellation-oracle-2026-10-01.md`: native workerd cancellation is not the Node loopback producer callback; keep these evidence claims separate.
