# Independent review: staging retained-log canary

Reviewed commits: `cd35519`, `33d3b59`, `1f88682`, `2262c63`, `66747a5`, `023cf34`, `57ab915`, and `a2e0c66` (2026-09-29). Scope: the synthetic canary harness, its offline tests, the current typed Rust trace schema, and the Cloudflare Observability API contract. This was a static review; I did not run the live canary, query retained account logs, modify production code, or inspect credentials.

## Findings

### Resolved — An arbitrary wrapper around a safe nested event could hide other retained fields

The `66747a5`/`023cf34`/`57ab915` follow-ups reject unknown typed or untyped log records and inspect both nonempty `source` and indexed `message` representations. Before `a2e0c66`, `embedded_events()` recursively found a version-1 event *anywhere* in a structured value, so a retained `source` such as `{"address":"secret@example.invalid","nested":<valid version-1 event>}` could pass the broad schema assertion. Commit `a2e0c66` now accepts only an exact event, an exact one-key `{"message": ...}` transport wrapper, or a singleton list, recursively bounded to depth five. Every other nonempty payload fails closed; the new wrapper fixture verifies the concrete counterexample. Cloudflare's [event schema](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/) permits structured `source` objects, so the exact-wrapper discipline matters.

**Disposition:** no further correction is required for this static failure path. A live query still must establish the actual Cloudflare wrapper shape; any different shape should produce `UNVERIFIED`, not be broadly allowed merely to turn the probe green.

### Resolved — The canary's copied trace vocabulary was stale

The original canary omitted `routing_list`, `routing_create`, `provider_http_status`, and `provider_error_code`, which the canonical Rust event schema emits. Commit `66747a5` adds those names, numeric range validation, and an offline routing diagnostic fixture. This removes the immediate false-negative path for concurrent address registration.

**Future maintenance:** derive the Python validator's fixed schema from a shared versioned schema artifact or add an explicit synchronization test/fixture for every Rust phase and optional field. Keep whole-window scanning for the synthetic markers.

## Confirmed boundaries and residual limits

* The `33d3b59` child environment allowlist no longer passes `CF_OBSERVABILITY_TOKEN` or `CLOUDFLARE_API_TOKEN` to `amail`; stdout/stderr of the native process and raw Cloudflare responses are not printed. The staging host, explicit confirmation argument, exact under-`.temp` paths, settings readback, and no-mail-mutation probe are appropriate safeguards. I found no concrete credential leak in the reviewed harness.
* The current Cloudflare [query API](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/) documents `parameters.view=events`, `dry=true`, a Unix-millisecond timeframe, `$metadata.id` cursor pagination, and `events.count` as the total matching count. Commit `2262c63` corrected the original top-level `view` placement. The [keys API](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/keys/) documents a result list with `key` and `type`. Thus the revised request shape and page-completeness check are plausible, not an invented API contract. A live result remains necessary because the schema does not guarantee how Rust `console_log!` text is represented/indexed.
* The CLI→API assertion is genuinely causal for the sampled successful call: `crates/amail/src/api.rs` sends `00-T-C-01`, journals `(T,C,R)`, and the authenticated mail API accepts `C` as the remote parent and emits `(T,S,parent=C,R)`. The harness additionally requires the rejected anonymous request's independent 4xx exit. It does **not** establish Cloudflare native waterfall tracing or external provider propagation, consistent with `docs/mail-trace-privacy-decision.md`.
* Cloudflare [Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/) documents head-based sampling and account/day caps; the deployed verifier requires a configured 1.0 rate, while the canary's own evidence still covers only returned retained records. The run should remain `UNVERIFIED` on missing rows, retention/indexing delay, truncation or an incomplete query, and should not be described as a full synthetic mail-content/panic-path privacy attestation.

## Disposition

No live run was attempted. The identified static false-pass/false-negative paths were repaired by `66747a5`, `023cf34`, `57ab915`, and `a2e0c66`. I found no remaining substantive defect in the reviewed canary after these corrections, but this does **not** attest actual retained Cloudflare data, indexing, access permissions, or mail-content/failure-path privacy. The present harness is a safely bounded probe of the two synthetic URL markers and CLI/API parentage once Cloudflare Observability access is available.
