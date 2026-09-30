# Default-branch R2 dispatch registration review

Reviewed on 2026-10-01: isolated commit
`bc404bc03fba3f1b63452e28216c6d2b8234f9f7` against default-branch base
`5c22160d96f5fb9c8fac7aabc5a4adfc4975a068`, in
`.temp/r2-dispatch-bootstrap`, branch `codex/bootstrap-worker-r2-dispatch`.

## Decision

**GO for a focused PR that merges this one workflow file into main solely to
register manual dispatch. No substantive defect found in this bootstrap. This
is not authorization for a live probe, B registration, deployment, or release.**

No project tests, live provider calls, workflow dispatch, push, or production
edits were performed. Inspection used Git object/diff operations, file reads,
and current official GitHub documentation. Only this review artifact was written
in the shared feature workspace; the isolated bootstrap branch was not changed.

## Evidence

- The diff contains exactly one added tracked path,
  `.github/workflows/staging-worker-r2-capability.yml`, 139 lines. Its blob
  `108945e60736859d36e6c71c2b92fb0cb03e5841` is identical to the reviewed feature
  branch file. `git diff --check 5c22160 bc404bc` reports no whitespace errors.
  Base main contains only `LICENSE`; this addition does not alter an existing
  main workflow, application, deployment, or release configuration.
- Lines 4-31 declare only `workflow_dispatch`, with exactly six inputs:
  `target`, `confirm`, `worker_r2_send_attest`, `worker_r2_prior_run_id`,
  `worker_r2_prior_run_attempt`, and `worker_r2_prior_sha`. There is no push, PR,
  schedule, repository dispatch, reusable-workflow, or workflow-run trigger.
- Both job-level conditions (lines 43-46 and 88-91) require the manual event,
  their own exact target, and `github.ref ==
  'refs/heads/codex/amail-v0.1.0'`. A dispatch selecting main, the bootstrap
  branch, a tag, or any other branch skips both jobs. Consequently neither
  checkout, Python setup, tests, staging Environment execution, nor the final
  provider-secret step can execute on main. The main-only checkout lacks the
  feature harness, but this is not a failure path because the jobs are skipped.
- Top-level token permission is contents read; recovery additionally requests
  actions read. Provider secrets occur only in final steps (lines 75-84 and
  127-139); no top-level secret expression, shell interpolation of input code,
  or production Environment is introduced. Main can record a skipped manual
  run and its nonsecret inputs, not execute the staged probe.
- First-attempt confirmations, exact recovery coordinates, no-secret synthetic
  tests, timeouts, and noncanceling staging job concurrency are preserved from
  the feature file. The prior source and wiring review remains authoritative:
  [review-r2-worker-created-ci-0f338a0.md](review-r2-worker-created-ci-0f338a0.md),
  including its `371ade7` corrective integration review.

## Platform prerequisite and merge plan

GitHub states that a `workflow_dispatch` workflow must exist on the default
branch; selecting a nondefault execution branch is supported with `--ref`:
[manual workflow documentation](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow),
[event documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch).
Thus registering this path on main is a platform requirement, not a reason to
merge the unfinished product branch. A focused PR should have main as its base,
only this path in the diff, and explicitly describe the branch guard and the
nondeployment purpose. Recheck the resulting PR diff if main advances; do not
merge PR #1 or copy other feature workflow/application files to satisfy this
registration step.

The whole guarded file is safe for this narrow registration and avoids a second
handcrafted dispatch-input schema diverging from the reviewed feature workflow.
A manual-only, unconditionally skipped stub could also register the path, but
would be a different change requiring its own review; it provides no needed
safety advantage over the present exact job guards. Do not introduce a stub
that checks out the feature branch from main or forwards/reuses the feature
workflow, because that would create a new main execution path.

## Remaining limits

This review establishes source-level bootstrap isolation, not hosted GitHub
admission or live capability. After merge, execution must explicitly select the
reviewed feature ref, whose exact SHA must have successful hosted source checks.
The one-send attestation, state freeze, route-first recovery readiness, and
private output contracts remain separate live prerequisites. The dedicated
workflow's job group serializes native acceptance/probes but not all deployment
jobs; the existing coordinated staging deployment freeze is still required.
