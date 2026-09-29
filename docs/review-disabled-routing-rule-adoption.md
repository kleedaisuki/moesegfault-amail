# Review: disabled Email Routing rule adoption

Status: independent review of the uncommitted `platform.rs`, `lib.rs`, and hosted workerd fixture changes on 2026-09-29. This is a source/fixture assessment only; no provider call, local heavy test, or historical incident reproduction was performed. The controlling contract is [disabled-routing-rule-adoption.md](disabled-routing-rule-adoption.md).

## Blocking finding: permanent unresolved rows can starve address reconciliation

**Priority: P1; confidence: high.** `reconcile_addresses` selects only the first 30 rows ordered by state and original `created_at` (`crates/mail-worker/src/lib.rs`, query near line 297). This change deliberately keeps `provisioning` rows with only disabled/unknown exact rules in `provisioning` indefinitely. Those rows do not mutate `created_at` or acquire a retry deadline, so the same oldest 30 will be selected on every Cron. Once 30 such addresses accumulate (three accounts at the documented ten-address cap suffice), a newer `provisioning` or `deleting` row is never visited. A deleted address can then retain its provider route indefinitely; a newly created enabled route can remain invisible to its owner indefinitely. The fixture covers one aged stalled row but not a backlog exceeding the fixed page limit.

The old ten-minute transition to `pending` removed long-lived unresolved provisioning rows from this query, so this liveness failure is specifically amplified by the intended safety change. The same fixed-head problem can occur with flagged `active` rows whose saved ID is disabled, although the query sorts them after provisioning and deleting. Preserve the no-blind-POST invariant, but make the queue fair: persist a bounded `next_reconcile_at`/last-attempt cursor or rotate a stable page key, ensuring each unresolved row remains observable yet cannot monopolize the first page. A small hosted fixture with 30 stalled rows plus one `deleting` row should establish eventual delete; ideally test successive Cron invocations and a still-stalled row's continued journal presence. Merely raising `LIMIT 30` postpones rather than repairs the failure.

## Non-blocking observation: the promised anomaly is not emitted

**Priority: P2; confidence: high.** The decision says a disabled-only `provisioning` row should preserve its repair journal **and surface a bounded health anomaly**. In the new `enabled_id=None, ids.nonempty` branch, Cron simply continues; `scheduled` logs only a generic error when the entire reconciliation returns `Err`. Thus an intentionally paused or unexpectedly disabled route produces no operational signal despite remaining unresolved. Emit a low-cardinality state/count signal (not address or provider response text), preferably aggregated per scheduled invocation and rate-bounded. Do not expose mailbox identifiers in logs or telemetry.

## Confirmed properties and limits

- `OwnedRule.enabled: Option<bool>` does not default missing status to true. Only `Some(true)` can be selected for add/Cron activation. The old untyped `rules_for_address` API still returns all exact-owned IDs, so delete/retire can remove disabled rules.
- The existing exact name, literal recipient matcher, and ingress Worker action remain the ownership gates. The add request refuses disabled/unknown-only inventory before POST, and a 2xx create response lacking positive enabled status is handled as an uncertain provider result rather than acknowledged as a mailbox. This preserves current HTTP code vocabulary and avoids immediate duplicate POST.
- Flagged active reconciliation only prunes alternatives when the committed ID is positively listed enabled. This protects an ambiguous or deliberately disabled saved route from accidental destructive cleanup. However, an ordinary unflagged active row is not inventoried; the decision explicitly scopes out continuous detection of out-of-band disablement.
- The new fixture cases cover single disabled/unknown inventory, mixed inventory, disabled create acknowledgement, aged provisioning, flagged active drift, and deletion of a disabled rule. `git diff --check` and `node --check infra/tests/worker-boundary/address-add.test.mjs` passed; the actual workerd suite still needs GitHub-hosted CI per project policy.

No conclusion here attributes the historical staging HTTP 500 to disabled-rule handling.
