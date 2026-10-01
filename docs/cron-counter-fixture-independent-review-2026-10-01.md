# Independent review: combined Cron synthetic exchange fixture

Date: 2026-10-01. Candidate: `b1ca139f4b8541e56ad965367e6b5e9131a36b67` (rebased equivalent of initially inspected `8b361a5c8aae4fd68ee5b2bdf0dd6e64b3e82326`; exact two-file diff empty). Comparison main: `c6f93bf4cadbb58c69027ebc6208d594ca713c80`. Scope: source review and syntax only; no local project tests/builds, provider requests, deployments, or pushes.

## Verdict

**GO for GitHub-hosted fixture execution, not a deployed resource-limit or release approval.** No consequential blocking fixture defect found. Candidate Worker Rust source is byte-identical to the compared main Worker source (`git diff HEAD c6f93bf -- crates/mail-worker` empty). The new fixture has not been executed in this review.

## Independent expected behavior and evidence

The actual `scheduled()` contract runs address reconciliation, accepted outbound recovery, semantic retry, storage reconciliation, deleted-content collection, orphan collection, search-job cleanup, then abuse retention. Errors are diagnosed and later phases are attempted. Therefore this check should demonstrate twenty admitted route exchanges and twenty admitted semantic document exchanges, followed by the search-job transition; it must not infer all maintenance phases succeeded or actual remote quotas were enforced.

| Claim | Source evidence / assessment |
| --- | --- |
| Synthetic topology respects per-domain cardinality | 200 current Mail-domain rules plus 150 on each of two foreign synthetic domains = 500 zone inventory entries and ten pages at 50/page. No single synthetic domain exceeds 200. The `.example.invalid` domains are symbolic fixture values, not actual provisioned Cloudflare domains: this is a cardinality model, not a proof of real zone topology or available domain slots. |
| Full routing allowance is consumed | `withProvider` paginates the persistent Map; actual reconciliation discovers 200 strict retired candidates, claims 30, and the shared twenty-call budget allows ten inventory GETs and five scoped GET/DELETE pairs. Destructive calls independently require the immediately preceding scoped GET for the identical provider ID. Five removals leave 495 rules. Lexicographic ID order need not be asserted for these count invariants. |
| Exactly twenty documents are embedded | Migration 0007 creates pending work and owner schedule entries through message INSERT triggers. Five distinct owners with four messages each match SQL `owner_rank<=4` and global `LIMIT 20`. Callback accepts only the exact OpenRouter POST URL, checks dimensions/input type/synthetic prefix, and returns a valid nonzero 256-element vector. Twenty callback invocations plus twenty committed message vectors establishes processing of the complete seeded set; vector commit removes work through a trigger. No fetch or real provider service is invoked by the stub. |
| Forty external exchanges | `calls` appends once for every outboundService invocation, including any unmatched request before rejection. This scheduled-only fixture performs no access-token API request, so OIDC GETs are not hidden in the count. Stub responses are direct HTTP 200 responses; the forty assertion explicitly says **nonredirecting**. It does not prove a redirect bound for production embeddings, which still use default follow behavior. Any unmatched redirect hop to a different endpoint is rejected, not forwarded to real networking. |
| Later search maintenance runs | Job begins `running` with expiry one second in the past but far inside the 24-hour expired-tombstone retention. Actual `search_jobs::cleanup` changes it to `expired`; subsequent delete should not remove it. Final state lookup therefore distinguishes later cleanup execution from the initial fixture state and proves continuation after address repair's intentionally incomplete bounded batch. |
| Privacy / credentials | All subjects, body text, owner IDs, zone ID, token/key, routing worker name and addresses are synthetic. The egress implementation never calls upstream fetch. Call recording excludes headers and bodies. Assertion failures can expose only synthetic input. No confidential destination or credential is added. |
| Discovery and runtime | `package.json` explicitly executes `address-add.test.mjs`; CI runs `pnpm test` after the production Rust/Wasm bundle. Node tests in this file are not configured concurrent. The new test has a 60-second timeout and the established fixture always attempts bounded disposal (10 seconds). System time is used only for a comfortably expired-but-retained job and due work; no sleeps or timing-sensitive race were added. Hosted execution remains necessary to establish its actual duration. |

## Important scope limits retained by the candidate

- No `MAIL_BODIES` or diagnostic Queue binding is installed in this fixture. Deleted/orphan collection obtains the absent R2 binding even for an empty selected set and can return a caught error. The subsequent search assertion is still meaningful because the scheduled handler continues; it is **not** evidence that every intermediate phase succeeds, or that R2/Queue resource consumption was exercised.
- Seeded messages are direct D1 fixtures and intentionally bypass actual SMTP, ZIP storage, alias ownership validation, and delivery. Messages use five indexing-owner identities; address rows use the existing helper's independent synthetic lifetime owners. This does not weaken the scheduler-count expectation, but it is not a representative full receiving workflow.
- Callback checks do not separately assert model/provider privacy flags. Those are existing production payload contracts outside this focused counter regression; there is no regression introduced in production code by this candidate.
- D1 statement figures in the budget document are explicitly **source-derived binding-call counts**, not observed quota errors. Trigger SQL work is not counted as a separate application binding call. The fixture does not instrument D1, emulate account-tier limits, measure CPU/RSS, or prove elapsed-time fairness.
- Static maximum accepted text recovery arithmetic is consistent with source: 4,000,000 text bytes -> 67 60,000-byte chunks -> 66 additional chunk writes; four other writes per recovered item plus two phase setup calls -> 1,402 for twenty items. The estimate excludes manifest bytes, while compressed/expanded archive bounds admit a highly compressible synthetic 4,000,000-byte text body. Native explicit body cap is separately documented, not incorrectly substituted for server admission.
- The 75 address-statement example includes both successful and budget-deferred per-row writes: two selects +30 claims +8 discovery statements +30 final/defer updates +5 current-state reads. It is not an actually measured trace.

## Performed checks and reproducibility

Executed only:

```powershell
git diff HEAD c6f93bf -- crates/mail-worker
node --check infra/tests/worker-boundary/address-add.test.mjs
git diff --check
```

Observed: no Worker-source difference; Node syntax check exit 0; whitespace check exit 0. The rest of this review inspected fixture helpers, production scheduled/reindex/cleanup/routing/recovery code, migration triggers and CI discovery. No provider contact or project test/build was performed.

Next authorized validation is the existing GitHub-hosted Rust Worker job at an exact candidate SHA, retaining both the focused fixture and full workerd coverage. A hosted pass would establish this synthetic integration behavior only. Remote quota enforcement and actual tier/resource behavior remain independent checks.
