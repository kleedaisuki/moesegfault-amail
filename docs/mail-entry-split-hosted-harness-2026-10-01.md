# Hosted native Mail entry-split harness

Date: 2026-10-01. Source baseline: `origin/main` at `8ca1815`.
Scope: credential-free test/observer changes only; no production entry/config,
Rust business code, package/lock/workflow, provider write, deploy or activation.
Implementation dependency: `crates/mail-worker/entry/{api,maintenance}.mjs` from
the separately owned scheduled-only product split implementation.

## Evidence contract

This fixture must run on GitHub Actions after **one actual worker-build 0.8.5
module-mode Mail build**. It imports the unchanged generated
`build/worker/shim.mjs` alias/module tree and the actual checked-in adapters.
No mock handler object or handwritten replacement SDK can satisfy the tests.
Node syntax checking is not hosted runtime evidence. No project build or test
was executed locally for this change.

Design/review inputs are Git objects `2065c76` and `a4392e2`. SDK implementation
was inspected in the cached pinned `worker-build-0.8.5/src/{main.rs,js/shim.js}`;
these match the [pinned generator](https://github.com/cloudflare/workers-rs/blob/cc174db40ba9f648623805e98053a4eba3bb50c0/worker-build/src/main.rs)
and [recovery shim](https://github.com/cloudflare/workers-rs/blob/cc174db40ba9f648623805e98053a4eba3bb50c0/worker-build/src/js/shim.js).
The generator constructs ordinary scheduled/fetch methods returning the Wasm
handler result, wrapped by the SDK Proxy. Composition is tested as this actual
runtime graph, not as an object with copied methods.

| Obligation | Native discriminator |
| --- | --- |
| Closed uploaded application surface | `mail-entry-split.test.mjs` loads both actual entries as separate native Workers; observer imports their ESM namespaces and checks only default export, exact own prototype methods, direct platform base. Maintenance cannot inherit generated app fetch/RPC. Native attempted HTTP cannot return a business response; API scheduled invocation cannot succeed. |
| Actual shared build artifact | Both source adapters import the same generated alias; module-mode alias must resolve to `../index.js`; the single `index_bg.wasm` byte digest remains identical. This is shared input evidence, not provider-upload digest evidence. |
| Initialization and lifetime | Real Rust cleanup finishes on eight successive scheduled slots with D1/R2 and only reviewed background capability names, without OIDC/ingress/send/Mail-domain bindings. |
| Event/Env/context preservation | Local observer forwards the original generated scheduled function and records exact controller, Env and context identity, cron/time and unchanged returned Promise identity. Independent Node-owned service barriers keep fixture background work pending after Rust completion; registered work must hold native dispatch, while an otherwise identical unregistered negative control must not. |
| SDK critical reset branch | A local Wasm module executes `unreachable` inside a temporary synchronous handler-method substitution on the **actual generated SDK prototype**. SDK Proxy must record the critical error; restoration precedes a subsequent actual Rust event. Exactly one SDK reinitialization log and completed post-reset D1 cleanup are required. |
| Eight rotations and complete-item semantics | Existing liveness fixture now subclasses the actual maintenance adapter and retains all eight/delayed/duplicate/missed-slot phase-order, item admission and complete-publication assertions. |
| Statement accounting and deadlines | Existing native counter, Routing, R2, embedding and final-diagnostics observers route through maintenance; assertions/budgets/deadline logic are not loosened or copied into a new implementation. |
| Real HTTP/Cron overlap | Accepted race uses separate actual API and maintenance adapters, separate Wasm/isolate instances, same explicit native D1/R2 identities, shared synthetic provider/lease barriers, and existing publication/delete/no-resurrection assertions. Address HTTP/Cron fixtures likewise use two real adapters over one local database. |

## Deliberate test-only machinery and limitations

`mail-entry-split-observer.mjs` is an independently configured local control
Worker. Its HTTP methods, introspection, lifecycle forwarding, temporary SDK
prototype substitution and trap injection **must never enter deploy inputs**.
The generated trap/control entry files live only in a uniquely named root
`.temp/mail-entry-split-*` directory and are removed after Miniflare disposal,
including failures. Production-generated build output is never rewritten or
polluted with a copied observer. Existing race observer now remains under
`infra/tests/worker-boundary` rather than being copied into `build/worker`.

The critical-error test proves the SDK's real synchronous panic/reset boundary;
it does **not** prove that an asynchronous Rust business panic is reset safely.
The generator's ordinary function branch catches synchronous throws, not every
rejected Promise. A separate real Rust panic regression remains an explicit
integration gate if panic coverage is required: obtain a reproducible Rust trap
or a separately built test crate, preserve the actual generator and distinguish
its global-error recovery path. Never describe this synthetic Wasm trap as an
observed Mail business panic, and do not add production panic hooks to pass it.

The waitUntil sentinel is fixture-owned background work launched after the
actual scheduled Promise completes, then held behind an independent service
barrier. Registered and unregistered controls differ only in native context
registration; their release barriers are always discharged during cleanup.
This does not claim Mail's
scheduled business function currently creates its own background tasks. The
API's genuine foreground and trace `ctx.waitUntil` contract continues to run in
its existing boundary/embedding/race paths through the API adapter. Production
surface absence is introspected separately from control observers, which may
have extra local-only HTTP/RPC methods by design.

Embedding instrumentation has a fixture-only dual event surface, composing the
actual API and maintenance adapters; its stream/cancellation/clock hooks remain
unchanged. It is not used as deployed surface evidence. Other scheduled-only
observers subclass maintenance and expose only their pre-existing local numeric
control paths; they no longer forward an application fetch fallback.

All synthetic egress is closed, with explicit local Routing responses and no
fallback to network/provider fetch. The harness uses `2026-08-06`, supported by
the pinned Miniflare/workerd dependency; production's `2026-09-25` configuration
is not modified or claimed validated by changing the test date.

## Integration and verification

The production split owner owns package/workflow changes and must add
`node --test mail-entry-split.test.mjs` to hosted checks after the actual build.
Retain existing default boundary suites and separately selected embedding,
Routing, maintenance-liveness and maintenance-diagnostics hosted jobs. Their
observers now require the adapter files. Rebase with accepted batching without
changing phase/budget/lease assumptions; exact statement expectations belong to
that accepted batching change and must be reviewed with its artifact.

Before commit: static `node --check` on every changed/new `.mjs` and
`git diff --check`. No dependency installation, project test/build, workload,
provider access, credentials, push, PR or deploy. Hosted outcomes, provider
surface/privacy pins, natural adaptive population inclusion, resource admission
and public-send gates remain **unverified/unchanged** until separately evidenced.

## Corrected lifetime discriminator after independent review

Independent review `fb7b6bb` found candidate `c4439f3` unsuitable for complete
lifecycle acceptance: its marker resolved from the same returned Promise and
could pass without `waitUntil`. The corrective fixture uses separately owned,
bounded arrival/release barriers and a negative control that omits registration.
While both background operations remain blocked, native unregistered dispatch
must finish and native registered dispatch must remain pending. Only releasing
the positive barrier may complete its background marker and dispatch. Failure
cleanup releases both barriers and awaits bounded event settlement.

Root reviewed the pending correction after the interrupted task was resumed.
Static Node parsing and whitespace checks are the only local verification;
actual lifetime/cancellation behavior still requires the integrated hosted
workerd build. The original reviewer limitation on asynchronous Rust panic
recovery is unchanged.

## Root integration after batching and Queue deadline

Integrated onto main 901fa73 (PR33), not the older pre-batching fixture baseline.
The existing accepted-stage observer now composes both real product entry adapters
rather than inheriting the mixed generated SDK; its test-only HTTP controls remain
outside upload inputs. The 379-statement native counter and 66-chunk/nine-stage-
transaction oracle are preserved. The thirteen final diagnostic cases, including
never-settling and committed/late acknowledgement, remain selected unchanged.
`test:entry-split` is registered as a separate hosted Worker CI step. Mail deploy
bundlers are aligned to the already-tested worker-build 0.8.5; no deployment target
is invoked by these source checks. No local runtime or toolchain install occurred.

The previous independent review rejected the original waitUntil case because it
registered the already-returned Rust completion. The amended case uses independent
Node-owned service barriers, a registered positive and identical omitted-registration
negative control. Actual workerd execution must distinguish them; source inspection
alone is not acceptance. Hosted results remain pending before provider operations.
