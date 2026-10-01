# Standalone staging Identity inbox artifact admission

Status: source implementation awaiting hosted source acceptance. No provider
write, deployment, route/account operation or secret change was performed.

Preserve the supported `Deploy staging Identity test inbox` workflow identity,
main-only invocation, staging environment, shared non-cancelling staging lock,
exact-route absence checks and private binding/R2 allowlist readbacks. It is not
silently deleted or recategorized as unsupported research; the ordinary `ci.yml`
staging deployment path remains compatible too.

The standalone workflow no longer installs floating stable or worker-build,
recompiles Rust, or bundles a new supposedly equivalent Wasm bridge. It consumes
the immutable producer artifact of a fully successful CI run for **exactly its
current main SHA**. The optional `source_run_id` selects an explicit successful
first-attempt main run. If omitted, a bounded lookup considers only successful
exact-current-main runs and selects a fully checked one; it never falls back to
an ancestor or rebuild. If docs-only main has no complete CI, explicitly run the
existing non-deploying `checks` target for that exact main source first.

Admission requires exact repository/workflow/event/branch/source identity, all
three CLI checks, site, infrastructure, build producer, stable Worker aggregate
and every currently assigned native suite. Complete bounded job/artifact
inventories and a unique nonexpired source-named artifact provide a fixed artifact
ID. Download uses that ID and original run explicitly. The existing manifest
restorer then checks original source/run/attempt, compiler/bundler and every file
of all seven module trees before route reads or deployment. Source identity is
unchanged; the original build run and distinct deployment orchestration run are
both retained in the admission record.

This is a deliberately strict exact-source consumer, not an extension of the
isolated canary's enumerated ancestor-diff exception. No global `ci.yml` dispatch
schema, generated artifact manifest or canary admission policy changed. Existing
project-managed provider Secrets remain as before; the normal GitHub token gains
only `actions: read` to select/download its own build artifact.

Final pinned Wrangler packaging and actual provider route/privacy readback remain
separate acceptance. Hosted source success cannot prove a deployed inbox or
release public Mail sending. Local checks are static syntax/diff only; new hosted
synthetic tests cover wrong/ancestor/PR/foreign/rerun identity, missing native/full
gates, expired/duplicate/truncated artifacts, original-run restore and preserved
workflow/route guards.

References:

* https://github.com/actions/download-artifact — fixed artifact IDs and explicit cross-run download.
* https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/storing-and-sharing-data-from-a-workflow — immutable artifacts and producer/consumer provenance.
* `deployment-artifact-foundation.md` — accepted nine same-run `ci.yml` consumers and remaining packaging/lifecycle boundaries.
