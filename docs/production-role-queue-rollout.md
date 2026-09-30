# Decision: production role-monitor rollout is a graph transition

Date: 2026-10-01. Status: **guarded source implementation; independent review and hosted checks pending, no live acceptance**.
No provider request, deployment, route change or local test was performed for
this artifact. Public sending and `abuse_contact_verified` remain held/unset.
The confidential destination stays in project Secrets and restricted memory;
it must not appear in this document, logs or public artifacts.

## Finding and chosen architecture

`deploy-role-monitor-production.yml` currently deploys a role Worker with
`ROLE_TRACE_EVENTS -> amail-trace-events`, but has no sink/Queue/private-retention
prerequisite, serving-version pin or post-deploy role capability audit. Its D1
check verifies allowable schema, **not** absence of arrivals or an expired lease.
Its before/after direct-forward audit is valuable but insufficient.

Meanwhile production `ci.yml` provisions/verifies the trace graph with the
default `api-only` contract. Adding the role producer would invalidate both
later sink provisioning and Mail readback. Silently allowing zero, one or two
producers everywhere would hide partial deployment and unauthorized attachments.

**Choose one shared trace graph and explicit lifecycle phases.** Keep the
reviewed closed API/Role envelope schema and queue-only sink. Bootstrap allows
only the documented empty -> sink -> API initialization states; strict phase-one
acceptance requires exactly API; phase-two and subsequent maintenance require
exactly API + role. Role Worker deployment and four-route cutover are separate
operations. Existing four direct forwards are unchanged until their own gate.

This extends [the staged contract](role-mail-monitoring.md), rather than creating
a new role Queue or weakening [the trace privacy boundary](mail-trace-queue-sink-decision.md).
A separate role sink is a viable isolation alternative, but duplicates schema,
Queue/DLQ, privacy and recovery work without resolving route/lease safety.

## State and invariant model

| State | Exact events producers | Consumer | Role routes / send state |
| --- | --- | --- | --- |
| P0: pre-bootstrap | No accepted trace graph | None accepted | Four direct forwards; sending held |
| P1: API accepted | `amail-mail` only | `amail-trace-sink` only | Four direct forwards; role absent or pinned non-Queue predecessor; sending held |
| P2: role deployed, unrouted | `amail-mail`, `amail-role-monitor` | Same sink | Four direct forwards; isolated role ledger empty and lease expired; sending held |
| P3(k): bounded cutover | Same exact two producers | Same sink | Exactly k reviewed rules target role, 4-k retain original forwards; sending held |
| P4: operational acceptance | Same exact two producers | Same sink | Four role rules, fresh healthy lease, original/digest/privacy evidence; sending still held pending other release gates |

Queue and DLQ identities are independently reviewed resource IDs, not names
adopted from the latest listing. Both retain messages for 86,400 seconds. Events
has exactly one Worker consumer with batch 10, wait 1,000ms, retries 3, retry
delay 30s and concurrency 2; the DLQ has no producer/consumer attachment.
No operation polls, purges or exports Queue bodies. Redelivery preserves the
producer's opaque event ID; duplicate safe trace records are permitted.

API and role original-context parent/Logs/Traces/Issues capture must all be
explicitly off in current-resource readback, with Logpush/tail/export surfaces
absent. Missing/null is not false. The sink must be private, queue-only, bounded,
without business storage, Email, Cron, HTTP, Tail or RPC surfaces. Its permitted
retention remains conditional on complete retained-record privacy acceptance.

All three serving deployments must be single-100 versions at reviewed pins.
Bracket serving identities, effective capture, Queue topology, role D1 and
rules around transitions. These reads detect observed drift, not an atomic
provider transaction. Freeze other deployment/settings/routing writers. Use
one non-canceling **workflow-level production graph-writer lock** across API,
sink, role and route mutation workflows; do not give mutually dependent jobs
the same job lock and deadlock them. Separate current groups do not provide this
cross-workflow exclusion. Read-only diagnostics need no mutation lock but must
report concurrent drift as unverified.

## Executable implementation and promotion sequence

### 0. Source and staging prerequisite

Implement and review the changes below; run hosted source/contract checks.
Before any production role deployment, accept staged API/sink and role
Email/Cron whole-record privacy, delivery/lease/fault behavior and restoration
of its disposable route. A green build or settings marker is not that evidence.
Promoted shared-schema/producer/sink/config source must match the accepted
staging source. If a merge changes the SHA, use an explicitly verified relevant
source-tree manifest or rerun at the promoted SHA; do not claim unrelated SHAs
are equal or relax an existing exact-SHA verifier implicitly.

### 1. Bootstrap and accept the production API/sink graph (P0 -> P1)

Manual, reviewed `main` source only; production send policy stays held. Audit
account/zone, production storage, four exact API-owned direct-forward rules and
verified private destination. Distinguish confirmed Worker absence from a failed
GET. If a role Worker already exists, require its exact predecessor version and
prove no trace producer attachment; unexpected role producer is not bootstrap.

Provision only absent exact Queue/DLQ resources; preserve returned IDs before
any later mutation. Existing resources need independent ownership pins and may
not be rewritten to resemble expected resources. Deploy sink, verify its pinned
capabilities, then deploy API with the exact Queue binding and all capture off.
Strictly read back `api-only` after API deployment. Emit realm-specific deployment
evidence only after successful readback. Run a distinct bounded production
retained-record API/sink canary with exact source/sink/Queue/DLQ pins and causal
IDs; complete records and content/failure paths, not merely safe custom payloads,
must pass. Require that immutable run before P2.

For a subsequent P4 maintenance run, **do not** execute this bootstrap path:
skip Queue creation and read back the reviewed `api-role` graph before and after
sink/API replacement. Every phase caller supplies topology explicitly.

### 2. Bootstrap role storage, then deploy role without routing (P1 -> P2)

Replace the current standalone production role workflow with a fail-closed
phase-two operation. Inputs: confirmation, exact main SHA, prior production
API/sink deployment run, distinct privacy-canary run, API/sink pins, existing
role pin or explicit first-bootstrap absence, Queue/DLQ pins. Historical evidence
must identify repository, workflow, realm, successful first attempt, exact source,
successful unique jobs and exact marker pins. Do not reuse staging markers as
production evidence.

First bootstrap: exact isolated production D1 must contain only permitted
provider bookkeeping; apply the reviewed additive role migration, then prove
exact schema, zero arrivals and singleton initial expired lease. Replacement:
require exact existing schema, zero arrivals and expired lease **before** migration
and again before replacement. Unknown/partial state or pending reports stops the
operation; never delete rows to force the gate. Database absence and first
deployment are explicit states, not exceptions swallowed by a replacement gate.

Recheck P1 pins, private destination, unchanged four forwards and storage before
one bounded role deployment. Suppress raw Wrangler output; use a restrictive
`.temp` secrets file, delete it on every outcome, and capture the exact new role
version even for recovery. Read back strict `api-role`, unchanged API/sink
serving identities, new single-100 role identity, exact isolated D1/send/Queue
bindings and private surfaces/capture. Preserve the four direct forwards.

The configured production Cron can run before cutover. Its route audit must
fail because rules are still direct forwards; an expired lease and a bounded
typed `routes_failed`/failure record are expected, **not** operational failure
that justifies early route change. Prove the role Cron event's complete retained
record is safe. A version marker is only recovery/configuration evidence.

### 3. Switch each exact operational rule separately (P2 -> P3(k) -> P4)

Only after accepted staging Email/fault/rollback evidence and production P2/Cron
privacy, use a separately reviewed route operation. Snapshot the four original
rule IDs and full expected shapes privately. For each rule: fresh full audit,
require unchanged old literal/enable/source/forward destination, replace only its
action with the exact role Worker, read back exact mixed topology, then send one
controlled external SMTP canary. Ambiguous mutation/send is reconciled, never
automatically replayed. Keep the remaining originals unchanged.

For each controlled role canary prove real Worker invocation, opaque D1 arrival,
accepted forwarding, original at the private destination (Inbox/Junk checked),
official `mail@moesegfault.dev` digest in Inbox and safe complete Email/Cron/sink
retained records with causal IDs. The current Worker cannot accept arbitrary
production aliases: do not invent a production disposable recipient without
a separately reviewed policy. The first reserved-rule canary is a real cutover
with its direct-forward restoration ready, not a risk-free preflight.

During mixed routes the existing all-four route audit cannot renew the lease.
After 4/4, observe natural Cron success, destination verification, bounded outbox
age and lease freshness; prove expiry/query/monitor failure causes Mail send
denial under a controlled, held policy. Use staged fault injection, not broad
production failure experiments. This phase does not itself allow public sending:
other production outbound/feedback/privacy/product gates remain mandatory.

## Failure, rollback and recovery

* Ambiguous creation/deployment/migration: preserve exact non-secret identities,
  stop the transition, and reconcile those resources read-only. Do not retry a
  mutation because the enclosing Actions run is red. Do not delete/purge Queue,
  DLQ or D1 to manufacture a clean state.
* Before route cutover: leave the four forwards intact and sending held. A
  compatible, already accepted all-capture-off version may be restored only with
  exact current-resource/topology readback; otherwise hold and repair forward.
* During/after cutover: first restore switched rules to their privately recorded
  exact old forwards using fresh conflict detection, verify all four, and keep
  sending held. Let the lease expire (or clear under a reviewed hold operation).
  Keep ledger/unknown forwarding outcomes for reconciliation; no automatic resend
  of originals whose delivery is ambiguous.
* Route restoration does **not** remove the role Queue producer or roll back D1.
  Remain `api-role` while it is attached. Returning to `api-only` requires a
  separate pinned producer-removal transition and a sink that can still decode
  queued Role events; do not roll the sink back to an API-only schema.
* Never restore historical original-context capture to improve diagnostics.
  Never assume Worker rollback reverses routing, observability settings, Queue
  attachments or database migration. Resource/data compatibility must be checked
  independently before restoring code.

## Minimal source changes / acceptance ownership

| Change | Contract / evidence |
| --- | --- |
| Realm-parameterize role graph/storage/capability gate | Reuse pure predicates from `check_role_trace_rollout.py` and `verify_role_monitor_staging.py`; explicit production constants, no production fault secret; separate first-bootstrap absence from replacement pins. |
| Production evidence verifier/formatter | Reuse historical run validation with explicit realm/workflow/main job names and production markers; separate config and bounded-privacy outcomes; exact pins and source provenance. |
| Harden `deploy-role-monitor-production.yml` | Explicit confirmation/evidence/pins; graph before/after, strict D1 lifecycle, one redacted deployment and captured version; never change routes. Disable existing unsafe dispatch path until replaced. |
| Make production `ci.yml` graph phase explicit | Bootstrap = `api-only` provision; maintenance = `api-role` readback, no provision replay. Propagate topology to sink isolation, API readback and every recovery caller; reject a wrong phase before mutation. |
| Shared production mutation lock | Workflow-level common lock plus external writer freeze; preserve within-workflow sink -> API dependency and no cancellation of stateful operations. |
| Dedicated route transition/restore helper and hosted tests | Exact 0..4 mixed rule contract, private old-shape snapshots, bounded partial recovery; never reinterpret `ensure_role_forwarding.py`'s strict all-forward audit as a Worker audit. |

Hosted fixtures must cover first absence versus failed read, wrong realm/pin,
unknown capture fields, missing/duplicate/extra producers, incorrect phase,
pending ledger/live lease, stale or duplicate historical attestations, mixed-rule
conflict and ambiguous deploy recovery. The source-only fixtures do not replace
live acceptance. Link resulting run IDs, immutable source, versions, resource
pins, bounded scopes and fixed outcomes in the existing acceptance ledger.

## Platform evidence and limits

Cloudflare documents [at-least-once delivery](https://developers.cloudflare.com/queues/reference/delivery-guarantees/)
and [per-message acknowledgements/bounded retries](https://developers.cloudflare.com/queues/configuration/batching-retries/).
These support stable opaque IDs and duplicate-tolerant tracing, not exactly-once
SMTP forwarding or a transaction across D1 and provider mail. Cloudflare also
warns that [Worker rollback does not change connected resources](https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/)
and data-schema changes can break restored code. Therefore graph/state recovery
is separate from code rollback. [Cron propagation](https://developers.cloudflare.com/workers/configuration/cron-triggers/)
is not immediate; natural runs and a stale lease must be observed rather than
attested from a source trigger declaration. These are platform-backed mechanics;
the full-record privacy and external Inbox properties remain empirical gates.

Current release/HTTP/DNS evidence is in [the release gap audit](release-gap-audit.md)
and [the DNS snapshot](production-dns-readiness-2026-09-29.md). This runbook
neither refreshes those observations nor authorizes deployment or release.


## Source implementation update (2026-10-01)

The original unsafe standalone role dispatch is replaced with an unrouted,
fail-closed operation. It requires exact production API/sink deployment and a
**distinct** production complete-record privacy run, plus exact-source staged
Email/Cron/fault/rollback privacy acceptance. All three historical inventories
must identify this repository, workflow, branch, first successful attempt,
unique successful jobs and exact realm-specific markers. The consumer in
`infra/deploy/require_production_role_phase1.py` intentionally cannot mint those
markers or accept a staging marker as production evidence.

`check_production_role_graph.py` provides bracketed production graph readback,
independently pinned Queue/DLQ identities, single-100 serving deployments,
immutable API/role bindings, current all-capture-off policy, private role
surfaces, verified private destination, exact full role rule snapshots and held
send policy. First bootstrap requires complete successful Worker absence and
pristine isolated D1. An unrouted replacement requires a pinned non-Queue role
predecessor, exact role schema/indexes, zero arrivals and an expired lease
(measured against D1 time in milliseconds). A successful additive migration
must leave the singleton initial lease and empty ledger. No row is deleted to
make any gate pass. A failed provider GET is never role absence.

Production API/sink CI lifecycle is explicit in the target:

* `production` + `RUN_PRODUCTION_API_ONLY_BOOTSTRAP` requires first API/role
  absence, positive existing global-held/unset-role-gate D1 readback, and bootstraps only the API-only graph. A pristine Mail policy database without the reviewed hold schema is not an accepted bootstrap; initialize/reconcile that state through a separately reviewed bounded migration before this graph operation. An already live API is not
  silently replayed as bootstrap. Partial bootstrap recovery requires separate
  reconciliation and reviewed transition before another mutation.
* `production-api-role-maintenance` +
  `RUN_PRODUCTION_API_ROLE_MAINTENANCE` requires strict existing API-plus-role
  readback before/after sink and API replacement. It never invokes Queue create
  or the permissive Queue initialization contract. It preserves nonempty role
  ledgers, requires the reviewed role routing count (0..4), verifies exact mixed
  rules and keeps sending held. It does not implicitly deploy ingress, replace
  lifecycle subscriptions or publish the website.
* Both use the single added `production_graph_freeze` input with
  `FREEZE_PRODUCTION_GRAPH_WRITERS`; together with the standalone role workflow
  they share workflow-level `amail-production-graph-writer`, cancellation off.
  Dependent sink/API jobs do not take that same job-level lock. The workflow
  remains within GitHub's 25 dispatch-input limit.

Maintenance pins come from independently reviewed project variables
`AMAIL_MAIL_VERSION_PRODUCTION`, `AMAIL_TRACE_SINK_VERSION_PRODUCTION`,
`AMAIL_ROLE_MONITOR_VERSION_PRODUCTION`, `AMAIL_TRACE_QUEUE_ID_PRODUCTION`,
`AMAIL_TRACE_DLQ_ID_PRODUCTION`, and `AMAIL_ROLE_ROUTED_COUNT_PRODUCTION`.
Successful deployment outputs carry the exact new version only for their
corresponding post-check. They do not overwrite reviewed variables or permit
an inferred/latest serving pin. The private destination remains a Secret.

Production deploy/migration wrappers suppress provider output, use repository
`.temp` restricted secret files with cleanup on every result, never replay an
ambiguous operation, and preserve a uniquely parsed returned version as recovery
information even if Wrangler subsequently reports failure. A timeout without a
returned version remains an explicit reconciliation obligation, not a retry.
The existing staging deploy default retains its prior command contract.

`production_role_routes.py` adds pure exact 0..4 mixed-route predicates and
full-snapshot one-action transition/restoration comparisons. It does **not**
issue a PUT, send a canary, or expose a route-cutover workflow. Therefore this
source update does not complete P3/P4 or authorize live routing changes.

### Intentionally closed prerequisites / remaining implementation

The production complete-record API/sink canary workflow and the combined staged
role Email/Cron/fault/rollback whole-record acceptance workflow are not yet
implemented. The evidence consumer reserves exact contracts
`.github/workflows/production-trace-privacy.yml` and
`.github/workflows/staging-role-acceptance.yml` respectively; absent workflows,
missing outcomes, duplicate markers, stale source or failed attempts reject
phase-two deployment. Before implementing either emitter, review its complete
record scope, opaque correlation, retention window and failure paths. Do not
weaken the consumer to make the dormant rollout executable.

A dedicated one-rule live cutover/restoration runner still needs its privately
persisted original snapshots, exact mixed-phase pins, provider ambiguity
reconciliation and external SMTP/destination/digest acceptance. The pure route
predicates are necessary source contracts, not that live runner. Source-only
fixtures cover first versus replacement storage, absence/error distinctions,
live lease/pending ledger, strict production bindings, mixed-route conflict,
one-rule restoration, shared workflow locks, missing historical evidence and
dispatch limits. These tests run on GitHub Actions; no local test/build,
provider request, production deploy or route mutation was performed.

Official provider references retrieved for implementation: documented
[SinglePage Worker script inventory](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/methods/list/),
[Workers deployment error codes](https://developers.cloudflare.com/workers/observability/errors/),
[rollback/resource separation](https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/),
and [Workers production practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/).
The design chooses successful inventory rather than treating error 10007 as
absence, because that code also covers a missing workers.dev subdomain.


### Review corrections and current lock scope

The bootstrap predicate now independently reads persisted global-held policy
and the unset role release gate before graph acceptance. A pristine Mail policy
schema is not interpreted as an accepted hold. The isolated role schema gate
compares the complete non-provider `sqlite_master` object set and conservative
SQL tokens against the actual reviewed CREATE TABLE/INDEX migration. It preserves
string-literal semantics and rejects changed types/defaults/UNIQUE/NOT NULL/CHECK,
index column order, extra views and triggers, not just object names and PKs.
Role HTTP absence now uses the sink's bounded complete account-zone inventory
and unfiltered account custom-domain readers, checking every readable zone.

Current implemented shared lock covers `ci.yml` production graph writes and the
standalone gated production role deploy only. Other existing route and send-policy
workflows have not yet joined it; therefore external freeze of **all** those
writers is still mandatory and the full cross-workflow exclusion promised by the
runbook is not accepted. No role route cutover workflow is enabled. Whether role
monitor integration is v0.1 scope is being reassessed against the owner's choice
of confidential direct forwarding and deferred operations center. These dormant
source gates must not be interpreted as an obligation to deploy a new ops system.
