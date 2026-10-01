---
name: amail-maintainer
description: Maintain amail CI, build artifacts, deployment, operational diagnostics and Cloudflare infrastructure. Use for repository or service operations, not ordinary user mail management.
---

# amail maintenance

Read `docs/infrastructure-foundation.md` first for current accepted evidence and
outstanding work. Filenames identify the relevant runbook; historical reviews
are evidence, not the active operational policy. This skill grants no additional
deployment, mail, secret or account authorization.

Use `docs/maintenance-operational-lanes.md` for the complete workflow/job
inventory, current source/deploy/recovery lanes and retired incident probes.
The completed September 30 marker-location, marker-discriminator and Security
Events reads have no current executable dispatch lane. Retained classifiers and
old run instructions are historical evidence, not permission to replay provider
reads from old source. Preserve recovery tools and supported acceptance gates;
do not retire the standalone Identity inbox or active native-tracing experiment.

## Pick the relevant lane

* **CI/build:** `.github/workflows/ci.yml`, `infra/ci/worker_artifact.py` and
  `infra/ci/native_suite.py`. The compiler is pinned in `rust-toolchain.toml`.
  Build once, verify same-run artifacts, then inspect all native matrix results
  plus the stable `Rust Worker (Wasm)` gate.
  The isolated native-tracing experiment may reuse a fully checked original-main
  build only after mandatory hosted current infrastructure checks and its narrow unchanged-
  compiler-input proof; its receipt keeps both identities. See
  `docs/native-cloudflare-tracing-canary.md`. This is not release admission.
  Its reviewed alternate Route transport uses only the fixed reserved infrastructure
  hostname and nonce-owned DNS/Route; read `docs/native-route-dns-lifecycle.md`
  before its distinct confirmation. Do not repeat historical workers.dev failures,
  borrow a product host or treat read permission as successful write admission.
  Native artifacts alone do not qualify a release. An exact cache hit, partial/miss and unreported state are different;
  use `ci_cache_lookup` and suite receipts rather than green-step inference.
  For a test-only native fixture repair, use `docs/native-fixture-replay.md`
  for the hosted diagnostic lane: unchanged compilation inputs and
  original artifact provenance are required. Diagnostic replay is not full CI,
  deployment or release evidence.
  For the final Wrangler packaging boundary, use the same diagnostic workflow
  with explicit `fixture=packaging` and an original fully successful main CI
  `build_run_id`. This is a separate credential-free dry-run job, not ordinary
  fixture replay or provider-upload acceptance. See
  `docs/worker-packaging-boundary-probe.md` for scope and evidence limits.
* **Runtime tracing/privacy:** `docs/runtime-observability-foundation.md` and
  `crates/trace-schema`. Separate implemented correlation from actual observed
  native tracing. Retain timestamps, status, source/version and request/trace IDs;
  exclude mail content, personal metadata, credentials and private destinations.
  See `docs/cli-telemetry-capability.md` for the authenticated attempts-v1 header,
  explicit rollback-safe upload route and five-minute realm-scoped observation.
  Deploy/read back the enriched Queue reader before an announcing API; the
  header proves parser support, not Queue delivery or native tracing.
  Do not hide all infrastructure metadata or dump arbitrary provider bodies.
* **Deploy/recovery:** `docs/control-plane-observability.md`, `docs/backend-operations.md` and the exact workflow/helper
  for the requested component. Keep project-managed Secrets as requested. Use
  source/run/version evidence and the shared writer lock; do not retry an
  ambiguous write, rebuild a supposedly identical artifact silently, or turn a
  failed read into resource absence. Preserve held sending unless its separate
  release operation is explicitly admitted.
  First held production bootstrap uses the protected CI
  `production-fresh-bootstrap` target, not ordinary activation. See
  `docs/fresh-mail-bootstrap-workstream.md` and
  `docs/fresh-bootstrap-recovery.md`. The durable recovery workflow takes the
  original protected run ID and observes immutable owned intent without replay;
  it cannot create, adopt, activate, delete stores or emit a success receipt.
  Initial admission refusal is diagnostic evidence only. Unknown submit versions
  and failed provider reads never become absence. Terminal cancelled creators are
  admitted only with unchanged original successful source gates and validated
  immutable evidence. Missing/truncated journals remain unavailable or rejected,
  never inferred ownership. Expired artifacts remain outside this bounded admission.

All runtime/cross-platform tests belong on GitHub Actions, not this developer
machine. Local static syntax/diff work is fine. Keep task artifacts under root
`.temp`/`.cache`; never put mail or credentials into build caches/artifacts.

For waiting, use one `gh run watch` per run or bounded metadata snapshots. If a
local watch handle disappears, inspect the existing GitHub run; do not dispatch
the provider operation again. Report meaningful evidence/failure/action, not
unchanged polling. Follow the owner's current priority in the foundation ledger
before resuming business-debug campaigns.

For actual user mail workflows, use the separate `amail` skill. Do not substitute
direct D1/R2 edits, an operator web inbox or an infrastructure token for normal
owner-scoped CLI behavior.
