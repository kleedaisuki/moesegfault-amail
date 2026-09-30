# Review: distinct settings-only containment attestation

Reviewed 2026-10-01. Commit: `781553370f398116e3ae510ac9a80d8f3616781f`.
Decision: **GO for hosted source checks of this gate slice**. No substantive
defect was identified. This is not authorization to dispatch the unfinished
settings helper/workflow, provision Queues, or release production.

## Scope and method

Inspected the exact commit diff, `infra/deploy/require_trace_containment.py`,
focused synthetic tests, deployment documentation, the settings-correction
ADR, and shared serving/binding/effective-observability predicates. Reused the
existing reviewed effective-readback boundary and official API research in
`staging-containment-settings-correction.md` and
`review-trace-containment-effective-gate-cf6de11.md`. No local tests/builds,
live provider calls, deployment, push, or production edits were performed.
Hosted execution and independent helper/workflow review remain outstanding.

## Contract assessment

| Boundary | Evidence | Assessment |
| --- | --- | --- |
| Explicit evidence kind | Gate lines 58-59, CLI default `deploy-v1` | No inferred fallback; settings-v1 accepts only the reviewed literal unchanged c3f version. |
| Immutable run identity | Lines 60-71 | Exact run ID, first attempt, completed success, project branch, workflow path, canonical SHA, dispatch trigger and exact repository are required. |
| Dedicated job correlation | Lines 72-87 | Complete bounded job page, exactly one successful dedicated settings job, positive integer job ID, completed status, same run ID, attempt and SHA; logs are requested for that job. |
| Unique attestation | Lines 39-48, 92-93 | Exact settings-v1/version marker anchored to line end with whitespace/log-prefix allowance; duplicate/mixed markers, suffixes and any `Current Version ID:` output deny. |
| Historical source intent | Lines 94-102 | TOML fetched at immutable run SHA, literal staging name and strict all-off source predicate including Issues. This proves observability intent, not deployment of current Rust or future Queue bindings. |
| Immutable serving bindings | Lines 118-120; `pin_staging_mail.bindings_match` | Exact version resource is checked against the pre-Queue binding set; extra/duplicate Queue bindings deny. Resource values are derived from reviewed checkout configuration. |
| Current control state | Lines 115-128; shared `effective_api_settings` | Same single-100 deployment/version bracket; explicit parent/Logs/traces/Issues-off, no Logpush/tails/external exports, exact-name typed Worker resource and noncontradictory legacy reads remain mandatory. |
| Compatibility | Existing deploy-v1 run/job/version/source and live-state checks | Existing default behavior is retained; new settings-only strengthening does not change deploy-v1 job correlation or substitute diagnostic success. |

The newly added synthetic tests cover successful settings evidence; run and
job provenance mismatches; incomplete/duplicate/wrong jobs; marker ambiguity;
unsafe immutable source; future source Queue intent without deployed-code
claims; explicit kind/version selection; exact live binding invocation and
extra Queue denial; and CLI default/explicit threading with fixed private
failure output. Existing shared tests cover capture/export/identity failures
and serving drift. These are source-level contract coverage, not live proof.

## Preconditions and limits

The source-operation obligation is intentionally separate from this parser:
the selected successful job's helper/workflow at that exact SHA must itself be
reviewed to perform only the fixed settings operation and emit the marker only
after full postchecks. TOML plus a log marker alone does not establish those
helper semantics. The helper and workflow are outside this commit's approval.

The serving bracket does not atomically lock non-versioned settings. Serialized
deployment and an out-of-band settings/deployment freeze remain operational
assumptions. Full retained-record privacy acceptance, Queue event causality,
other Workers, and production release remain separate gates. No historical
failed run becomes successful evidence through this new kind.
