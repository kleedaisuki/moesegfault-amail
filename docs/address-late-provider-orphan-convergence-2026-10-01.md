# Late provider-create orphan: bounded provider-first convergence

Date: 2026-10-01. Status: architecture recommendation; **not implemented,
tested, deployed, or authorization for any live route operation**.

Inspected main: `89ce49f0166307ea6fcd7657459dd6b2e9726257`.
The corresponding relevant source in feature `add03b69f3c30ba6b9a39ac4658e3cf4358d7126`
is identical. Serving staging version `c3f6401a-1e84-4f51-91df-ae77d90683e9`
must be mapped separately; source inspection does not establish its provenance.
This note extends the restricted-retirement exception contract in
`.temp/quota-retirement-exception/docs/staging-quota-restricted-retirement-contract-2026-10-01.md`.
Use that contract's confidentiality, writer-exclusion, and retained-escrow rules;
do not relax existing `hosted.recover` into a provider-delete capability.

## Decision in one paragraph

**Reconcile the finite provider objects, not the indefinitely accumulating
address tombstones.** On every address-maintenance tick, including ticks with
zero due D1 rows, obtain one complete, explicitly bounded zone rule inventory.
For strict managed-route candidates, fetch the corresponding permanent address
rows by primary key. A candidate for a confirmed retired row rearms the existing
repair journal; state-aware cleanup deletes only strictly validated owned IDs.
Share the same inventory with the ordinary due-row reconciler rather than
listing the whole zone separately for each row. Post-provider-I/O owner-scoped
rearm improves latency but is **not** the correctness mechanism: the invocation
can die before it runs. No public API or D1 schema change is necessary.

This makes the reported late-orphan case ordinary desired-state drift. It does
not prove that all earlier creates have finished, provide exactly-once provider
operations, or make a finite quiet observation into proof of future absence.

## First layer: data and invariants

The permanent `addresses.address` primary key owns one lifetime with immutable
issuer/subject. Normal code never removes/reassigns a retired name. D1 state is
the desired routing state; provider rules are the actual external state.
`needs_reconcile` and `next_reconcile_at` are scheduling hints, not provider
fences or completion receipts. Retired rows free account slots but keep names
reserved. The inbound handler only assigns a mailbox owner for `state='active'`
(`lib.rs`, around line 2463); an orphan route does not change that ownership
check, although it still consumes provider capacity and invokes ingress.

Safety invariants:

1. A retired address never becomes active or gets a new owner through repair.
2. Cleanup never deletes an active row's committed route merely because a
   previous D1 write/read acknowledgment was uncertain.
3. Each DELETE ID is validated as one single-purpose managed route for this
   exact permanent address and ingress; an arbitrary saved ID is not authority.
4. An absent/foreign address row, malformed route, or ambiguous ownership is
   a retained anomaly, not permission to delete.
5. Partial/inconsistent inventory is never interpreted as route absence or
   grounds to clear a repair marker.

Liveness invariant, with explicit assumptions:

> If a permanently retired address has a managed provider route; creates/edits
> eventually stop; repeated bounded complete inventories eventually observe
> stable rules; D1 and provider calls eventually succeed; and the scheduled
> repair budget is fair and continues running, that route is eventually removed,
> even if its creator never executes another instruction.

This is eventual convergence, not a five-minute/24-hour SLA. Scheduler outages,
rate limits, permanent permission failures, ownership conflicts, or inventory
above the admitted bound prevent the liveness claim and require alerting.

## Second layer: remove the late-effect special case

Current source permits the following timeline:

| Time | D1 / invocation | Provider |
| --- | --- | --- |
| T0 | ADD claims `provisioning`; sends POST | POST is in flight |
| T1 | DELETE changes the same lifetime to `deleting` | No visible rule |
| T2 | Cron sees no rule; sets `retired`, clears saved ID, sets repair=1 | No visible rule |
| T3 | Next Cron sees no rule; sets repair=0 | No visible rule |
| T4 | Creator is canceled, or activation CAS cannot change retired | Delayed POST creates a rule |
| T5 | No due row; current Cron never selects this tombstone | Orphan persists |

Relevant code: `ADDRESS_RECONCILE_SQL`, `reconcile_addresses` lines 298-428;
`add_address` lines 1403-1530; `delete_address` lines 1554-1582; and
`platform.rs::rules_for_address_typed/create_rule/delete_rule`.

The current create-error flagger only updates active rows. The post-create
readback classifies `deleting/retired`, but does not rearm a clean retired row.
Even correcting both cannot repair a canceled continuation. Keeping tombstones
selected for seven minutes, ten minutes, or an arbitrary TTL merely moves T4
after that deadline: the inspected provider API does not document a maximum
side-effect delay or a completion-status lookup for an unknown create.

Under the proposal, the next complete provider inventory after T4 finds the
actual route, point-reads the retired lifetime, and schedules ordinary removal.
The age of the tombstone is irrelevant. A late route after marker clearing is
rediscovered on a subsequent tick; marker races are no longer permanent leaks.

## Third layer: small interfaces and bounded work

Use three internal responsibilities rather than a generic workflow engine:

```text
list_rule_inventory(env, budget) -> CompleteInventory | Incomplete/Failure
classify_rule(inventory, address, ingress) -> StrictOwned | Foreign/Conflict
reconcile_addresses(env, inventory, budget) -> durable scheduled progress
```

`CompleteInventory` must be a distinct internal type which cannot be constructed
from a partial page. It contains raw typed fields only in ephemeral memory,
indexes by ID and recipient/name conflicts, and preserves provider order. Never
log provider payloads, addresses, subjects, rule IDs, tokens, or D1 owner values.
Expose only fixed codes, counts, and approved opaque evidence hashes.

One representative tick:

1. Acquire the complete zone inventory with a hard page/object/response-size
   bound. Launch sizing can reuse the existing budget design's ten pages at
   50/page (500 rules), covering its modeled roughly 404-rule topology. This is
   an operational admission cap, **not** Cloudflare's universal zone limit.
   Validate success, shape, unique IDs, coherent pagination, and actual terminal
   page. Do not accept a short intermediate page if explicit metadata says more
   pages remain. Fail closed above the cap or on malformed/later-page errors;
   there is no cleanup or absence inference from the prefix. No enabled filter:
   disabled rules still consume resources and need cleanup.
2. Extract candidates restricted to this Worker `MAIL_DOMAIN`, exact name
   `amail {address}`, and pinned ingress. Include near-matches in the conflict
   index, not the deletion set. This must never sweep another mail realm, apex
   operator rules, or arbitrary Worker-targeted rules in the shared zone.
3. Query corresponding address rows through bounded `address IN (...)` primary
   key batches, e.g. at most 50 bindings per batch and ten batches. Return only
   fields needed for state and identity checks. This is at most 500 point keys,
   not `SELECT all retired rows`. Unknown rows are anomalies, not route garbage.
4. For each retired candidate with strict scope and no conflicts, conditionally
   set `needs_reconcile=1,next_reconcile_at=-1` only if it is currently retired
   **and marker=0**. Batch these conditional writes. Do not repeatedly overwrite
   due times of already-flagged rows: that could undermine existing fairness.
   Do not alter `cf_rule_id`, owner, name, slot, birth, or state. Provider inventory
   is discovery; it does not issue direct orphan DELETEs.
5. Select/claim the existing bounded due rows in due-time order, as today. Use
   the already obtained inventory for their route lookup. Before each destructive
   step validate the target ID's current full rule scope (bounded ID GET) and
   current allowed D1 state. Keep active committed-route preservation, enabled
   activation requirements, conditional state writes, and rotation on failure.
   Do **not** enlarge the absence-based `provisioning -> pending` race by using
   an early shared snapshot as new evidence that a creation lease expired. Keep
   that branch on a fresh complete recheck within the address call budget;
   when the budget cannot pay for it, leave provisioning and rotate for another
   tick. A fresh recheck preserves the existing observation boundary, not a proof
   an unknown in-flight POST cannot commit afterward. Improving creation-lease
   fencing is a distinct state-machine task, not silently bundled into batching.
6. Deletion budget exhaustion, strict-scope conflict, or an unknown response
   leaves repair intent intact and rescheduled fairly. Never retire/clear marker
   merely because the current tick did not have enough budget to remove all
   confirmed IDs. Clearing a retired marker is allowed only after this tick's
   confirmed target removals or complete absence. That is a point-in-time
   projection; ongoing provider-first discovery remains active afterward.

The permanent audit **must not** be skipped when due rows are empty. This changes
step 1 of `docs/routing-reconcile-subrequest-budget.md`, whose no-due early exit
would retain this bug. Share inventory to avoid doubling zone-list work. At an
empty zone this costs one GET per maintained tick, not one GET per tombstone.

Bound example: ten list GETs plus five scoped ID GETs plus five DELETEs = at most
20 external calls for address work. With today's 20 embedding calls that is 40
external calls, excluding redirects and any future added egress. This is a static
model, **not** an account-plan or whole-Cron limit guarantee. Existing combined
Cron has independently documented D1-budget risks; add a counted shared budget,
verify its actual plan, and test the full scheduled invocation. If Free cannot
admit all phases, use a separately bounded address invocation/phase allocation;
do not deploy a reaper which starves later maintenance by exhausting limits.
Choose the bounded deletion policy for request-path DELETE too: leave remaining
work in deleting, return existing 202, and let Cron continue. Normal 202 already
means accepted retirement intent rather than instantaneous route absence.
Fresh absence rechecks draw from the **same** 20-call address budget, reducing
available deletes; they are not added on top of the stated maximum. If a recheck
may require ten pages and the remaining budget is smaller, defer it before I/O.

Optional latency-only helper after **every** completed provider-create outcome:

```sql
UPDATE addresses
SET needs_reconcile=1,
    next_reconcile_at=CASE WHEN needs_reconcile=0 THEN -1
                           ELSE next_reconcile_at END
WHERE address=?1 AND owner_iss=?2 AND owner_sub=?3;
```

Use it only after provider I/O was potentially submitted, preserve `MAX`-style
intent semantics, and do not make response success contingent on a best-effort
helper. It also allows flagged pending to restore provisioning through the
existing state-aware branch, rather than posting again. It must not directly
compensate a route or change a retired state. If D1 fails or the isolate dies,
periodic provider discovery handles retired remnants. This proposal does **not**
claim to solve the independent lost-marker/late-route-on-pending issue completely;
extend positive provider discovery to pending/provisioning/active drift only as
a separately tested scope if that becomes the implementation's goal.

## Fourth layer: destructive ownership, not an `any` matcher

The current selector accepts any matching action and any matching recipient,
and current delete/Cron append a saved ID even if inventory did not match it.
Those are insufficient predicates for a new automated orphan reaper. Tighten
**every destructive path that the new rearm invokes**, including normal DELETE
and active duplicate pruning, before enabling automatic discovery.

Strict target shape:

- Confirmed valid ID; exact expected name; explicit supported `source=api`.
- Exactly one matcher: literal `to` for this exact normalized address.
- Exactly one action: Worker with exactly one value, the pinned ingress.
- Exact realm and an existing permanent row; retired/deleting states license
  desired absence, while active only licenses removal of noncommitted duplicates.
- Enabled=false/unknown does not make a strictly owned rule foreign or protect
  it from retirement; enabled=true remains necessary for adoption/delivery.

`source=api` is **not** creator provenance: Cloudflare explicitly includes
dashboard, generic API, and Terraform in it. The safe automatic policy additionally
requires an operational contract: `amail {address}` for permanently allocated
names in this realm is exclusively managed by Mail, and other writers do not edit
those managed IDs. Reserved operator names remain outside candidate allocation.
An identical copy by an account administrator is indistinguishable from a late
Mail-created duplicate using the current API/schema; do not pretend names or
source labels cryptographically solve this. Without namespace exclusivity, the
automatic branch is **detect-and-rearm/alert only**, requiring authenticated
baseline/manifest review before removal of unsaved IDs.

Before issuing any DELETE for a saved ID, validate it through the current
inventory and current ID GET. If the ID now refers to another address, name,
ingress, action set, or management source, preserve it and emit a fixed conflict
code. Do not append it to a delete list merely because D1 stores it. If it is
absent from complete inventory/confirmed missing, absence may contribute to
settlement, but does not authorize deleting an unrelated rule ID.

A pre-delete GET narrows but does not eliminate a concurrent provider-edit race:
the documented DELETE is ID-addressed and advertises no content If-Match/fence.
Under authorized exclusive management, normal Mail actors only create/delete
these exact IDs and never repurpose them, making that race benign. If a foreign
writer can repurpose them concurrently, do not assert safety; preserve a conflict
and require operational exclusion. Adding D1 CAS or a random name suffix would
not fence that provider writer. Assume provider IDs identify immutable lifetimes;
this needs confirmation before treating missing-ID retry as universally safe.

## Alternatives and why not

| Alternative | Failure/cost | Decision |
| --- | --- | --- |
| Recheck after successful POST; rearm deleting/retired | Creator can die before rearm; errors may still commit | Useful latency improvement only |
| Already-retired public DELETE rearms marker | Requires caller to know/retry; no independent discovery | Optional future semantics, not this fix |
| Watch tombstones for N minutes | No documented provider latency bound; delays can exceed N | Reject as sole correctness mechanism |
| Keep every retired row flagged forever | Lifetime-growing SQL/provider scans and starvation | Reject |
| Epoch/fencing counter on D1 marker | Prevents a lost flag but cannot cancel an external POST | Unnecessary for recurring retired discovery |
| Queue/DO/transactional outbox for all allocation | Bigger migration; downstream create still lacks documented idempotency | Not required for this bug |
| Delete every rule naming the ingress | Breaks other realms/operators and unknown foreign rules | Reject |
| Inventory-first periodic drift discovery | Work bounded by admitted actual rules, not historical rows | Choose, with strict scope and budget |

## Compatibility and executable rollout

No new endpoint, CLI flags, DELETE fields, OAuth scopes, address states, or DB
columns. Preserve body `deny_unknown_fields`, existing 200/201/202/409/503
vocabulary, immutable retired-name behavior, account ten-slot rules, message/R2
ownership, and existing active idempotent add behavior. Strict destructive scope
holds suspicious legacy rules instead of deleting them; that is intentional
safety containment, and needs operator-visible fixed diagnostics rather than a
claim all historical records silently converge.

1. Implement typed complete inventory/strict classification and hosted fixtures
   first. Do not change create/adoption behavior beyond demonstrated contracts.
2. Replace per-row zone lists with shared inventory and explicit budgets; retain
   scheduling fairness and state-conditional transitions. Verify disabled/missing
   enabled semantics and active saved-ID preservation with existing suite.
3. Add provider-positive retired-row discovery/rearm. No historical backfill is
   needed: rules created by old versions, including a late old POST after rollout,
   will be found even if its row marker is already zero. New code handles legacy
   exact rule names without a token/name migration.
4. Add post-provider helper only if its bounded latency benefit justifies it.
5. Independently review; run exact-head Rust/Wasm plus expanded Miniflare tests
   in GitHub Actions, including the full scheduled budget. No local tests/builds.
6. Deploy to held staging only after current privacy/binding/version gates are
   met. Verify serving provenance, zero public-send cutover, and bounded synthetic
   deployed drift repair without printing private inventory. A previous serving
   version remaining in flight is specifically covered by new provider discovery.
7. Rollback needs no schema rollback; it restores the old liveness gap. Preserve
   any unresolved repair/ciphertext evidence and suspend quota/new address
   campaigns if the reaper is rolled back or its health cannot be established.

The rollout is compatible with old HTTP callers and old pending provider creates.
It cannot restore knowledge of historical request completion. It is not permission
to execute a ten-address campaign or finalize retained escrow merely because a
new reconciler has been deployed. A terminal campaign oracle still needs its
separately reviewed producer-quiescence or explicit enduring recovery policy;
two quiet inventories remain only point-in-time evidence.

## Hosted adversarial tests: required, not performed here

The existing `infra/tests/worker-boundary/address-add.test.mjs` executes actual
Rust/Wasm through workerd/Miniflare, real conditional D1 statements, and fake
provider responses. It covers uncertain activation, duplicate preservation,
disabled/unknown enabled state, and scheduler fairness. Its current fixed
responses do not orchestrate the killed late-POST timeline; use controlled
deferred promises/barriers and a persistent synthetic provider rule store.
All fixture egress stays denied unless matched. Retain DB/provider evidence in
the synthetic fixture, not logs from real services.

| Adversarial fixture | Required outcome |
| --- | --- |
| POST side effect only after two retire/clear Cron ticks; abandon creator | Next independent tick discovers/removes route despite repair=0 and no due rows; no second POST |
| Provider success response before retire, activation response lost | Preserve confirmed active route; never cleanup from uncertain response alone |
| POST response malformed/request fails but store commits afterward | Same retired discovery; no blind create retry |
| Route appears after complete inventory and marker clears | Next tick rediscovers; no permanent lost flag |
| More than 30 due rows and >5 removable rules | Bounded calls, fair rotation, remaining markers persist; every eligible route eventually gets a turn |
| Thousands of historical tombstones with zero provider rules | One bounded inventory, no all-tombstone SQL/provider loop |
| 50/51/404/500/501 rules; later-page 403/malformed/duplicate IDs | Correct page counts; incomplete/over-budget scan causes no DELETE or absence-based clearing |
| Retired exact route disabled or enabled omitted | Removal permitted only if all ownership/scope fields confirmed; no activation |
| Same name with additional matcher/action or other ingress | Conflict; no deletion of any rule for that conflicting scope |
| Saved ID repurposed to foreign address or other realm | No DELETE of saved ID, no marker-cleared cleanup claim |
| Exact-looking route but no address row / source unknown/wrangler | Detection-only anomaly; no deletion |
| Both staging and production ingress/rules, apex operators | Only this realm's permanently owned rows eligible; all other IDs unchanged |
| Pre-delete GET scope changes, 404, response lost, D1 unavailable | Fail closed on change/unverified read; preserve intent; later discovery converges on confirmed scope |
| Old version's in-flight POST commits after new version serves | New provider-first path cleans legacy exact shape without new schema/token |
| Active duplicate with another actor retiring during pruning | Never remove the committed active ID based only on marker; all writes stay state-conditional |
| Permanent provider failure or unknown management exclusivity | Fixed degraded/conflict diagnostic, retained journal and escrow, no claimed SLA/pass |

## External grounding and consequential unknowns

Cloudflare's documented [create](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/create/)
is POST with a returned rule ID; the documented fields do not advertise a create
idempotency key or a bound on delayed side effects. Its
[list](https://developers.cloudflare.com/api/typescript/resources/email_routing/subresources/rules/methods/list/)
is paginated and allows enabled/page/per_page filters, with per_page at most 50,
not an exact-address filter. Its
[delete](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/delete/)
is ID-addressed, with no advertised If-Match content predicate. These are
documentation observations, not proof of undocumented provider behavior.

Production grounding: [Kubernetes controllers](https://kubernetes.io/docs/concepts/architecture/controller/)
continuously compare external actual state to persistent desired state rather
than trusting that a prior operation's continuation always runs. AWS's
[idempotent API guidance](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/)
distinguishes retries/late requests and stable intent. Our inference is to make
retired drift continuously discoverable and avoid claiming a timeout undid POST;
no Kubernetes deployment or general controller platform is needed here.

Research grounding: [Anvil, OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/sun-xudong)
formalizes eventually stable reconciliation and verifies Rust Kubernetes
controllers. Its useful implication here is separate safety from liveness and
state the eventual provider/scheduler assumptions explicitly. It does not verify
our code or Cloudflare contract; importing a verifier is not a launch prerequisite.
An inexpensive next step is the hosted barrier-controlled timeline tests above,
not a speculative proof of an unknown external API's completion bound.

Before adoption resolve: (1) management namespace exclusivity and legacy strict
shape inventory, (2) serving source/bindings/privacy gate, (3) actual plan and
whole-Cron D1/external-call budget, (4) persistent audit health and recovery owner,
and (5) campaign terminal-evidence policy for unknown historical creates. Resolve
these through source/hosted tests and separately approved bounded evidence; this
design performs **no live provider calls** and issues no new probing permission.
