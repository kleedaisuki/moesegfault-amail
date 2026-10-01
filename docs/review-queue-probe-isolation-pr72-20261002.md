# Independent source review: PR 72 Queue probe isolation

Date: 2026-10-02
Verdict: GO for source acceptance; no substantive blocker found. Hosted execution acceptance remains the leader's separate gate.
Confidence: high for the bounded diff and source contracts; no execution or provider verification claimed.

## Identity and method

Reviewed checkout: .temp/queue-probe-isolation.
Head: 1d088044e9f65a7d2136ffa30e9e113f6f7f803f.
Base: bfb02765c622bced2ad2b8a10f6717cce79c6199.
The checkout was clean. All six changed files were read, as were the maintainer skill, infrastructure foundation ledger, unchanged helper, selector, targeted CI discovery/syntax wiring, shared workflow-source extractor, and deployment counterpart references. Git diff --check returned no errors. Repository searches traced the probe's callers and fixed output labels. No accepted source was modified.

No local tests, builds, package installation, workflow dispatch, GitHub mutation, provider request, or merge was performed. Public GitHub/Cloudflare documentation was read through web browsing; this is not a credentialed provider/API operation.

## Findings

No demonstrated correctness, compatibility, recovery, or material design defect in this change.

## Contract evidence

| Concern | Source evidence | Assessment |
| --- | --- | --- |
| Automatic provider surface | .github/workflows/probe-queues.yml:5-6; diff deletes only the legacy push mapping, besides the explanatory header | workflow_dispatch is the only remaining event. No push, PR, schedule, workflow_call, or workflow_run is added. |
| Manual API compatibility | Workflow filename, display name, probe job, checkout/setup, Python version, timeout, permissions, environment variables, and command unchanged | No new input, branch restriction, confirmation, credential identity, or ref behavior. Existing operator dispatch remains source-compatible. |
| Helper/output compatibility | infra/provider/probe_queues.py unchanged against base; main reads env and uses urllib GET | Missing credentials return 2 without HTTP; 200 returns 0/read_available; HTTP failure returns 1/not_available; URLError returns 2/network_error. No response-body print/read is introduced. |
| Hidden caller/build/promotion edge | Explicit .github and infra search plus repository probe/name/output references | Sole production helper invocation is its own standalone workflow. No build, native artifact, release/promotion, or recovery consumer was found. No import-time HTTP: main runs only under the script entry guard. |
| Exact CI exemption | infra/ci/pr_scope.py:23; select/current_scope unchanged except exact path addition | Exact diagnostic path skips unrelated PR compilation only. Selector changes themselves request full checks, so this PR requests full source checks. Unknown workflows, compiler/shared inputs, and mixed actual consumer edits remain conservative. Non-PR current_scope remains full. |
| Mandatory source checks | ci.yml dns job:1726-1749, workflow-lint.yml independent push/PR syntax guard; existing test_pr_scope contracts | Infrastructure discovery does not depend on selector outputs. Existing legacy-branch PR exclusion predates this change; normal scoped PR checks and pushes still discover the new test. No live helper is run by automatic source checks. |
| Meaningful regression coverage | infra/tests/test_probe_queues.py five tests; test_pr_scope.py new exact/mixed test | Event identity/no-input surface, job/helper/Secrets identities, other workflow direct callers, no-credentials no-call, single mocked GET/timeout/body-free output, fixed HTTP/network errors, fail-full nearby inputs, and worker mixed edits are checked. HTTP is patched before main in every invocation. These are source/synthetic contracts, not live permission proof. |
| Recovery/deployment preservation | No ci.yml/helper changes; actual ensure_email_events.py and ensure_trace_queues.py invocation references remain in deployment jobs | Read-only permission probe owns no created resources or recovery obligations. Existing actual graph/deployment/recovery paths are untouched, not replaced by HTTP 200. |
| Documentation | docs/maintenance-operational-lanes.md:175-207; docs/outbound-abuse-operations.md:20-32 | Correctly distinguishes coarse read from Queue Write/graph admission, disallows historical replay, preserves manual authorization, and explicitly states current-source cleanup does not disable old branch/run definitions. Hosted evidence is not fabricated. |

## Limits and operational caveats

- GO does not assert pending hosted runs passed, nor authorize deployment, manual provider diagnosis, credential alteration, sending, or merge.
- Current source removal cannot retroactively disable the legacy trigger in another branch's old workflow definition or an old run. The runbook states this explicitly. No remote branch or workflow-disable action was taken.
- The tests intentionally target the current repository's block-layout source. They are not a universal YAML/call-graph proof; independent hosted YAML validation remains necessary. Their syntactic strictness is acceptable for this bounded contract.
- The unchanged helper calls urlopen once; HTTP transport redirects are platform behavior, not a newly introduced application retry contract. No live behavior was exercised.
- Existing deployment helper internals, all other workflow implementations, and remote branch-protection/registration state were outside this review. The review verifies preservation, not global operational readiness.

## External references checked

- [GitHub manual workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow): workflow_dispatch, repository write access, default-branch registration, and non-default source ref are documented. Retaining the existing event/no-input structure aligns with this supported interface; no live dispatch was needed.
- [Cloudflare List Queues](https://developers.cloudflare.com/api/resources/queues/methods/list/): GET /accounts/{account_id}/queues accepts read permissions as well as write permissions. Thus successful list access cannot establish Queue Write. This supports the new documentation's narrow evidence boundary.

This is maintenance contract review, not an academic/research contribution. No speculative framework or unrelated redesign is warranted.
