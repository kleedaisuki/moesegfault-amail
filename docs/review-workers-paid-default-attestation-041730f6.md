# Independent review: staging Paid/default attestation

Date: 2026-10-01. Candidate: `041730f6c58cf6a32d10914256132d11594dc94d`. Base: `13b2c284bae38e196a0d63c721675d007a3f790a`.

## Verdict

**GO for this documentation-only evidence update. No substantive findings. NO-GO for treating this review or the attestation as deployment authorization or workload/privacy acceptance.**

## Evidence checked

- The candidate changes only `docs/workers-tier-cron-preflight-2026-10-01.md` (28 additions, 8 deletions). `git diff --check` passes. No source, configuration, workflow, schedule, or CPU override is changed.
- Root supplied first-hand transcript evidence that the user answered Paid for the current Workers plan, then default for the exact staging Worker's Settings > CPU Limits. The reviewer did not independently observe the Dashboard or Billing. The document correctly labels the evidence `operator_attestation`, not independent subscription API verification.
- Static inspection of base `crates/mail-worker/wrangler.toml` confirms production/default and staging triggers both use `*/5 * * * *` (lines 61 and 98), with no `cpu_ms` entry. Source absence is not represented as a runtime measurement; the operator's default report supplies the separate staging setting evidence. Production Dashboard settings remain explicitly unverified.
- The official [Workers CPU table](https://developers.cloudflare.com/workers/platform/limits/#cpu-time), retrieved on the review date, specifies 30 seconds CPU for Paid Cron intervals below one hour. Its [duration table](https://developers.cloudflare.com/workers/platform/limits/#duration) separately specifies 15 minutes wall time for Cron. Network/database waiting is excluded from Worker CPU time. The candidate correctly derives the five-minute contract as 30,000 ms CPU, not 15 minutes CPU or the general HTTP maximum.
- The official [D1 limits](https://developers.cloudflare.com/d1/platform/limits/) still lists 1,000 queries per Paid Worker invocation. The candidate retains this stricter documented policy without claiming observed enforcement or replacing it with the generic internal-subrequest allowance.
- Historical `standard` labels, missing API `limits.cpu_ms`, and subscription-read permission denial remain historical metadata. They are not retroactively promoted into subscription, billing-permission, or numeric CPU evidence. The document does not invent an observation timestamp.
- The new decision expressly preserves release/privacy holds and leaves actual CPU/memory fit, privacy/capture settings, Issues availability, deployment identity, and serving state unproven. It neither requests Billing permission nor authorizes a live probe, deployment, limit-exhaustion experiment, or plan/settings mutation.

## Scope and limits

This is an independent diff/source/document review with public primary-document retrieval. No local project tests, builds, compiler/toolchain invocation, authenticated provider calls, Actions dispatch, deployment, push, or merge was performed. Historical probe safety and returned values were assessed as documented claims, not re-executed. Attestation provenance depends on root-provided transcript evidence; no independent billing entitlement or Dashboard state verification is claimed. No academic claim or architectural change is introduced that would require a research comparison.
