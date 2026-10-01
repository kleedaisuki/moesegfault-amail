# Mail maintenance statement admission implementation

Date: 2026-10-01. Source-only candidate, based on accepted-projection candidate
`25acdf1`; **not hosted-validated, deployed, Paid-verified or release-approved**.

## First atomic slice: accounting only

The private `database::{Database,Statement}` adapter is the only MAIL_DB binding
owner in the Mail Worker. Foreground construction has no maintenance admission
state and forwards the existing prepare/bind/first/all/run/batch behavior. It does
not change API data, limits, error bodies, journal authority or provider sends.
Scheduled construction supplies one invocation-owned shared budget and a fixed
phase identity. Each of the established eight phases receives its ADR grant:
170/380/90/2/65/65/5/5. Their sum is 782; the remaining 18 control tokens are not
borrowable. Each `first/all/run` debits immediately before the binding operation;
`batch(N)` debits N atomically before submitting. Failure, rollback and no-op do
not refund. Prepare/bind/result inspection are not submissions. There is no raw
handle, Deref, exec, dump, session or statement-inner escape hatch.

Every Cron nested database call uses the phase adapter: route discovery/claims,
fresh desired-state read before provider DELETE, accepted projection/release and
terminal-resolution batches, embedding lease/retry/cooldown, storage ledger,
deleted/orphan GC, search-job cleanup and abuse retention. HTTP address deletion
passes its foreground adapter into the same provider verification helper.
The established phase order remains unchanged in this accounting commit. Before
accepted R2/parse work, a serial item checks that its maximum 74-statement
projection fits the remaining grant (current projector before due-rotation).
Denial retains accepted state/ZIP/journals and services subsequent phases.

## Deferral schema and rollout skew

`MaintenanceBudgetDeferred` / `ResourceDeferred` is one new closed diagnostic
pair, allowed only for standalone maintenance. It adds no fields, SQL, address,
owner, provider body or resource key. A caught denial emits at most one such event
for that phase, not a provider-failure event. Existing diagnostic pairs retain
their validation. The Rust trace schema and active Python safe sink-canary mirror
must be deployed/validated together.

An **old** Queue sink deserializes unknown enum variants as invalid; its handler
acknowledges and drops invalid records. Therefore an older sink would silently
lose this new deferral evidence, not automatically accept it. The CLI does not
consume server maintenance records, and its operation telemetry contract is
unchanged. No exhaustive Rust enum match requires a broad API revision. Rollout
must deploy/verify the updated private sink **before** enabling new producers;
an undeployed Queue/sink is not evidence of compatibility. No public wire-schema
version bump is implied by this private additive vocabulary.

## Evidence and remaining release blockers

Native tests exercise grant denial without mutation, per-statement batch counts,
phase independence, invocation/phase batch scope and exact deferral validation.
A provider-free built-workerd fixture seeds twenty accepted maximum-valid 4MB
text archives and verifies five complete projections / fifteen retained accepted
rows, 330 chunk writes, and later privacy-retention cleanup. SQL trigger counts
are **lower-bound** submission evidence; they do not emulate remote D1 quotas or
measure actual CPU/RSS. Tests run on GitHub-hosted runners only. Local evidence is
limited to rustfmt, Python AST parsing, Node syntax and `git diff --check`.

The first slice does **not** establish fair due selection, phase rotation,
finite per-phase/invocation admission, 10-second Cron provider timeouts, capped
incremental R2 reads, single final Queue flush, or maximum-valid archive CPU/RSS
completion. These remain separate source/evidence work. Workers Paid and effective
short-interval Cron CPU admission must be independently verified before deploy;
`usage_model=standard` and an omitted `cpu_ms` do not establish either. Published
D1 remains 1,000 Paid / 50 Free statements per invocation; <=800 is not Free-safe.

References: [ADR](mail-cron-budget-architecture-decision-2026-10-01.md),
[whole-Cron review](mail-cron-budget-review-2026-10-01.md),
[D1 limits](https://developers.cloudflare.com/d1/platform/limits/),
[D1 batch](https://developers.cloudflare.com/d1/worker-api/d1-database/),
[workers-rs D1 v0.8.3](https://github.com/cloudflare/workers-rs/blob/v0.8.3/worker/src/d1/mod.rs),
[Workers production practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/).
