# Review: disabled Email Routing rule adoption

Status: independent review of the uncommitted `platform.rs`, `lib.rs`, migration `0008`, and hosted workerd fixture changes on 2026-09-29. The initial findings below were rechecked against the due-time scheduler revision. This is a source/fixture assessment only; no provider call, local heavy test, or historical incident reproduction was performed. The controlling contract is [disabled-routing-rule-adoption.md](disabled-routing-rule-adoption.md).

## Revised verdict

The previous P1 starvation and P2 anomaly findings are **addressed in the current draft**. No new release-blocking defect was found in the inspected diff. GitHub-hosted Rust/Wasm and Miniflare tests must still validate actual behavior; source review is not an integration pass. One documentation mismatch remains: the decision's scheduling paragraph still describes strict state priority and the resulting 31-failing-delete starvation, whereas the implementation and tests now use one due-time ordering across all states. Update that paragraph before treating the decision record as final.

## Blocking finding: permanent unresolved rows can starve address reconciliation

**Initial priority: P1; current status: addressed; confidence: high for the source-level argument.** The initial draft selected only the first 30 rows ordered by state and original `created_at` (`crates/mail-worker/src/lib.rs`). This change deliberately kept `provisioning` rows with only disabled/unknown exact rules in `provisioning` indefinitely. Those rows did not mutate `created_at` or acquire a retry deadline, so the same oldest 30 would be selected on every Cron. Once 30 such addresses accumulated (three accounts at the documented ten-address cap suffice), a newer `provisioning` or `deleting` row would never be visited.

The revised draft adds `next_reconcile_at` with a default-zero migration and backfills preexisting `deleting`/flagged `retired` rows to `-1`. The query uses one global due-time ordering, and each selected row is conditionally advanced five minutes **before** provider I/O. Thus a disabled-only row remains in the repair journal but stops pinning the next batch; failed provider requests also cannot pin its head indefinitely. A fresh delete receives urgent due `-1`. The pure SQLite regression checks that 30 failing deletes advance and expose the 31st delete plus a `provisioning` row next time; the hosted fixture checks that 30 stalled provisioning rows do not block one urgent disabled-route deletion. These are discriminating regressions for the original counterexample. They do not prove a strict latency bound under an indefinitely growing supply of new urgent deletes, which the product does not currently promise.

## Non-blocking observation: the promised anomaly is not emitted

**Initial priority: P2; current status: addressed in the draft.** The original draft silently continued for a disabled-only `provisioning` row. The revised Cron emits a fixed, low-cardinality warning once per selected batch when it sees a non-enabled owned rule, and a separate fixed warning when the 30-row batch is full. Neither embeds address, account, rule ID, or provider payload. A full batch is correctly a saturation hint, not proof that an unprocessed row exists. The warnings are bounded per invocation, although repeated Cron invocations can appropriately repeat an unresolved anomaly.

## Confirmed properties and limits

- `OwnedRule.enabled: Option<bool>` does not default missing status to true. Only `Some(true)` can be selected for add/Cron activation. The old untyped `rules_for_address` API still returns all exact-owned IDs, so delete/retire can remove disabled rules.
- The existing exact name, literal recipient matcher, and ingress Worker action remain the ownership gates. The add request refuses disabled/unknown-only inventory before POST, and a 2xx create response lacking positive enabled status is handled as an uncertain provider result rather than acknowledged as a mailbox. This preserves current HTTP code vocabulary and avoids immediate duplicate POST.
- Flagged active reconciliation only prunes alternatives when the committed ID is positively listed enabled. This protects an ambiguous or deliberately disabled saved route from accidental destructive cleanup. However, an ordinary unflagged active row is not inventoried; the decision explicitly scopes out continuous detection of out-of-band disablement.
- The new fixture cases cover single disabled/unknown inventory, mixed inventory, disabled create acknowledgement, aged provisioning, flagged active drift, and deletion of a disabled rule. `git diff --check` and `node --check infra/tests/worker-boundary/address-add.test.mjs` passed; the actual workerd suite still needs GitHub-hosted CI per project policy.
- The workerd fixture's replacement `outboundService` uses a one-use exact method-and-URL exchange table and throws on unmatched egress. This retains a closed network boundary without the unavailable `createFetchMock` API. Fixture responses use synthetic JSON only; no live provider mutation is part of this test.

No conclusion here attributes the historical staging HTTP 500 to disabled-rule handling.
