# Worker packaging boundary probe

Status: credential-free source probe awaiting hosted observation. This does not
change ordinary deployment, native source acceptance, provider state or release
admission. No local build/runtime/install is part of the investigation.

## Question and smallest discriminating experiment

The ordinary artifact foundation now restores and rechecks native-tested
generated module trees instead of compiling again in deployment jobs. Pinned
Wrangler still performs a final JavaScript bundle. Does that packaging preserve
Wasm bytes and the composed Mail HTTP/private Queue semantics, and which exact
boundary remains untested? A source artifact hash cannot answer this question.

The independent PR diagnostic chooses **one successful full-main source run at
the exact PR base SHA**, validates the original required job/artifact inventory,
downloads its fixed artifact ID and runs the unchanged strict original-context
restore. Current checkout differences may contain only the diagnostic's four
owned files and public Markdown. Rust, adapters, configs, runtime/lockfiles,
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

The workflow is an independent diagnostic, not a dependency of the stable Worker
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

On a source PR containing only the owned probe files/docs, GitHub automatically
executes the diagnostic. The base must already have one complete successful
full-main source artifact; a docs-only base without such evidence must first get
normal manual checks, not silently borrow a cached or nearest ancestor artifact.
The public artifact `worker-packaging-probe-<run>` contains source coordinates,
package receipts, esbuild metadata, package output bytes and native TAP evidence.
Use one run watch and record step/job versus whole-run times. No latency SLA or
packaging speedup is claimed without equivalent repeated measurements.

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
