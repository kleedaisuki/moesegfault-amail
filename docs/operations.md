# Mail operations and release

Current delivered state is in [validation](validation.md); this runbook is not the
[public manual](https://amail.moesegfault.dev/manual/). Do not reuse old held-state
snapshots as present policy or dispatch authority.

## Active topology

| Component | Source/configuration | Boundary |
| --- | --- | --- |
| Public API mail.moesegfault.dev | crates/mail-worker/wrangler.toml + entry/api.mjs | HTTP/RPC, no Cron |
| Private maintenance | crates/mail-worker/wrangler-maintenance.toml + entry/maintenance.mjs | Scheduled only, no HTTP/RPC/send binding |
| Email ingress | workers/mail-ingress | Bounded MIME to private API binding |
| Lifecycle consumer | workers/mail-events | Delivery/bounce/complaint Queue to Mail D1 |
| Private trace sink | workers/trace-sink | Queue only; exact API + maintenance producer pair |
| Release site amail.moesegfault.dev | site | Introduction/manual/changelog |

Production API and maintenance share response-owned fresh Mail D1
`d9be9bb4-5a73-4223-85d6-b04763e6f03b`,
`moesegfault-mail-production-708b6d6c734779d657f5abb3`, and R2
`moesegfault-mail-raw-production-708b6d6c734779d657f5abb3`.
Current checked-in configurations are authoritative for bindings.
The authorized v0.1.2 normal upgrade in run `37104468990` replaced only API
(`50bd330d-2f9b-4102-8c8e-9bbaada927fe`) and scheduled maintenance
(`293d4049-c56a-40ee-8bc3-ef345a7a4eb7`), preserving exact live allowed policy
and the retained external graph. Receipt artifact `11267970678` records deployment
coordinates. Before a future writer run, explicitly review and advance the
source-owned predecessor pins; the v0.1.2 controller intentionally refuses to
repeat an upgrade against the now-replaced original epoch. Do not rerun it to
reset state or turn an old snapshot into current authority.
Original production D1 `ad06f7f3-8897-4150-b9a9-7a46a8e55b30` and R2
`moesegfault-mail-raw-production` were retained, not silently migrated/deleted.
Staging uses separate D1 `74f35f95-42ce-482c-86e6-dffbdd35cbbe` and R2
`moesegfault-mail-raw-staging`. Never cross-bind realms.

An HTTP Custom Domain is not SMTP MX. User addresses end in @mail.moesegfault.dev;
official site sender is mail@moesegfault.dev. Identity production/staging issuers
and clients are distinct. HTTP health does not establish message delivery.

## Supported hosted lanes

ci.yml pushes/PRs validate source without deployment. Manual targets:
checks, staging-inspect, staging, staging-e2e, production-inspect, production,
production-api-only-maintenance,
production-fresh-bootstrap and production-fresh-online.
The actual workflow input/confirmation schema is authoritative; no historical
incident document may restore a removed dispatch mode. staging-e2e retains the
normal native-login/two-SMTP/ZIP/search journey and RUN_STAGING_E2E confirmation.

### v0.1.2 staging-only candidate

The reviewed branch is `codex/v0.1.2-agent-first-performance`. Dispatch `checks`
for hosted source/performance checks and downloadable native candidates without
deployment. `staging-inspect` plus `INSPECT_STAGING_V012` reads only fixed staging
capabilities; `staging` plus `RUN_STAGING_V012` is the isolated graph writer.
All staging inspection/deployment/native acceptance runs share the workflow-level
staging writer lock; same-run resource jobs remain sequential. No tag, Release,
production deployment, public-site replacement or global-send policy enable is
part of this lane. Protected staging synthetic identities are not production users.

Current deployed site source `25f22cd79a68452c73ff63e3ed695bcb1cbfde19` completed
[staging 37072106319](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37072106319).
The unchanged installed Mail runtime and exact active graph were admitted before
only the staging site was deployed. The final user-facing unpublished three-platform
CLI/skill bundle is
[candidate artifact 11256560216](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37074671896/artifacts/11256560216)
from successful checks producer `37074671896`, source
`2ea0d09febcaa51c276de0e82e1bdf5074d16f17`. This later helper-only correction did
not redeploy the Mail runtime or site. Actual deployed
site browser acceptance [37072847760](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37072847760)
passed all twelve cases with zero client scripts. Native owner acceptance [37075181256](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37075181256)
passed against that exact checks producer, including one scoped real self-send,
receipt recovery/replay/delivered feedback and exact owned cleanup. The complete
scope and prior failed acknowledgments are in [validation](validation.md), not
inferred from deployment. Keep component provenance separate: deployed site
revision remains `25f22cd79a68452c73ff63e3ed695bcb1cbfde19`.

Actual initial inspection [37046570528](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37046570528)
found legacy API version `c3f6401a-1e84-4f51-91df-ae77d90683e9` with both fetch and
scheduled handlers and five-minute Cron; maintenance, trace sink and trace queues
were absent. Ingress and lifecycle were present. This snapshot is neither a drain
witness nor proof of a new deployment. Current live reads remain authoritative.

The staging writer accepts either this frozen immutable legacy contract or an
exact already-active split graph. It restores the same-run tested artifact before
any provider mutation, keeps global sending held, preserves D1/R2 and additive
migrations, and deploys the private sink before trace producers. Initial migration
deploys the API fetch-only with empty Cron and private maintenance paused. It then
brackets the exact API/paused-maintenance serving versions, empty schedules and
held policy throughout a monotonic 31-minute observation window. Admission uses
the pinned old version's immutable `resources.script_runtime.usage_model`; missing,
unknown or grandfathered Bundled models stop before writes because their duration
is not bounded by the standard contract.

This bound combines documented [Cron propagation up to 15 minutes](https://developers.cloudflare.com/workers/configuration/cron-triggers/)
with [scheduled invocation wall time of 15 minutes](https://developers.cloudflare.com/workers/platform/limits/)
and a one-minute margin. A bare elapsed wait, zero lease count or caller assertion
is not equivalent evidence. Existing execution leases are read and retained:
pending work and foreground projection leases are legitimate, not a reason to
empty a mailbox or clear fences. Old scheduled execution is bounded by the
provider contract; any residual lease remains the runtime's normal opaque-token
fence. The same-run witness records the pinned cohort, model, limits, sample count
and preserved lease counts. Only then is the private five-minute maintenance Cron
enabled and the exact API + maintenance producer pair read back. Already-split
ordinary replacements preserve the cadence and do not repeat this initial wait.
After successful initial readback, retain the returned trace Queue/DLQ identities
as the reviewed staging environment variables used by later exact-graph runs.
Do not infer ownership from a matching name or replace these pins on a failed read.

Deploy ingress and lifecycle with captured exact UUIDs, then read their immutable
same-realm service/D1/vars/secret bindings, private surfaces, Queue/DLQ consumer
settings and domain-scoped subscription twice. Failed inventory does not authorize
creation. Ambiguous submits are not retried; keep observed versions and inspect
the fixed graph before any recovery. Do not use fresh-bootstrap as this migration.

#### Owned sink-only interruption

Run [37053907751](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37053907751)
passed its source gates but stopped at sink verification after successfully
creating both trace Queues and deploying sink version
`be786239-402d-4e72-89c9-0acbe88b0b86`. The verifier incorrectly demanded the final
API + maintenance producer pair during sink-only preparation. Initial preparation
must verify the private sink/DLQ/retention with zero producers; the subsequent
API-only phase admits the sole API producer, and final activation still requires
the exact API + maintenance pair. Privacy and Queue consumer assertions remain
unchanged; this is phase ordering, not a relaxed terminal graph.

Only this reviewed interruption can use `target=staging`,
`confirm=RUN_STAGING_V012`, `staging_resume_run=37053907751`. The helper verifies
the original failed run/attempt, every source gate, skipped later writes, immutable
predecessor and provision artifacts, and the unique successful typed sink submit.
It requires the exact original runtime tree; only the reviewed controller,
verification/tests and documentation may differ. The current run still runs full
source gates and deploys new components from its own same-run tested artifact.
The old artifact is ownership provenance, never a replacement for current bytes.

Before continuing, live reads must match the original API/ingress/lifecycle pins,
absent maintenance, global held sending, exact sink version/deployment, all private
surface/capability/sanitized-retention predicates, and both exact trace Queue IDs
with zero producers. Only then are Queue creation and sink deployment skipped.
Any changed pin, attached producer or failed predicate stops without replaying
those writes. The remaining migration follows the ordinary staging sequence above.
This input does not recover arbitrary failed runs or ambiguous submissions.
The second reviewed boundary is `staging_resume_run=37058617870`: API replacement
and paused-to-active maintenance cutover completed before the final graph check
rejected an unrelated historical staging contact Worker by name. Its immutable
job metadata, three exact successful typed submit receipts and bounded cutover
witness are mandatory, alongside original owned Queue/sink provenance. Live
reads must match the exact known API/maintenance/sink deployment/version tuple,
unchanged ingress/lifecycle, global hold and strict final two-producer graph.
The old contact Worker is retained only with a serving/Cron/capability bracket
proving no Mail DB/R2, API/maintenance/sink service or trace main/DLQ Queue edge.
Production role absence remains mandatory. This does not assert contact-monitor
correctness or general population isolation, and grants no route/Cron changes.
After read admission, API, maintenance, sink, Queue, migration and sending-policy
write steps are skipped; remaining ingress/lifecycle/site deployment consumes the
current run's tested artifact. The original wait/witness is not replayed or
relabeled as current execution. Normal future split replacements still require
reviewed Queue/DLQ variables; observed names never supply writer ownership.
If later adapter verification fails after a confirmed submit, inspect the current
immutable adapter versions, lifecycle Queue shape and exact subscription before
continuing. The inspection artifact carries closed adapter failure labels and
non-content numeric/type/predicate facts; it is not permission to redeploy the
adapters. [Cloudflare consumer settings](https://developers.cloudflare.com/api/resources/queues/subresources/consumers/)
define null maximum concurrency as automatic platform scaling; do not treat an
arbitrary explicit limit as equivalent merely to pass a gate. Lifecycle producer
and subscription ownership must likewise follow the actual reviewed graph, not
a guessed provider response shape.
The observed subscription read contains optional source display metadata `name`.
[Pinned Wrangler 4.142.0 EmailSendingEventSource](https://github.com/cloudflare/workers-sdk/blob/wrangler%404.142.0/packages/wrangler/src/queues/subscription-types.ts)
defines the three selectors type/zone_id/domain. Match those exactly, permit only
a bounded string `name`, and reject all other additional fields; never replace
that contract with arbitrary subset matching. Before/after raw snapshots still
require metadata and selected Queue/subscription state to remain unchanged.

`staging_resume_run=37065145834` selects only the third owned interruption after
successful ingress/lifecycle submits and before the site writer. It binds full
source gates, exact typed adapter receipts, original sink/Queue and cutover proof,
and identical tracked runtime. Fresh immutable ingress/lifecycle pins and their
complete current private/Queue/subscription graph are mandatory. Successful read
admission skips both adapter deployments, lifecycle Queue creation and subscription
reconciliation as well as earlier runtime writes; only the current candidate site
is deployed. The current run still validates/packages its own tested user bytes.
Before another full continuation, `target=staging-inspect` with
`confirm=INSPECT_STAGING_V012` and the same explicit `staging_resume_run` can run
the identical read/provenance preflight without deployment authority. The read
confirmation is not accepted by any writer phase. Failures expose only a closed
known `staging_*` reason (otherwise `unknown`), never provider response prose.
The typed sink-submit log is fetched by an explicit authenticated GitHub GET,
then its short-lived 302 target is restricted to the observed GitHub Actions Azure
log account family and downloaded without bearer credentials or redirects, at an
eight-MiB bound. This is transport separation, not a weaker ownership proof or
additional token authority; API permission denial stops the read admission.
When fetch-only API, scheduled maintenance and sink are present, inspection also
reads their full active graph with observed immutable pins and reports only a
closed structural verdict. Historical staging role presence is projected with
handlers/Cron and boolean Mail database/service/body-bucket/trace-Queue capability
facts. These read diagnostics are not ownership pins or authority to remove the
role Worker, accept an unreviewed graph or replay an already successful submit.
The v0.1.2 candidate lane also skips the unrelated Identity verification-inbox
deployment; the original non-candidate staging lane remains available unchanged.

The staging site depends on the runtime graph, renders v0.1.2 candidate copy, and
gets an exact source-revision header only in its generated staging assets. Smoke
checks all three pages, v0.1.2 status, noindex/nofollow, source SHA, navigation,
manual exploration commands and real TOC targets. Public v0.1.0 stays unchanged.
The existing browser lane's `live-staging` target takes that deployed revision and
only reads the fixed staging origin; it cannot deploy or open mail authority.
The generated staging-only host headers additionally use `public, max-age=0,
must-revalidate, no-transform` to prevent automatic provider analytics injection
without touching public-site or zone-wide settings. After one successful submit,
semantic readiness is polled with public GETs for at most 120 seconds: all three
routes must simultaneously satisfy the exact revision/header/content contracts.
HTTP 200 alone is insufficient, and propagation never authorizes another submit.

For owner acceptance, download the same-run `cli-candidate-v0.1.2-RUN_ID` artifact
using GitHub Actions or `gh run download RUN_ID -n cli-candidate-v0.1.2-RUN_ID`.
Verify `SHA256SUMS` and `candidate.json` before use. The three native candidates
(Linux x64, Windows x64, macOS ARM64) plus skill are review assets, not the formal
five-platform release gate. Use staging explicitly for tests; do not accidentally
use the CLI's stable production defaults. Staging grants, if separately exercised,
must remain recipient-bound, one-use and attached to owned synthetic fixtures.

The existing `staging-e2e` native-login journey explores the new offline discovery
topics, reads held policy/owner quota and bounded owner events, and checks a random
unsubmitted send intent returns typed 404/stop. It retains exactly two real SMTP
fixtures: only after the first DATA receipt is verified does the second include
its RFC reply/reference relation; Reply-To is the same run's owned route. Get,
ZIP and metadata search must preserve and find those relations. Existing route
cleanup is unchanged. With no separate send confirmation, this does not exercise
live outbound feedback; no fake send/event rows are seeded in staging D1 and
general sending remains held.
For v0.1.2 acceptance, pass `source_run` equal to the successful same-source
staging/checks producer run. The job admits its immutable candidate artifact ID,
verifies all bundle checksums/producer provenance and copies only the reviewed
Windows release executable under `.temp/staging-cli` for native login/SMTP tests.
This proves the user-downloadable release bytes, not a separately rebuilt debug
binary. An omitted input preserves the historical hosted debug-build fallback;
it is not the preferred v0.1.2 candidate-byte acceptance. Source SHA must match
exactly; do not use ancestry or a successful sub-artifact from a failed run.

An explicit `send_confirm=RUN_STAGING_OWNED_SEND_V012`, together with the normal
`confirm=RUN_STAGING_E2E` and exact `source_run`, admits one additional protected
synthetic self-notification after the original two-message cleanup. The existing
operator canary helper's staging-only guarded mode requires this run's private
nonce, exact owned active alias/rule and GitHub actor. Its conditional UPDATE
preserves global hold and atomically refuses any still-live grant; the established
main/production wrapper remains unchanged. Its `RETURNING id` must contain exactly
one integer gate ID 1 before exact owner/recipient/case/hold readback. D1 aggregate
`meta.changes` includes audit-trigger writes and is not single-row admission.
Lost/failed grant acknowledgment may still have installed an unused live slot;
inspect its safe predicates/audit and allow normal expiry, never overwrite it. The grant targets one hashed self
recipient for 15 minutes and is consumed by the original persisted send UUID.
Ambiguous grant writes or provider submissions are not retried. The probe discards
first stdout, retrieves server/local receipt, and replays the identical ZIP/key
only after positive accepted/archive evidence; provider/local IDs must remain
unchanged. Real delivered outcomes and their owner-indexed event have a bounded
wait; absence or failure never authorizes a new send.

Exact original ZIP/UUID/hash are fsynced under private root `.temp` outside the
disposable credential home before grant/submission. Unknown/error keeps them;
only positive acceptance and successful journey/cleanup remove the private ZIP.
Neither private file nor credentials/mail bodies are public artifacts. The probe
closes only its one new alias and deletes only verified task-created messages;
accepted/unknown journals remain. A private two-boolean comparison between the
actual received RFC header and provider ID records this fixture's mapping evidence,
not a global identity contract. The outbound RFC field is not fabricated from
provider-ID syntax. This optional probe is not another sending campaign, a global
policy enable, or production mail authority.

### Normal production active-split upgrade

The normal `production` target now requires `RUN_PRODUCTION_SPLIT_UPGRADE` plus
`FREEZE_PRODUCTION_GRAPH_WRITERS`, trusted main, protected production environment
and first attempt. Before rollout, use the existing `production-inspect` target
with `INSPECT_PRODUCTION_V012` and the same freeze for read-only actual admission.
This lane is implemented but not yet actual production upgrade acceptance; record
its hosted inspection/deployment evidence in [validation](validation.md).

The source-owned predecessor is successful online run `36938451911`, artifact
`11199880674`, receipt SHA256
`f1fa430eb66c13094b7d204ba13afcfb321b7147e15db752eac4ceafac39d18b`.
Its exact API/maintenance/sink and retained adapter deployment/version UUIDs,
response-owned production D1/R2 and trace Queue/DLQ IDs are fixed in
`infra/deploy/production_upgrade.py`. Current names or latest inventory cannot
adopt another writer epoch. Retained ingress/events/sink sources and trace-schema
closure must equal the original `45f8dc41c82866ce47877601340113e28e8fb99d`
component trees except Cargo package.version; their deployed versions, queues and
lifecycle subscription remain unchanged, not redeployed to stamp a version.

Read admission requires complete active split capabilities/private surfaces,
API empty Cron, maintenance five-minute Cron, exact API + maintenance trace
producer pair, original stores, four verified direct forwards and lifecycle
consumer/subscription. It snapshots the existing global policy, including operator
metadata, whether allowed or held. Fingerprints bracket that unchanged policy and
private external graph across jobs; no hold/allow/grant/contact writer runs.
Historical staging and activation checks still require their original hold.

[Worker versions](https://developers.cloudflare.com/workers/versions-and-deployments/)
do not version D1/R2 contents. Therefore code replacement/rollback preserves
stores and assumes compatible persistent formats, rather than treating a code
UUID as a data rollback.

Full hosted source gates and restored/reverified same-run modules precede any
schema or runtime write. Apply compatible additive migrations, replace fetch-only
API, verify against still-active old maintenance, then replace scheduled-only
maintenance at its existing cadence and verify the complete graph again. This is
rolling replacement of compatible versions, not old-work drain proof: preserve
execution fences, pending work, accepted/unknown journals and user aliases.
There is no pause/reactivation, fresh store, bootstrap, role Worker or 31-minute
legacy cutover. Effective capture-off is read or narrowly corrected only on the
exact newly submitted API/maintenance version; private write coordinates and
returned UUIDs are retained. Failed/ambiguous writes stop without retry.

After success, the emitted non-content upgrade receipt supplies the next reviewed
writer epoch; the source-owned predecessor must be explicitly updated before a
future normal upgrade. A partial result requires exact owned reconciliation,
never another blind normal dispatch. `production-api-only-maintenance` remains the
historical held single-API graph lane and cannot maintain today's active graph;
fresh bootstrap/online targets remain separately authorized storage transitions.
Infrastructure-only changes with unchanged application inputs still need no live
runtime deployment.

Keep actual-production-users for separately authorized owned production journeys,
send-control/attest/direct-contact/role-forwarding/grant workflows for explicit
operator actions, fresh-mail-bootstrap-recovery for read-only recovery, and the
standalone Identity test inbox for its protected narrow use. Release/site workflows
remain separate. Queue capability probe is manual only, not normal-source traffic.
Do not build a new incident workflow around every provider failure.

## Deploy and rollback

1. Admit exact source and full hosted gates, then restore/reverify the same-run
   Worker artifact. [Artifact rules](deployment-artifact-foundation.md) apply before
   secrets, migrations or provider mutation. Serialize production graph writers
   using the existing shared lock; never nest the same lock and deadlock.
2. Use scoped existing credentials: CLOUDFLARE_ACCOUNT_ID/API_TOKEN for deployment,
   CF_EMAIL_ROUTING_TOKEN for literal rules, OPENROUTER_API_KEY for indexing, stable
   realm-specific INGRESS_SECRET for ingress/API. No browser/global-key fallback.
3. Apply forward-compatible migrations before dependent runtime. API stays fetch-
   only with empty Cron; maintenance owns scheduling. Deploy compatible sink/readers
   before producers. Preserve direct forwards and lifecycle attribution.
4. Independently read serving version/deployment, exact immutable bindings, Queue
   producers/consumer/DLQ, capture flags, public surfaces and schedules. Names or
   TOML intent alone do not prove the active graph.
5. For rollback hold new sending first when required, retain additive state and
   replay/idempotency evidence, restore only compatible prior runtime/configuration,
   and read back actual graph. Never restore API Cron, purge queues, drop migrations,
   delete stores or resend an unknown provider submission.

Timeout/failed read is UNKNOWN, not resource absence. Capture exact owned response/
receipt coordinates before further work. Do not repeat a write after a lost watch.
Fresh bootstrap is not ordinary maintenance; see [recovery](fresh-mail-bootstrap-workstream.md).

## Durable mail invariants

Address creation spans D1 and Routing, not a distributed transaction. Reserve
ownership/quota first; confirm the exact enabled API-owned literal worker rule
before activation. Disabled rules are not active mailboxes. An ambiguous activation
write may have committed: use exact owner/rule readback as positive evidence and
preserve the route for state-aware reconciliation. Never inline-delete or issue a
second provider create to compensate for uncertain D1 state. Failed readback proves
nothing. Active state must not be marked for a reconciler branch that deletes routes.
Retired names remain reserved; route retirement precedes ownership release.

Outbound provider acceptance and delivery differ. Keep accepted/unknown journals,
one-submission idempotency and fenced HTTP/maintenance projection. Publish content/
chunks/storage-ledger/terminal state only when the matching owned projection is
complete. Deferral preserves drafts/reservations; it cannot resurrect deleted mail
or authorize a second send. Maintenance phases have bounded budgets/deadlines and
fair scheduling; do not bypass resource permits with compensation SQL or hide
deferred work as success. See [indexing](semantic-indexer-operations.md).

## Release and maintenance discipline

Release tags build five native archives, skill bundle and SHA256SUMS; verify exact
published bytes and provenance. Published site state requires a real nondraft
Release with expected assets. Candidate site deployment cannot imply release or
send authorization. Keep user manual, command help and packaged skill aligned.

Prefer a small static set of product-contract tests and existing platform lanes.
Document durable semantics/decisions here, not a new per-task audit ledger. Delete
unused experiments; Git history is the archive. This follows production
[SRE simplicity](https://sre.google/sre-book/simplicity/): maintenance machinery must
serve user value, not become the product.

Recent [pipeline-aware test optimization research (ICST 2025)](https://arxiv.org/abs/2501.11550)
also separates fast feedback from costly acceptance. Its learned selection system
addresses large industrial pipelines; this project uses a small explicit suite
instead of adding another selection or coverage platform.
