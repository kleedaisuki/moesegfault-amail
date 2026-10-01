# Worker packaging boundary probe

Status: initial hosted observation succeeded; consolidated workflow awaiting its
own hosted observation. This does not
change ordinary deployment, native source acceptance, provider state or release
admission. No local build/runtime/install is part of the investigation.

## Question and smallest discriminating experiment

The ordinary artifact foundation now restores and rechecks native-tested
generated module trees instead of compiling again in deployment jobs. Pinned
Wrangler still performs a final JavaScript bundle. Does that packaging preserve
Wasm bytes and the composed Mail HTTP/private Queue semantics, and which exact
boundary remains untested? A source artifact hash cannot answer this question.

The packaging mode of the existing native-fixture diagnostic selects **one
explicit successful full-main source run** using its existing `build_run_id`,
validates the original required job/artifact inventory,
downloads its fixed artifact ID and runs the unchanged strict original-context
restore. Successful main `push` and `workflow_dispatch` runs are both accepted;
there is no push-only discovery query, newest-run fallback or uniqueness
assumption across multiple successful runs. The original source must be an
ancestor of the current checkout. Current checkout differences may contain only
the existing native-fixture workflow, this probe's helper/fixture/contracts,
the replay workflow contract test and public Markdown. Rust, adapters, configs, runtime/lockfiles,
ordinary admission/build policy and unknown inputs require a new source build.
Original build and current diagnostic identities remain distinct.

Wrangler `4.142.0 deploy --dry-run --outdir ... --metafile ...` packages each of
the six ordinary generated products with its real source-owned config, for the
default and existing staging environments (the Identity inbox's default config
is itself staging-only). There are no Cloudflare credentials, protected
environment, secret file, Rust toolchain or custom build command. The native
tracing canary is excluded because its config deliberately contains a Rust
custom build; it has separate source-owned tested-byte deployment configs.
Every original generated input is rehashed before/after packaging. The receipt
records package timing, config/output hashes, exact matching original Wasm and
whether the final JavaScript matches any tested generated JavaScript module.
Unexpected multiple/missing JS/Wasm outputs fail visibly, not under guessed
extension exceptions.

## Native output graph versus source graph

Miniflare `4.20260730.0` consumes explicit arrays containing **only** each dry-run
entry's actual JavaScript and Wasm. This prevents resolving imports against
source adapters or the original generated trees. All output graphs must load;
Mail API packages additionally execute real Rust `/health` and unauthorized
address-list responses and reject scheduled events. A separate test-only
inspector imports the packaged API and asserts a sole default export, only its
own `fetch` method and direct platform `WorkerEntrypoint` inheritance.

The packaged sink is consumed through a test-only subclass of its **packaged**
default bridge, using an actual post-Rust console barrier. A valid typed record
must be retained exactly; a poison metadata record must be acknowledged without
retry or poison logging. Egress is closed. Control modules are in-memory fixture
modules, never files in the dry-run output or upload inputs. TAP completeness
checks reject failed/skipped/cancelled/todo or missing tests.

Current source native HTTP tests already execute `entry/api.mjs`, not just its
generated shim. The remaining difference is the Wrangler transform. In
particular, blindly remapping `mail-entry-split.test.mjs` to bundled entry paths
is unsafe: its source observer separately imports and mutates the original SDK
class, potentially a different class from the bundled one. A passing source-side
reset/lifecycle test would not prove the packaged graph. The diagnostic does not
pretend to repeat those assertions using that observer.

## Acceptance limits and reproducibility

The packaging job is an independent diagnostic, not a dependency of the stable Worker
gate or a deploy/release consumer. The selector/workflow/source change still
receives normal source CI. The package result cannot admit a failed full source
run, replace exact-current-main artifact requirements, extend the canary's
ancestry exception or claim provider-uploaded bytes/version/readback.

This probe can establish packaged Wasm identity, complete ordinary module graph
loading and narrow packaged API/Queue semantics. It does **not** establish full
business regression coverage on transformed JS, SDK trap/reset lifecycle
equivalence, scheduled-only maintenance packaging, fresh bootstrap generated
configs, provider runtime compatibility or actual upload multipart bytes. Keep
those distinctions when interpreting a successful run. No `--no-bundle` flag or
new module discovery policy is added to production: configuration defaults and
relative imports must be measured before considering that separate change.

Dispatch `native-fixture.yml` with `fixture=packaging` and the original full-main
CI `build_run_id`. Its packaging job and ordinary one-file replay job are
mutually exclusive. Existing ordinary replay commands and admission remain
unchanged; they do not install Wrangler. There is no additional workflow, input,
secret, environment or provider permission. A source without complete successful
full-main evidence must first get normal manual checks, not silently borrow a
cached or nearest ancestor artifact. The original run is selected explicitly;
unchanged compiler inputs are proved against that run's exact SHA.
The public artifact `worker-packaging-probe-<run>` contains source coordinates,
package receipts, esbuild metadata, package output bytes and native TAP evidence.
Use one run watch and record step/job versus whole-run times. No latency SLA or
packaging speedup is claimed without equivalent repeated measurements.

Initial hosted run `36886683271` on source
`b301847cded5231c9da17dd875a7db9d727180bb` succeeded with 11 ordinary dry-run
packages and all 16 packaged-runtime assertions. That historical standalone
workflow has been replaced by the explicit mode above. Its successful runtime
result is evidence for those bytes and narrow semantics, not proof that the
revised orchestration has executed or that any provider upload occurred.

## Primary references

* [Cloudflare bundling](https://developers.cloudflare.com/workers/wrangler/bundling/): default esbuild transform, preprocessed-code-only no-bundle alternative.
* [Cloudflare module configuration](https://developers.cloudflare.com/workers/wrangler/configuration/#find-additional-modules): rules, base directory and module-discovery behavior differ from Miniflare's `include` schema.
* [Wrangler deploy source](https://github.com/cloudflare/workers-sdk/blob/main/packages/wrangler/src/deploy/index.ts): dry-run packaging and metafile output are platform mechanisms, not a custom compiler/cache.
* [Reproducible Builds](https://reproducible-builds.org/docs/definition/): byte identity is about specified inputs/environment/output, not merely a successful build/test step.
* [An Empirical Study on Reproducible Packaging in Open-Source Ecosystems (ICSE 2025)](https://doi.org/10.1109/ICSE55347.2025.00136): packaging reproducibility is a separate practical supply-chain boundary across ecosystems.

Recent reproducible-packaging research motivates measuring the final output,
but neither hashes nor a narrow differential runtime check prove universal
semantic equivalence. No research novelty is claimed. Precise provenance and output execution are
preferable here to speculative semantic-equivalence predictors or a new cache
framework. The strongest next experiment depends on what the real package graph
shows: either validate an unchanged no-bundle closure, or explicitly test/package
and promote the final transformed module tree under the existing full gate.
