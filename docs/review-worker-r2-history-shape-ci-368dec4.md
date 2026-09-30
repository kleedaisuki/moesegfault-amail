# Reduced historical Worker-R2 diagnostic CI review

Reviewed 2026-10-01 at `368dec48f37465031a4d57c70aa3b80083c0c018`.
Scope: the workflow diff, its new contract tests and documentation, existing
workflow concurrency and source-test lane, and the imported helper contract.
The earlier helper assessment is retained in
`review-worker-r2-history-shape-f400648.md`. No local tests, live queries,
credential reads, provider mutations, email sends or production changes were
performed. Only this review artifact is added.

## Decision

**GO for nondeploying hosted source checks. No substantive defect found.**
This does not authorize or attest a live query, historical delivery, R2
capability, B registration, privacy containment, or release readiness.

## Evidence

| Boundary | Evidence | Assessment |
| --- | --- | --- |
| Dispatch shape | `ci.yml` input header and diff | Existing `confirm` is reused; static enumeration yields 24 top-level inputs, below GitHub's 25-property limit. Only one new choice is added. |
| Execution scope | `staging-worker-r2-history-shape` job `if` | Requires manual dispatch, exact target and feature branch; staging Environment, five-minute deadline and read-only contents/actions permissions are explicit. Push/PR source checks cannot enter this job. |
| Credential ordering | First Bash guard and step-local environment | Exact new confirmation and `GITHUB_RUN_ATTEMPT=1` are required before setup/tests and before the sole explicit provider-token/GitHub-token helper step. No user input is interpolated into shell source. No failure bypass is present. |
| Source validation | Three test invocations and existing all-infra unittest discovery | Original provenance tests, reduced-schema tests and workflow contract tests precede credentials. Normal hosted source CI discovers the new workflow test as well. Static examination confirms the extracted Bash guard fixtures cover correct/wrong/empty confirmation and retry/empty attempt. No local execution is claimed. |
| Concurrency | Unchanged workflow-level group expression | Both historical targets on the same feature ref resolve to `ci-refs/heads/codex/amail-v0.1.0`, with `cancel-in-progress=false`; they cannot execute concurrently. Push/check runs use a distinct checks group. This does not establish FIFO ordering or unlimited pending-run retention. |
| Query contract | Fixed helper invocation and reviewed helper | Only original run `36751791789` is passed. The helper validates original provenance and derives its immutable window, then makes one bounded reduced historical GraphQL read; no send, route/R2 operation or correction helper is invoked. |
| Output and isolation | Job steps, helper closed output, exact diff | No artifact upload, raw provider print, shell tracing or retry loop is added. Classified success retains `delivery=UNVERIFIED`. Existing historical target, correction target and other gates are unchanged; no source acceptance rule is weakened. |

The checkout action necessarily uses its built-in read token before the guard;
the gate protects explicit diagnostic credential exposure and provider execution,
not a claim that checkout has no token. The synthetic tests perform no provider
operation and receive neither explicit diagnostic credential environment value.

## External contract and limits

GitHub's [workflow syntax reference](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs)
(consulted October 1, 2026) specifies a maximum of 25 dispatch input properties.
Its concurrency contract supports the shared non-cancelling active-run exclusion;
pending runs may still be superseded, so dispatch should follow confirmed hosted
source results rather than assuming all queued probes will execute.

Hosted syntax/tests are still required. This static review does not verify actual
token access, response schema, provider retention/completeness or the outcome of
the earlier experiment. First-attempt gating excludes workflow reruns, not a
separately created new dispatch; operationally authorize at most one new bounded
diagnostic and do not treat the lane as an automated retry mechanism.
