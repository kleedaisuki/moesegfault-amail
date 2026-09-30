# Review: current-Worker capture-off PATCH (49654d0)

Date: 2026-10-01. Updated after narrow re-review of correction
`84ded1429357667aa504beabe797125d26034718`.
Verdict: **GO for hosted source verification and separately reviewed workflow
wiring, followed by one guarded staging dispatch when both pass**.
The original P2 finding below is resolved in source. No remaining substantive
defect was found in the reviewed helper; this is not a live settings attestation
or approval of unreviewed workflow wiring.

## Scope and method

Reviewed commit `49654d022c13b7e2d6f55ffee1eac6fe4285618d`, its helper, synthetic
contracts and alternative-operation runbook. Traced reused
`apply_staging_capture_off.py`, `pin_staging_mail.py` and
`crates/mail-worker/check_observability.py`, and reused the documented failed
legacy-settings attempt rather than querying it again. Inspected the official
Cloudflare skill and current public API/SDK references. No local tests, builds,
private requests, deployment, production edits or workflow wiring were performed.

## Original necessary correction (resolved)

### P2: readback-null preferences can enter a nonnullable writable projection

Location: `infra/deploy/apply_staging_current_worker_capture_off.py:91-103`
(`projection`), through `capture_disabled`, `valid_sampling`, and
`safe_observability` in `crates/mail-worker/check_observability.py`.

The projection preserves optional provider preferences, but its checks describe
acceptable *readback*, not the writable schema. For example, starting with an
otherwise valid current Worker fixture, setting `observability.logs.persist`
to `None` passes `capture_disabled` (its Boolean type check skips null), survives
the reviewed policy overlay (which does not supply `persist`), and passes
`safe_observability` (`None is not False`). The emitted PATCH consequently
contains `"persist": null`. Explicit null `logs.destinations`, or null
`traces.persist`, `traces.destinations`, or `traces.head_sampling_rate`, similarly
survive and are forwarded.

The pinned official writable
[WorkerEditParams types](https://github.com/cloudflare/cloudflare-python/blob/c9dd8956de93575640e06ea28e802951175099a0/src/cloudflare/types/workers/beta/worker_edit_params.py)
declare these preferences as Boolean, string sequence or float, not nullable.
In contrast, `traces.propagation_policy` is explicitly Optional and should
continue to preserve null. The
[Edit Worker API](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/edit/)
also gives nonnullable optional value types for those preferences. Absence and
explicit null are not interchangeable when generating a mutation request.

Impact: a provider readback containing these null preferences can lead to a
schema-invalid write attempt instead of failing at projection readiness. The
subsequent attestation still fails closed, so this is not demonstrated privacy
bypass; it undermines the intended one-shot, schema-valid mutation contract and
can consume the guarded attempt unnecessarily. No live occurrence of these null
fields has been established. Confidence: high in the source path and writable
schema discrepancy, conditional on provider state containing a listed null.

Remedy: add a narrow writable-observability validator before returning the
projection. Reject explicit null for optional Boolean/list/numeric request
fields; preserve absence and the explicitly nullable propagation policy. Keep
the existing strict unknown-field/readback and all-off predicates. Add synthetic
tests for each rejected null preference proving the writer is not called, and
retain the nullable propagation-policy preservation test. Do not silently drop
preferences or change the shared readback predicate to implement write semantics.

### Resolution at 84ded14

The new `validate_write_policy()` runs after the known-field/all-off predicates
and before returning the writable projection. It checks present Boolean
preferences using exact Boolean type, present destination preferences as lists
of strings, and present sampling preferences as finite non-Boolean numeric
values in [0, 1]. Explicit null in all originally identified nonnullable fields
now fails before `apply()` can reach the write. Absent preferences remain absent;
the explicitly nullable trace propagation preference remains preserved. The
synthetic additions cover every originally listed null field, invalid numeric
and destination values, and the accepted nullable propagation preference.
They were inspected, not executed locally. Existing unknown-field and effective
capture predicates remain unchanged. The correction does not loosen the
positive GET, policy round-trip, serving pin, or unaffected-state obligations.

The same commit also adds an 18-line historical evidence section describing a
one-page provider-reported legacy PATCH success with completeness unverified.
That section explicitly refuses to substitute the observation for current
Issues=false, complete attribution, or this alternative's acceptance, and does
not authorize another legacy PATCH. This documentation-only observation does
not change the helper's safety conclusion. The referenced live run was not
independently re-queried in this narrow review.

## Boundaries that held under source review

- The operation uses PATCH on the validated current Worker ID, never PUT, the
  historical script-settings path, code upload or deployment creation. Official
  [Edit Worker](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/edit/)
  documents partial update semantics. All six required top-level writable fields
  are supplied; raw response IDs, references, timestamps, preview bindings and
  subdomain URL/suffix are not round-tripped.
- Explicit typed subdomain flags and bounded tags are preserved. Logpush=false
  and empty tail consumers are established before mutation. Unknown current
  subdomain or capture-policy fields block the operation.
- Deployment ID and single-100-percent approved version are checked before and
  immediately before the write, then again afterward; the exact existing
  pre-Queue binding set is checked before and after. A real external freeze and
  workflow-level service concurrency remain necessary: these reads are not a
  provider-side atomic lock.
- There is at most one PATCH and no retry, fallback or rollback. The strict
  response decoder rejects redirects, duplicate members, nonfinite constants,
  non-200/non-success objects and oversized responses. An ambiguous transport
  failure leaves `patch:attempted`, not an accepted or rejected assertion.
- A matching PATCH response is not acceptance. Independent current-resource
  GET must show explicit off for parent/Logs/traces/Issues, match the projected
  policy, preserve every unaffected response field, and pass serving brackets.
  The distinct `current-worker-v1` marker is not parsed as historical
  `settings-v1` evidence and cannot reopen public sending.
- Provider objects and arbitrary exception details remain in memory; stdout
  consists of fixed phase labels and the approved version. Public-send D1 hold
  and retained-record privacy acceptance are neither read nor changed.

## Remaining limits and integration conditions

Synthetic contracts were inspected, not executed; hosted verification remains
required. Workflow wiring is outside this commit and requires independent review
of first-attempt/ref/SHA guards, secret injection order, service concurrency with
`cancel-in-progress: false`, and the real external deployment freeze. Requiring
an exact observability round-trip is intentionally conservative: normalization
or omission fails rather than being treated as off. The alternative operation
does not resolve the outcome of the previous failed legacy PATCH, prove provider
permission/support, delete retained historical Issues, or replace the complete
retained-record privacy canary.
