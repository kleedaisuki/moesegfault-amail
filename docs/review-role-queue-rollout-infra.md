# Review: phased staging role Queue rollout infrastructure (2026-10-01)

## Scope and distinct decisions

Reviewed `a325059`, `351b2e0`, compatibility follow-up `e39ff58`, pre-mutation state correction `03cb16f`, and safe-marker caller correction `c4dd186`, against `docs/role-mail-monitoring.md`, the Queue privacy ADR, current CI/reusable canary workflows, role serving-capability audit and existing hosted SMTP acceptance caller.

- **GO for push to non-deploying hosted source CI and the separate read-only capture diagnostic.** No automatic push/PR role deployment is introduced; the role mutation job requires branch-local manual dispatch, exact target and explicit confirmation. This is source review, not a claim that hosted tests already passed.
- **GO for the live role rollout gate code, subject to successful hosted tests and all documented live prerequisites.** Both identified source defects are resolved; this is not authorization to skip any live prerequisite. successful immutable phase-one deployment, actual bounded retained-record canary, reviewed exact versions/Queue IDs, and effective capture-off remain operational prerequisites. No production cutover, public sending or role SMTP/Cron privacy acceptance follows from this review.

No local builds/tests, live requests, deployments, queue-body reads, secret reads, pushes or production edits were performed. `git diff --check` produced no whitespace errors. Test conclusions below derive from source inspection only.

## Resolved caller integration finding

### P2 — New safe deployment marker was incompatible with the existing hosted SMTP provenance reader (resolved in `c4dd186`)

Location: `infra/deploy/deploy_staging_role_monitor.py:63`; `workers/role-monitor/hosted_acceptance.py:34-38,187-200`.

The new deploy wrapper captures and suppresses Wrangler output, then emits only `staging_role_deployment=version_captured version=<uuid>`. The existing `logged_version()` caller recognizes only timestamped `Current Version ID: <uuid>`. A newly successful role rollout therefore supplies zero accepted version candidates and raises `deploy_log_version_ambiguous` before the subsequent real SMTP acceptance can run. Existing tests construct only legacy Wrangler lines, so they do not exercise the changed producer/consumer contract.

Impact: deterministic inability to use the new role deployment run for the required hosted SMTP acceptance. This fails closed rather than exposing mail, but blocks delivery acceptance after an otherwise successful role replacement. Confidence: high; directly traced producer and parser contracts.

Remedy: recognize the exact safe new marker inside the exact successful deploy step's time window; retain historical legacy compatibility deliberately if needed. Reject duplicates, mixed old/new marker ambiguity, malformed UUIDs and markers outside that step. Add synthetic caller fixtures for the actual wrapper output. `c4dd186` implements the exact safe marker parser with a globally unique marker requirement, rejection of malformed safe mentions and mixed legacy evidence, and the existing exact successful deploy-step timestamp window. The added caller fixture exercises actual marker acceptance plus duplicate, mixed, outside-window, unverified and invalid-UUID rejection. Legacy-only history remains supported. Source re-review resolves the deterministic incompatibility; no raw Wrangler output is restored. Hosted execution remains pending.

## Resolved finding

### P1 — D1 initial-state checks previously occurred only after mutation (resolved in `03cb16f`)

Before correction, `check_role_trace_rollout.verify('before')` checked the route, versions, topology and capture settings but not the role ledger or lease. `check_staging_db.py` checks schema ownership, not whether rows are pending or the lease is active. Thus a correctly migrated but nonempty role ledger or active lease could pass prechecks, allow migrations/Worker replacement, and fail only during the after-phase audit.

`03cb16f` adds `role.inspect_d1()` to before-mode, which is used both before migration and immediately before replacement. It checks exact isolated tables/indexes, zero arrivals and the initial expired singleton lease. A pristine schema is intentionally rejected by this replacement-only target, consistent with requiring an old serving-role version; bootstrap is separate, not a permissive fallback. New synthetic fixtures assert the check is invoked and failure aborts the bracket. This resolves the source failure path; hosted execution remains pending.

## Positive checks and limits

- `api-only` remains default and exact sole API producer; `api-role` is readback-only with exactly API and role. Duplicate/missing/foreign producers are rejected by count plus exact set checks. Sole sink consumer, bounded retries, one-day retention and unattached DLQ are preserved.
- Queue/DLQ identities are independently pinned, distinct and canonical, never selected only by name. API immutable serving bindings include the exact producer binding. Sink identity/capability checks remain isolated.
- Phase-one evidence requires distinct completed successful first-attempt branch-local same-source manual runs, exact API/sink jobs, an exact sink marker, and a separate actual bounded privacy marker. Preflight or generic green CI cannot substitute for retained-record privacy. Same-source contract is restrictive but intentional, not a correctness defect.
- All three serving deployment/version identities and Queue topology are bracketed. New role audit checks immutable bindings, effective Logs/traces/Issues-off, absent synthetic route, private HTTP surfaces and initial D1 state. The old role is version-pinned but not incorrectly required to already own the future Queue binding.
- `e39ff58` preserves the historical no-argument pre-Queue binding helper contract; queue-api remains explicit and requires a reviewed Queue ID. Historical callers do not silently adopt extra capabilities.
- Confidential destination/provider credentials are written to a restricted repository-local temporary file, captured provider output is not printed, and cleanup runs in `finally`. Deployment is not automatically retried. Successful captured version is a recovery pin, not an after-phase verdict.
- Failed/ambiguous transition requires read-only reconciliation, held sending and absent synthetic route. Provider settings/attachments are not atomic: external writers must remain frozen; read brackets cannot prove absence of transient changes between observations.
- Existing production direct forwards and public-send hold remain unchanged. Email/Cron whole-record canaries, lease/fault acceptance, external original/digest delivery and deliberate production rollback still need independent live evidence.
