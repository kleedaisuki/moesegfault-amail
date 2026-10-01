# Review: quota public zone coordinate hotfix

Date: 2026-10-01
Candidate: `56c999eec4db9aefd25ccb082615a950495797e7`
Baseline: `d3e2f7d`
Decision: **GO for hosted source checks only. No live admission.**

## Findings

No substantive defect found in the bounded change. The workflow diff replaces exactly three `secrets.CLOUDFLARE_ZONE_ID` references, in preparation, campaign, and recovery, with `6edff81c6ed02f412e70868076411a5e`. This matches existing baseline literals in `.github/workflows/ci.yml` and `.github/workflows/staging-worker-r2-capability.yml`; it does not introduce a new provider target. No conditions, confirmations, mode selectors, permissions, key references, dispatch triggers, or commands change.

The identifier already exists in tracked source and is a zone coordinate rather than an authentication capability. The diff contains no credential, private destination, native account identifier, or mail contents. Account/API/routing/native credentials and the versioned recovery key remain secret references.

`infra/tests/staging_ten_address_acceptance.py:77-98` rejects missing capabilities before source/provider operations: all required values must be nonempty, the recovery key is decoded/validated, and key generation is checked. The three `AMAIL_TEN_ADDRESS_RECOVERY_KEY_V1` references remain unchanged. Therefore the reported absent recovery key continues to prevent preparation/campaign/recovery; this patch cannot establish key availability. Its absence was reported by the parent secret-name audit, not independently queried by this review.

Global held-state enforcement remains unchanged in the coordinator (`Readback`/gate at approximately line 293). Manual-only, first-attempt, exact branch, staging environment, source-run, actor, and privacy requirements are not relaxed. With all prerequisites satisfied, the intended runtime effect is only to supply the established zone coordinate that was previously missing via an absent Secret. No deployment or automatic live execution is added.

## Test assessment

The new hosted contract test checks exactly three quota literals, removal of the absent-secret dependency, cross-workflow coordinate agreement, and preservation of all three versioned key references. It is meaningful for this source-wiring regression: a stale/mismatched coordinate, incomplete replacement, or key-reference loss fails it. It is deliberately a source contract, not proof of provider permissions, zone/domain ownership, recovery-key availability, effective privacy, or real quota behavior. Existing composition/crypto and workflow guards remain necessary; successful hosted source checks do not authorize a live dispatch.

## Scope and limits

Inspected candidate/baseline complete diff, workflow surroundings, existing zone literals, coordinator capability admission, and new/existing workflow tests. `git diff --check` passed. No local project tests/builds, provider requests, secret enumeration, push, deployment, or live workflow dispatch were performed. Hosted results were not available/claimed by this review.
