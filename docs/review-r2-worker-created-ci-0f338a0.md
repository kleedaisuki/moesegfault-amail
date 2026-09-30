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
