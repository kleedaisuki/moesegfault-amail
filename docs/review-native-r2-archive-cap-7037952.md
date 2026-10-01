# Independent review: native accepted R2 archive cap

Date: 2026-10-01. Candidate: `7037952763b5b9869d5b852774524d49ac264dc4`,
relative to `6e91c8ccd86ebb3e1dede3f979ced4ee189edf11`.

## Decision and scope

**GO for provider-free hosted CI; no substantive blocking defect identified in
this bounded source slice. Not deployment approval or a hosted-pass claim.**
Reviewed the complete new reader, its Cron caller, observer and shared fixture,
package test selection, Cargo manifest/lock, and the existing maintenance ADR,
implementation record and preceding independent accounting/fairness review.
No local project tests/builds, provider inventory/actions, push or deployment
were performed. This review commits documentation only in an isolated worktree.

## Evidence-backed assessment

1. **Actual dependency/API:** Cargo.lock resolves `worker` **0.8.7**, despite the
   manifest's compatible 0.8.3 lower bound and implementation note's 0.8.3 link.
   Inspected the installed locked source and official tagged source. In 0.8.7,
   `ObjectBody::response_body` checks `bodyUsed` and obtains the native body as
   `ResponseBody::Stream`; it does not buffer or copy payload bytes into Wasm.
   The enum is publicly exported. Obtaining this stream before checking metadata
   is therefore not an allocation-before-admission regression. Native prefetch
   is outside the application's retained-byte bound.
2. **Compressed-byte contract:** metadata above `MAX_ZIP` cancels the unlocked
   stream without acquiring a reader/requesting a chunk. Accepted metadata is
   not the only bound. Each native Uint8Array is type-checked, its length compared
   against checked remaining space, and only an admitted chunk is copied. The
   first single/cumulative overflow returns before `to_vec()` and before another
   `read()`. Exact cap is accepted by `fits`; EOF must match metadata. ZIP hash,
   parsing and service-draft validation remain after successful bounded reading.
   No archive is deleted and no accepted journal is terminalized on rejection.
3. **Allocation limits:** returned/accumulated byte length is <=5 MiB. The current
   `bytes.extend(chunk.to_vec())` can retain a temporary admitted chunk alongside
   the growing Vec, and Vec capacity can exceed length. This is finite and does
   not invalidate the stated length cap; it is not an exact 5-MiB memory/RSS cap.
   The implementation documentation correctly disclaims a 128-MB isolate safety
   guarantee. CPU/RSS evidence for maximum valid parsing remains a release gate.
4. **Reader lifecycle:** each read promise settles before branching. Ordinary
   error/overflow paths await reader cancellation, then release the lock; EOF
   releases the lock without redundant cancellation. A metadata mismatch at EOF
   needs no cancellation because the stream is already closed. Swallowed cancel
   rejection does not imply a binding write was canceled. The native methods are
   invoked with their correct receiver, avoiding an illegal-invocation bug.
   There is no drop guard: termination or a future externally introduced timeout
   that drops this Rust future cannot be advertised as executing cleanup. Current
   Cron awaits this future directly; finite read/cancel deadlines remain explicitly
   deferred ADR work rather than an established guarantee of this patch.
5. **Progress and external effects:** due advancement still occurs before GET.
   Missing/invalid content yields a successful durable deferral and the loop
   services the following item. Read failures become per-item errors and are
   caught before continuing. The helper performs no HEAD, second GET, retry,
   provider send, storage mutation or SQL submission. Existing accepted projector
   fencing remains unchanged. No detached future can later perform a provider
   call because no provider call is created here.
6. **Error/privacy boundary:** reflected read/reader errors are mapped to fixed
   `accepted_archive_read_failed`; cancellation errors are discarded. One narrow
   exception to the helper's documented sole-returned-code wording is
   `body.response_body()?`, which can forward workers-rs BodyUsed/native getter
   errors. This is not a demonstrated privacy leak: `reconcile_outbound` discards
   individual errors and emits only fixed `send_index_pending`, and scheduled
   diagnostics do not stringify the native exception. Normal fresh GETs have an
   unused body. Optional hardening is to map this acquisition error to `failed()`
   too (or qualify the helper documentation); it is not a hosted-CI blocker.

## Hosted fixture fidelity and limits

The test-only entrypoint imports the unchanged built production shim and replaces
only a native R2 binding/object surface. The locked SDK identifies body objects
by `bodyUsed` property presence; the proxy preserves that native property, native
binding constructor and unrelated method receivers. The plain synthetic stream
still goes through real Rust/native-reader/Wasm code. Broadening modulesRoot to
the repository root allows the production shim's relative glue/Wasm imports;
the existing module rules cover those file types. Hosted CI must verify actual
worker-build shim subclass compatibility; this review did not execute it.

| Contract | Source-level discriminating evidence |
| --- | --- |
| Oversized metadata | Zero pulls, one cancellation, no arrayBuffer |
| Oversized first chunk | One pull, one cancellation; following pull not requested |
| Cumulative overflow | Two pulls, one cancellation; first chunk admitted, second rejected |
| Durable rejection | Accepted state and original bucket object remain; no indexed text |
| Following work | Real healthy R2 archive becomes exactly indexed after rejected item |
| Egress | Fixture permits only the existing synthetic routing GET and rejects everything else |

The zero high-water mark intentionally removes producer prefetch from pull-count
assertions; these counts must not be described as real R2 network/chunk behavior.
The tests prove behavior through the built reader when hosted, not Wasm allocation
measurements or remote R2 cancellation reliability. Their `arrayBuffers` count
detects whole-object buffering; pre-copy rejection additionally depends on the
clear Rust ordering, not an instrumented Uint8Array copy counter.

Useful nonblocking follow-up contracts: exact-cap valid archive, short/long EOF
metadata disagreement, native read rejection followed by healthy progress, and
cancel rejection. The current three tests exercise overflow but not these paths.
Existing maximum-valid recovery tests supply a healthy large-body compatibility
case. They do not replace the separately deferred hung-read/hung-cancel deadline
and deployed CPU/RSS tests.

## Primary external sources checked

- [Locked workers-rs 0.8.7 R2 source](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/r2/mod.rs)
  and [GET builder](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/r2/builder.rs)
  establish native stream acquisition and body-object classification.
- [Cloudflare R2 Worker API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/)
  defines GET's body as a ReadableStream and distinguishes body-returning GET
  from metadata-only HEAD.
- [WHATWG Streams Standard](https://streams.spec.whatwg.org/#default-reader-prototype)
  establishes read result shape, rejection and reader lock-release semantics;
  [Cloudflare ReadableStream API](https://developers.cloudflare.com/workers/runtime-apis/streams/readablestream/)
  documents Workers' stream surface.
- [Workers production practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/)
  supports streaming instead of buffering unknown-sized inputs. This review uses
  API/standard verification and reuses the ADR's research grounding; it makes no
  novel academic or formal-verification claim.
