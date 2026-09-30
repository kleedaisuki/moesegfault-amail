# Fast hosted infrastructure feedback without weakening source acceptance

## Scope and decision

Design recorded on 2026-10-01 against the source near `553cf43` and follow-up
`ed0a8c3`. No workflow change or local test execution is part of this design.
The developer workstation remains free of project builds and test toolchains.

**First fix orchestration:** inspect the existing Infrastructure job as soon as
it completes, rather than treating whole-workflow completion as the first usable
feedback. **Then add an optional `infra-checks` target to the already registered
`ci.yml`**, reusing the unchanged complete Infrastructure job. Full source checks
remain mandatory before live operations, deployment, or release. The fast target
is a precheck, never source acceptance or a release attestation.

## Measured workload and causal explanation

The relevant workload is repeated workflow/Python contract corrections, not Rust
runtime performance. These were real hosted push runs, not controlled identical
repetitions; timestamps below come from GitHub run/job APIs. UTC times and
creation-to-completion durations include scheduling and job cleanup.

| Revision / push run | Created | Infrastructure completed | Infra job duration | Full run completed | Full elapsed | Avoidable post-result wait |
| --- | --- | --- | --- | --- | --- | --- |
| `eb4c09f`, [36759561330](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36759561330) | 18:34:37 | 18:34:58, failed | 0:16 | 18:40:15, failed | 5:38 | 5:17 |
| `553cf43`, [36760335507](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36760335507) | 18:41:04 | 18:41:20, failed | 0:12 | 18:46:13, failed | 5:09 | 4:53 |

For the first run, the failed Python step ended at 18:34:55; job cleanup ended
three seconds later. Rust Worker work ran 18:34:42–18:40:14 (5:32). Its pinned
bundler install was skipped, but the exact project cache missed and Rust/Wasm
compilation/bundling still dominated. The second run's Infrastructure failure was
also already known while the Worker continued. Thus waiting for `gh run watch`
on the complete run inserted approximately five minutes into an otherwise
seconds-long corrective feedback loop. This is an orchestration dependency, not
a need to weaken tests or parallelize provider mutations.

Both workflows failed. A passing Worker/cache-save job in a red run is not a
passing source revision. Its result must not authorize live testing.

## Existing scheduling and cancellation contracts

* `dns` is the job ID for **Infrastructure probe unit tests**. It has no `needs`,
  no environment, no secrets, and runs alongside CLI, Worker, and site jobs.
* The current workflow group is `ci-checks-${github.ref}` for push/PR and manual
  `target=checks`; these cancel obsolete check runs. Other manual targets share
  `ci-${github.ref}` and do not cancel active runs.
* A push run for the project branch and its PR counterpart use different refs
  (`refs/heads/...` versus `refs/pull/.../merge`). The PR counterpart currently
  skips broad suites for this project branch, avoiding duplicate compilation.
* CLI matrix `fail-fast: false` affects that matrix only. An Infrastructure
  failure does not automatically cancel Worker/CLI/site jobs. Keeping their
  evidence is reasonable; waiting for them before inspecting Infra is not.
* Adding `infra-checks` to the existing checks group would accidentally cancel
  full source validation. Leaving it in the default manual group would queue
  behind live operations and could replace another pending manual operation.
  Neither is acceptable.

## Minimal implementation boundary, after CI ownership is released

Only the CI owner should edit `ci.yml`; this document does not do so.

1. Add **one value** `infra-checks` to the existing `target` choice. Add no new
   dispatch input, arbitrary command, module selector, or confirmation.
2. Add `inputs.target == 'infra-checks'` only to the `dns` job's manual predicate.
   Keep all existing steps: complete `infra/tests` discovery, Identity inbox and
   role route safeguards, Mail observability privacy tests, private-inbox source
   configuration, and staging isolation source contract. Do not cherry-pick the
   previously failing test, and do not skip source contracts on a fast pass.
3. Give this target a third isolated workflow group:

   ```yaml
   concurrency:
     group: ci-${{ github.event_name == 'workflow_dispatch' && inputs.target == 'infra-checks' && 'infra-checks-' || ((github.event_name != 'workflow_dispatch' || inputs.target == 'checks') && 'checks-' || '') }}${{ github.ref }}
     cancel-in-progress: ${{ github.event_name != 'workflow_dispatch' || inputs.target == 'checks' || inputs.target == 'infra-checks' }}
   ```

   This preserves existing `ci-checks-${ref}` and `ci-${ref}` names while isolating
   `ci-infra-checks-${ref}`. New fast runs may supersede old fast runs; they must
   never supersede full checks or a live operation. This is illustrative syntax
   to review/test, not deployed configuration.
4. For workflow-edit prechecks, add conditional pinned YAML-parser validation
   and its synthetic fixtures to `dns` **only for `infra-checks`**, reusing
   `infra/workflow_lint/requirements.txt` and existing guard commands. These
   supplement, not replace, the independent push/PR syntax guard. A malformed
   `ci.yml` can still be rejected before this job starts; that is a failed
   precheck, not a reason to bypass the independent syntax lane.
5. Extend `test_ci_iteration_contract.py` with a table of three dispatch classes
   and push/PR. Assert: exact concurrency separation, cancellation only for
   source/precheck classes, exactly `dns` eligible for the fast target, unchanged
   full-check suite membership, no secrets/environment/cache/artifact in fast
   scope, no provider/live/deploy/release eligibility, and reuse of all Infra
   steps. Keep the dispatch-count upper-bound contract rather than stale exact
   input counts. Update the existing predicate assertion for the expanded
   cancelable selector deliberately; do not delete its safety checks.

No push trigger, required check, production dependency, live target predicate,
serving-version pin, mutation lock, or release attestation is changed. A workflow
shown green for `infra-checks` must always be labeled/reported as **Infra-only**.
The selected ref and `head_sha` must be checked before using even that result.

## How the lane actually saves time and cost

On `main` or `codex/amail-v0.1.0`, a push still starts full source CI. Dispatching
`infra-checks` immediately afterward duplicates the already running Infra work
and does **not** reduce compilation cost. For ordinary project-branch fixes,
monitor the Infra job directly and prepare a correction once it is red. A newer
push safely supersedes obsolete source checks under the existing policy.

For several related contract edits, a temporary candidate ref outside the two
push branch filters can carry committed source and use manual `infra-checks`.
Do not open a PR for each precheck: the existing PR trigger would start broad
checks. Do not broaden push `paths` or exempt the integration branch. After the
candidate passes, integrate the exact reviewed code onto the project branch and
require its full push CI, or explicitly run `target=checks` on the immutable
candidate before any further use that requires complete source evidence. No
check result from the temporary ref can stand in for the final integration SHA.
Temporary candidates may not save trusted Worker caches or invoke live targets.

Example once implemented (not dispatched by this design):

```powershell
gh workflow run ci.yml --ref codex/infra-feedback-candidate -f target=infra-checks
gh run view <run-id> --json headSha,event,status,conclusion,jobs
```

Before integration, verify the selected fast run has exactly the Infrastructure
job active, and no provider calls, secrets, artifacts, or deployment side
effects. For immediate zero-code job monitoring:

```powershell
gh api 'repos/kleedaisuki/moesegfault-amail/actions/runs/<run-id>/jobs?per_page=100' --jq '.jobs[] | select(.name == "Infrastructure probe unit tests") | {id,status,conclusion,started_at,completed_at}'
```

Inspect failure logs for that completed job only; do not wait for unrelated
builds. Once green, wait for the full source run before crossing a live gate.

## Expected effect and hosted validation

The observed **failure diagnosis** can already move from 5:09–5:38 to 0:16–0:21
after push creation: approximately 4:53–5:17 less corrective wait for these two
cases. This is based on existing job results, not a claimed measured new-lane
speedup. A full-green fast lane will execute later Infra steps and optional
syntax checks, so budget approximately **20–45 seconds plus runner queue time**;
measure it rather than promising the failed-job duration for a passing suite.
Full source acceptance remains approximately minutes, workload/cache dependent.

Validation must run hosted, once source review and CI ownership allow:

1. Full source push CI validates the implementation, including expanded lane
   contracts and independent syntax guard; it must be green.
2. One fast dispatch at that reviewed SHA verifies only Infra executes and all
   its steps plus optional syntax guards pass. Record creation/first job/end,
   test counts, skip matrix, selected SHA, and run links.
3. If a future natural regression occurs, confirm its fast red result can drive
   correction without waiting for whole-source completion. Do not manufacture
   repeated failed hosted builds purely to demonstrate an already measured
   orchestration issue.

The target is useful only when there are repeated contract-only candidates or
the orchestration currently insists on a whole-run result. It does not speed
SMTP delivery, provider state propagation, privacy acceptance, or production
promotion. Those remain guarded separate workloads.

## Alternatives and external grounding

* **No new lane, job-level monitoring:** cheapest immediate improvement; removes
  observed corrective waiting but not the full-build runner cost.
* **New infra workflow:** cleaner UI but duplicates steps and brings the known
  default-branch registration/bootstrap problem for manual dispatch. An existing
  target avoids that trap.
* **Path-filtered full CI/test selection:** rejected here. Workflow/config
  changes can affect all suites; path-filtered required workflows may remain
  pending. Avoid changing acceptance coverage to solve seconds-long contract
  feedback. GitHub documents these interactions in [workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore).
* **Shared concurrency or cancel-on-Infra-failure:** rejected; the former can
  invalidate acceptance, and the latter discards useful broad-suite evidence.
  [GitHub concurrency](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency)
  documents group-scoped cancellation and pending-run behavior.
* **Local tests:** excluded by the user's disk/toolchain constraint, not treated
  as the obvious fallback.
* **Learned/scheduled test omission:** Google's [Speculative Testing with
  Transition Prediction](https://research.google/pubs/speculative-testing-at-google-with-transition-prediction/)
  is relevant to large test-selection workloads, but the measured problem here
  is waiting on an unrelated compilation after a completed failure. A small
  deterministic feedback boundary is more appropriate than learned omission.

[GitHub manual workflow documentation](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
requires a dispatchable workflow on the default branch and supports selecting
another ref. Reusing registered `ci.yml` avoids introducing a second bootstrap.
Its 25-input maximum is unaffected: this proposal adds a choice value, not an
input.

## Reproducibility

Read run metadata and non-sensitive timing/conclusion fields only:

```powershell
gh api repos/kleedaisuki/moesegfault-amail/actions/runs/36759561330
gh api 'repos/kleedaisuki/moesegfault-amail/actions/runs/36759561330/jobs?per_page=100'
gh api repos/kleedaisuki/moesegfault-amail/actions/runs/36760335507
gh api 'repos/kleedaisuki/moesegfault-amail/actions/runs/36760335507/jobs?per_page=100'
```

Use ISO timestamps, not run `run_started_at`, as documented in the existing
[critical-path baseline](hosted-iteration-critical-path-2026-09-30.md). No mailbox
data, provider logs, credentials, or private operational recipient are needed.
