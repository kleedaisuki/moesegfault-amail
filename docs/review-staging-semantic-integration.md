# Review: hosted semantic E2E integration (340ba9a)

Scope: reviewed the commit diff, `infra/tests/staging_semantic_e2e.py`, the parent inbound harness, the manual GitHub workflow, and `docs/staging-e2e-plan.md` / `docs/staging-semantic-e2e.md`. No live mail, deployment, or heavy local test was run. This artifact assesses reachability and test semantics, not deployed behavior.

## Resolved finding — opt-in stage was unreachable from the intended hosted dispatch

**Original severity: P1 for semantic acceptance; confidence: high.** At `340ba9a`, `infra/tests/staging_hosted_e2e.py` defaulted `AMAIL_STAGING_SEMANTIC_E2E` to `0` and appended `--check-semantic` only for `1`, but `.github/workflows/ci.yml` declared no semantic input or environment mapping. Hence a manual hosted dispatch always ran the basic probe. This was a reachability defect, not evidence that the semantic assertions themselves were wrong.

**Correction rechecked in the shared tree (2026-09-29):** the pending `.github/workflows/ci.yml` edit adds a default-off boolean `semantic` input and maps it to `AMAIL_STAGING_SEMANTIC_E2E: ${{ inputs.semantic && '1' || '0' }}` only for the hosted E2E job. Commit `dbaca83` makes the final fixed success marker distinct for semantic versus basic and adds a static workflow wiring test. The documented manual command supplies `-f semantic=true`. These changes resolve the reachability and false-claim concern at the source level, provided the pending workflow edit is committed and deployed with them. They have **not** been live-dispatched, so semantic acceptance remains unverified.

## Other reviewed paths

The changed semantic call reuses the two existing SMTP deliveries after ZIP/literal-search checks and before `mark`/`delete`; it does not itself create another address, send mail, or mutate read state. Failures flow through the pre-existing `finally` cleanup. The retry guard matches only the allowlisted `503 semantic_index_incomplete` label and stops by a monotonic seven-minute deadline; other CLI/provider failures remain failures. Raw CLI output and stderr are captured, with only fixed labels emitted. The two-message check correctly limits its claim: it cannot establish independently complete 256-dimensional exact-cosine results or cursor pagination. I found no additional material defect in those changed paths. Existing test assumptions remain mock-only and are not a substitute for a hosted dispatch.
