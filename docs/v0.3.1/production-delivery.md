# v0.3.1 privacy cutover and production delivery

The owner authorized production publication **after successful staging acceptance**,
then upgrade of every local CLI entrypoint and the global amail Skill. This note
records the ordered cutover and eventual delivery coordinates; authorization and
prepared source do not establish deployment or publication success.

## Why this is not an ordinary model upgrade

v0.3.0 automatically indexed eligible mail through Qwen. v0.3.1 introduces
account-wide default-off semantic consent and Voyage 4 through OpenRouter.
Migration `0018_semantic_consent.sql` keeps existing document embeddings, defaults
all accounts off, invalidates prior semantic search generations and blocks old
Workers from acquiring fresh indexing leases. Applying a new model variable alone
would neither revoke existing egress nor produce compatible vectors.

The new runtime admits document/query provider requests only for an enabled
account generation; publication also requires that exact generation and claim.
Only `user` can enable or disable the switch, with normal browser approval or the
human's existing explicit YOLO preference. Each off-to-on transition re-indexes
all eligible retained mail. Disable retains embeddings but revokes new work;
already dispatched provider bytes cannot be recalled. See
[indexer semantics](../semantic-indexer-operations.md), not this deployment note,
for the durable state machine.

## Approved provider policy

Before any v0.3.1 runtime or migration write, the synthetic Voyage provider gate
must pass the owner-approved `voyage4_no_training_retention_v1` contract: only
`voyageai`, no fallbacks, `data_collection: deny`, response cache off and no request
`zdr` override. The route is non-ZDR; upstream may retain inputs and outputs for an
unspecified period under its terms. The enable consent page and status must carry
that disclosure/policy identity. Disable or mail deletion does not prove remote
erasure. Do not alter stricter account-level ZDR or OpenRouter content logging/use
preferences as a rollout workaround. Provider gate failure stops before writes;
no migration or deployment success follows from a locally prepared policy change.

## Production predecessor and preservation

The accepted predecessor is completed v0.3.0 production run
[40116604490](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/40116604490),
source `d3d913d4bf59f48790a2753bc066033b4d8cf7a6`, receipt `12570076705`.
The [completed v0.3.0 delivery](../v0.3.0/production-delivery.md) holds its exact
serving versions. Fresh read-only admission must match that reviewed epoch and
preserve the stores, address ownership, all profile/mailbox fences, accepted or
unknown sends, paid grants, budgets, currencies, current sending policy, direct
contacts, lifecycle subscriptions and retained ingress/events graph. No customer
mail is a test fixture and no production account is enabled by the migration.

## Rollout and readiness

The independent controller is `infra/deploy/production_v031.py`; the historical
v0.3.0 writer must not be replayed. Use trusted `main`, protected `production`,
first attempt and the existing shared production-graph writer lock:

| Existing workflow target | Confirmation | Required `production_graph_freeze` |
| --- | --- | --- |
| `production-inspect` | `INSPECT_PRODUCTION_V031` | `FREEZE_PRODUCTION_GRAPH_WRITERS` |
| `production` | `RUN_PRODUCTION_V031` | `FREEZE_PRODUCTION_GRAPH_WRITERS` |

Inspection is read-only and verifies exact serving versions, retained graph,
current policy, schema through migration 0017 and a supported old scheduled usage
model. The writer additionally requires all current source gates plus restored,
reverified `mail_api` and `trace_sink` artifacts before mutation. The default is
same-run admission; the reviewed promotion path instead requires both
`source_run` (the original successful build/check producer) and
`staging_acceptance_run` (a separately successful real semantic journey). Its
`accepted-staging-artifact/v1` chain keeps the original manifest/compiler/source/
run identities intact and checks complete runtime closure against the current
trusted main checkout. A failed deployment with green source gates remains a
failed deployment, not real-user acceptance. See
[artifact promotion](../deployment-artifact-foundation.md).

The provider order is:

1. Replace the backward-compatible private trace sink; retain exact queues and
   producer ownership, ingress, lifecycle consumer and subscriptions.
2. Install the consent-aware fetch-only API before 0018. Missing preference schema
   fails semantic processing closed; ordinary compatible mail flows remain live.
3. Install the tested private maintenance entry with empty Cron. Bracket exact
   serving API/maintenance pins, paused schedules, capture-off, preserved policy
   and retained external graph throughout the old scheduled cohort witness.
4. Observe at least 31 monotonic minutes: documented 15-minute Cron propagation,
   15-minute scheduled invocation wall limit and a one-minute margin. Missing or
   unsupported predecessor usage models stop before writes. Elapsed sleep alone
   is not the witness. Record `old_http_drain: NOT_CLAIMED`: old admitted HTTP and
   provider bytes cannot be recalled by the schedule bound.
5. Apply only additive migration 0018, verify the complete source-derived schema,
   zero enabled preferences, unchanged retained-vector count and preserved existing
   address ownership. Do not retrieve mail content or vectors for this check.
6. Activate the new maintenance at its existing five-minute cadence and verify the
   complete immutable graph, private surfaces, queues, capture settings, empty API
   Cron and unchanged policy/retained ownership again. Bounded unauthenticated,
   no-redirect public-health reads must report `status=ok`, `version=0.3.1` and
   `api_version=2` within 120 seconds before success; propagation never authorizes
   another deployment submission.

The non-content `production-v031/v1` receipt records actual pins, source/run,
preserved address count, semantic model/default, policy/retained fingerprints and
the scheduled witness. Inspection records `schema_migration_applied: false` and
labels semantic defaults/model as **after upgrade**, not as facts about the old
live automatic-indexing runtime. Completed upgrade records the migration as
applied only after its actual checks. Aggregate non-NULL vector-count preservation
is not byte-equality evidence. A concurrent legitimate deletion can safely stop a
partial promotion; it does not authorize rollback, suppressing the check or replay.
The upgrade receipt is not emitted as success until final graph/public readback.
Any failed or ambiguous provider mutation stops with its captured coordinates and
requires exact owned reconciliation, not another blind dispatch. No sending-policy
change, resource creation, consent enablement or automatic rollback belongs to
this controller. Retained legacy vectors are not rollback permission to a
pre-consent API or background sender. A completed receipt becomes the next
reviewed predecessor; a future writer must explicitly advance the pinned epoch.

Formal five-platform CLI/Skill publication requires matching production health,
the existing outbound attestations, native profile journeys, checksums,
attestations and published-byte verification. Reviewed release promotion reuses
the original three already-tested native executables with embedded provenance,
and builds/tests only the two missing targets; it neither reruns green native
suites nor calls reused binaries a new build. Public-site replacement follows the
verified public assets. Local replacement follows matching archive/Skill source
verification, daemon stop and private backups; credentials and YOLO preferences
must not be reset. Success receipts will be added only after actual readback.
