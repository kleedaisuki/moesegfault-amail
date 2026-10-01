# Independent embedding HTTP boundary review — 7363835

## Decision and scope

**GO for hosted source CI after the narrow lifetime correction `91b1de5`.** The initial static review did not identify the subsequently demonstrated compile defect; the hosted result and corrective review below supersede that part of the initial assessment. This is not deployment approval, production runtime verification, or proof that the whole Cron invocation fits platform resource limits. Reviewed candidate `7363835eb9fb332c558dc75488c01515fa4aba9c`, based on `c6f93bf`, with particular attention to `crates/mail-worker/src/platform.rs`, the separate built-Wasm fixture, its package script, and existing CI invocation.

No local project test/build, live provider call, deployment, or secret access was performed. Runtime assertions remain pending GitHub Actions. Confidence is high for the static contract and moderate until the native fetch/reader cancellation fixtures run in workerd.

## Hosted compile failure and exact correction

[Hosted run 36801307357](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36801307357) reported Rust E0597 in `platform.rs`: the tail-expression select/match temporary retained the losing exchange future borrowing the local abort signal through local destruction. This is concrete negative compilation evidence, not an unverified concern, and the initial static GO was not a compilation-success claim.

Independently inspected exact correction `91b1de57cfb2f8ed52f76e6d673ba8e0bdaccb7a`, atop PR #20 head `0c9e1f1`. Its only changed file is `crates/mail-worker/src/platform.rs`; it binds the existing match to local `result`, terminates the statement, then returns the owned result. The select temporary and losing future are thus destroyed before `signal`. The owned result retains no borrow. Timeout still calls native `controller.abort()` inside the same branch before returning the fixed transient error; dropping a Rust future does not replace native abort.

**Narrow corrective review: GO to push for exact-head hosted source CI.** No fixture, deadline, redirect, response cap, status classification, or public-error changes. No local project build/test, live provider call, or deployment was performed. A subsequent exact-head hosted compile and runtime fixture result remain necessary; this update does not claim the E0597 fix has already compiled or that native cancellation has passed runtime tests.

## Checked contracts

- `Cargo.lock` pins worker 0.8.7. Current official generated Rust API exposes `Fetch::send_with_signal(&AbortSignal)`, `AbortController::signal`, consuming `abort(self)`, and `Response::body()`. The implementation uses these signatures coherently. In corrected source `91b1de5`, a non-tail match statement destroys the select temporary/losing exchange future before the locally owned signal is destroyed.
- A fixed approved URL and `RequestRedirect::Manual` prevent following 3xx responses. Cloudflare explicitly warns that outbound default-follow redirects forward sensitive headers across hosts. Existing failure classification is preserved and provider bodies/JS errors are not added to diagnostic errors.
- One select deadline includes both native fetch and body consumption. The timeout branch aborts before returning its fixed transient classification. It does not merely drop the Rust future and claim that native transport was stopped.
- The successful-body path gets a native reader, checks the incoming typed-array length before a Rust copy, uses subtraction of the already bounded accumulator length, and stops before requesting another over-limit chunk. Cancellation on read/size failure is awaited within the same deadline. Lock-release and cancel errors are discarded without raw error logging. Empty/invalid JSON still enters the fixed malformed class.
- Successful result validation and 256D unit normalization are unchanged. The bound protects the Rust accumulator, not platform buffering, a provider-created single JS chunk, synchronous JSON CPU time, or whole-request duration; documentation correctly makes these distinctions.
- Existing invalid-request/dependency/rate-limit/transient status classes remain intact. Public semantic errors remain fixed `503 semantic_unavailable` through the existing caller. The change does not log input, key, provider body, or arbitrary JS errors.

## Hosted fixture assessment

The fixture drives the production built Rust/Wasm semantic route with migrated synthetic D1, ephemeral signed OIDC, and deny-by-default egress. Its independent assertions cover all five common redirects, exact-limit success, oversize early rejection and underlying cancellation, malformed/truncated/wrong-dimension response, header/body stalls, and sentinel absence from API body/headers/runtime diagnostics. The package script includes the new file and existing CI invokes `pnpm test` after the production bundle is built.

These tests can discriminate important regressions: auto-follow causes forbidden foreign egress; removing the body bound yields a drained large response; removing the deadline permits the stalled body to exceed the Node test timeout and makes the delayed valid header response succeed instead of returning unavailable. The elapsed assertion alone is deliberately not taken as proof of an exact 30-second return, because setup/disposal and the synthetic outbound-service lifetime are included.

The fixture does not establish a real OpenRouter SLA, production Cloudflare cancellation behavior beyond the hosted workerd environment, every non-200 scheduler class, or an upper bound on the entire Cron. Those limits do not block hosted source CI for this bounded change.

## Resolved documentation correction

The initial source note referenced worker-rs v0.8.3 while Cargo.lock pins 0.8.7. Independently inspected follow-up `c343170876dcba293fc4b761c4f5c862fb59774d`: it changes only the two reference labels/URLs to v0.8.7. The issue is resolved; the production and fixture diff remains exactly `7363835`. The final candidate through `c343170` retains the GO-for-hosted-source-CI verdict.

## Primary references checked (2026-10-01)

- [Cloudflare Request API](https://developers.cloudflare.com/workers/runtime-apis/request/): manual redirect and abort-signal semantics, sensitive-header forwarding warning.
- [Cloudflare native default reader API](https://developers.cloudflare.com/workers/runtime-apis/streams/readablestreamdefaultreader/): read, cancel, and release-lock contracts.
- [Cloudflare Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/): bounded/streamed external responses and production error discipline.
- [worker 0.8.7 Fetch API](https://docs.rs/worker/0.8.7/worker/enum.Fetch.html) and [current source](https://docs.rs/worker/latest/src/worker/global.rs.html).
- [worker 0.8.7 AbortController API](https://docs.rs/worker/0.8.7/worker/struct.AbortController.html) and [current source](https://docs.rs/worker/latest/src/worker/abort.rs.html).
- [worker 0.8.7 Response API](https://docs.rs/worker/0.8.7/worker/struct.Response.html) and [current source](https://docs.rs/worker/latest/src/worker/response.rs.html).
