# Product ADR: scheduled-only Mail maintenance Worker

Date: 2026-10-01. Status: **implementation-ready design; not implementation,
deployment authorization, privacy acceptance, or resource admission**.
Source/config/workflow baseline: main `6d149ee1ffdda89c2d08f1279ff2b0b8b974f4cf`.
Predecessors: observation ADR `c0e88569c87217de54e39dd47f6d4addf2a9e086` and
independent review `2811010ecbeff429f66c8b4e15ebf6febca796a8` (available as Git
objects, not baseline files). This decision develops conditional B into a product
topology. It does not silently turn partial A evidence into three-resource proof.

## 1. Decision and product boundaries

Choose **one persistent scheduled-only Rust Mail maintenance deployment per
realm**, alongside the existing public API. Reuse the same compiled Mail business
artifact with two small, checked-in JavaScript entry adapters. Do not copy the
eight maintenance phases, introduce an HTTP/RPC invocation hop, split phases into
eight scripts, or create a generic scheduler/deployment framework.

The split has a product purpose beyond a measurement experiment: HTTP and
maintenance have independently owned execution surfaces, capabilities, and
release pins. The API retains its stable name, route, ingress service binding,
auth, wire contracts, foreground transports, and necessary trace Queue producer.
Scheduled maintenance retains the same durable ownership and phase semantics.
It is not a one-off measurement Worker that calls back into the mixed API.

```text
CLI / HTTP / existing ingress service binding
                    |
          amail-mail[-staging] (fetch only)
                    |                    \
                    |                     TRACE_EVENTS producer ----+
          same-realm MAIL_DB / MAIL_BODIES                            |
                    |                                                v
          amail-mail-maintenance[-staging]                 unchanged Queue + DLQ
          (scheduled only, natural five-minute Cron)                 |
                    |                                                v
                    +---- TRACE_EVENTS producer --------> Queue-only trace sink

native adaptive metrics = exact maintenance script + actual version + UTC window
```

The expected steady Queue producer set is exactly
`{amail-mail, amail-mail-maintenance}` or the exact `-staging` pair, never a union
with historical role-monitor. The API producer does **not** disappear when its
old Cron disappears. API routes, Email ingress/events, site release and public
send holds are not changed or admitted by this split.

## 2. Baseline findings that constrain the implementation

| Baseline owner | Observed contract | Required integration change |
| --- | --- | --- |
| `crates/mail-worker/src/lib.rs` | `#[event(fetch)]` and `#[event(scheduled)]` share one crate; scheduled runs eight rotated phases with one `MaintenanceBudget` and one `MaintenanceTurn` | Select the entry surface outside the business binary; keep dispatcher/accounting unchanged |
| `crates/mail-worker/wrangler.toml` | Production and staging both track `*/5 * * * *`; API public routes and trace bindings coexist | Permanently change both API Cron arrays to explicit `[]`; new maintenance config owns future cadence |
| `infra/deploy/ensure_trace_queues.py` | Closed `api-only` / historical `api-role`; strict readback requires exact producer count, names, consumer settings, Queue identities and one-day retention | Add one explicit `api-scheduled` topology, not permissive additional producers |
| `deploy_production_mail.py` / `pin_staging_mail.py` | Staging deploy demands `AMAIL_TRACE_TOPOLOGY=api-only`; immutable API bindings plus exact single-100 deployment are pinned | Permit the explicit selected split phase; API binding contract otherwise stays unchanged |
| `prepare_production_graph.py` / `check_production_role_graph.py` | Production bootstrap/API-only maintenance are selected explicitly; role absence, held sends, exact API/sink pins and four direct forwards are bracketed | Add direct-only split stages without enabling historical role rollout or reading its ledger |
| `.github/workflows/ci.yml` | Check `worker` uses worker-build 0.8.5; Mail `deploy-worker` and `staging-worker` install 0.8.3; sink uses 0.8.5 | Align Mail checks/deploys to 0.8.5 and test the actual adapter/module graph |
| CI writer control | Production workflow-level `amail-production-graph-writer` covers only current production targets; staging uses job-level `staging-native-mail-acceptance` locks, including separate sink/API jobs | Extend production target classification and put the whole staging split transition under one non-cancelling graph-writer workflow lock |
| `infra/ci/worker_cache_key.py` | Fingerprints committed `crates`, `workers`, boundary tests and whole `worker` job; deploy jobs do not consume its project cache | Put adapters under `crates/mail-worker`; do not import new untracked external build inputs |
| `workers/trace-sink` | Queue-only, validates shared closed `Record` schema before logging, invocation logs off; existing diagnostic records already accepted | Preserve schema/sink policy; split producer ownership changes even with zero record-schema changes |

This design must be rebased after active PR31 / accepted-batching integration.
It assigns no changes to `accepted.rs`, accepted SQL/journals, budgets/deadlines,
or existing batching/race fixtures. Re-run their established hosted tests against
the rebased artifact; do not copy their logic into a new crate to avoid conflicts.
The separately owned accepted-0010 fenced-runtime cutover takes precedence where
applicable: independently establish its schema/version and old unfenced HTTP
completion/termination gates first. This split does not drain old HTTP: current
foreground work has no general hard lifetime bound. Fetch-only replacement and
Cron drain cannot certify that an old projection HTTP/replay stopped writing.
If that cutover has already emptied old API Cron, preserve the actual empty
predecessor; never reactivate it merely to follow the diagram or state table.

## 3. Entry adapter and artifact contract

Source inspection matters here. Cached worker-build 0.8.3/0.8.5 and upstream
0.8.5 commit `cc174db40ba9f648623805e98053a4eba3bb50c0` show that the default
generated shim is a **Proxy-wrapped WorkerEntrypoint class**, with generated
handler methods and initialization/reset recovery. `build/worker/shim.mjs` is a
compatibility alias to `build/index.js`. It is not an object whose `scheduled`
property can simply be copied. [Pinned upstream generator](https://github.com/cloudflare/workers-rs/blob/cc174db40ba9f648623805e98053a4eba3bb50c0/worker-build/src/main.rs),
[pinned recovery shim](https://github.com/cloudflare/workers-rs/blob/cc174db40ba9f648623805e98053a4eba3bb50c0/worker-build/src/js/shim.js).

**Chosen contract:** platform-level adapter uses composition, not inheritance
from BuiltMail. An illustrative interface (documentation, not an installed
prototype) is:

```javascript
import { WorkerEntrypoint } from "cloudflare:workers";
import BuiltMail from "../build/worker/shim.mjs";

/** Sole maintenance entry surface; keep the generated SDK recovery boundary. */
export default class MailMaintenance extends WorkerEntrypoint {
  /** Execute in this invocation with its original event, environment and context. */
  scheduled(event) {
    const mail = new BuiltMail(this.ctx, this.env);
    return mail.scheduled(event);
  }
}
```

`crates/mail-worker/entry/api.mjs` symmetrically exposes only `fetch(request)`
and delegates to `new BuiltMail(this.ctx, this.env).fetch(request)`.
Both import the exact same generated module tree from one `worker-build --release`
execution within a release job. The Wasm byte digest must match for the two
uploads; the entry modules/Worker version IDs are intentionally different.
Default 0.8.5 module mode is mandatory: reject `CUSTOM_SHIM`, `RUN_TO_COMPLETION`,
`COREDUMP`, `--no-panic-recovery`, and unexpected exported entry classes/handlers.

Why composition: extending BuiltMail inherits `fetch`, contaminating the
scheduled-only surface; calling a raw Wasm export bypasses the SDK wrapper;
copying/proxying every generated method recreates an SDK. A normal same-isolate
method call neither invokes another Worker nor moves CPU/memory to an API script.
Return the underlying Promise and preserve `ctx.waitUntil` ownership; never
fire-and-forget or catch-and-relabel errors in the adapter. Construct per event,
keep environment/context invocation-scoped, and do not add a global Env cache.

The final upload's top-level exported application interface must be exactly one
default adapter class. No `export *`, named entrypoint/RPC export, queue/email/
tail/test handler, or inherited application `fetch` is permitted on maintenance.
Internal generated imports may contain unused business methods; they are not a
deployed entrypoint. Do not pretend this is cryptographic removal of HTTP code.

This constructor/Proxy/lifetime contract is a source-grounded **candidate**, not
yet validated against deployed workerd. Credential-free hosted validation must
exercise the real generated shim, including scheduled completion and recovery.
If composition cannot preserve runtime semantics, stop that slice and extract
one shared Rust maintenance dispatcher plus a minimal scheduled crate. That is
a bounded fallback, not permission to duplicate eight implementations or invoke
the API remotely. No toolchain/date upgrade should masquerade as split evidence.

## 4. Data ownership, bindings and privacy

No D1 migration, R2 relocation, new durable coordinator, or per-script quota
partition is part of this change. D1 journals/claims/fences remain authoritative;
Worker/version identity is **not** a new owner of an accepted record. Preserve
exact accepted provider identity, immutable ZIP, unknown/submitting/accepted
protection, projection lease/token checks, quota charging, tombstones, and full
valid-item completion. HTTP and new Cron retain existing concurrent access.
API sends are never retried because a maintenance version was rolled back.

Five-minute Cron already allows multiple executions within a 15-minute lifetime;
separate scripts remove HTTP/Cron isolate competition, not Cron/Cron overlap.
Per-item CAS/leases remain necessary. No new global lease is justified solely
by analytics. Intentionally running old and new schedulers concurrently is not
allowed: every cleanup phase has not been proven duplicate-safe.

| Capability | Existing API | New maintenance |
| --- | --- | --- |
| `MAIL_DB`, `MAIL_BODIES` | Unchanged reviewed realm resources | Exactly the same realm's resource IDs/names; reject cross-realm or extra D1/R2 |
| `TRACE_EVENTS` | Remains producer | Producer on the same existing realm Queue |
| `CF_ZONE_ID`, `EMAIL_INGRESS_WORKER_NAME` | Unchanged | Required by routing inventory/repair; exact reviewed realm values |
| `OPENROUTER_EMBEDDING_MODEL` | Unchanged | Required by background reindex; same reviewed model |
| `CF_EMAIL_ROUTING_TOKEN`, `OPENROUTER_API_KEY` | Unchanged | Separately provisioned on this script; same reviewed realm scope/policy |
| `EMAIL`, production `OFFICIAL_EMAIL` | Unchanged | Forbidden: Cron projects accepted archives, it does not submit mail |
| `INGRESS_SECRET`, OIDC issuer/client, `ADDRESS_DIAGNOSTICS` | Unchanged | Forbidden; no auth or ingress endpoint |
| `MAIL_DOMAIN` | Unchanged | Omitted in the baseline scheduled call graph; add only if rebased source demonstrates a maintenance need |
| `VERSION_METADATA` | No API contract change in this slice | Explicit version metadata binding, checked in immutable version capability readback |

New `crates/mail-worker/wrangler-maintenance.toml` selects
`entry/maintenance.mjs`, with explicit production/staging names. Pin the existing
Mail `compatibility_date = "2026-09-25"` and flags for this split, rather than
coupling it to an unrelated runtime upgrade. Declare every realm's bindings and
vars explicitly. D1/R2 IDs must be provided; no automatic resource provisioning.
Resource equality is validated by binding name, never list position.

For both maintenance realms explicitly set `workers_dev=false`,
`preview_urls=false`, `routes=[]`, `logpush=false`, and all capture subsystems
off: observability, logs, invocation logs, traces, Issues. No public custom
domain/route, version URL, preview endpoint, assets, inbound service binding,
Queue consumer, email trigger, Tail consumer, or auxiliary alarm/RPC entrypoint.
Absence of a fetch implementation is not enough: even a failed attempted HTTP
invocation can contaminate a native population. Do not health-probe this script.
[Wrangler configuration semantics](https://developers.cloudflare.com/workers/wrangler/configuration/).

Provision secrets only in a protected realm job using an exact two-name secret
allowlist and the existing redacted `--secrets-file` pattern, temporary mode-0600
file under root `.temp`, cleanup on all exits. New scripts do not inherit secrets
from API or default environments. Do not print secrets or provider envelopes,
retry ambiguous deploy writes, or accept the returned version as a binding pin.
Use immutable version binding readback plus serving deployment brackets.
[Production binding/secret guidance](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/),
[actual runtime version metadata](https://developers.cloudflare.com/workers/runtime-apis/bindings/version-metadata/).

Inbound bindings are controlled by the tracked application graph and all
authorized writers: static repository check rejects any service target naming
maintenance; exact known deployed callers keep their expected binding contracts.
Freeze dashboard/other deployment writers and restrict creation of such bindings
under the operational authorization. Current-script settings do not reveal all
possible external callers. If the account permits unaudited writers/callers, mark
`population_isolation=UNVERIFIED`; do not broaden into an unreviewed account-wide
version/binding crawl or infer absence from a failed read.

Keep existing typed Queue diagnostic records unchanged (`Service::Mail` remains
compatible). Existing sink validates data, not producer script identity; Queue
control-plane ownership establishes producers. New terminal/invocation summary
schema and changes to accepted batching are **out of scope**. If independently
approved later, roll compatible sink/schema before any producer, retain old-record
acceptance through Queue/DLQ retention, and never emit arbitrary IDs/error prose.
Producer Logs/Tail/Logpush/Issues remain off irrespective of typed sink retention.

## 5. Closed graph states and persistent trigger ownership

Use a small fixed enum per realm, not state inferred from the provider's latest
inventory. A protected transition attestation records state, source SHA, API/
maintenance/sink version and deployment IDs, resource/Queue pins, trigger sets,
artifact/toolchain digests, last write/readback timestamps, operator drain
disposition, and predecessor attestation. Normal public output contains fixed
labels and reviewed release tags; no raw provider response, MIME or ledger rows.
Private metadata is bounded and never includes secret values. It is an operator
release record, not a new Mail DB table or orchestration service.

| State | Strict Queue topology | API Cron | Maintenance Cron | Allowed next write |
| --- | --- | --- | --- | --- |
| `legacy-pinned` | `api-only`, maintenance script absent | Reviewed existing set | Absent | Prepare graph checks; independently safe API replacement if authorized |
| `prepared` | `api-scheduled`, both exact producers | Reviewed legacy set | `[]` | Remove old API schedule and select fetch-only API adapter |
| `old-draining` | `api-scheduled` | `[]` | `[]` | Readback/wait/drain only; no new activation |
| `paused` | `api-scheduled` | `[]` | `[]` | Activate only after explicit admission of prior drain; or safe replacements preserving pause |
| `active` | `api-scheduled` | `[]` | Exactly `*/5 * * * *` | Independently pinned API/sink/maintenance replacement preserving graph and cadence; or disable maintenance |
| `new-draining` | `api-scheduled` | `[]` | `[]` | Readback/wait/drain only; no scheduler restore |
| `legacy-recovery` | Explicit `api-only` or `api-scheduled` as attested | Explicit restored legacy set | `[]` | Separately reviewed recovery, not normal split deployment |

`prepared` is an exact two-producer graph immediately when the no-trigger Worker
attaches its Queue binding. It is not valid to keep testing `api-only` until Cron
activation. First two-producer deploy may be non-atomic: pre-readback must match
exact one-producer predecessor; post-readback must match exact two-producer
successor. An ambiguous result is an interrupted transition requiring reconciliation,
not a permissive `{one or two}` maintenance policy or automatic replay.

Extend `ensure_trace_queues.py` only with `api-scheduled` strict **readback**;
retain api-only provision/recovery behavior and historical api-role tests intact.
No new Queues are needed for a split of an already provisioned realm. Consumer,
DLQ, retention, counts and complete inventory predicates remain unchanged. Require
one consumer sink and no DLQ producers/consumers. Wrong role, unknown, duplicate,
cross-realm, missing API and maintenance-only sets all fail closed.

**Permanent API rule:** both root/staging tracked API `crons=[]` after split
implementation, API main becomes `entry/api.mjs`, and every normal API deploy
and readback enforces those empties. Omission is forbidden. No config generation,
old Actions checkout, normal code rollback, or historical helper may restore the
old schedule. API normal-deploy preflight rejects a legacy state; entering
`legacy-recovery` requires a separately reviewed recovery config/source exception.
Legacy live triggers before cutover are explicitly a migration predecessor,
not allowed by normal API source. Deployment freezes prevent merging config
changes from becoming an unplanned production Cron removal.

Maintenance config initially tracks `[]` in both realms. Activation is a reviewed
config change to that realm's cadence plus the separately authorized trigger
write; normal maintenance deploy later requires `active` state and preserves the
tracked exact cadence. A pause/emergency disable uses an exact-name empty-trigger
write, records `paused`/`new-draining`, and blocks normal active deployment until
an explicit resume or a checked-in paused config is selected. API/sink replacement
can remain legal during a stable pause. Do not leave cadence restoration to an
unconditional later `wrangler deploy` from a stale checkout.

Cron triggers are script-level non-versioned settings, not part of code rollback.
Maintain source configuration as desired truth and independently read the actual
schedules endpoint. Empty `crons` removes; omission leaves live triggers untouched.
Propagation may take up to 15 minutes; new-name Cron event visibility can lag.
[Official Cron contract](https://developers.cloudflare.com/workers/configuration/cron-triggers/).
The narrow transition helper uses only the fixed selected script's
`PUT /accounts/{account_id}/workers/scripts/{script_name}/schedules`, with body
`[]` for stop/pause or `[{"cron":"*/5 * * * *"}]` for authorized activation;
then exact `GET` readback requires the complete `result.schedules` set. It never
accepts arbitrary cron/name/URL input, edits an unknown predecessor or retries
an ambiguous PUT. [Schedules update API](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/schedules/methods/update/),
[schedules readback API](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/schedules/methods/get/).

## 6. Cutover runbook (staging first, then separately authorized production)

1. **Review/hosted source gates.** Rebase after PR31 and accepted batching; land
   adapters/config, exact graph validators, deployment/state guards and tests
   before any split provider mutation. Independently review the deployed module
   surface and closed metric reader. Keep existing Issues acceptance and send
   holds unchanged. Authorization is per realm and per phase, not implied by merge.
2. **Freeze graph writers.** Exact approved source/check run/toolchain, protected
   realm/branch confirmation, and one realm-wide non-cancelling workflow lock.
   Freeze dashboard/out-of-band writers, other API/sink/ingress/settings/trigger
   jobs and Cron-invoking experiments. Existing production lock is extended;
   staging job locks alone cannot protect the interval between sink/API jobs.
   Do not nest identical workflow/job concurrency keys and deadlock yourself.
3. **Pin predecessor.** Current exact API/sink deployments, immutable bindings,
   effective capture-off (including independent Issues), old triggers, private
   producer graph, direct forwards/ingress targets, held sending and resource
   identities. Do not assume tracked Cron proves the live predecessor. Unknown
   state or failed readback stops before mutation. No migrations for the split.
   Require the independent accepted-fence/schema cutover attestation when the
   selected artifact depends on it; never reuse a split drain as its HTTP drain
   evidence. The split workflow must not call the ordinary deploy jobs' remote
   migration steps as a side effect. A future unrelated schema migration remains
   a separately authorized compatibility/cutover operation.
4. **Prepare new script.** Explicit `[]` Cron, required independent secret
   provisioning, same D1/R2, same Queue, no routes or extra capabilities. Capture
   exact returned version for recovery without replay; bracket serving readback,
   immutable version resources, current privacy/surface/trigger settings and
   exact two-producer Queue successor. API/sink/forwards remain unchanged. Record
   `prepared`. No fetch, test endpoint, remote scheduled test or synthetic seed.
5. **Stop old dispatch.** Deploy independently safe API fetch-only adapter with
   tracked root/staging `crons=[]`, retain API producer/routes, and capture/pin
   new API version. Bracket readback confirms old API schedule empty, new
   maintenance schedule empty, graph/resources/privacy/holds unchanged. Record
   `old-draining` and the last acknowledged empty-trigger write/readback time.
   An already-running legacy version may continue; absence of scheduled on the
   new API wrapper is defence in depth, not evidence of global propagation.
6. **Drain and decide.** Budget at least 15 minutes for trigger propagation plus
   15 minutes for any execution started at the propagation boundary; use last
   acknowledged stop time conservatively and restart this budget on any trigger
   drift/write. Bracket old/new serving identities and both empty trigger sets
   at entry, propagation boundary and final drain readback; preserve the freeze.
   Check known admitted old work/claim outcomes through existing privacy-safe
   evidence without deleting/releasing claims, inspecting private mail or
   inventing a native/application timestamp join. Record the bound assumed,
   latest known old start and operator disposition. The 30-minute elapsed
   budget alone is **not** documented proof against delayed starts/retries,
   deploy propagation or delayed analytics. Missing Queue summaries/native rows
   are not drain proof. If dispatch/lifetime assumptions or active ownership
   cannot be established, record `drain=UNVERIFIED`, keep both schedules empty
   in `paused`, and require a bounded operator/vendor-supported resolution.
7. **Activate new only.** Explicitly admit drain, recheck graph immediately
   before writing, commit/select realm's reviewed maintenance Cron cadence,
   apply exact-name trigger update and read it back without assuming code
   version changed. API schedule must stay empty before and after. Pin new
   script/version/privacy/resources twice, retain freeze and record `active`.
   Do not release public sending or change Issues/capture to obtain metrics.
8. **Observe and accept separately.** Run the small natural-event discriminator
   below; only after it succeeds plan representative resource windows. Resource
   failure or incomplete work pauses maintenance for investigation. Staging
   success does not admit production's distinct data/load/resource graph.

Readback must bracket `deployments` single-version/100%, immutable `versions/{id}`
resources, current settings/worker surface/route/subdomain/preview state and
script schedules, plus Queue ownership and forwarding snapshots. Require the
same deployment IDs and exact pin versions before/after nonversioned reads;
reject split percentages, unknown/extra bindings, malformed/truncated response,
stale source attestations or drift. Reuse existing bounded privacy predicates
and readers; add a narrow exact maintenance selector rather than relaxing API
checks. Settings alone are not immutable version-capability proof.
[Version/settings separation](https://developers.cloudflare.com/workers/versions-and-deployments/).

## 7. Rollback and interrupted writes

Preferred rollback keeps the split: disable new triggers, enter `new-draining`,
apply the same propagation-plus-execution decision and pin both empty sets,
then deploy a previously safe maintenance artifact in `paused`. Preserve API
fetch-only, API `crons=[]`, exact two-producer Queue, sink compatibility, accepted
journals and shared state. Re-enable only through the explicit `paused -> active`
transition after readback; never roll back code while leaving an unsafe schedule.

Full topology rollback is exceptional: drain new first, choose independently safe
legacy API code/privacy pin with a checked recovery config, then explicitly
restore only the old Cron set in `legacy-recovery`. Source old-Cron restoration
must be a reviewed recovery change; future normal API deployment stays blocked
until returning to the split. The disabled new script may remain as the exact
second producer (explicit `api-scheduled` recovery graph), avoiding deletion and
schema retention problems. If removal is required, separately detach its Queue
binding or delete the already-drained new script, reconcile exact `api-only`
successor and all versions/bindings before restoring old dispatch. Never detach
the API producer, purge Queue/DLQ, revert Mail data or blindly overwrite drift.

If a deploy/trigger write times out or returns an unclear version, do not retry.
Read only the exact expected scripts/resources to reconcile predecessor/successor;
an unrecognized intermediate graph remains held with both schedules off where
safely established. Never infer absence from HTTP failure. Maintain recovery
version/attestation even on later verification failure. External writes and D1/R2
data are not reverted by code rollback; lease expiry is not an operator licence
to clear journals. [Cloudflare rollback boundaries](https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/).

## 8. First native availability discriminator and evidence labels

The product split removes a missing event discriminator only if **natural
scheduled events actually populate adaptive metrics**. Schema visibility does
not prove this. The first observation is an access/inclusion experiment, not a
stress test, performance regression claim, or peak-memory gate.

After separately authorized isolated deployment/cutover and safe freeze:

- Privately pin the exact maintenance script, single serving version and closed
  UTC window after propagation/drain. Ensure no other entry surface/invocation,
  no deploys and no synthetic scheduled dispatch. Observe natural completed ticks.
- Use a separately reviewed fixed schema/type/unit contract for
  `workersInvocationsAdaptive`: exact `scriptName`, exact `scriptVersion`,
  `datetime_geq`, `datetime_lt`; query selected count/status/dimensions and
  `cpuTimeP99`, `wallTimeP99`, `memoryUsageBytesP99`. Do not invent event filters
  absent from the supplied schema or infer CPU/wall units from field spelling.
  Count/sampling helper fields require their own named schema check, not recursive
  discovery. If scalar/unit/filter contract remains unknown, stop numeric claims.
- Read one small closed 20-minute completed window, with a predeclared telemetry
  grace and one bounded delayed requery (for example 60 minutes, not infinite
  polling). Cron Past Events visibility delay is not an adaptive freshness SLA.
  Exact bounded scheduled CPU rows can separately show natural events, but do
  not join individual rows to adaptive/application records by nearby timestamps.
- Bound reader to at most 64 result groups, 256 KiB response, 20-second request,
  closed query/document/window and zero provider-response artifact upload. Full
  result limit, partial errors, unknown dimensions, mismatched version, malformed
  unit/value or incomplete sampling semantics remain non-admitting. Convert only
  after the fixed unit contract; emit fixed availability/coverage labels and
  approved bounded aggregate values, never raw rows/error prose/IDs.
- Before/after readback rechecks script/version/deployment, capture switches,
  no-route/no-preview surface, both trigger sets and exact two-producer graph.
  Any contamination invalidates the population claim even if metrics look cheap.

Outputs distinguish `scheduled_presence={observed,unverified}`,
`adaptive_scheduled_inclusion={observed,unverified}`,
`cpu_wall_units={verified,unverified}`, `memory_scope=sampled_shared_isolate`,
`resource_admission=UNVERIFIED`, and unchanged Issues/send gates. No data, denied
access, null quantiles, sampling loss or delayed delivery is **inconclusive**, not
zero cost. If scheduled presence is observed but adaptive inclusion is not,
seek a bounded vendor clarification or retain A diagnostics; do not enable raw
capture, add a fake fetch canary or claim B succeeded automatically.

Only then measure repeated comparable windows covering all eight rotation
positions, maximum service-valid ZIP/HTML complete-item work, accepted repair,
routing inventory, embedding stalls, cleanup/backlog and realistic Cron overlap.
Natural empty ticks cannot establish those workloads; any hosted synthetic
seeding/provider writes need separate authorization. Keep failures and deferred/
completed work separate from resource quantiles, report samples/coverage/lag,
and do not average P99 buckets or call them maxima. Same-resource D1 aggregates
still combine API/Cron: moving the script does not create per-Cron D1 telemetry.

**Measurement contract:** provider CPU/wall are reservoir-sampled quantiles;
wall includes registered background work. Memory is invocation-time **shared V8
isolate usage**, not peak invocation allocation, Wasm-only memory, exclusive Cron
memory or peak RSS. Splitting isolates removes HTTP competition, not simultaneous
Cron, rare over-limit allocation or lost final records. Low memory P99 is never
a hard 128 MB proof. Keep bounded-input/allocation reasoning and complete valid
maximum-item/failure evidence alongside native observations.
[Native metrics semantics](https://developers.cloudflare.com/workers/observability/metrics-and-analytics/),
[memory fields in bytes](https://developers.cloudflare.com/changelog/post/2026-06-30-memory-usage-metrics/),
[GraphQL sampling](https://developers.cloudflare.com/analytics/graphql-api/sampling/).

The Paid five-minute Cron CPU ceiling is 30 seconds and scheduled duration ceiling
is 15 minutes; do not transplant the HTTP five-minute CPU setting. Local R2/
embedding deadlines in `6d149ee` are not hard whole-Cron wall or remote-cancel
guarantees. [Applicable runtime limits](https://developers.cloudflare.com/workers/platform/limits/).

## 9. Minimal implementation slices and hosted verification graph

| Slice / minimal path diff | Scope and acceptance |
| --- | --- |
| 1. `crates/mail-worker/entry/{api,maintenance}.mjs`, API TOML main/empty crons, new maintenance TOML | Composition adapters, exact surfaces, paused per-realm config, shared artifact; no Rust business/schema edit |
| 2. `infra/deploy/ensure_trace_queues.py`, its existing tests | One new exact `api-scheduled` readback producer set; preserve legacy defaults/consumer/retention/inventory fail-closed checks |
| 3. `infra/deploy/check_mail_maintenance.py` (narrow new checker), `check_staging.py`, API pin/deploy helpers, production prepare/graph helpers | Exact realm/resource/capability/privacy/version/trigger predicates; fixed stage enum and transition guards; no generic registry/orchestration |
| 4. New `infra/deploy/deploy_mail_maintenance.py` and bounded split transition/attestation helper | Fixed names/realm/secrets, redacted ambiguous-write recovery, trigger state transition, caller-selected predecessor and exact successor; reuse readers/predicates |
| 5. `.github/workflows/ci.yml`, workflow contract tests, `infra/ci/worker_cache_key.py` tests if inputs change | Align 0.8.5; credential-free source checks; protected explicit staging/production prepare/stop/activate/pause/resume phases and split steady-maintenance targets; extend whole-graph concurrency; do not make `target=checks` deploy |
| 6. `infra/tests/worker-boundary/mail-entry-split.test.mjs` plus existing fixture integration | Real generated adapter/module tests and same-resource race/recovery/phase/accounting regression graph |
| 7. Fixed privacy-reviewed metrics reader/workflow (separate approval) | Natural scheduled adaptive inclusion/type/unit check; no provider access before safe split deployment |

Do not edit the sink/schema just to create a second producer. If unrelated changes
require a new sink version, its normal split-maintenance path must read
`api-scheduled` before and after replacement; legacy `staging-trace-sink` and
production api-only maintenance cannot execute their old checks in a migrated
realm. Keep existing command defaults strict for legacy callers, and require
new explicit topology/stage selections rather than silently autodetecting them.
Normal `staging-worker`, production bootstrap/replacement, ingress dependent jobs,
API/sink privacy readbacks and graph attestation labels must all acknowledge the
selected graph; post-split legacy deployment targets fail before any write.

Hosted test DAG (design obligations; **none executed locally for this ADR**):

```text
closed config/workflow/Queue/state tests (no credentials)
                       |
       worker-build 0.8.5 real Mail artifact, once
                       |
  actual API adapter + actual maintenance adapter + same Wasm digest
          /                        |                         \
existing API contract       real scheduled eight phases       negative surfaces
and ingress tests           budgets/deadlines/accepted        no fetch/RPC/consumer
          \                        |                         /
             shared local D1/R2 race/recovery regressions
                       |
      independent source review + hosted checks exact SHA
                       |
 separate realm authorization + freeze + pin + cutover/drain
                       |
 natural-event adaptive availability discriminator (not resource admission)
                       |
 representative windows + completion/failure evidence + separate acceptance
```

Pure tests cover every state/edge, no transition inferred from inventory, duplicate
producer rows/count mismatch, missing API/new producer, wrong realm/role/unknown
producer, extra capabilities, enabled Issues/preview/route, omitted/nonempty API
crons, split traffic, missing/wrong/stale version, concurrent graph drift,
partial/oversized response, ambiguous deploy/trigger outcomes, no write replay,
and rollback leaving both schedules active. Test known caller service bindings
cannot target maintenance and no API rollback restores Cron implicitly.

Hosted workerd tests load the real generated module tree and adapter; don't assert
only source strings or invoke the mixed shim and call that scheduled-only proof.
Assert the actual exported adapter interface, no inherited app fetch, preservation
of event.schedule/cron, same Env/context, await/waitUntil completion, panic/reset
boundary, per-invocation state isolation, exactly one phase dispatcher, all eight
rotations and unchanged 800-statement accounting. Shared D1/R2 HTTP/Cron accepted
races and existing deadline/boundary/liveness suites must run against selected
entry adapters. Test-only service observers remain local, cannot become deploy
inputs. Use root `.temp` / `.cache` for generated bundles/fixtures; production
config dates remain distinct from a harness's supported workerd date.

The production experience is explicit configuration truth, platform bindings,
complete readback and staged release under one writer, not hopeful retries.
The research connection is controlled pre-production comparison under noisy
infrastructure: [ServiceLab, OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/chow).
Adopt repeated workload-matched comparisons and separate availability from
performance confidence; its hyperscale sensitivity does not certify rare
five-minute-Cron tails. The first informative result is whether the isolated
natural population exists in adaptive metrics at all.

## 10. Unresolved assumptions with decisive next checks

| Unresolved fact | Smallest decisive check / non-admitting outcome |
| --- | --- |
| Composition preserves real SDK Proxy/runtime lifecycle | Hosted real-shim adapter test on aligned deploy 0.8.5; failure selects shared-dispatcher fallback |
| Rebased maintenance requires only the listed capabilities | Static call-graph + real minimal-binding scheduled fixture after PR31/batching rebase; any missing capability is reviewed explicitly |
| Drain can be accepted without prohibited raw capture | Authorized pinned stop/drain protocol and bounded operational/vendor evidence; uncertainty leaves both schedules off |
| Exact-version native scheduled events populate adaptive fields | First separately authorized natural-event closed-window discriminator; missing data remains unverified |
| Unit/sampling/filter contract supports a numeric comparison | Fixed named schema/type and official units clarification, no recursive discovery or dataset fallback |
| Split work fits under representative load | Subsequent complete maximum-valid-item and overlap windows; quantiles alone do not admit peak memory |

## Artifact verification

Selected internal knowledge by filenames and inspected exact baseline source,
Queue/sink, deploy helpers, graph/pin predicates, CI/cache contracts; retrieved
public Cloudflare and pinned workers-rs primary documentation on 2026-10-01.
Read existing cached bundler source; did not install or build tools. This isolated
worktree change is documentation only. No local project test/build, provider
call/deploy, credential read, workload, push or PR. Effective capture, Issues
acceptance, public sending, runtime measurements and resource admission remain
unchanged.

## Implementation checkpoint (2026-10-01)

The initial source slice changes both API trigger arrays permanently to empty,
adds a paused scheduled-only configuration and composes both platform entrypoints
over the same generated worker-build 0.8.5 SDK/Wasm graph. Exact same-realm Queue
producer validation admits the API + maintenance pair only in readback mode.
Source/capability/serving checkers and mock contracts are included. Activation,
provider writers, trusted state-artifact consumption and runtime population/CPU
admission are separate follow-up implementation, not provided by this checkpoint.
No automatic deployment is added. Normal legacy deployment paths retain their
existing api-only topology guard; a split graph cannot silently pass that guard.
The previous API pin check now explicitly requires fetch-only + no schedules;
legacy predecessor reads must use the separately bounded migration graph reader,
not pretend legacy code is the desired split API.

The actual-SDK harness is integrated against the post-PR33 source, preserving
accepted staging batches and the final Queue timeout cases. Hosted source CI is
required before any provider write; local project builds/tests remain prohibited.
