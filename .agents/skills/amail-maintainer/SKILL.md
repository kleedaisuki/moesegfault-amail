---
name: amail-maintainer
description: Maintain amail CI, build artifacts, deployment, operational diagnostics and Cloudflare infrastructure. Use for repository or service operations, not ordinary user mail management.
---

# amail maintenance

Read `docs/infrastructure-foundation.md` first for current accepted evidence and
outstanding work. Filenames identify the relevant runbook; historical reviews
are evidence, not the active operational policy. This skill grants no additional
deployment, mail, secret or account authorization.

## Pick the relevant lane

* **CI/build:** `.github/workflows/ci.yml`, `infra/ci/worker_artifact.py` and
  `infra/ci/native_suite.py`. The compiler is pinned in `rust-toolchain.toml`.
  Build once, verify same-run artifacts, then inspect all native matrix results
  plus the stable `Rust Worker (Wasm)` gate. Native artifacts alone do not qualify
  a release. An exact cache hit, partial/miss and unreported state are different;
  use `ci_cache_lookup` and suite receipts rather than green-step inference.
* **Runtime tracing/privacy:** `docs/runtime-observability-foundation.md` and
  `crates/trace-schema`. Separate implemented correlation from actual observed
  native tracing. Retain timestamps, status, source/version and request/trace IDs;
  exclude mail content, personal metadata, credentials and private destinations.
  Do not hide all infrastructure metadata or dump arbitrary provider bodies.
* **Deploy/recovery:** `docs/backend-operations.md` and the exact workflow/helper
  for the requested component. Keep project-managed Secrets as requested. Use
  source/run/version evidence and the shared writer lock; do not retry an
  ambiguous write, rebuild a supposedly identical artifact silently, or turn a
  failed read into resource absence. Preserve held sending unless its separate
  release operation is explicitly admitted.

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
