# Review: effective Mail API capture-off

Reviewed source: `1ce6092`, `a0639cd`, and `9bc227b`, 2026-09-30. Scope: shared API
readback predicate, staging serving pin, local Issues intent, synthetic tests,
and relevant rollout callers. No local test/build, private API call, deployment,
or push was performed. This is source review, not privacy acceptance.

## Resolved finding

**P2 — unsupported legacy null export representation rejects positive current
Worker evidence.** `crates/mail-worker/check_observability.py:127-132` treats a
present null legacy `tail_consumers` as an export conflict. Parent-confirmed
readback run `36736823997` returned that representation at `/script-settings`,
while current Worker resource returned a typed empty tail list. Once independent
Issues-off is established, this legacy null still prevents both `verify()` and
`pin_staging_mail.run()` from succeeding. The effective-readback architecture's
item 5 explicitly distinguishes unsupported missing/null from conflicting
non-null values. The synthetic legacy-conflict test currently codifies the
rejection rather than the intended endpoint-specific contract.

Required remedy was to permit missing/null *legacy* export values only alongside the already
required explicit current-resource false Logpush and typed empty tail list;
continue rejecting enabled Logpush, malformed non-null values, populated lists,
and explicit legacy capture conflicts. Add null-legacy acceptance coverage through
both checker and pin, plus malformed/nonempty rejection. Do not change the
positive current Worker requirements or enabled sink predicate. Follow-up
`9bc227b` implements this distinction in the shared predicate and updates
synthetic null acceptance/non-null conflict tests. Independent source re-review
finds the known path corrected; required current capture flags, Issues, Logpush
and the typed empty tail list remain explicit positive evidence. Optional null
inactive preferences are not used as enablement evidence. No unresolved finding
remains from this review.

## Positive assessment and boundaries

- Current Worker exact name and bounded typed identity are required; preview
  templates cannot satisfy the predicate. Parent, Logs, native traces and Issues
  all require literal false, independently. Absent Issues correctly stays
  UNVERIFIED. Dormant sampling/persistence/invocation preferences cannot authorize
  capture.
- Single-100% deployment/version identity is checked before and after settings;
  supplied expected version is enforced. This detects observed serving drift,
  not concurrent non-versioned A-to-B-to-A setting changes. The documented freeze
  and later retained-data canary remain necessary.
- The exact Worker REST path matches the official [Get Worker schema](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/get/).
  Explicit optional Issues support is in that schema; absence is not disabled.
  Local API realms now require explicit Issues false; sink validation remains
  unchanged by these commits.
- Transport is bounded and malformed/denied envelopes fail closed. Synthetic
  tests cover required literal capture fields, external exports, exact path,
  serving drift and both realms, but their hosted results were not reviewed here.
- `infra/deploy/require_trace_containment.py` still uses the old strict legacy
  `safe_settings` readback. These commits do not authorize Queue rollout; that
  caller needs a separately reviewed shared effective-policy migration while
  preserving immutable successful deployment provenance.

Verdict: **GO for hosted source checks and a separately guarded staging
containment deployment.** No demonstrated false-positive privacy acceptance or
remaining substantive defect was found in the reviewed changes. This is not a
live containment or Queue rollout attestation; effective Issues-off still needs
provider readback, hosted tests still need execution, and the rollout caller
above still needs its separate effective-policy migration.
