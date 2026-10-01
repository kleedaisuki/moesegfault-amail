# Embedding outbound HTTP boundary

## Contract

The Rust Mail Worker sends one POST only to the fixed OpenRouter embedding endpoint. It requests the configured Qwen embedding model, 256 dimensions, and the existing zero-data-retention/data-collection-deny policy. `RequestRedirect::Manual` refuses all redirect responses under the existing transient classification; Authorization and private query/document input cannot be forwarded to a redirected origin.

One hard 30-second deadline spans fetch headers and the response body, using worker-rs `AbortController`, `Fetch::send_with_signal`, and the platform `Delay`. Deadline expiration aborts the native transport and retains `provider_transient`; no raw network error is propagated. This is a wall-clock transport bound, not a promise that JSON decode/CPU execution or the entire API request finishes in 30 seconds.

Only status 200 is decoded. Existing status classes remain unchanged (400/413/422 invalid request, 401/403 dependency, 429 rate limit, other statuses transient). The successful response body is limited to **65,536 actual decoded bytes**, independently of Content-Length. Its native `ReadableStreamDefaultReader` reads chunks incrementally. The JavaScript typed-array length is checked before a Rust copy, avoiding worker-rs ByteStream's unconditional per-chunk allocation. A chunk crossing the remaining allowance is rejected without accumulation or a further read. Reader cancellation is explicitly awaited on size/read failure, then its lock is released; cancellation/release errors never enter diagnostics. Native transport abort terminates pending reads at the total deadline. The platform still owns the incoming JavaScript chunk, so this is not a bound on provider/platform internal buffering or arbitrary single-chunk allocation before Rust observes it.

The accumulated bounded bytes are decoded using serde_json only after EOF. JSON/dimension/nonfinite/zero-norm failures preserve `provider_malformed`. A valid 256D result keeps the existing unit-normalization behavior. Public semantic-search failure remains `semantic_unavailable`; neither response text, API key, query, nor document text is attached to diagnostics.

## Hosted regression coverage

`infra/tests/worker-boundary/embedding-http.test.mjs` exercises the production Rust/Wasm bundle in Miniflare/workerd, with fresh migrated local D1, ephemeral signed OIDC credentials, and denied-by-default synthetic egress:

- 301/302/303/307/308 foreign redirects: exactly one approved provider exchange, zero foreign calls;
- valid 256D JSON at exactly 64 KiB: successful semantic API result;
- 16 MiB incrementally generated response with no Content-Length: early rejection, native scoped reader cancellation fulfills, no reads after the over-limit chunk;
- malformed JSON, truncated JSON, wrong dimensions: existing private public failure;
- stalled headers and stalled body: real 30-second transport deadline and the exact attached native fetch signal observed aborted;
- private query, provider-body, and key sentinels absent from API body/headers and captured runtime logs.

The existing Worker CI `pnpm test` automatically includes this separate file. No live provider request, local project build, or local project test was performed. Static Rust formatting, JavaScript syntax, and Git whitespace checks were performed; **hosted runtime results remain pending**. These fixtures are integration regression evidence, not production deployment evidence or a provider availability/SLA guarantee.

## Cancellation oracle correction

Hosted run [36801826315](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36801826315) compiled the Rust implementation and passed 71 of 73 workerd tests. The two failures were Node-side synthetic `ReadableStream.cancel()` callback assertions, while oversized-body 503, early rejection, valid responses, redirects and both approximately 30.8-second deadline responses passed. This does not establish upstream source cancellation.

The pinned Miniflare bridge explains why the original oracle was invalid: [index.ts at commit 96fd16f](https://github.com/cloudflare/workers-sdk/blob/96fd16f0e06e82eb99001c70e4935e992e69cb87/packages/miniflare/src/index.ts) creates the Node loopback request without the native abort signal (lines 1579–1585), and independently drains `response.body` with `for await` while ignoring `write()` backpressure and without a response-close-to-iterator-cancel path (lines 1859–1861). Native workerd cancellation therefore need not invoke the original Node callback. The observed `produced < total` is a return-time observation, not proof that this independent bridge producer permanently stopped.

The revised **test-only** `embedding-native-observer.mjs` subclasses the unchanged generated Rust WorkerEntrypoint. Its pass-through instrumentation tags only the fixed OpenRouter exchange's native body and attached signal, excluding Identity and D1. It records reader read counts/byte lengths (never body contents), cancellation invocation and fulfillment, absence of reads after crossing the cap, and native abort invocation plus that exact signal's `aborted` state. Fixed synthetic response headers carry only numeric counters. The fixtures explicitly close the independent Node producer during cleanup. Production Rust is unchanged by this oracle correction; neither the observer nor its synthetic headers are deployed. Revised hosted results remain pending. This proves native API use when passing, not a guarantee that a remote provider stops computation or that the Node bridge propagates cancellation.

## References

- [Cloudflare Request API redirect warning](https://developers.cloudflare.com/workers/runtime-apis/request/): default-follow outbound fetch may forward sensitive headers.
- [Cloudflare response API](https://developers.cloudflare.com/workers/runtime-apis/response/): JSON helpers consume the complete body.
- [worker-rs 0.8.7 (Cargo.lock) Fetch implementation](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/global.rs): native abort signal propagation.
- [worker-rs 0.8.7 (Cargo.lock) ByteStream implementation](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/streams.rs): typed-array-to-vector copy before the caller sees a chunk.
