# Worker-created R2 probe Actions wiring review

Reviewed commit: `0f338a04752adf48560643511fd7fe49601bcf7a`.
Review date: 2026-10-01. Scope: the two new dormant manual jobs, dispatch
inputs, synthetic workflow checks, and their integration with the reviewed
`staging_worker_created_r2.py` source (`58acbd7` plus source fixes through
`e290a48` and test-loader fix `fbbce73`).

## Decision

**GO for nondeploying hosted source verification. No substantive defect found
in the reviewed wiring. Live dispatch is not authorized by this review.**

Before any mutation, the owner must inspect successful hosted checks at the
exact reviewed successor SHA, independently confirm the intended one-send
grant, and coordinate the staging state freeze. Neither synthetic checks nor
an absent-object recovery establish live existing-object GET/DELETE capability
or authorize B registration.

No local tests, live API operations, workflow dispatch, or push were performed.
This review changed only this review artifact.

## Contract trace

| Requirement | Evidence | Assessment |
| --- | --- | --- |
| Dormant/manual, reviewed branch only | `.github/workflows/ci.yml:270-275,316-320` | Both jobs require `workflow_dispatch`, their own exact target, `refs/heads/codex/amail-v0.1.0`, and the staging Environment. Push/PR cannot activate them. |
| Confirm before tests, provider secrets only afterward | `ci.yml:282-300,329-352` | Exact confirmation and current attempt 1 are checked before Python setup/tests. The probe also requires the explicit one-send attestation. Recovery validates positive run ID, prior attempt 1 and lowercase 40-hex SHA before tests. |
| Probe/recovery identity agrees with immutable provenance reader | `ci.yml:269,301`; `infra/tests/staging_worker_created_r2.py:40-41,166-219` | Job name `One-shot Worker-created R2 GET/DELETE` and step name `Probe Worker-created private R2 object` match `JOB_NAME` and `PROBE_STEP_NAME` exactly. Recovery passes the prior run, attempt and source SHA; the reader checks branch, workflow, completed failed/cancelled/timed-out originating run/job, exact run/SHA and a started non-skipped probe step, within a bounded 24-hour window. |
| Ubuntu supports the route action POSIX alarm | `ci.yml:274,320`; `staging_worker_created_r2.py:103-116` | Ubuntu-only jobs provide `SIGALRM`/`setitimer` for the reviewed 45-second route-action timer. No Windows fallback is relied upon. |
| Minimum operation dependencies for recovery | `ci.yml:322-324,353-365`; `staging_worker_created_r2.py:509-539` | Actions read and contents read are explicit. GitHub token enters only the final step. Recovery uses routing and private R2 access; it receives neither B credentials nor send attestation and does not run sender/D1/B preflight. Shared existing Cloudflare token grants may be broader, but this wiring does not require additional send/D1 grants for recovery. |
| Route token and send token are not conflated | `ci.yml:308-311,361-364`; `staging_worker_created_r2.py:109-110,256-285` | Exact-route mutation uses `CF_EMAIL_ROUTING_TOKEN`; sender read and the single synthetic send use `CLOUDFLARE_API_TOKEN`. The account/zone are consistent with the existing staging fixture. Actual grants still require independent confirmation; the input string is an attestation, not a permission probe. |
| No production or B mutation path | `staging_worker_created_r2.py:435-446,457-463,512-518`; `workers/identity-test-inbox/ensure_route.py:23-24`; `infra/tests/staging_second_principal.py:30-32` | Probe opens only the existing A apex test alias, targeting `amail-identity-test-inbox-staging` and its private staging bucket. This is a staging fixture on the apex zone, not a user mail-domain route or production Worker. No B secrets or registration are supplied. |
| Recovery closes route before object/provenance work | `staging_worker_created_r2.py:512-518` | After input shape checks, recovery closes/readbacks the exact owned A rule before reading prior GitHub metadata or any candidate object. This remains possible when normal sender/contact preflight no longer succeeds. Foreign/duplicate routes fail closed in the shared helper. |
| Mutations are not canceled by newer source CI | `ci.yml:133-135,276-279,325-327` | Manual state-changing runs keep the noncanceling workflow group and both new jobs share noncanceling `staging-native-mail-acceptance`. Source checks use the separate cancelable group. This is serialization, not a guarantee against external Cloudflare changes. |
| Finite job timeout leaves nominal cleanup reserve | `ci.yml:276,325`; `staging_worker_created_r2.py:448-495` | Twenty minutes accommodates the 420-second source window plus closure, bounded object reconciliation and settle under ordinary provider response timing. The timeout may still kill a trickling/outage response; this is explicitly acknowledged in `docs/staging-second-principal.md:90`, and separate route-first recovery remains mandatory after uncertainty. |

## Synthetic coverage and limits

`infra/tests/test_staging_worker_created_r2.py:541-580` checks both new job
blocks for dispatch/branch/runner/Environment/concurrency guards, first-attempt
input, mode, test-before-secret ordering, no B credentials, exact originating
job/step names, send attestation on probe and Actions read/provenance SHA on
recovery. Both manual jobs run this suite before provider Secrets enter their
last step. The ordinary infrastructure job also discovers the suite through
`ci.yml:1493`.

The workflow fixture is a textual contract check, not an Actions expression
interpreter. Static inspection of the executable YAML guards supplements it;
hosted execution is still required to establish Python 3.14 loader behavior,
PowerShell multiline condition parsing, and actual runner setup. No claim is
made here that those checks have already passed at `0f338a0`.

The preceding source review remains authoritative for MIME ownership,
pagination, irreversible DELETE denial, uncertain writes and cleanup order:
[`review-r2-worker-created-source-58acbd7.md`](review-r2-worker-created-source-58acbd7.md).
This review does not reopen its resolved defects or certify real send grants,
provider delivery, private Worker binding state, cleanup after process death,
or production readiness.

## Corrective integration review: `371ade7`

**GO for nondeploying hosted source CI of the corrective commit. Live remains
NO-GO until default-branch workflow registration, exact-SHA hosted success and
separate mutation approval are established.** No local tests, live operations,
dispatch or push were performed in this follow-up.

The previous review missed a material platform admission constraint: adding
four inputs raised `ci.yml` from 23 to 27 dispatch inputs, so run
`36748735128` had zero jobs. Its earlier GO did not establish workflow validity.
GitHub currently documents a maximum of 25 top-level inputs and requires the
workflow file on the default branch for manual dispatch:
[official workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs).
These obligations are now explicitly inspected rather than deferred to job
execution.

Changes inspected at `371ade7a8d78abb282b8ef8fd299d10802faf730`:

- `ci.yml` again declares exactly 23 top-level inputs; the dedicated
  `.github/workflows/staging-worker-r2-capability.yml:6-31` declares exactly
  six, with unique names. Static PowerShell text enumeration independently
  confirmed both counts; no project test was executed locally. The new
  synthetic count contract at
  `infra/tests/test_staging_worker_created_r2.py:583-597` checks 23/6, unique
  names and the 25-input ceiling. Its indentation-based matcher is appropriate
  to the actual workflow layout, not a general YAML validator.
- The dedicated workflow has only `workflow_dispatch` (`:4-5`); both exact
  target/branch/Environment/Ubuntu guards (`:43-49,88-97`), confirmations and
  current attempt 1 (`:55-66,103-118`), tests-before-provider-secrets
  (`:70-84,122-139`), 20-minute budgets and noncanceling native-acceptance job
  groups (`:49-52,97-100`) are preserved. Recovery retains Actions read and no
  B credentials/send attestation. No automatic or production mutation trigger
  was introduced.
- `staging_worker_created_r2.py:189-192` now accepts only the dedicated
  canonical or reviewed branch-qualified workflow path. Job/step names remain
  unchanged and exactly aligned (`workflow:42,74`). The canonical and qualified
  provenance fixtures move with the source; the existing wrong-workflow,
  wrong-job/SHA/run and skipped-step rejection fixtures remain in place. No
  live probe ran under the invalid integrated workflow, so rejecting its old
  path does not strand an existing Worker-created recovery object.
- `docs/staging-second-principal.md:88-92` now names the dedicated workflow,
  records the zero-job failure and clearly identifies default-branch
  registration as an unsatisfied operational prerequisite. Availability on a
  feature branch is not treated as dispatchability.

**Concurrency scope changed and must not be overstated.** Dedicated workflow
group `staging-worker-r2-${{ github.ref }}` (`:36-38`) differs from `ci.yml`'s
manual workflow group. The preserved repository-wide job group serializes
native acceptance/provisioning/probes across workflows, but does not lock the
separate staging deployment jobs. Thus the split no longer inherits the old
single-workflow serialization against a manual staging deploy. Before live
use, the owner must explicitly freeze staging inbox/deployment changes as
already required by the review; otherwise a deploy could change bindings or
privacy policy after probe preflight. This does not block nonmutating hosted
source checks, and it is not evidence that such a race has occurred. If future
unattended dispatch is intended, enforce a shared state-lane lock rather than
relying only on operator coordination.

All source-level cleanup limits and the NO-GO for B remain unchanged.
