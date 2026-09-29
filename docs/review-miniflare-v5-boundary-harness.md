# Review: Miniflare v5 address-boundary harness correction

Reviewed on 2026-09-29. Scope: the `workers`-array change in
`infra/tests/worker-boundary/address-add.test.mjs`, the new
`miniflare-config-smoke.mjs`, its CI placement, the pinned package and lockfile,
and the failure in hosted run
[36578322798](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36578322798).
This was a static review; no local dependency install, Rust build, or live mail
request was run.

## Assessment

No substantive defect found in the focused correction. Run `36578322798`
reached all 13 cases, but each failed at `new Miniflare()` with
`ERR_VALIDATION`: top-level `modules`, `scriptPath`, `modulesRules`,
`compatibilityDate`, `bindings`, `d1Databases`, and `outboundService` were
rejected, and `workers` was required. It therefore supplies **no evidence**
about address registration, D1 activation, or the historical staging HTTP 500.

The corrected configuration puts the one named Rust/Wasm Worker and its D1,
bindings, and `outboundService` inside `workers: [{ ... }]`; `cf: false` stays at
the shared level. The current [Cloudflare-maintained Miniflare API reference]
(https://github.com/cloudflare/workers-sdk/blob/main/packages/miniflare/README.md)
documents both the array form (`SharedOptions & { workers: WorkerOptions[] }`)
and a per-Worker `outboundService` callback. It also documents that the first
Worker is the HTTP entrypoint, `getBindings()` defaults to that Worker,
`getWorker()` exposes `scheduled()`, and `dispose()` closes the runtime.
Those contracts match this single-Worker fixture.

The outbound callback handles only one-use, exact method-and-URL synthetic
OIDC/Routing exchanges and never delegates to Node `fetch`. An unmatched
request throws and increments a counter that the fixture asserts is zero.
No service binding or alternate network adapter is configured. Thus the
Worker's global `fetch` cannot reach the live Identity or Cloudflare Routing
API through this harness under the documented `outboundService` contract.
The early smoke uses an exact-match, local-only outbound callback and starts a
synthetic Worker with local D1; it runs before the expensive Rust build and
always disposes Miniflare in `finally`. The real test similarly disposes its
instance after success or failure.

## Verification boundary

The early smoke checks the constructor, event dispatch, D1 binding,
outbound callback invocation, and teardown, **not** the Rust/Wasm bundle or the
13 address assertions. The previously pinned `5.20260926.0-alpha` package had
behavior different from its own README, so the next hosted
run must prove that both the smoke and post-build tests execute. A green
synthetic run would be a regression guard, not a reproduction or repair of
the fourth live staging 500. No new real alias or provider route should be
created merely to validate this harness correction.

No production code, deployment binding, or live routing configuration is
changed by this focused patch.

## Stable v4 pin after v5 constructor failure (run 36579868487)

The next hosted run [36579868487](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36579868487)
failed in the early smoke before any Rust build. Its installed
`miniflare@5.20260926.0-alpha` rejected `name`, `modules`, `script`,
`compatibilityDate`, `d1Databases`, and `outboundService` at `workers[0]` and
required `workers[0].config`. This disproves the previous review's assumption
that the package's bundled README describes the pinned constructor: that README
still documents the v4 option shape, while the package's actual TypeScript
declarations define a v5 `{ workers: [{ config, dev }] }` schema.

The v5 package exports `convertV4MiniflareOptions`, but its implementation
explicitly rejects `modulesRules`, which the Rust/Wasm fixture needs to load
the generated binary. Reimplementing generated module discovery just for this
test would be fragile. Instead, pin the last published stable v4 release,
`miniflare@4.20260730.0`, whose Worker options include `modulesRules`, D1,
and `outboundService`. This is also the last v4 version in the npm version
list as of this review. The stable package depends on `undici@7.28.0`, inside
the [reported advisory range](https://github.com/cloudflare/workers-sdk/issues/15007),
so the pnpm workspace overrides that transitive dependency to patched
`undici@7.29.0` within the same major version. The lockfile records the exact
resolved versions.

The smoke dispatches an external-looking request through a local-only callback
and checks exactly one callback invocation, guarding the no-live-egress path
before a Rust build. It cannot prove the generated Rust/Wasm module graph loads:
that remains for hosted post-build tests. This is a fixture compatibility fix,
not evidence that the Rust Worker boundary cases pass or that staging HTTP 500
is resolved.

### Runtime compatibility-date ceiling (run 36581375547)

The following hosted run [36581375547](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36581375547)
passed the frozen v4 install, then failed at workerd startup: the fixture asked
for `2026-09-25`, while bundled workerd `1.20260730.1` supports at most
`2026-08-06`. Both synthetic fixtures now use that latest supported date.
**Production Wrangler configuration remains `2026-09-25`**; this local harness
tests the address-add logic on an older runtime, not exact production
compatibility behavior. That gap is intentional and must not be interpreted as
production parity. If a future regression depends on post-August runtime
semantics, upgrade this harness to a compatible newer workerd/module-loading
setup rather than silently changing the production date.
