# Historical diagnostic test boundary correction review

Reviewed October 1, 2026 at `ed0a8c3cb3ce1eb8f191ffbb0ccd670c6eb8275e`.
Scope: the single test-file diff and unchanged per-job workflow assertions.
No local tests, live reads, provider mutations or production edits were made.

## Decision

**GO for hosted source checks; no substantive defect found.** This corrects a
test extraction boundary, not a workflow privilege or diagnostic behavior.
No hosted pass or live capability is attested by this static review.

## Evidence

The former split selected everything between the original historical job and a
named later preflight job. Inserting the reduced-schema job in that interval
therefore included its unrelated credentials and caused the original job's
single-secret assertion to count two jobs. `workflow_job()` now anchors the
exact escaped job name at two-space indentation and terminates at the next
top-level job name or end of input. Missing and duplicate selected jobs raise
instead of silently selecting an arbitrary block.

The new fixture inserts a differently named, credential-bearing adjacent job
before the old sentinel and checks that only the owned block and one owned
token are selected. It also covers final-job extraction, missing target and
duplicate target. Existing manual feature-ref/staging, confirmation, test-before-
credentials and excluded mutation credentials/helper assertions remain unchanged;
their strict single-secret checks still apply to the selected job. The diff
touches no workflow or provider helper.

The extractor is deliberately structural for this repository's existing
unquoted two-space job keys; it is not a general YAML parser. That matches the
current source and the existing workflow-boundary helper pattern. Hosted source
execution remains necessary to verify the fix against the actual workflow.
