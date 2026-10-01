# Independent infrastructure source-contract review

Date: 2026-10-01 UTC. Reviewer: integration_contract_review.

## Scope and verdict

No substantive source defect found in the inspected changes. Source GO is
conditional on each exact reviewed head retaining its hosted required checks;
it is not merge permission, deployment, provider/runtime/privacy acceptance or
permission to resume Mail debugging/sending.

| PR | Reviewed head | Boundary | Evidence status at review |
| --- | --- | --- | --- |
| 60 | `c1f22f944d5daf7aa771a96d205d89f7283201d1` | Exact diagnostic-consumer PR scope exemptions | Infrastructure/syntax/CLI/site/build passed; full native/aggregate still pending in run 36878941903 |
| 62 | `461183b4cb83b050f7de44f1b50efa33db16b1c1` | Retirement of three completed fixed-window read jobs | Infrastructure/syntax/CLI/site/build and most native passed; full run 36878849332 still pending |
| 58 | `53de8997c6f9d0148ecf5524b5558659474e64e4` | Standalone inbox exact-current-main artifact admission | Full hosted PR run 36877404614 success, 14:34:31–14:39:23 UTC; syntax success |

PR 58 was assessed against its deployment-lifecycle base, not as a duplicate
review of PR 55. Baseline reference for PR 60/62: origin/main `d593d1a`.
The root checkout was dirty/stale and was not modified. Review knowledge lives
in a dedicated repository-local worktree based on origin/main.

## PR 60: conservative consumer selection

The only policy delta is three exact additions to `INFRASTRUCTURE_ONLY`:
`native-fixture.yml`, `native-tracing-canary.yml`, and `native_fixture.py`.
Their present code consumes already compiled trees; none invokes Rust compilation
or produces new Wasm module bytes. Native fixture execution remains a hosted
diagnostic, not a substituted full-suite acceptance run. The canary workflow
retains mandatory hosted synthetic checks and original checked-artifact
verification before provider work.

`native_fixture.api` also supplies metadata reads to `validated_worker_build`
and the PR 58 inbox admission helper. This dependency is real, but metadata-only:
synthetic infrastructure discovery includes the replay and admission tests. The
change does not bypass these contracts or alter their release/full-CI predicates.
Compiler inputs, package/lockfiles, worker-boundary native fixtures, actual Worker
source and configs still select Worker compilation and all native suites.
Selector/admission/artifact/suite helpers and unknown workflows remain full.
Mixed edits take the union, including full checks for unknown/shared changes.

Metadata or Git diff failure, malformed SHA/encoding, incomplete NUL termination
and oversized output retain the existing full fallback. Non-PR events select
full scope. The unconditional `dns` infrastructure job and independent
`workflow-lint.yml` guard have no new selector dependency/path suppression.
No release/deployment consumer or stable Worker aggregate is changed.

The actual hosted comment-only probe is independently verified:

* PR 61 head `524cf36cb2d3e96d2a06a392467838ed8ada97d4`;
  run [36878536461](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36878536461).
* Pull-request event, conclusion success, created 14:43:05 and completed/updated
  14:43:38 UTC: 33 seconds observed wall time.
* Scope and infrastructure actually succeeded; CLI, site, Worker producer,
  native matrix, aggregate and provider/deployment jobs were skipped.

This proves the real hosted scoped path, not the selector modification's full
checks or trusted-main promotion. The contrast with a historical 322-second
orchestration PR is workload-specific and uncontrolled, not a paired benchmark
or latency guarantee. Exact filename exemptions must be re-reviewed if those
files acquire compiler/build behavior in a future change.

## PR 62: complete edge removal without recovery breakage

The workflow delta removes exactly three dispatch choices and their complete
job blocks: `staging-trace-marker-location`,
`staging-trace-marker-discriminator`, `staging-trace-security-events`.
No other executable workflow content changes. Targeted repository searches of
checked-in workflows and infrastructure show no remaining invocation/caller for
the three scripts. No `needs`/reusable caller depends on the deleted jobs.

These are completed immutable September 30 incident reads, not writers,
recoveries, ordinary source checks or supported promotion prerequisites. Their
classifiers, original confirmation/time-scope logic, private-output regressions,
and historical evidence remain. In particular, discriminator imports its first
classifier, and both modules/tests are retained. Test deletions remove obsolete
assertions that those workflow jobs remain executable; privacy/scope/error tests
are preserved and a new all-workflow retirement contract replaces the old wiring
assertions. Recovery jobs, current native-tracing workflow, stable gates and
standalone inbox deployment remain available.

The change does not claim remote disabling, cancellation, old-ref deletion or
prevention of historical run replay. Its runbook explicitly documents this
residual surface and forbids treating archived queries as current runbooks.
No CLI/HTTP/ZIP/Identity/storage/binary contract is modified. Removing the
executable edges is preferable to retaining secret-bearing jobs under `if: false`.

## PR 58: exact-current-main inbox admission

The supported workflow identity, manual main-only job, staging environment,
non-cancelling shared staging lock, route absence checks on both sides of the
write, private R2/config verification and deployed allowlist readback remain.
Floating stable compiler setup, local build/test/bundle steps are replaced with
download of a full checked exact-source artifact, not an ancestor/rebuild path.

Admission requires repository, workflow, branch, allowed event, exact source,
successful completed first attempt and complete bounded job/artifact inventories.
Every current native suite and all CLI/site/infrastructure/build/aggregate gates
must succeed. Duplicate/expired artifacts are rejected. The optional lookup
checks only exact-current-main successful runs, bounded to five candidates;
when it cannot qualify one it fails closed and supports an explicit run ID.
Documentation explains the docs-only-main remedy: run non-deploying exact-SHA
checks first, not ancestor reuse.

Download is bound to original run and fixed artifact ID. Restore preserves the
original run/attempt under unchanged current SHA, and invokes the existing
manifest verifier for compiler/bundler, every generated file/hash and all seven
module trees. Source config points at restored `build/worker/shim.mjs` and has
no implicit Rust build command. Provider route/config reads occur after restore.
Existing job-level provider secrets remain unchanged; no new provider access or
deployment was exercised by this review. Final Wrangler packaging/live readback
is deliberately separate acceptance, not inferred from hosted synthetic CI.

## Method and limits

Read the maintainer skill and foundation ledger first; inspect PR metadata,
focused diffs, selector/workflow/helper callers and synthetic test contracts.
Inspect existing hosted run/check metadata only. `git diff --check` passed for
all three reviewed diffs. No local project/runtime/cross-platform tests,
compiler install, provider operation, deployment, route/account mutation,
secret read/output or merge was performed. Historical baseline/runtime PRs
54/55/56 were not re-audited. Future PR head changes invalidate these exact-head
verdicts until their deltas are inspected.

Platform references checked against primary documentation:

* [GitHub workflow triggering](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
  — event filters and conditional job execution are different boundaries; the
  mandatory workflow is not removed by the scoped expensive-job policy.
* [GitHub reusable workflow configurations](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations)
  — workflow callers and historical source semantics matter to retirement.

This focused review claims no new test-selection or orchestration research.
Existing `ci-source-scope-and-latency.md` places dependency-aware selection versus
learned prediction in context; no learned/approximate admission mechanism is
introduced. The relevant practical result is preserving strict trusted-source
gates while shortening unrelated diagnostic repair loops.
