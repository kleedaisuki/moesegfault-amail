# Review: production CI graph phases (60627a8 + bbc5fb6)

Date: 2026-10-01. Reviewer scope: independent static review of the net CI wiring,
its direct helper callers, and the existing production writer workflows.

## Verdict

**GO for hosted source checks only. NO-GO for a live production graph rollout.**
The changed dispatch, phase mapping, dependency wiring and strict topology
readbacks have no identified source-check blocker. One material cross-workflow
exclusion gap must be resolved before the documented whole-graph rollout can be
claimed. This review is not deployment, privacy-canary, routing or release
acceptance. The separately reviewed production held-policy helper correction is
not re-adjudicated here.

## Finding P2: the shared lock does not cover existing production route/policy writers

Locations: `.github/workflows/ci.yml` workflow-level concurrency;
`.github/workflows/deploy-role-monitor-production.yml` workflow-level concurrency;
`.github/workflows/role-forwarding.yml` concurrency;
`.github/workflows/send-control.yml` and
`.github/workflows/attest-send-gate.yml` production mutation jobs.

The new CI bootstrap/maintenance targets and role deploy share
`amail-production-graph-writer` with running cancellation disabled. However,
reserved role forwarding uses `reserved-role-forwarding-production`, while the
operator policy and release-gate workflows have no corresponding exclusion.
They remain separately dispatchable on main while graph replacement is running.

Trigger/impact: a concurrent production policy/gate dispatch can change the held
send/release predicates that `check_production_role_graph.py` brackets, including
a change after its final read. Route reconciliation remains an independent
control-plane writer and is not excluded by the declared graph lock. The route
helper currently refuses existing conflicting rules and only creates missing
ones, so this is **not** a demonstrated Worker-route overwrite in a healthy
four-rule state. It is nevertheless an executable violation of the documented
whole-graph writer exclusion, not just a naming preference. The freeze input is
an operator assertion; it does not enforce exclusion against these repo-owned
writers.

Remedy: use the same non-canceling workflow-level lock for production route
mutators and production policy/release-predicate mutators, selecting a separate
staging group where appropriate. Keep read-only audit operations outside the
mutation lock if desired. Add source guards for the complete writer inventory,
not just CI and role deployment. Do not use the workflow lock as a job-level
lock inside the workflow that already holds it. Emergency holds must remain
operationally usable; explicitly model/document any intentional emergency
exception rather than silently treating it as ordinary serialized maintenance.

Confidence: high for the lock mismatch and production policy execution path;
conditional for the timing of an actual concurrent operator dispatch. No such
concurrent run was performed or observed in this review.

## Verified static properties

* `ci.yml` has **25 top-level dispatch input names, all unique**, including
  `r2_prior_run_id` and `r2_prior_run_attempt`. The corrected regex counts digits.
  The independent workflow lint checks YAML/duplicates/dispatch limits; the
  narrower production guard is not the sole YAML-validation mechanism.
* `production` selects bootstrap / `api-only`;
  `production-api-role-maintenance` selects maintenance / `api-role`.
  Mutating graph jobs are manual and main-only. The helper requires the matching
  `RUN_PRODUCTION_API_ONLY_BOOTSTRAP` or
  `RUN_PRODUCTION_API_ROLE_MAINTENANCE` confirmation and
  `FREEZE_PRODUCTION_GRAPH_WRITERS` before Queue/sink mutation.
* Sink deployment needs the Worker and infrastructure source jobs. API deployment
  additionally needs CLI, site, live synthetic provider contract and the sink.
  `dns` discovers the production helper/workflow fixtures before graph mutation.
  The preexisting `provider-live` synthetic OpenRouter job itself is independent
  of source jobs; this change extends it to maintenance. Thus the narrower claim
  **source contracts gate production graph mutations** is supported, but a claim
  that every secret-bearing/provider job waits for source tests would be false.
* Maintenance uses Queue readback with exact `api-role`, not Queue creation.
  It verifies the old graph before sink replacement, new sink with unchanged
  API/role, and old/new API around replacement. Reviewed project pins are not
  rewritten or adopted from a latest-version listing.
* Workflow-level production graph lock is distinct from the existing dependent
  sink/API job locks, so the introduced lock does not self-deadlock those jobs.
  `cancel-in-progress` evaluates false for both production graph targets.
* Post-bootstrap API acceptance requires strict `api-only`, private capture,
  role absence, four forwards and held policy before the configuration marker.
  Maintenance requires exact API+role/sink identity, bindings and capture,
  reviewed 0..4 route count and unchanged snapshots. It does not erase a live
  role ledger to manufacture an empty state.
* Phase-two role evidence remains fail-closed on the missing actual production
  and staged whole-record acceptance emitters. The graph configuration marker
  is not a privacy marker. No route-cutover runner or send-unhold was added.
* Maintenance does not select ingress/events/site production jobs or a release.
  Bootstrap preserves the existing release-ready published/attested asset gate
  for site deployment. This change creates no tag or GitHub Release.
* Net CI changes only add the maintenance option to the ordinary source checks
  and existing synthetic promotion probe; the staging manual target predicates,
  push non-deploying behavior and independent workflow-lint lane are unchanged.

## Method and limits

Reviewed committed net diff `60627a8^..bbc5fb6`, current matching CI/test files,
`docs/production-role-queue-rollout.md`, prepare/graph/deployment/evidence helpers,
existing forwarding/policy/gate workflows and workflow-lint configuration.
Input count was a PowerShell text inspection, not execution of project tests.
No local test/build, provider API call, live dispatch, production edit, deployment,
route mutation or release was performed. Unrelated shared-worktree edits were
not included in the review or modified.

Official reference retrieved on 2026-10-01:
[GitHub workflow syntax: dispatch inputs and concurrency](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
The documented top-level dispatch maximum is 25. Concurrency groups apply across
workflows in the repository; keeping a running operation non-canceling does not
by itself promise an unlimited pending queue. This review does not require a new
queueing option for the intended manually frozen, single-transition operation.
