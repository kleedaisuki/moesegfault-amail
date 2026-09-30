# Independent review: production graph predicates at d58921f

Date: 2026-10-01. Reviewed commit: `d58921fd557cd28dab69d7d8905df2984d75381a`.
Initial decision at d58921f: **CHANGES REQUIRED**. Narrow corrective review at `0191a32e706c7f6058bd15e3199a65de40858b06` + `0ad1d389491f4c4b58a69c43a4f2ee0b999768c0`: **GO for hosted source checks of these predicates; all three findings below resolved in examined corrective source.**
This is a source review, not a live deployment, privacy canary, or release acceptance.

## Scope and method

Inspected the four committed files, their imported Queue/capture/binding/routing/schema predicates, role migration and source, and the production graph decision document. Reviewed the exact committed files with `git show`; concurrent uncommitted orchestration is excluded. No local tests, remote provider operations, workflow dispatches, deployment or production edits were performed. The reasoning examples below are executable-path analysis, not test-run claims.

## Findings

### Resolved P1 — Bootstrap authorization does not prove held send policy

Location: `infra/deploy/prepare_production_graph.py:24-39`.

The maintenance branch calls `verify()`, which brackets `held_send()`. The bootstrap branch checks absence of API/role scripts, four forwards and pristine role storage, but never reads the Mail global policy or role release gate. Consequently valid confirmations plus absent API/role and valid role storage yield `production_graph_prepare=explicit_phase_verified` even if an existing Mail database has global `state='live'`, a set release gate, or an unavailable policy read. Worker absence is not policy absence: D1 can outlive a Worker or be initialized independently.

Impact: a caller relying on this explicit pre-mutation authorization can proceed to bootstrap mutations without establishing the documented held boundary. A later deployment/readback failure cannot retroactively establish the precondition. This code does not itself unhold or send; the concern is authorization, not a demonstrated live send.

Correction: distinguish pristine Mail storage (including successfully established absence of policy schema, if that state is intended) from existing migrated policy, and require an explicit held/unset state before accepting the latter. Require reviewed policy initialization and positive held readback before the new API can serve; recheck around the bootstrap transition. Do not swallow missing-table/failed-read errors as a pristine state or silently change an existing policy to make the predicate pass. Add negative hosted tests for live/set/missing/unreadable policy. If a separately reviewed orchestration owns a prerequisite instead, make that dependency explicit and test it before the authorization marker; it is not established by this commit.

Confidence: high for the missing read; downstream impact depends on the separately reviewed caller.

### Resolved P2 — Exact schema gate accepts materially different tables and indexes

Location: `infra/deploy/check_production_role_graph.py:55-68`; fixture `infra/tests/test_production_role_rollout.py:21-27`.

`module.valid_schema()` checks column-name sets and only the `INTEGER` primary keys of `arrival_seq` and `singleton`. The new index inventory checks only two index names. It does not verify the other column types, nullability/defaults, unique arrival ID, CHECK constraints, index columns/order, or absence of user triggers/views. The new positive fixture actually declares *all* arrival fields `INTEGER`, including the reviewed migration's TEXT `id`, `role`, and `forward_state`, and is expected to pass.

Trigger: preexisting/partially altered role storage retains names and the two primary keys but differs semantically (for example, removes UNIQUE(id), substitutes an index definition, or adds a trigger changing lease state). Empty rows and expired current lease still pass, and `CREATE ... IF NOT EXISTS` migrations do not repair these definitions.

Impact: storage reuse can be authorized without the documented exact isolated schema and its future-write invariants. Maintenance skips the row checks by design, making the schema predicate the sole storage contract in that phase. This is not a reason to erase or rewrite a live ledger.

Correction: verify the complete reviewed user schema against a migration-derived canonical manifest (table/column contracts, constraints and index definitions) and reject unexpected triggers/views/objects. Keep a narrow exact provider-bookkeeping allowlist rather than broad name-prefix exemptions. Update the positive fixture to the true migration schema and add hostile same-name schema/index/trigger fixtures in hosted checks.

Confidence: high; acceptance follows directly from the predicate and existing positive fixture.

### Resolved P2 — Role HTTP-route absence is checked in only one zone

Location: `infra/deploy/check_production_role_graph.py:139-151` (`role_capabilities`).

The route audit reads `/zones/{role.ZONE}/workers/routes` only. An account with another zone can attach `amail-role-monitor` there while the configured mail zone has no role HTTP route, workers.dev/previews are off and the filtered custom-domain array is empty. The predicate still succeeds.

Impact: the claimed private Email/Cron-only role surface is not established account-wide. This is a conditional configuration-drift path, not evidence an unexpected route currently exists. The source review does not imply that an Email-only module would successfully serve useful HTTP content; public invocation itself violates the chosen no-HTTP contract.

Correction: reuse the sink's complete bounded account-zone inventory and exact per-zone route audit, fail closed on unreadable/truncated inventories, and assert no route references the role script. Preserve unrelated users' routes; do not delete or take them over. Add a two-zone negative fixture and a failed/truncated inventory fixture.

Confidence: high for the omitted zone; occurrence is conditional on another account zone.

## Preserved strengths and non-findings

- Strict Queue readback requires the exact pinned Queue/DLQ, one bounded sink consumer, exact `api-only` or `api-role` producers, and no DLQ attachment. It does not consume or purge messages.
- Exact serving pins and single-100 deployment readback are retained. No permissive latest-version fallback or role-producer bootstrap adoption was introduced.
- Existing forwards and confidential destination remain in private memory and are fully compared around checks. Mixed-route predicates reject duplicate roles, altered literal matchers, action bundles and wrong Worker names. One-step comparisons preserve all untouched full rule shapes.
- Production bindings retain the fixed database/realm/official sender and exclude the staging fault secret. Missing current capture switches fail closed.
- Successful bounded script inventory is used for role absence; no failed GET is interpreted as absence. Cloudflare documents Scripts List as `SinglePage`, so inventing mandatory pagination there is not justified.
- Cloudflare documents the Domains `service` filter; that filter is not a finding.
- No reviewed code writes routing, role storage, settings or send policy. Imported Queue reconciliation is explicitly invoked in readback phase.
- A configuration/graph marker is not retained-record privacy, SMTP delivery or release acceptance. Such live evidence remains outside this review.

## External contract references

Retrieved official documentation during review:

- [List Worker Scripts (SinglePage)](https://developers.cloudflare.com/api/go/resources/workers/subresources/scripts/methods/list/).
- [List Worker Domains (service filter)](https://developers.cloudflare.com/api/resources/workers/subresources/domains/methods/list/).

These references support the API inventory/filter judgments, not a claim that current production state was inspected.

## Narrow corrective re-review

Reviewed exact diffs at `0191a32` and `0ad1d38` only, including the added fixtures. No local/hosted tests, live reads, deployment or production edits were performed by this reviewer. Concurrent orchestration and the separately reviewed production graph-writer lock are outside this verdict.

1. **Bootstrap hold resolved:** the bootstrap path now invokes the shared `held_send()` before provider script inventory and phase acceptance. It demands a persisted held policy and an unset role gate; missing policy/schema, unreadable state, or a set gate fail closed rather than become pristine bootstrap. The documentation makes the required migrated Mail storage explicit. Hosted fixtures cover early denial and the shared policy/gate predicate.
2. **Schema drift resolved:** role storage now checks full user TABLE/INDEX DDL against the reviewed migration, retaining literal tokens and index ordering, with a narrow exact provider-table exclusion. Unexpected views/triggers/user objects cannot fit the exact object set, and pristine bootstrap inspects the whole schema rather than tables alone. Positive fixtures now use actual migration DDL and correct TEXT field types; negative fixtures cover type, nullability, unique/CHECK constraints, index order, changed quoted literals and extra views/triggers. The conservative DDL equivalence may reject benign alternate spelling; that is a fail-closed limitation, not authorization of incompatible storage.
3. **Cross-zone route gap resolved:** role surface checks now reuse the sink's complete bounded account-zone inventory and inspect each zone's bounded, unique route array. A role attachment in a second zone is rejected. Custom domains use the existing reviewed bounded account-wide helper. The new two-zone fixture traces the second request and denial. Unreadable/truncated inventory behavior is inherited from the existing sink inventory contract rather than relaxed.

No additional substantive defect was found in this narrow correction review. This GO permits hosted validation of corrected source only: it does not accept an unreviewed caller, unlock production writers, authorize live rollout, prove current privacy/delivery, or release public sending.
