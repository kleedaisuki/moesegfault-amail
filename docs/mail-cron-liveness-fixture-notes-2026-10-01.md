# Native Cron liveness fixture notes (2026-10-01)

## Scope and evidence status

The new `maintenance-liveness.test.mjs` exercises the unchanged built Rust/Wasm
scheduled handler through a test-only WorkerEntrypoint subclass and native
Miniflare D1/R2. It is selected by `pnpm test:maintenance-liveness` in the existing
non-deploying Worker CI checks after worker-build. No provider resources, Email
binding, real SMTP, Identity, or OpenRouter are involved. Unexpected egress fails
closed; the sole allowed external request is a local empty routing inventory.

**Runtime evidence pending GitHub Actions.** Only `node --check` was run locally
on both new modules. No local project build or runtime test was performed. No
push, commit, deployment or provider mutation was performed.

## Discriminators

| Case | Mechanism | Required observation |
| --- | --- | --- |
| Slow maximum valid accepted item | Native 300 ms timer before each of 66 real chunk UPSERTs | At least 19.8 s real invocation time; first journal sent; exact 4,000,000-character reconstructed text; second due CAS and R2 GET untouched; later retention target deleted |
| Cutoff during admitted projector | Invocation-only Date.now offset +116 s after the 40th successful chunk | All 66 writes and atomic publication finish; no new business phase submission or second item admission; retention target remains |
| Slow setup | Offset +16 s after the outbound stale-reservation setup submission | First complete item still receives its entitlement; no second due CAS or R2 GET |
| Insufficient headroom | Offset +56 s after the first addresses submission, with addresses-first slot | Outbound setup, due CAS, R2 access and chunks all absent |
| Rotation | Eight configured scheduled slots plus duplicate and skipped slot events in one isolate | Native phase first-submission order matches slot modulo eight, independent of event receipt order |

`accepted()` seeds only synthetic immutable ZIPs through the production held-send
one-use canary trigger. The trigger grant is expired before scheduled dispatch.
Readback independently reconstructs text from `messages` and ordered chunks.
Setup and readback use direct native bindings, never observer counters.

## Observer semantics and limits

The observer wraps `prepare`/`bind` but records only executor invocation, not
speculative statement construction. Due CAS IDs and native R2 accesses are captured
to distinguish admission from partial attempt. Native batch statements are
unwrapped and retain actual transaction semantics. Phase detection recognizes
only existing phase entry SQL, retaining a unique first-submission order. Unknown
D1 submission methods fail rather than silently escaping observation.

Logical clock injection is confined to `scheduled()` and restored in `finally`.
No production flags or policy injection APIs are added. Offsets exercise admission
policy, not native timer cancellation or real platform hard termination. The real
300 ms case remains essential: a fake-clock-only test is not evidence that the
old 15-second chunk-loop starvation discriminator runs against wall time.

The fixtures do not emulate Paid remote D1 quotas, production latency, cancellation
of admitted writes, or a hard end-to-end 120-second bound. Runtime pass/fail must
be evaluated on the exact hosted build. Native timers and all binding submission
paths remain integration risks until that hosted run completes.

## Interface reference

Cloudflare's [Miniflare Scheduled Events documentation](https://developers.cloudflare.com/workers/testing/miniflare/core/scheduled/)
documents `getWorker().scheduled({ scheduledTime: new Date(...) })`; explicit
historical slots make invocation arrival time distinct from schedule-slot order.
The fixture uses the repository's pinned Miniflare version and existing module
rules/migration fixture rather than introducing a separate runtime setup.
