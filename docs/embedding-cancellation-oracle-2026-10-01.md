# Embedding cancellation oracle: native workerd versus the Node bridge

## Decision

The two failing cancellation assertions in [hosted PR #20 run 36801826315](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36801826315), head `2b27109684452c1635f171000073c29b2c373530`, do **not establish that production cancellation is broken**. They observe a Node-side `ReadableStream` behind Miniflare's HTTP loopback bridge, not the native response reader used by Rust/Wasm. Exact pinned upstream source explains why cancellation need not propagate to that Node callback.

Do not merely delete the assertions or label this hosted result green. Replace the unsupported remote-source oracle with scoped instrumentation of the actual native reader cancellation and attached fetch abort signal; retain size, timing, public-error, approved-egress, and privacy assertions. Production code need not change on the evidence currently available. Exact-head hosted validation of the revised oracle remains required.

No local project tests/builds, real provider calls, deployments, secret access, or production edits were performed in this investigation. Only source inspection, public upstream retrieval, and existing hosted-run readback were used.

## Observed result and competing explanations

The exact hosted run passed 71 of 73 built-Wasm boundary tests. The oversized response returned the expected `503 semantic_unavailable`, and its Node source had not produced all 16 MiB by return. Header and body stalls returned in about 30.8 seconds, within the 39-second assertion. Only the Node `cancel()` boolean assertions failed. This is one hosted observation, not a latency distribution or production SLA measurement.

| Explanation | Evidence | Conclusion |
| --- | --- | --- |
| Rust never calls cancellation or abort | Candidate explicitly calls native reader `cancel()` on size/read error; timeout calls worker-rs `AbortController.abort()` | Static counterevidence, but runtime native invocation still needs an oracle |
| Miniflare loses the relationship between native transport and Node stream | Exact pinned bridge independently drains the Node stream and supplies no native abort signal to its reconstructed Node request | Strong source-backed explanation for the failed callback assertions |
| Node callback is merely delayed | Waiting cannot make an absent close-to-cancel bridge path a reliable contract | Not a sound basis for sleep/retry until green |

The existing `produced < total` assertion means only **not fully produced at API-return time**. It does not establish permanent source stoppage: the bridge can continue consuming its Node stream after the native Worker has stopped reading. It must not be presented as proof that a real provider was not drained.

## Exact dependency and primary-source chain

The fixture lock pins `miniflare 4.20260730.0` and `workerd 1.20260730.1`; Cargo.lock pins `worker 0.8.7`.

1. The [Miniflare release tag](https://github.com/cloudflare/workers-sdk/releases/tag/miniflare%404.20260730.0) is annotated tag object `f789c8b4bda494570fffc171723df3df5c66b316`, resolving to workers-sdk commit `96fd16f0e06e82eb99001c70e4935e992e69cb87`.
2. In [that exact Miniflare index.ts](https://github.com/cloudflare/workers-sdk/blob/96fd16f0e06e82eb99001c70e4935e992e69cb87/packages/miniflare/src/index.ts#L1541-L1597), `#handleLoopback` reconstructs a Node Request from the loopback HTTP request; lines 1579–1585 provide method, headers, body, duplex, and cf, but no native AbortSignal. The custom `outboundService` fetcher receives this reconstructed request.
3. [The same file's `#writeResponse`](https://github.com/cloudflare/workers-sdk/blob/96fd16f0e06e82eb99001c70e4935e992e69cb87/packages/miniflare/src/index.ts#L1813-L1870) independently iterates the Node response body at lines 1859–1861 and writes each chunk. This loop does not listen for response/socket close to cancel the iterator, and does not use `write()` backpressure to terminate iteration. An explicit comment at lines 1847–1849 explains why a pipeline is not used. Therefore canceling the workerd-side HTTP response does not entail invoking the original Node underlying-source `cancel()` callback. This is a limitation of this oracle/bridge, not a claim about every Miniflare transport mode.
4. [worker-rs 0.8.7 global.rs](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/global.rs) places the supplied signal on the second native fetch init object. [abort.rs](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/abort.rs) calls the real web-sys AbortController, rather than only dropping a Rust future.
5. The [pinned workerd tag](https://github.com/cloudflare/workerd/releases/tag/v1.20260730.1) resolves to `26b5461b7dcc640bb16072f1ba6f2c6df82572ba`. [Its HTTP implementation](https://github.com/cloudflare/workerd/blob/26b5461b7dcc640bb16072f1ba6f2c6df82572ba/src/workerd/api/http.c%2B%2B) uses `AbortSignal::maybeCancelWrap` for the header response promise, and wraps a received response body in `AbortableInputStream` tied to the request signal. This supports the native API boundary as the correct observation point. It does not prove the remote provider physically ceased all work.
6. [Cloudflare's native reader contract](https://developers.cloudflare.com/workers/runtime-apis/streams/readablestreamdefaultreader/) identifies `cancel()` as canceling the associated stream and returning a Promise. A Node stream in another process/transport is not that native stream.

Reproduce the source mapping without building or testing using GitHub's `git/ref/tags/miniflare%404.20260730.0`, then `git/tags/<annotated-object-sha>`, and `git/ref/tags/v1.20260730.1`. Read the commit-addressed files above, not mutable `main` snapshots.

## Minimal safe replacement oracle

Use a **test-only workerd module wrapper** importing and forwarding the unchanged built Rust shim. Patch native methods only in the isolated synthetic Worker realm, and preserve their original receiver, arguments, values, and promise fulfillment/rejection semantics. Do not reimplement production embedding logic or make the observer perform cancellation on behalf of production.

- Intercept native fetch only to identify the fixed approved embedding endpoint. Tag its exact second-init `signal` before awaiting fetch, so a header stall is observable. Tag the exact returned response body in a WeakSet. Do not inspect/log headers, input, keys, body content, or arbitrary errors.
- Tag a reader only when `getReader()` is called on that tagged response body. Observe the actual native `read`, `cancel`, and `releaseLock` methods only for tagged readers; all unrelated OIDC, D1, and API-body activity passes through uncounted.
- Record fixed numeric/boolean data: read calls, fulfilled chunk lengths, first cumulative-byte crossing of 65,536, reads after the crossing, cancel calls, cancel promise fulfillment/rejection, and release-lock calls. Native chunks may coalesce, so do not hard-code nine 8-KiB reads.
- For the oversize fixture, require expected private 503, a crossed native byte cap, zero further reads after crossing, exactly one native cancel invocation whose promise fulfills, and lock release. This distinguishes removing `cancel`, removing the byte cap, or reading additional chunks; it is stronger than the old Node boolean.
- For header/body timeout fixtures, require expected private 503 within the existing time window and that the **exact signal attached to approved fetch** becomes aborted through production's native controller invocation. A body fixture also establishes that a native reader was acquired/pending before abort. Observing pending native-read rejection can add evidence, but do not confuse callback scheduling after API return with failed transport cancellation.
- Export only fixed synthetic count headers from the wrapper's response; they must never be present in the production shim or deployment. Check sentinels against the observer output too. Normal exact-limit success should show no cancel/no abort, making the observer itself falsifiable.
- Explicitly close or otherwise stop the Node synthetic source in fixture teardown, independently of the production assertion. Label this cleanup as **fixture cleanup**, not observed provider cancellation; this prevents the bridge from draining 16 MiB after native rejection.

If native observation fails or instrumentation reliability is unclear, the next discriminating probe is a tiny independent JS workerd Worker calling native `fetch(...).body.getReader().cancel()` through the same pinned Node `outboundService`, with native completion observed and Node callback separately recorded. That control isolates the bridge without modifying the Rust production helper. Run it only in hosted Actions; no live provider is necessary.

## Scope of an eventual passing result

A passing revised hosted fixture would establish that the production built Rust/Wasm invokes and completes native reader cancellation on oversize, stops native reads at the bound, and invokes native abort on the attached fetch signal at the total deadline. It would **not** establish that the bridged Node source callback fires, that a provider stops computation immediately, that platform buffering is capped at 64 KiB, or that every real network/production cancellation path has been tested. Those distinctions must also replace the stronger unsupported wording in `docs/embedding-http-boundary.md` and the independent review record.

## Independent review of corrective fixture `a6ed78f`

Inspected `a6ed78f0a3608a5664259312da0622aa2a530ea6` in `.temp/embedding-http-bound`, including the complete new native observer, updated API fixture, module rules, and corrected documentation. **GO for exact-head hosted source CI**, with one narrow strengthening requested below; not runtime-success evidence or deployment approval.

- The observer imports/subclasses the built Rust WorkerEntrypoint and forwards `super.fetch(request)`; it does not supply substitute embedding, cancellation, timeout, or authentication behavior.
- `init?.signal` is the correct capture point for this pinned worker-rs API. `Fetch::send_with_signal` leads to `fetch_with_request`, which explicitly calls `init.set_signal(...)` and native `fetch_with_request_and_init(req, &init)`. It does not pass an undefined init and hide the signal only inside a Request.
- Streams/readers/signals are tracked by WeakSets only for the fixed approved endpoint. Every exercise constructs a new Miniflare instance/Worker realm; the observer's module-level stats do not accumulate across cases. Scope excludes OIDC/D1 traffic.
- Oversize assertions establish a native byte crossing, zero later reads, one cancel invocation and fulfilled cancellation, and no rejection. Exact-limit success's no-cancel/no-abort assertions provide a negative control. Counter headers contain no content and are covered by the existing sentinel check. Async wrappers add promise observation, not transport cancellation; their timing is diagnostic, not production-like profiling.
- The body-stall assertion should additionally require at least two native read invocations and nonzero received bytes. That demonstrates the short prefix was received and the next body read was pending, rather than permitting a header-stall failure to masquerade as body coverage. This was sent to the implementer/root before hosted push. Recording lock release is a useful optional assertion but is not necessary to distinguish the invalid Node callback from native cancellation.
- Revised exact-head hosted execution remains pending. This review does not suppress the previous 71/73 failure or assert a real-provider result.
