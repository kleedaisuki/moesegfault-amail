# Independent Cron embedding / retained R2 source review

Date: 2026-10-01.

## Decision and exact scope

**GO for exact-candidate hosted, non-deploying CI. No substantive source defect found.**
This is not hosted runtime acceptance, merge/release approval, deployment permission,
or a hard invocation-duration guarantee.

Reviewed candidate `ef941052cf565f33f938afec990c025208072554` against merged main
`59ab7a55f38c4646e08cdf2539176fff2ab4a46d`. Earlier `f6dbea8` was superseded:
`ef94105` adds the previously absent CI selection of the new Cron embedding suite
and simplifies an observer conditional; conclusions apply to `ef94105` only.

Reviewed the complete changed Rust files, native observers, test fixtures, package
scripts and CI step; traced surrounding invocation clock/admission, embedding
claims/fenced persistence/backoff, accepted due advancement and full publication.
Reused the implementation deadline note, existing routing policy and cancellation
oracle documents discovered by filename first. No implementation file was changed.
No local project tests, build, dependency install, live provider call, deployment,
secret read, or sending-unhold action was performed. Git diff whitespace inspection
passed. Tests below are inspected authored discriminators, not executed results.

## Evidence matrix

| Contract | Source evidence | Authored hosted discriminator |
| --- | --- | --- |
| Cron-only 10-second full embedding exchange | `platform::embed_cron` races one `embedding_exchange` covering headers and bounded native body; duration is min(10s, original invocation remaining). `PhaseTurn::embedding_deadline` borrows the same clamped invocation clock. | Separate real header/body stalls, 108s late-claim jump producing seven remaining seconds, valid normalized 256D persistence. |
| Foreground 30s preserved | `embed_classified` still selects its existing 30s timer and unchanged body helper; it passes `None` for Cron ownership. Existing provider classification and awaited foreground cleanup remain. | Existing exact-limit, oversize, malformed, redirect, header/body timeout and privacy cases remain in `pnpm test`. |
| Timed-out reader remains owned | Cron stores `Option<JsValue>` outside the losing future; timeout explicitly drops that future before controller abort and cleanup. R2 likewise acquires/stores reader outside `read_chunks` race. | Native embedding exact-signal abort and reader-cancel counts; stalled native R2 reader cancellation. |
| Cancellation cannot extend expired Cron | Shared `finish_native_reader` invokes cancel synchronously, attaches fulfillment/rejection bookkeeping, then releases lock without awaiting cancellation. Existing routing behavior is preserved by helper rename only. | Metadata-rejected R2 source with never-settling cancel still permits following healthy item. |
| R2 absolute 30s starts before GET | `repair_accepted` clips original phase deadline to 30s before native GET and checks remaining before submission; `archive_read::read` uses remaining absolute time, not a fresh 30s body allowance. Native GET is awaited, never raced/abandoned. | Late GET shifts only synthetic clock by 35s, then asserts zero reads and one cancellation; real pending native body times out around 30s. |
| Valid 66 x 300ms native body accepted | Observer materializes the actual independent immutable ZIP and divides all bytes into 66 chunks; native pull uses actual platform timers with zero high-water mark. Metadata stays real. | Reconstructs complete indexed 4,000,000-byte text, asserts `sent`, 67 reads including EOF, no cancel, and untouched following due item. |
| Expired embedding performs zero transfer | Duration admission occurs before embedding request construction/native fetch. Typed `Deferred` remains distinct from provider errors. | 116s claim jump asserts zero exchanges/calls/aborts and unchanged failure metadata. |
| Policy deferral is not provider failure | `process_embedding` releases only exact message/token lease fields and returns closed maintenance marker. Attempts, next due, error, cooldown and quarantine are not updated. SQL still uses existing counted D1 adapter. | Deferred cases inspect work/dependency records; ordinary 429 still increments attempt and sets existing rate-limit cooldown. |
| Accepted projector never cut off mid-success | New deadline checks end at retained-byte read. Hash/ZIP validation and existing `accepted::publish` are untouched; no checks added to projector chunks or successful fenced embedding persistence. Deleted accepted recovery bypasses R2 as before. | Existing separate 66 x 300ms SQL UPSERT liveness suite remains selected, as do budget/counter and HTTP/Cron race suites. |

## Hosted CI isolation

`.github/workflows/ci.yml` runs the Wasm worker job on `ubuntu-latest` with the
existing 60-minute job bound. It builds the real Rust shim and invokes `pnpm test`,
`pnpm test:maintenance-liveness`, `pnpm test:routing-deadline`, and now
`pnpm test:embedding-deadline`. R2 cases remain in the ordinary `pnpm test` file list.
The `workflow_dispatch target=checks` selection enables this checks job, not
staging/production deployment jobs. The added step has no environment, secret,
provider, or deployment invocation. Fresh Miniflare realms, local migrated D1/R2,
strict synthetic outbound services and test-only shim subclasses keep observation
out of production deployment sources. Native API instrumentation preserves original
receiver/arguments/results; it does not perform cleanup for production.

## Non-blocking verification limits and useful next step

No claim is made that R2 GET, submitted D1 work, CPU ZIP/hash parsing, or admitted
successful SQL projection are preemptible. A native GET can exceed the deadline;
this code only denies its late returned body. Native cancel initiation and signal
abort do not prove remote provider computation/billing stopped. A healthy archive
whose entire GET/body exceeds 30s may remain accepted indefinitely; the policy note
explicitly treats this as a supported-latency hypothesis, not a production SLA.

Required next gate: exact-SHA hosted CI must actually pass all selected suites;
retain test timing, counts, and SHA rather than treating this review as runtime proof.
An optional additional discriminator would delay headers for ~6s then body for ~6s:
it directly falsifies a future accidental timer restart at headers. Current source
already has a single outer race, so absence of that extra case is not a finding.

## External grounding

Retrieved public primary references during review:

- [Cloudflare Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/): bounded streams, request-local resource ownership, and binding-based access support the chosen implementation style.
- [R2 Workers API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/): native `get` and returned readable body are separate boundaries; do not infer a cancelable GET from reader cancellation.
- [Native default reader](https://developers.cloudflare.com/workers/runtime-apis/streams/readablestreamdefaultreader/): cancel returns a Promise; initiating cancel is distinct from awaiting fulfillment.
- [Beldi, OSDI 2020](https://www.usenix.org/conference/osdi20/presentation/zhang-haoran): durable fault-tolerant serverless workflow/state primitives are a structural comparison if ephemeral whole-unit feasibility proves inadequate, not evidence that these native operations can be canceled or a reason to redesign without measurements.
