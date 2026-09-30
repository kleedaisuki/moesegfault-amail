# Worker-created private R2 probe — independent source review

Reviewed 2026-10-01. Scope: commit `58acbd7`, both new Python files, their
existing route/R2 transport/inventory helpers, `staging-second-principal.md`,
and `review-r2-worker-created-capability-9d5f5f6.md`. No production edits,
local tests, live provider calls, workflow dispatch, or push were performed.
Public official documentation was consulted. This is source inspection and
failure-path reasoning, not hosted execution evidence.

## Decision

**NO-GO for live execution or B provisioning. Fix the findings below before
accepting the source and wiring the guarded workflow.** The narrow alternative
is still worthwhile: Worker-binding creation followed by same-token REST
GET/DELETE distinguishes required read/delete operations from the failed REST
PUT. The implementation does not call REST PUT or use B credentials.

## Findings

### 1. P1 — recovery rejects the existing canonical workflow path

Location: `infra/tests/staging_worker_created_r2.py:156-157`;
test fixture: `infra/tests/test_staging_worker_created_r2.py:315`.

`prior_window()` requires the path to start with `.github/workflows/ci.yml@`.
The existing repository's successful-run provenance contracts and fixtures
(`infra/deploy/require_role_trace_phase1.py:completed_run`,
`infra/tests/test_require_trace_containment.py`) use the canonical REST path
`.github/workflows/ci.yml`. Such a valid prior run is rejected after route
closure, before object recovery, leaving a Worker-created synthetic object
unreconciled. The new unit fixture encodes the suffix assumption and therefore
does not exercise the repository's established response shape.

Accept the exact canonical workflow path; if a branch-qualified representation
is deliberately supported, constrain it to the exact reviewed branch rather
than an arbitrary prefix. Preserve separate SHA/branch/attempt validation.
Add a canonical-path positive test and wrong-workflow negative cases.
Confidence: high for the executable canonical-path rejection; no fresh live
metadata was fetched to re-attest the currently returned representation.

### 2. P1 — outer cleanup repeats a definitely denied DELETE

Location: `infra/tests/staging_worker_created_r2.py:290-305,369,385-388`.

`delete_owned()` correctly stops its own retry on `r2_delete_denied`. However,
the first DELETE's 403 becomes `object_delete_denied`, is caught by `probe()`,
then `finally` invokes `reconcile()`. The same still-present object is selected
and `delete_owned()` issues another DELETE. Therefore the whole procedure
violates the explicit no-repeat-after-definite-denial contract even though
`test_definite_delete_denial_never_retries` passes at the inner-function level.
The cleanup may also erase the informative denial label in favor of an
aggregate cleanup failure.

Carry a no-further-delete state through the outer cleanup: route closure and
read-only reconciliation still run, but cannot issue a second DELETE after
definite denial. Add a whole-`probe()` call-order test proving exactly one DELETE
under 403, plus an ambiguous-response case retaining conditional readback.
Confidence: high; direct deterministic call-chain evidence.

### 3. P2 — skipped probe jobs are accepted as originating recovery evidence

Location: `infra/tests/staging_worker_created_r2.py:160-167`.

The job predicate accepts any matching name with `status=completed`; it does
not reject `conclusion=skipped`, establish an actually started probe step, or
require one unique matching job with the expected run/SHA. Once this job is
added to the shared `ci.yml`, an unrelated failed manual target can contain a
skipped probe job satisfying this predicate. It then becomes accepted prior
probe provenance. Strict MIME still limits deletion, so this is not a claim of
arbitrary-object deletion, but it violates the explicitly required originating
target/run validation and can falsely report recovery for a nonexistent probe.

Require exactly one matching job, immutable run/attempt/SHA identity, an
appropriate non-skipped terminal conclusion, plausible started/completed
timestamps, and the exact source-owned probe step actually started. The workflow
must use that exact step name. Tests must reject skipped jobs/steps, duplicate
names, unrelated targets, wrong run/SHA, and stale windows.
Confidence: high for predicate acceptance; impact applies when CI wiring adds
the job to the shared workflow.

### 4. P2 — the 240-second route-open budget does not constrain nested scans

Location: `infra/tests/staging_worker_created_r2.py:253-260,352-365`;
helpers: `staging_second_principal.py:136-165` and
`workers/identity-test-inbox/ensure_route.py:list_rules`.

The open-clock starts only after creation and its internal readback. The only
budget check before send and the polling loop condition surround `one_key()`;
neither constrains its full keyset scan. The reused helper allows up to 20
25-second requests, and route scans allow up to 200 20-second requests. Slow
responses or unsolicited keys can therefore overrun the advertised window;
an eventual workflow timeout can terminate the runner before `finally` closes
the publicly reachable verification route. These are finite request counts,
but not the specified short enforceable route-open deadline with cleanup reserve.

Start the clock before the possible create, enforce the deadline across nested
open-route requests, and reject inventory immediately when a second key is
observed rather than walking up to 1,000 objects. Preserve separately bounded
route cleanup after the mutation budget expires; do not make cleanup itself
depend on a now-expired mutation deadline. Add simulated-time tests for slow
create/readback, expired inventory, and cleanup ordering.
Confidence: high for missing deadline propagation; no claim that this occurred
in a live run.

## Preserved strengths and remaining acceptance boundaries

- Cleanup is installed before ambiguous creation, and exact route closure
  precedes object GET/DELETE. Closure failure suppresses object mutation.
- One send call uses no-redirect/no-retry transport. No identity verification
  code is generated or parsed; the candidate must match the versioned synthetic
  subject/body, exact A recipient, sender, bounded MIME and original time window.
- The marker is reproducible correlation, not an authentication capability.
  Visible headers and matching content do not prove authenticated SMTP or
  Identity integrity. GET/DELETE capability remains the narrow claim.
- Recovery closes the route before remote run metadata and does not rely on
  B credentials, D1 state, sender permission, or ordinary preflight.
- Exact-key absence needs GET and complete inventory; unknown or multiple
  objects fail closed. Fixed failure labels suppress provider/private material.
- No workflow integration is reviewed here: branch/environment/attempt guards,
  reviewed source pin, hosted-test evidence, shared non-canceling mutation
  concurrency, timeout reserve, capacity, and final-step-only secrets still need
  independent review. No hosted tests or live capability have passed by virtue
  of this artifact; B remains NO-GO until separate acceptance.

## Primary references

- [GitHub workflow runs REST](https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run-attempt):
  attempt-specific run metadata is distinct from job execution evidence.
- [GitHub workflow jobs REST](https://docs.github.com/en/rest/actions/workflow-jobs):
  job/step status and conclusion must be distinguished when establishing that
  the originating operation actually ran.
- [Cloudflare Email Sending REST](https://developers.cloudflare.com/email-service/api/send-emails/rest-api/):
  the send request and delivered/queued reply are provider state, not proof of
  private object persistence or permission to read/delete it.

Implementation agent was notified with the exact failure paths and remedies.

## Scoped follow-up: `1e809cc`

Source inspected without running tests. Findings 1 and 3 are resolved at source
level: canonical and exact branch-qualified workflow paths are accepted;
unique matching job/run/SHA and non-skipped terminal job plus started probe-step
evidence are now required. New fixtures cover canonical/qualified paths, wrong
workflow, skipped job/step, wrong run/SHA and duplicates. CI wiring still must
agree with `PROBE_STEP_NAME` and be independently reviewed.

Finding 2 is only **partly resolved**: a first DELETE 403 is carried through
outer cleanup as read-only, and the new whole-probe test captures that path.
However, an ambiguous first DELETE followed by GET-present and a conditional
retry returning 403 is still caught as `object_delete_unverified` by the inner
retry handler. The outer `finally` then permits deletion again. Preserve the
definite-denial label/state on the conditional retry as well, and add a
whole-probe ambiguous-then-403 call-order test.

Finding 4 remains pending. **Overall NO-GO is unchanged.**

## Final source follow-up: `e290a48`

**GO for nondeploying hosted CI of the source and synthetic tests. NO-GO for
live dispatch until workflow wiring is reviewed and hosted checks pass.**
No local tests, provider calls, workflow dispatch, or push were performed by
this reviewer. Earlier findings remain in this document as historical review
evidence, not an assertion that the resolved paths are still present.

- Findings 1 and 3 remain source-resolved as described above.
- Finding 2 is now source-resolved for both first-DELETE-403 and
  ambiguous-first-DELETE/conditional-retry-403. `CleanupState.may_delete` is
  shared with the outer `finally` and becomes irreversibly false for either
  denial. `reconcile()` then only performs read-only reconciliation. The new
  whole-probe test expects exactly two DELETE calls in the latter sequence,
  never a third after definite denial.
- Finding 4's unbounded-count exposure is removed: short-window inventory
  allows at most two requests, rejects a second key immediately, and requires
  an explicit empty lexicographic page for a singleton. Each route action gets
  a 45-second POSIX alarm and diminishing request timeout; its timer covers
  create/readback scans. The open clock starts before creation, the mutation
  window is now 420 seconds, and polling reserves 90 seconds for independent
  route closure. Tests exercise expired pre-send budget and an expired nested
  route request without making provider calls. These source changes are
  sufficient to enter nondeploying hosted verification.

### Required live-wiring checks, not established by this source review

1. The exact `PROBE_STEP_NAME` must be used; immutable reviewed source and hosted
   test evidence must precede the secret-bearing mutation step. Branch,
   environment, first-attempt confirmation, concurrency and capacity guards
   remain separate obligations.
2. Pin the probe/recovery job to POSIX/Linux if relying on `setitimer`; the
   fallback on platforms without it only bounds socket/request behavior.
3. Size the workflow timeout to include preflight, the 420-second mutation
   budget, independent closure, post-close MIME/object reconciliation and
   settle, with reserve. Do not cancel mutation runs to make newer CI faster.
4. Do not overstate the timer guarantee: the hard alarm currently covers route
   actions, not inventory/send reads. `urllib` socket timeouts are not a strict
   total-response wall-clock limit if a response continuously trickles bytes.
   A literal hard 420-second guarantee across all route-open I/O would require
   an encompassing deadline/timer, preserving independent cleanup when it
   expires. The finite request counts and nominal timeouts should be described
   accurately until that stronger contract is added.

Hosted CI success would establish synthetic behavior, not current grants,
live Worker-created object read/delete capability, successful cleanup, or B
provisioning readiness. The narrowly gated live harness and its originating-run
recovery require a separate integration review before execution.
