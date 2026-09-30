# Review: read-only capture preflight diagnostic (03fcd90)

Date: 2026-10-01 (Asia/Singapore).
Verdict: **GO for same-revision hosted source CI, then one manual read-only diagnostic.**
No substantive defect found in the reviewed change. This is not permission to
retry the settings mutation, containment acceptance, or Queue/public-send approval.

## Scope and evidence

Reviewed commit `03fcd905106ff49a983561cc8124b9b06513051f`: diagnostic,
synthetic contracts, dedicated workflow job, and decision update. Traced the
reused `apply_staging_capture_off.py` bounded reader/source policy/normalizer,
`pin_staging_mail.py` deployment/binding predicates, and Mail Worker's effective
capture checker. Read the existing correction decision and its independent
review first. Unrelated concurrent role-rollout and R2 edits are excluded.

No local tests/builds, provider calls, live diagnostic, mutation, deployment, or
push were performed. Test assertions below were inspected, not executed.

## Verified contracts

| Boundary | Source evidence |
| --- | --- |
| Read-only, bounded fixed endpoints | Diagnostic lines 15-20 import readers and predicates, not `apply` or `patch_policy`. Lines 111, 121, 132-135, 159 perform at most six GETs. The reused request builder has no data/method override, refuses redirects, uses a 15-second timeout and 262,144-byte bound, and performs no retries. Imports have no provider side effects. |
| Exact serving pin and bracket | Lines 102-117 require literal c3f and a valid single100 deployment. Lines 159-166 compare the full deployment/version pair and discard collected bins on observed drift. A failed final read returns incomplete, not diagnosed. This brackets code selection, not atomic non-versioned settings. |
| Exact manual source context | Lines 182-187 require exact confirmation, expected c3f, attempt 1, workflow_dispatch, reviewed branch, typed SHA/account, and a token. Workflow lines 464-489 independently constrain target/branch/confirmation/pin/attempt before credentials. |
| Phase-preserving provider failures | Lines 33-48 classify exception types/status ranges, never their text. Lines 120-142 preserve per-endpoint failure categories, continue independent settings reads without retry, and lines 171-173 cannot report a complete preflight after a read failure. HTTP denial, not-found, 5xx, transport, timeout, and malformed/provider-envelope cases remain bounded categories. |
| Shared contracts, not new acceptance | Lines 123-127 use the exact shared binding validator before emitting fixed mismatch causes. Lines 145-149 use the same Issues-only relaxation and effective/legacy predicates as the existing correction helper. Lines 168-173 report relaxed pre-correction predicates only. Missing Issues does not become full capture-off evidence. |
| No provider data or rollout marker | Lines 24-30 define closed output fields; all produced values are literals. Binding causes never expose names, values, IDs, or counts. Lines 194-197 emit neither settings-v1 nor Current Version ID markers. A diagnosed blocked preflight can exit zero because successful diagnosis is intentionally distinct from successful containment. |
| Credential isolation and gate preservation | Workflow lines 492-496 run focused synthetic contracts without credential environment; only lines 499-506 receive project secrets. The dedicated job retains non-cancelable shared staging deployment concurrency and has no deploy, PATCH, Queue provisioning, SMTP, login, or existing containment-gate modification. Full infrastructure CI discovery includes the new test file. |

The synthetic suite inspects exact endpoint order and one Worker resource read,
forbids PATCH, distinguishes binding/policy/normalization/projection failures,
asserts incomplete transport handling and closing deployment read, discards bins
on drift, and checks fixed output plus invalid dispatch inputs. It explicitly
demonstrates that the reported dormant defaults and absent Issues can pass the
relaxed preflight while failing the real full capture policy.

## Execution and interpretation limits

1. Require hosted source checks at the immutable reviewed revision before the
   one first-attempt dispatch. Focused job tests are additional protection.
2. Keep the external staging deployment/settings freeze; GitHub concurrency
   does not serialize dashboard or other-provider changes.
3. Treat `diagnosed` as complete bounded readback, and `preflight=pass` only as
   the current Issues-relaxed helper preconditions. Neither establishes the
   phase reached or PATCH outcome in historical failed run `36742914068`.
4. Preserve the failed correction provenance and closed rollout state. Use
   resulting fixed categories to select a reviewed next step; do not blindly
   retry mutation or treat omitted Issues as disabled.

No production correction is required by this review. Actual hosted test and
provider endpoint/permission behavior remain unverified until the approved run.
