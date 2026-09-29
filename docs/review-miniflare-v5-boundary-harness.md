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
The early smoke likewise installs a throwing outbound callback and starts a
synthetic Worker with local D1; it runs before the expensive Rust build and
always disposes Miniflare in `finally`. The real test similarly disposes its
instance after success or failure.

## Verification boundary

The early smoke checks the v5 constructor, event dispatch, D1 binding, and
teardown, **not** the Rust/Wasm bundle, outbound callback invocation, or the
13 address assertions. The pinned `5.20260926.0-alpha` package can have
behavior different from the current `main` API reference, so the next hosted
run must prove that both the smoke and post-build tests execute. A green
synthetic run would be a regression guard, not a reproduction or repair of
the fourth live staging 500. No new real alias or provider route should be
created merely to validate this harness correction.

No production code, deployment binding, or live routing configuration is
changed by this focused patch.
