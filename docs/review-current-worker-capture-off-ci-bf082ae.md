# Review: isolated current-Worker correction workflow (bf082ae)

Date: 2026-10-01. Verdict: **GO for hosted source checks only**.
No substantive defect was found in the reviewed workflow wiring. This is not
a provider-state attestation, authorization to dispatch before hosted checks,
or a public-send/privacy/release approval.

## Scope and method

Reviewed commit `bf082aeaba9b400382fec3658bfe724b40599bec`: the new job and
dispatch input in `.github/workflows/ci.yml`, its four workflow contract tests,
and the manual-integration runbook addition. Traced the helper's environment
guard and reused the independent helper review of `49654d0` corrected at
`84ded14` in `review-current-worker-capture-off-49654d0.md`. Inspected the
existing source-test lane, staging Mail deployment lock and legacy settings
job. Read current official GitHub workflow documentation. No local tests,
builds, live provider requests, workflow dispatches or production changes were
performed. The only repository write is this review artifact.

## Safety contracts inspected

| Contract | Source evidence and assessment |
| --- | --- |
| Dispatch input limit | Counted the top-level input declarations in the committed workflow: exactly 24, with only `mail_deploy_freeze` added. Below the documented maximum of 25. The new test independently checks exactly 24. |
| No automatic/production mutation | The new job requires `workflow_dispatch`, its exact target, and `refs/heads/codex/amail-v0.1.0`. Push/PR, main, tags, `checks`, and `production` fail this conjunction. Existing production job predicates remain unchanged. |
| Environment and service serialization | Job uses staging Environment and `deploy-mail-staging` with `cancel-in-progress: false`, matching the existing staging Mail deploy and legacy correction jobs. Workflow-level manual concurrency is also non-canceling; source-check concurrency uses a separate group. |
| Input guards before provider credentials | The first Bash run requires exact confirmation, fixed approved serving version, dedicated Mail freeze acknowledgement, and attempt `1`. Values enter via environment variables, not shell interpolation of expressions. No Cloudflare secrets are in job-level env or preceding steps. |
| Hosted source tests before provider access | The manual job executes helper, extracted workflow-guard and observability contracts before its sole credential-bearing step. Default Bash failure handling stops on an unsuccessful test command. Push/checks source CI additionally discovers both new test files through `infra/tests`. |
| Correct helper wiring | Final step supplies `AMAIL_EXPECTED_WORKER_VERSION`, `AMAIL_CURRENT_WORKER_CONFIRM`, and `AMAIL_CURRENT_WORKER_FREEZE` from their intended inputs and the two existing project Cloudflare secrets. The helper independently repeats manual event, branch, attempt, confirmation, freeze, version and revision-shape checks before its requests. |
| Minimal GitHub access | Job inherits only `contents: read`; there is no job permission override, Actions write, deployments write, OIDC grant or artifact upload. Checkout disables credential persistence. |
| Legacy acceptance unchanged | The diff does not alter `staging-containment-settings`, its helper, the `trace_containment_kind` options, or settings-v1 parsing. The new helper emits distinct current-worker-v1 evidence, which downstream settings-v1 gates still cannot accept. |

The workflow contracts inspect these guards and execute only the extracted
non-mutating Bash gate in hosted Linux. They reject blank/wrong/retry input
variants and verify test/secret ordering. They do not themselves prove
Cloudflare effective settings, actual Environment protection settings or a
real external deploy freeze.

## Operational boundaries and next action

The freeze input is an operator acknowledgement, not a provider-side lock.
Concurrency serializes cooperating repository jobs, not dashboard writes or
external deployment systems. `GITHUB_RUN_ATTEMPT == 1` prevents rerunning the
same run; it does not prohibit a separately created new manual dispatch. These
are explicit runbook boundaries rather than defects in this reviewed wiring.
Enforce the external freeze and do not blindly create a replacement dispatch
after an ambiguous attempted PATCH.

First push the reviewed source and require both normal hosted source CI and
independent workflow lint to pass at the exact revision. Only then consider
the separately approved one-shot staging operation with its documented exact
inputs. Positive explicit current parent/Logs/traces/Issues-off readback,
unchanged resource projections and serving brackets remain required. Even a
successful current-worker-v1 result needs a separate reviewed downstream
attestation integration and retained-record privacy acceptance; this change
does not satisfy those gates.

## References

- [GitHub workflow dispatch inputs](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs): at most 25 top-level inputs.
- [GitHub workflow permissions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions): unspecified permissions become none when an explicit permission is set.
- [GitHub workflow/job concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency): concurrency groups coordinate repository runs/jobs; disabling in-progress cancellation does not turn the acknowledgement into an external lock or guarantee pending-run order.

## Narrow correction review: e4830ca

Reviewed `e4830cae2226fb02e1648992a6a5f30a65c16ec8` after the reported hosted
infrastructure-test failure at `eb4c09f`. Verdict: **GO for hosted source
checks; no substantive defect found in this focused correction**. The reported
failure came from an older R2 workflow test requiring exactly 23 inputs after
the separately reviewed Mail freeze input raised the actual count to 24. This
review inspected the source change, not raw hosted logs or a rerun.

Both affected tests now enforce the real platform ceiling (`<=25`), uniqueness,
and their required contract names rather than an unrelated exact total. The
current-Worker test still requires `mail_deploy_freeze` and retains all branch,
confirmation, attempt, service-lock, environment, test-before-secret and helper
wiring checks. The R2-specific test retains all six dedicated R2 input names;
its ci.yml contract also requires the dedicated Mail freeze. New fixtures accept
25 valid inputs and reject 26 inputs, duplicate names, and a missing required
Mail freeze. Thus the change removes a stale assertion, not the necessary
dispatch boundary or safety acknowledgement.

The small regex-based contract tests are not complete YAML validators. The
independent `workflow-lint.yml` parser lane remains unchanged and checks all
workflow files; this correction does not replace or bypass that broader guard.
No executable workflow, helper, mutation endpoint, secret or attestation parser
changed in this commit. No local tests, live requests or production writes were
performed in this narrow review. The original next-action and operational
boundaries above continue to apply.
