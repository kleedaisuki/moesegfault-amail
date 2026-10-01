# Provider-free EmailService and accepted-send race harness

## Decision and scope

Investigated 2026-10-01 at Mail `origin/main` `ea54512f8ce798e097bc7645e5ee2f690030748c`. This is a source-supported harness design, **not an executed test result**. No local project build/test, live mail, provider API, or deployment was performed. Only this investigation document is changed.

**Use the existing hosted Rust/Wasm workerd lane, with a generated test-only entry module that substitutes `EMAIL.send` and intercepts the return of the real D1 acceptance UPDATE.** Keep production Rust, generated production shim, D1 schema, and R2 objects untouched. A send-only deferred promise cannot reproduce the consequential race: it blocks *before* the accepted journal exists. The deterministic barrier belongs *after* native D1 commits `state='accepted'` and *before* its `run()` promise resolves to HTTP Rust.

This follows the project's existing address-boundary approach: real built Rust/Wasm, local platform storage, tightly controlled synthetic I/O. Cloudflare itself maintains local MessageBuilder sending tests. No claim is made that this exact race harness is independently production-proven; the supported primitives and upstream regression practice are the evidence, while the new combination requires hosted execution.

## Versioned evidence

| Layer | Inspected evidence | Consequence |
|---|---|---|
| Project lock | `Cargo.lock`: worker / worker-sys / worker-macros **0.8.7**; Cargo.toml's `0.8.3` is a compatible range | Inspect resolved version, not minimum manifest version |
| Rust binding | [v0.8.7 SendEmail EnvBinding](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/email.rs), [generated bindings](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker/src/bindings/email.rs) | SendEmail uses unchecked JS object conversion; builder send is JS `.send(builder)` and result getter is `.messageId` |
| Built entry | [v0.8.7 shim](https://github.com/cloudflare/workers-rs/blob/v0.8.7/worker-build/src/js/shim.js) | Default export is a proxied WorkerEntrypoint class, **not** a default object with static fetch/scheduled |
| Existing hosted runtime | `infra/tests/worker-boundary/package.json`, lock, `address-add.test.mjs` | Pinned Miniflare **4.20260730.0**, workerd compatibilityDate **2026-08-06**, actual production Wasm build, local D1 and strict outboundService |
| Miniflare simulation | [pinned email plugin](https://github.com/cloudflare/workers-sdk/blob/miniflare%404.20260730.0/packages/miniflare/src/plugins/email/index.ts), [pinned implementation](https://github.com/cloudflare/workers-sdk/blob/miniflare%404.20260730.0/packages/miniflare/src/workers/email/send_email.worker.ts) | `email: { send_email: [{ name: 'EMAIL' }] }` installs local WorkerEntrypoint `.send`, validation, files/logs, synthetic ID; no barrier/fault injection option in plugin schema |
| Upstream tests | [pinned email regression tests](https://github.com/cloudflare/workers-sdk/blob/miniflare%404.20260730.0/packages/miniflare/test/plugins/email/index.spec.ts) | MessageBuilder local integration is exercised upstream, not just a TypeScript declaration |
| Supported harness channel | [pinned Miniflare README](https://github.com/cloudflare/workers-sdk/blob/miniflare%404.20260730.0/packages/miniflare/README.md), serviceBindings and wrappedBindings sections | Function-valued service binding can access Node test state and return an awaited Response; JSON `bindings` cannot carry functions |

The pinned README's generic “Sending Email ... Not yet supported” paragraph conflicts with the inspected pinned email plugin and its upstream tests. Use executable source/schema as stronger evidence here; do not infer absence from that stale paragraph or use main's newer configuration shapes for the pinned package.

[Current local sending documentation](https://developers.cloudflare.com/email-service/local-development/sending/) explicitly separates local simulation (not delivered) from `remote: true` (real mail). It documents binary attachment serialization limits. Therefore **never** enable remote bindings for this harness; ordinary native local simulation is useful for a separate smoke test but is not a deterministic acceptance-race injector.

## Concrete test-only route

Generate the entry under the build module root, for example `crates/mail-worker/build/worker/accepted-race-test.mjs`, in hosted CI or the test's setup only. Load it with existing `workerModuleRules` so `shim.mjs`, `index.js`, and `.wasm` remain the actual built artifacts. Do not overwrite `shim.mjs`. Do not add a production feature flag or runtime endpoint.

The source-supported entry pattern is a subclass of the built default class:

```js
import BuiltWorker from './shim.mjs';

/** Replace only synthetic external acceptance and one await boundary. */
export default class RaceWorker extends BuiltWorker {
  constructor(ctx, env) {
    super(ctx, {
      ...env,
      EMAIL: {
        /** Exercise Rust's real builder conversion, not provider MIME transport. */
        async send(builder) {
          const response = await env.TEST_CONTROL.fetch('https://test.invalid/send', {
            method: 'POST',
            body: JSON.stringify({
              from: builder.from, to: builder.to, subject: builder.subject,
              attachmentCount: builder.attachments?.length ?? 0,
            }),
          });
          if (!response.ok) throw new Error('synthetic send failure');
          return await response.json(); // { messageId: '<synthetic@example.invalid>' }
        },
      },
      MAIL_DB: wrapDatabase(env.MAIL_DB, env.TEST_CONTROL),
    });
  }
}
```

This pattern must first pass a hosted built-shim smoke test; inheritance through worker-build's proxied class is source-supported but was not executed during this investigation. If the installed worker-build emits a different default shape, fail with a clear contract assertion rather than guess/copy generated Rust handler code. Keep the original initialization/reset machinery in the import and inheritance path.

`wrapDatabase` should be a thin JS Proxy around the **native** D1Database. Preserve `.constructor` and bind nonintercepted methods to their native target; worker-rs D1 EnvBinding checks the constructor name. Intercept `.prepare(sql)` only to decorate the returned native statement. Rewrap `.bind(...args)` results. For the exact HTTP acceptance UPDATE, replace `.run()` with:

```js
/** Expose a committed accepted journal before allowing HTTP projection to resume. */
async function acceptanceRun(nativeStatement, control) {
  const result = await nativeStatement.run();
  if (result.success && result.meta.changes === 1) {
    const response = await control.fetch('https://test.invalid/after-accepted', {
      method: 'POST',
    });
    if (!response.ok) throw new Error('synthetic post-acceptance failure');
  }
  return result;
}
```

Match a fixed known SQL contract (normalized whitespace, full acceptance prefix plus owner/idempotency guard), assert the match is hit exactly once, and fail the test if it moves. Do not intercept all UPDATEs, mutate native `meta.changes`, simulate SQL results, or gate Cron's `state='sent'` UPDATE. Externally executed fixture queries use `mf.getBindings().MAIL_DB` directly and bypass the wrapper.

Configure `serviceBindings: { TEST_CONTROL: async (request) => ... }` with a Node deferred promise for `/after-accepted`. `/send` records the safe synthetic builder fields and returns one fixed valid messageId. The controller never calls fetch, never serializes attachments/body into logs, rejects unknown method/path, and always releases/rejects the deferred barrier in `finally`. Use finite Node test timeouts, not sleeping to encourage a race. Synthetic fixtures contain no actual user's identity or correspondence.

## Deterministic schedule and assertions

1. Fresh native local D1 with all production migrations; local R2; ephemeral OIDC key/token; owned active synthetic alias; valid independently built ZIP; sending configured enabled, dependency embedding paused or fully mocked. Global outboundService is strict allowlist, with unexpected requests failing/counting; no live credentials.
2. Start real `POST /v1/send` without awaiting completion. `.send(builder)` returns fixed provider ID once. Native acceptance UPDATE commits. Controller signals the barrier arrived and holds its Response.
3. Read native D1: assert one `accepted` row with the expected message/provider IDs, R2 archive present, and no projected message/body chunks yet. This prevents a superficially green test blocked at the wrong boundary.
4. Dispatch `await (await mf.getWorker()).scheduled()` while HTTP remains blocked. Assert exact projection content/metadata, chunk contiguity, storage ledger, and journal state according to the intended recovery contract.
5. Release HTTP. Assert convergent HTTP outcome and exactly one provider `.send` invocation. A correctness improvement may allow idempotent 202; a handled pending outcome is distinct from a Wasm trap or data loss. Assert no projected chunk deletion or duplicate message.
6. Repeat Cron and replay the same HTTP idempotency key; assert no provider resend, no body loss, no storage/quota double counting, same message ID. Also exercise inverse order and one post-acceptance injected throw to verify durable recoverability.

For the known code path examined in `.temp/accepted-recovery-integrity/crates/mail-worker/src/lib.rs`, provider success is followed by the accepted UPDATE and then `store_text`, INSERT messages, ledger marking, and sent UPDATE. Recovery independently selects accepted rows. The chosen boundary directly separates these operations. The integrity implementer may move/refactor SQL; the harness must update its explicit contract rather than silently missing the barrier.

## Fidelity and adoption limits

| Established if hosted test passes | Not established |
|---|---|
| Actual Rust send handler, ZIP validation, builder JS conversion and messageId getter | Cloudflare provider acceptance, actual MIME compilation, binary attachment delivery |
| Actual Wasm async interleaving across HTTP/Cron with real local SQLite/D1 and R2 | Deployed D1 replication/timing, production quotas or account configuration |
| Actual acceptance journal and projection race, with deterministic barrier | Provider unknown outcomes unless separately scripted; live deliverability |
| Exactly-one *mocked* provider invocation and idempotent persistence | Universal exactly-once mail delivery across network failures |

Keep a separate native simulation smoke if binding construction fidelity matters, and retain the already required live bounded outbound acceptance after privacy/operational gates. Synthetic tests are the fast discriminating regression layer, not permission to skip deployed acceptance. A serviceBindings callback is I/O through a supported internal harness channel, not interception of EmailService by global fetch: global `outboundService` alone cannot replace `.send`.
