# v0.2.0 staging delivery contract

## Scope and admission

The active candidate branch is `codex/v0.2.0-billing`. Hosted `checks` validates
source and produces unpublished native candidates. `staging-inspect` uses
`INSPECT_STAGING_V020`; `staging` requires `RUN_STAGING_V020`. No tag, Release,
production promotion or production send-policy mutation is authorized by this work.
The unchanged workflow-wide staging graph writer lock serializes provider writers.
Historical V012 interruption recovery remains bound to its original immutable
runs and branch; it is not a general V020 recovery receipt.

Worker builds remain credential-free and occur once in hosted `worker-build`.
Every staging mutator restores the same-run exact artifact, verifies source/run
identity and file hashes, and refuses changed bytes. API is fetch-only with empty
Cron; private maintenance alone owns scheduled work. Trace sink is Queue-only,
and realm-isolated lifecycle/ingress graphs remain independently read back.
Production admission and confirmations are unchanged. Initial V020 predecessor
admission may omit the four Billing bindings only for the exact source-owned
V012 API `01f14a8e-d5b1-41f9-9f8c-325c2e288ba7` and maintenance
`3d23d537-6379-4fcb-84c2-2c1b8a9f4857` cohort. Every other graph and all
post-deploy readbacks require the full desired binding set; there is no generic
optional-binding or arbitrary historical fallback.

## Billing realm

Staging API configuration fixes:

- `BILLING_BASE_URL=https://billing-staging.moesegfault.dev`
- `BILLING_SUBSCRIBE_ORIGIN=https://subscribe-staging.moesegfault.dev`
- `BILLING_RETURN_URL=https://amail-staging.moesegfault.dev/billing/return`

Scheduled maintenance uses the same fixed staging Billing URLs to flush the durable
usage outbox; it gains no HTTP or user-mail-send capability.

The staging GitHub environment must contain `BILLING_SERVICE_KEY`, equal to
Billing staging's `AMAIL_SERVICE_KEY`. Provision through secret-tool stdin from
an ignored local secret source; never print it or put it in artifacts. Both API and scheduled-maintenance
submissions include this key through a mode-0600 repository `.temp` secrets file,
removed on success and failure. Production delivery does not inherit this key.

The return route is static and script-free: it does not consume query parameters,
change account state or claim payment success. The next action is a fresh
`amail billing status` authoritative read. `site/scripts/check-billing-return.mjs`
checks the built route during hosted site validation. Real human authorization
and Billing-state convergence still require integrated staging acceptance.

## Version and migration

All workspace package versions and local-package Cargo.lock coordinates are
0.2.0. Site candidate/current coordinates match. Vendored MoeSegfault Style
remains independently pinned at v0.1.2. Historical changelog entries remain.
Old CLI requests are rejected by the v2 API contract; hosted direct HTTP owner
probes send `x-amail-api-version: 2` rather than accidentally testing only 426.
Existing account addresses must survive additive migration and be classified
Free; source migration tests and live readback, not this document, prove this.

## Local evidence and remaining delivery

On 2026-10-07 the infrastructure suite passed all 161 tests, including 20 staging
rollout, 16 adapter, 7 realm-secret, 6 canary and 4 candidate-selection contracts.
Node release-state contracts passed 27 tests. Source-only staging adapter and
realm-isolation checks passed. No local heavy Rust/Wasm/site build or provider
write was performed. Root coordinates secret provisioning, immutable source
commit, one hosted workflow dispatch, live observation and actual user/Billing
end-to-end verification; this note is not evidence that deployment has occurred.
