# Privacy trace implementation review (2026-09-29)

Scope: the mail API observability config, verifier, Rust trace events, CLI journal/upload migration, related tests (implemented in `e4d939d`), and the CI effective-settings gate. No deployed settings, retained logs, private mail, or credentials were read. This note records the implementation state reviewed on 2026-09-29.

## Current assessment

No material static-review blocker remains in the reviewed privacy trace change. This is **not** a deployed privacy attestation: the effective settings and retained logs still require live verification.

## Resolved during review

* The initial effective-settings privacy gate was not invoked by either mail API deployment job. `.github/workflows/ci.yml` now runs its unit tests in the `dns` prerequisite job and calls `python check_observability.py --realm production|staging` immediately after the corresponding Worker deployment and before the health smoke test. Both deployment jobs use `crates/mail-worker` as their default working directory and expose the Cloudflare account/token environment variables needed by the verifier. A failed readback or unsafe setting will now fail the job. This is post-deploy detection, not pre-deploy prevention; the local-config unit test provides the earlier check.
* The initial verifier rejected any nonempty `destinations`; Cloudflare's official `GET /script-settings` example includes the built-in `"cloudflare"` destination for ordinary retained logs and traces. The implementation now accepts only the built-in sink and rejects external destinations, with a realistic mocked readback test. Source: <https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/get/>.
* The first telemetry validation narrowed the historical `/v1/telemetry` acceptance of trace IDs, status values, and byte buckets. It now preserves historical acceptance, emits a client trace event only for a strict valid trace ID/status, and re-buckets any accepted byte count before logging. Thus old upload batches are not newly rejected for those fields, and arbitrary legacy IDs are not retained in the new event.

## Verification and limits

* Passed: `cargo test -p amail-worker --lib trace::tests`, `cargo test -p amail --bin amail telemetry::tests`, Python verifier unit tests, and `cargo check -p amail-worker --target wasm32-unknown-unknown` (only an unrelated pre-existing unused-mut warning).
* Parser slicing is guarded by exact 55-byte ASCII input before byte-position slicing; malformed multibyte input is rejected without panic. New server spans are generated separately from unauthenticated caller headers; authenticated/inbound parents are parsed only after their trust checks. Event operation, phase, service, and outcome use a closed vocabulary; existing application warning strings do not interpolate mail content.
* These tests cover serialization, parsing, local schema migration, mocked settings, and compilation, **not** actual retained Cloudflare log content or deployment settings. The planned synthetic canary and restricted post-deployment review remain necessary to substantiate the privacy claim, particularly for uncaught platform exceptions and Workers Logs indexing of Rust `console_log!` JSON strings.
