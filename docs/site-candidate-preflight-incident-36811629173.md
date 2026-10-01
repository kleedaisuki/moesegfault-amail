# Candidate preflight rejected Mail CI evidence — 2026-10-01

## Current disposition

The failed attempt remains a correctly rejected operator-input error, not a
production gate defect. Under separate root authority, corrected deployment
[36812171794](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36812171794)
used exact-source site CI `36811105233` and succeeded; subsequent exact-revision
live browser acceptance also passed. See the [current fixed ledger](site-production-candidate-lane.md#current-fixed-candidate-update-and-live-browser-outcome-2026-10-01)
for evidence and limits. The original incident investigation below is retained
with its original attribution; it did not perform that deployment.

During evidence curation, read-only GitHub metadata/logs independently confirmed
the failed run's `SOURCE_CI_RUN_ID=36811105489`, gate-step failure and skipped
provider deployment/live-smoke steps, as well as both CI workflow identities.
Thus the workflow did not reach its provider mutation step. This observation
is not a provider-wide audit of other actors or simultaneous operations.
No gate change, new target, diagnostic PR or failure waiver is warranted.

## Original outcome and boundary

Production candidate workflow run [36811629173](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36811629173), on exact main source
`47d391615e671722c7f01bb7cf8963987f6150f9`, failed at the read-only
`check_candidate_site_gate.py` preflight, before provider/deployment steps.
Root reported no provider mutation. The original investigation recorded the failed attempt only; it did not
authorize or establish a subsequent deployment or live acceptance.

The gate behaved correctly. Root confirmed that the supplied source evidence
was Mail `ci.yml` run [36811105489](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36811105489), not the required dedicated site-only
`site-ci.yml` run. An exact SHA, main branch, push event and completed successful
conclusion are necessary but not sufficient: workflow identity must also match.

Root independently identified successful exact-source site-only run
[36811105233](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36811105233). Its suitability must still be rechecked against the exact source
of any separately authorized dispatch. This historical note is not transferable
CI evidence for a later source commit.

## Cause and source evidence

Root reported selecting the Mail CI run after consulting the stale shared
primary worktree's gate/documentation rather than the current default-branch
source. Inspection of the isolated current-main worktree established:

- `infra/release/check_candidate_site_gate.py` sets `SOURCE_WORKFLOW` to
  `site-ci.yml` and `SOURCE_JOB` to `Astro candidate site source checks`.
- `check_run` requires matching workflow ID, exact SHA, trusted branch,
  accepted event, completed status and successful conclusion.
- `.github/workflows/site-candidate.yml` describes its `source_ci_run_id` input
  as a successful Candidate site CI run for the exact source SHA, and reuses
  `site-ci.yml` for same-commit source checks.
- `docs/site-production-candidate-lane.md` explicitly excludes Mail CI from
  the standalone source-evidence contract.

Therefore the generic rejection was not evidence of a token/context mismatch
or a production-source defect. Matching Mail CI metadata does not satisfy the
intentional site-only boundary. No gate condition should be relaxed.

## Disposition and verification scope

Root cancelled the proposed diagnostic/preflight production-source change once
the operator input error was confirmed. Exploratory, uncommitted source/test
edits were restored; only this incident note remains. No diagnostic PR, new
workflow target or behavioral change is delivered.

This bounded investigation inspected Git-tracked source and documentation in
`.temp/candidate-gate-diagnostic`, based on `origin/main` at the source above.
It ran no local project tests/build, provider operation or workflow dispatch.
Independent GitHub API observations and the no-provider-mutation report were
supplied by root, not repeated by this note's author. Any retry belongs to root
under separate authority and the existing unchanged deploy contract.

The practical prevention is to select evidence from the exact checked-out
main source and required workflow filename, not a stale worktree or a generic
successful CI label. Preserve the existing explicit site-only workflow/job
identity and exact-source checks.
