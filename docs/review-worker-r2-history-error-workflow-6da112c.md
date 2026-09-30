# Historical Email error-class workflow review

Reviewed 2026-10-01 at `6da112caa7d83822b81e93b6914b780f97aa5436`, net changes
`1dcf7a6..6da112c`. Source helper review is separately recorded in
`review-worker-r2-history-error-6c34c43.md`. No local tests, live requests,
mail sends, routing/R2 operations or production edits were performed.
Concurrent uncommitted production workflow changes are excluded.

## Decision

**GO for nondeploying hosted source checks. No substantive defect found in the
final committed workflow wiring.** After those checks pass, the reviewed lane
can perform its separately authorized single content-free historical query.
This is not delivery acceptance, R2 capability acceptance or release approval.

The initially requested intermediate `cdb57f5` contains only documentation and
tests, not the job; it is not a deployable/dispatchable wiring revision. The
additional `e47cfa6` supplies the lane and `6da112c` normalizes its committed
workflow line endings. Review approval applies to the final revision, not that
incomplete intermediate commit. Ignoring line-ending differences, the final
normalization introduces no semantic changes.

## Contract trace

| Boundary | Evidence and assessment |
| --- | --- |
| Dispatch schema | The net diff adds one option to existing `target` and no input declarations. Static scoped extraction finds 24 declarations and 24 distinct names. Existing independent YAML guard rejects duplicate keys and more than 25 inputs. Its implementation/lane is unchanged. |
| Trigger and isolation | New job requires `workflow_dispatch`, its exact target, and `refs/heads/codex/amail-v0.1.0`; uses staging Environment, five-minute timeout, and only contents/actions read permissions. No push-triggered provider query is added. |
| Input guard | Before the credential-bearing step, Bash checks exact confirmation `READ_WORKER_R2_HISTORY_ERROR_CLASS_36751791789` and `GITHUB_RUN_ATTEMPT == 1`; failure exits nonzero. Guard inputs are passed through environment variables, not script interpolation. No failure bypass is present. |
| Synthetic checks | Original-history, new error-class, and new workflow-contract suites execute before the only credential-bearing helper step. Bash default failure behavior prevents later execution after a failing suite. The synthetic workflow suite extracts only the guard and checks valid/invalid confirmation and first/retried/empty attempt. |
| Credential boundary | Provider step receives only Analytics token, GitHub read token, fixed zone, confirmation and bytecode-disable flag. No sending/routing-write/R2 credential, mutation tool, or artifact-upload step appears in this lane. Standard checkout credentials are read-only repository credentials; they are not provider credentials. |
| Historical restriction | Helper command supplies fixed original run `36751791789`. Previously reviewed helper validates immutable original-run provenance/time window and requests only `__typename`, one row per dataset, through one bounded no-redirect GraphQL POST. No event content/identity is selected. |
| Existing contracts | Net semantic diff leaves original history/shape jobs, other dispatch targets, source CI selection, permissions and manual concurrency unchanged. No live deployment or other target is weakened. |
| Authority/output | Closed helper output always retains `delivery=UNVERIFIED`; no raw provider payload or output artifact is introduced. Successful classification, including error/unknown bins, cannot authorize mail operations. |

## Limits and next step

Synthetic suites and workflow-lint were inspected, not run locally. Require
hosted checks on the reviewed committed revision before the one diagnostic.
The full uncommitted working tree is not covered: future additional dispatch
inputs must still satisfy the shared 25-input/uniqueness contract and receive
separate review. No result here changes the existing B-account NO-GO or public
sending/privacy hold.
