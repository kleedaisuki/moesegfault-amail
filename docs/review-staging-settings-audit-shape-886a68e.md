# Review: historical Audit shape discriminator (886a68e)

Date: 2026-10-01 Asia/Singapore.
Verdict: **GO for hosted source checks, then one bounded read-only historical
shape diagnostic if those checks pass.** No substantive defect was found in
this scoped change. This verdict does not authorize any settings mutation,
retry of the original PATCH, broadened query, or privacy/rollout acceptance.

## Scope and evidence

Independently inspected commit `886a68e7a0a640b162744c3e3a956c36f57a48fd`,
the new helper and synthetic tests, shared reader and unchanged strict
classifier, workflow diff, previous review and forensic decision. Reused the
official API evidence already recorded in
`review-staging-settings-patch-audit-182535f.md`; no new external schema claim
is needed for this source-only diagnostic. The reported historical run
`36754040787` is supplied context, not independently repeated evidence.
No local tests/builds, live request, workflow dispatch, deployment, mutation,
push or production-source edit was performed. Synthetic tests were inspected,
not executed.

## Contract assessment

| Contract | Evidence and conclusion |
| --- | --- |
| Same immutable historical query | `staging_settings_patch_audit.py:18-24,48-74` retains the literal six-second interval, account Audit v2 endpoint, ascending direction, limit 100, 15-second timeout and 1 MiB body cap. New main calls that shared transport exactly once (`staging_settings_audit_shape.py:137-138`). There is no PATCH, body, retry, cursor follow-up or caller-controlled endpoint/window. Redirect handler remains rejecting. |
| Original classifier unchanged | The diff only extracts `read_audit_payload` and wraps it with the original object guard (`staging_settings_patch_audit.py:77-82`). Original classifier logic is untouched. Numeric count observation in the new helper does not satisfy or change the original string-count policy. |
| No raw private output | New helper lines 14-27 declare all output labels and allowlists. Lines 31-63 reduce values and keys to closed type/presence/unknown/mixed bins. Lines 112-117 inspect selected action/raw fields for type only; actor, record ID, URI, method, timestamp and numeric status values are not emitted. Final output at lines 143-145 prints only those fixed labels and generated bins. Unknown provider field names never become output. |
| Bounded and incomplete evidence | Lines 97-117 inspect row structure only for lists of at most 100 rows. Oversized row lists leave row bins skipped. Lines 118-123 reject missing/null/nonempty cursors, unknown envelope/result-info/row/action/raw keys, unusable/mismatched counts and malformed containers for the aggregate. No continuation occurs even on rejected frames. |
| Parser failure normalization | Shared transport retains HTTPException/URL/OS/timeout normalization and JSON ValueError/Unicode/recursion normalization with suppressed exception context. New main only emits fixed error categories (lines 139-145). Existing and new tests explicitly exercise BadStatusLine and IncompleteRead without private stdout/stderr. |
| CI context and credentials ordering | `ci.yml:545-584` restricts the target to manual dispatch on the development branch, staging environment and first attempt with exact confirmation. Both original and new focused synthetic suites precede the only credential-bearing read step. Non-cancelable staging serialization remains. The diff extends the target choice without adding/changing the existing 23 dispatch inputs. |
| Outcome meaning remains narrow | `SHAPE_DIAGNOSED` indicates a bounded inspected shape frame, not PATCH matching, page/audit coverage, request attribution, effective settings, historical success or privacy acceptance. The helper docstring and forensic decision explicitly maintain this distinction. |

## Useful limits

The standard `messages` field is observed through a predefined type bin but
remains unknown to the original strict envelope key set. This can intentionally
leave the shape aggregate UNVERIFIED while still identifying the schema
discrepancy. Likewise a bounded numeric count can produce SHAPE_DIAGNOSED with
`strict_count=mismatch`; it cannot turn the original audit into CLASSIFIED.
These are disclosed diagnostic semantics, not weakened outcome acceptance.

The byte bound limits the complete parsed response; the row bound limits
subsequent shape inspection, not JSON parser row allocation. Existing transport
behavior is unchanged, and the bounded parsed body is not persisted.

Next gate: hosted tests, then at most one diagnostic using this exact fixed
query. Whatever its result, preserve the independent effective-state gate and
the settings mutation freeze until separately justified evidence exists.
