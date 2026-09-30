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
