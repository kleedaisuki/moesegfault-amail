# Independent review: durable quota campaign arm and explicit selectors

Date: 2026-10-01. Reviewed commits: `447e7bb` and `5ded982`, atop
`396c0b3`, compared with the local `origin/main` reference at `89ce49f`.
Worktree: `.temp/quota-escrow-wiring`.

## Decision and scope

**GO for hosted source-only checks. No substantive source defect found in this
bounded change. This is not permission to dispatch a live campaign or deploy.**
The new CLI selectors remain absent from existing workflows. Exact supervisor /
handoff admission, original workflow registration, writer exclusion, current
privacy and provider/service provenance remain obligations of future workflow
wiring. No public-send or release gate is closed by this review.

Inspected the complete two-commit diff, surrounding acceptance/controller,
Escrow read/attach/arm/binding/finalizer implementation, synthetic tests and
existing expiry-recovery review. Only static source inspection and
`git diff --check` were performed. No local project tests/builds, provider calls,
workflow dispatch, credentials, push or production-source edits were performed.
This document records inspected test contracts, not observed test results.

## Verified source paths

- `campaign_escrow` rejects foreign original-run input, wrong phase and missing
  artifact before reading capabilities. Durable campaign/prepare require the
  fixed retained generation. `_execute` admits exact hosted dispatch, checkout,
  independent source CI and original artifact provenance before native work.
- `hosted._campaign` authenticates exact local/downloaded ciphertext and its
  original run/generation, current checkout, owner, service version and Identity
  provenance. Complete empty baseline admission happens before escrow access.
- `Escrow.read` exhausts bounded chunks, validates aggregate count/bytes, each
  chunk and ciphertext digest, authenticates the manifest, checks all `BOUND`
  fields (original run, attempt, repository/workflow, source, version,
  generation, digest, size/count/reservation), then repeats complete readback.
- Durable campaign requires sealed state with no arm time or receipt and exact
  downloaded bytes. `attach` admits only the exact immutable artifact ID and
  authenticated envelope; it cannot replace a different prior attachment.
  Complete `_observe` is repeated after attachment, covering global snapshot,
  owner list, serving/binding/hold checks and resource storage.
- Concrete `Escrow.arm` requires sealed exact bytes/artifact, this invocation's
  conditional `changes == 1`, and independent authenticated complete armed
  readback. The controller checks the returned Arm's original-run, digest,
  artifact and integer timestamp before the first `add`.
- Read/attach/arm/permit failures occur **before** entering the mutating
  `try/finally`. Missing, zero-change, lost or already-armed acknowledgment
  cannot grant address addition or cleanup deletion. The successful campaign
  retains complete ciphertext and armed metadata; it neither creates a terminal
  receipt nor purges chunks.
- Legacy `campaign` passes `client=None` to the shared controller, preserving
  its admission/serial mutation/cleanup contract. Legacy selectors still call
  `execute`; there is no exception-based transport fallback.
- Explicit `recover-escrow` chooses only retained-ciphertext finalization with
  empty artifact ID. It requires a distinct completed original invocation,
  authenticated original-source provenance, fresh read-only owner/service/
  storage checks, native teardown and scratch removal before receipt creation.
  Final complete authenticated receipt/ciphertext readback remains common to
  new and prior terminal states. This path returns the retained label before
  artifact-only `_purge`; it does not download an artifact or gain add/delete.

## Test contracts inspected

New synthetic tests exercise actual controller composition with existing
synthetic SQL/manifest fixtures, not merely a caller `passed` flag: attach/arm/
first-add ordering, retained armed envelope without receipt, lost arm response,
already-armed parent, mismatched permit, pre-arm read/attachment failures,
foreign-original/wrong-phase rejection and explicit selector dispatch. Existing
Escrow tests independently cover zero-change and competing conditional arm;
existing retained-recovery tests cover same/current run, incomplete original,
wrong source/key/generation, corrupt chunks and late terminal chunk loss.

**Optional confidence improvements, not blockers:** add a composition test that
changes owner/global/provider/storage admission during `attach` and asserts no
arm/add/delete; add a controller-level zero-change SQL arm fixture asserting no
add/delete. Current source clearly repeats `_observe` and uses concrete arm's
strict zero-change contract, and lower-level coverage exists, so these are not
reported as demonstrated defects.

New functions and selector tests have English PEP 257 docstrings; selector
rationale and mutation/retention constraints are documented rather than merely
restating calls. The durable-seam document links the design/provider evidence
and preserves dormant/source-only/live-NO-GO distinctions. Its earlier
"future workflow" follow-up text is consistent with the selectors remaining
unwired. Hosted exact-source checks are still required before integration.
