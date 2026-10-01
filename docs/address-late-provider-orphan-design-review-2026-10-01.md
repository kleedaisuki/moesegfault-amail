# Independent review: bounded late-provider orphan convergence

Date: 2026-10-01
Reviewed proposal: `9184bfd37d821de8b9bbd45ccd93b0034d70079b`, `docs/address-late-provider-orphan-convergence-2026-10-01.md`.
Reviewed code: the proposal worktree's `crates/mail-worker/src/lib.rs` and `platform.rs`, existing address-boundary fixture, and `docs/routing-reconcile-subrequest-budget.md`. The worktree reported a clean status before this artifact was written outside it.

## Decision

**GO for implementation and hosted adversarial verification. Not GO for deployment or any provider mutation.** No substantive architectural blocker was found in the proposal as written. Its positive provider discovery closes the specific permanently-retired late-POST orphan gap under its explicitly stated stable-provider, finite-inventory, exclusive-management, continued-scheduling, and eventual-success assumptions. It does not close every address allocation race, prove historical producer quiescence, or justify destroying retained recovery evidence.

This is a design review, not executable verification. No local project tests/builds, Cloudflare account/provider calls, push, or production changes were performed. Official public API documentation was retrieved.

## Why the mechanism works

The present selector in `lib.rs:298` selects provisioning/deleting states or `needs_reconcile=1`. The retired branch around lines 415-425 can clear that flag. A POST submitted in add around lines 1451-1490 may become visible after both retirement and the flag clear; its continuation may not run. No subsequent selected tombstone then discovers the route. The proposed audit runs even with zero selected rows, scans provider objects, and point-looks-up their permanent D1 addresses. Therefore a stable late exact route is rediscovered independently of its original creator and tombstone age. Rearming retired rows uses the existing conditional journal rather than reactivating them.

The work bound follows the admitted provider inventory, not the number of historical retired rows: at most ten pages and 500 returned objects/point keys, followed by a finite due-row phase and explicit external-call budget. This is the right representation change; an arbitrary tombstone TTL would not establish the same convergence property.

## Safety assessment

The proposal correctly refuses the current permissive matcher (`platform.rs:250-269`) as destructive authority: the existing implementation accepts any matching action and matcher, and existing DELETE/Cron append the saved ID even when list classification did not own it (`lib.rs:369-373`, `1563-1574`). The proposal explicitly requires tightening every destructive path reached by rearm, not merely the new discovery branch.

The specified destructive predicate must remain conjunctive: exact realm/name/address, supported explicit management source, exactly one literal-to matcher, exactly one single-valued pinned Worker action, current permanent row, state-aware authorization, and full current ID GET. Saved IDs are evidence to validate, not deletion capabilities. Active committed IDs remain protected; uncertain activation acknowledgments are not compensated by DELETE. Disabled/omitted-enabled routes may be retired when otherwise strictly owned, but cannot be adopted as deliverable.

Namespace exclusivity is a real operational precondition. The API says `source=api` also covers dashboard/API/Terraform, so an exact-looking foreign administrator copy cannot be distinguished cryptographically. The proposal correctly falls back to detect/alert without that precondition and acknowledges the unfenced GET-to-DELETE external edit interval. No D1 CAS can fence a foreign provider writer.

## Implementation acceptance obligations (not new design findings)

1. **Complete inventory type and terminal proof.** Verify metadata and actual termination; duplicates, impossible pagination, a failed later page, oversized response, or exceeded cap must never become absence. With metadata absent and ten full pages, do not construct CompleteInventory merely because the object cap was reached; either terminal metadata proves completion or this tick is incomplete. The proposal already requires this distinction.
2. **Budget and fair rotation are executable contracts.** The stated 20 address external calls include fresh provisioning absence checks, scoped GETs, and DELETEs, not just listing/deletion. Budget exhaustion must leave intent intact. A first problematic row must not abort all progress without a claimed retry slot. More than 30 due rows and more than five deletable rules need an eventual-turn assertion, not only a maximum-call assertion.
3. **Whole scheduled invocation, not isolated address arithmetic.** Current `scheduled` runs address reconciliation before outbound, semantic projection, storage, garbage collection, orphan cleanup, search cleanup, and abuse expiry. D1 batching still consumes the platform's query accounting; ten lookup batches plus discovery writes and 30 claims/state updates cannot be treated as free. Count D1 and external budgets in the complete hosted scheduled fixture and verify the actual plan before deployment. The note already lists this gate; 40 modeled external calls alone is not sufficient evidence.
4. **Stale shared snapshot settlement.** A shared inventory can omit a route created afterward. Clearing a retired marker is only a point-in-time projection because future audit remains independent; this is safe for the proposed liveness goal. In contrast provisioning-to-pending must retain the fresh complete recheck and existing state fence/age gate. Do not quietly reuse the initial inventory for that branch.
5. **Current-read and response uncertainty.** Parse supported GET/DELETE success envelopes where present; HTTP 200 alone must not turn `success=false`, malformed, mismatched ID, or unknown body into removal confirmation. A known-ID 404 can be treated only according to the explicitly tested missing-resource contract; 403/transport/decode uncertainty retains intent. `platform.rs:328-340` currently only checks DELETE HTTP status, so the implementation review must inspect this boundary rather than assuming the existing helper already meets the stricter note.
6. **No clearing on scope conflict.** A saved ID repurposed to a foreign rule must keep the anomaly/repair claim visible, even when there are zero strict-owned IDs in the inventory. Near-match conflicts need indexes broad enough to capture the same recipient with changed name/ingress/matchers/actions. Unknown-row candidates are never provider garbage.
7. **Old-version scope.** A late old POST is covered by exact legacy names/source/action shape. Old source temporarily serving concurrently still carries its own unsafe destructive helpers; version/provenance/writer-exclusion gates must therefore remain in force. The proposal does not promise that deploying the new reaper retroactively changes old invocations or produces a final campaign teardown oracle.

None of these is grounds to withhold implementation: each is already a material requirement or explicit limit of the proposal. They are grounds to withhold automatic cleanup deployment if its implementation or evidence omits them.

## External verification

Retrieved official documentation on 2026-10-01:

- [List rules](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/list/): zone/account list; enabled filter, page, per_page maximum 50; optional result pagination metadata; rule source `api` or `wrangler`. No exact-recipient query is documented. API source explicitly includes dashboard, generic API, Terraform.
- [Get rule](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/get/): ID-addressed read returns rule fields needed for current strict classification; fields including source are optional in the published schema, so omission must not be promoted to positive ownership proof.
- [Delete rule](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/delete/): ID-addressed DELETE; the inspected documented interface has no content If-Match precondition. This is documentation evidence, not proof that every undocumented capability is absent.

No documented atomic-list snapshot guarantee or globally unique immutable ID-lifetime guarantee was established by this review. The proposal appropriately does not claim either. Repeated stable inventories and exclusive ID management are necessary assumptions; they must remain visible in implementation/operations documentation.

## Confidence and limits

High confidence in the representation and the specific retired late-orphan liveness argument. Moderate confidence in feasibility of the bounded whole-Cron allocation until hosted measurements/counts establish it. No assurance of current live inventory strict-shape compatibility, deployed Worker provenance, Issues privacy containment, actual account-plan budgets, independent recovery ownership, or campaign terminal-evidence policy. All live gates remain unchanged.
