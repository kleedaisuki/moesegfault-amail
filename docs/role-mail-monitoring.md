# Architecture finding: monitored system-role mail after the Junk-folder canary

## Source-only staged shared-Queue rollout contract (2026-10-01)

**Implementation is not deployed acceptance.** The reviewed typed role producer
shares the private trace sink with Mail, but role deployment is now a distinct
`staging-role-queue-rollout` manual target rather than an automatic consequence
of a broad staging deployment. Production's four exact direct forwards are
unchanged, `abuse_contact_verified=0` and public sending remain held. No role
SMTP/Cron delivery or retained-record privacy success is claimed here.

| Stage | Exact events-Queue producers | Consumer | Required evidence |
| --- | --- | --- | --- |
| Initial sink provisioning | Empty, then sole `amail-mail-staging` | Sole `amail-trace-sink-staging` | Existing bounded create/readback and original-context capture-off containment |
| Phase1 accepted before role mutation | **Exactly** `amail-mail-staging` | Same sole sink, same reviewed Queue/DLQ IDs | Successful immutable phase1 API/sink rollout plus a separate actual bounded retained-record privacy canary |
| Phase2 readback after one role deployment | **Exactly** Mail API and `amail-role-monitor-staging` | Same sole sink, same reviewed Queue/DLQ IDs | Stable single-100 API/sink/new-role versions, exact serving resources, strict role capture-off, absent synthetic route, empty isolated ledger and expired lease |

`ensure_trace_queues.py --phase readback --topology api-only` remains the strict
default. `--topology api-role` is legal **only** for readback, never provisioning
or partial recovery. The producer array count and exact script set reject
duplicates, missing peers, cross-realm names and arbitrary extras. Both stages
preserve one-day retention, the sole sink's bounded retries and an unattached
DLQ. No topology checker reads, purges or consumes Queue bodies. The shared
sink's explicit `AMAIL_TRACE_TOPOLOGY=api-role` also uses strict readback rather
than inheriting the empty-producer initialization allowance.

The role manual target requires `RUN_STAGING_ROLE_TRACE_ROLLOUT`, the existing
`role_deploy_run` as phase1 provenance, a distinct `trace_sink_canary_run`, the
reviewed API/sink/current-old-role versions, and repository variables
`AMAIL_TRACE_QUEUE_ID_STAGING` / `AMAIL_TRACE_DLQ_ID_STAGING`. Historical evidence
must come from completed successful **first-attempt**, branch-local runs of this
workflow at the exact promoted source SHA, with successful exact API/sink jobs
and a distinct canary job. Same-source promotion is intentional: API, role and
sink share a closed schema; a newer role must not silently use an older sink
whose schema has not been proved compatible. A marker from a preflight or a
configuration-only check is not whole-record privacy acceptance. The sink's
non-secret version/Queue marker is emitted only after its isolation readback;
the separate bounded-privacy marker only after the real retained-record canary.

`check_role_trace_rollout.py` brackets **all three** serving deployment/version
identities around exact Queue-ID/topology and effective capture checks, and
rechecks Queue topology as well. Mail's Queue binding comes from the pinned
immutable version resources, not `/settings`. The default
`pin_staging_mail.py --phase pre-queue` remains strict for the historical
settings-only containment version; new Queue-capable callers must explicitly
select `--phase queue-api` and supply `AMAIL_EXPECTED_TRACE_QUEUE_ID`. Missing
pins fail before provider access; a default pin never silently adopts a new
Queue capability.

The role deployment captures only its exact new version, never raw Wrangler
output, and uses one restricted secrets file under repository `.temp`, deleted
after every outcome. It never automatically retries an ambiguous deploy. A
captured new version is a recovery pin, not a successful phase2 attestation.
On any later readback failure, do not rerun deployment: inspect the exact new
version and Queue attachments read-only, keep the synthetic route absent and
sending held, and reconcile deliberately. External deployment/configuration
writers must remain frozen through each transition; read brackets detect drift
at their observations, not an atomic provider transaction or changes that occur
and revert between reads. Role Email/Cron full-record canaries, operational
lease/fault tests and external original/digest delivery still precede production
cutover. The original production-forward rollback policy remains authoritative.

The documented Cloudflare [Queue detail contract](https://developers.cloudflare.com/api/resources/queues/methods/get/)
exposes explicit producer/consumer arrays and totals, and [version readback](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/get/)
supplies immutable resources. Unknown response shapes remain unverified rather
than being treated as equivalent to a configured source declaration.

Status (2026-09-29): **the separate monitor and mail-API lease check are implemented in this branch, but have not passed hosted CI, been deployed, or been accepted**. Four exact `abuse`/`postmaster` rules at the apex and receiving mail subdomain still forward directly to one confidential owner-controlled external mailbox; this branch does not cut them over. Cloudflare reported 4/4 controlled canaries as forwarded/delivered, and the owner confirmed all four arrived **in Junk**. The destination must not be written here or in public logs. Reachability is proved; timely notice and response are not. Keep `abuse_contact_verified=0` and public sending held.

## Why analytics polling cannot be the primary arrival alarm

Cloudflare exposes individual Email Routing events via `emailRoutingAdaptive`, but the `Adaptive` suffix denotes an **adaptively sampled** GraphQL dataset. Cloudflare warns that sampling can miss rare events, and shorter queries only *reduce* that risk. Its GraphQL API has no cursor pagination; using a `limit` and time ordering cannot establish that every same-timestamp event was read under a burst. The 31-day retention and observed 4/4 canaries establish usefulness for reconciliation, not a lossless per-message feed. Therefore a Cron Worker that polls `emailRoutingAdaptive` must **not** drive a once-per-report alert or justify the send gate. The existing `workers/mail-events` Queue consumer cannot be reused: Cloudflare's Email Sending subscriptions explicitly do **not** publish inbound Email Routing/forwarding events. [Sampling](https://developers.cloudflare.com/analytics/graphql-api/sampling/), [rare-event warning](https://developers.cloudflare.com/analytics/faq/graphql-api-inconsistent-results/), [pagination](https://developers.cloudflare.com/analytics/graphql-api/features/pagination/), [Email metrics](https://developers.cloudflare.com/email-service/observability/metrics-analytics/), [event subscriptions](https://developers.cloudflare.com/email-service/platform/event-subscriptions/).

| Approach | Delivery-path change | Per-arrival completeness | Decision |
| --- | --- | --- | --- |
| Keep four provider `forward` rules and poll routing analytics | None | Not established: adaptive sampling and no cursor | **Reject as sole alarm**; useful for aggregate health and canary reconciliation. |
| Keep forwarding and poll the external mailbox's Inbox **and Junk** through its authenticated API | None at Cloudflare | Possible only after proving folder coverage, OAuth renewal, throttling, and owner authorization | Defer: adds a new sensitive mailbox-access integration and vendor dependency, contrary to the current simple forwarding choice. |
| Route only four role aliases to a small Rust Email Worker, which durably records minimal arrival metadata and calls `forward()` | Adds one reviewed component on the critical path | Provides an explicit event for every **invoked** handler, conditional on durable-write and SMTP-failure tests | **Recommended if unattended per-arrival alerts are needed**. Keep original forwarding policy and an audited rollback to the four direct `forward` rules. |

The Worker option is a real availability trade-off, not a free observer: Cloudflare rules choose **one** destination, either verified-address forwarding or a Worker. An Email Worker can call `message.forward()` to the verified destination, but cannot tee events while the original rule remains `forward`. Worker deployment, runtime and D1 then sit on the role-mail path. This trade-off is preferable to incorrectly claiming a sampled analytics stream is complete, **provided** staging proves failure behavior and production retains a fast, tested revert path. [Routing rules](https://developers.cloudflare.com/email-service/configuration/email-routing-addresses/), [Email handler/forward API](https://developers.cloudflare.com/email-service/api/route-emails/email-handler/).

## Smallest reliable Worker contract

Use **one** no-public-HTTP Rust Worker with `email` and `scheduled` handlers, a private role-only D1 database containing a metadata/outbox table and a monitor-health row, one 5-minute Cron Trigger, and a restricted `send_email` binding. The previously provisioned but empty, isolated ops D1 may be reused **after a fresh read-only emptiness audit**; do not bind this Worker to the user-mail D1, since a D1 binding grants the Worker broad database access. Do not resurrect the removed ticket UI, case store, attachment archive, or privileged agent API. A role report's full MIME remains only in Cloudflare's transit and the chosen external mailbox; the Worker does not read, parse, duplicate or log the raw stream. No third-party model receives report content.

1. The handler accepts only the four configured envelope recipients. Generate a random report ID; before forwarding, insert `(id, role_enum, received_at, forward_state='pending', alert_state='pending')` into D1. Never persist sender, subject, body, Message-ID, recipient destination, MIME, or a hash of those fields. Add `X-Amail-Role-Ref: <id>` to the forward only if the provider accepts it; Cloudflare permits `X-` headers. Do not use an attacker-controlled Message-ID as the outbox key. The confidential destination is a Worker secret (or a deploy-time protected binding value), not a repository constant.
2. `await message.forward(destination)` exactly once in a handler invocation. Mark forwarding accepted, or leave a durable `pending/unknown` row if the call or follow-up state update fails; provider acceptance is **not** proof of destination Inbox placement. A forwarding error must be observable and must not turn the row into false success. A failed **initial D1 insert** cannot silently accept and drop an unalerted report. Before production cutover, inject this failure in staging and verify the actual SMTP outcome (retry/rejection versus silent delivery); Cloudflare's public docs do not justify assuming a particular retry guarantee for a thrown Email Worker exception.
3. The scheduled handler scans unalerted rows, emits a bounded, content-free digest (counts, four role categories, oldest-arrival age, and `forward=unknown` urgency) from `mail@moesegfault.dev` to the same **verified** confidential destination, then marks those rows alerted. It may retry; duplicate digest notices are safer than missed ones. Rate-limit digest volume rather than dropping report rows under an attacker-generated flood. Alert mail contains no report-derived URL, sender, subject, body, attachment, or instruction to trust the report. Any reference is a random local ID, not reporter input. The alert tells the owner to inspect **Inbox and Junk** for the original and to respond, if justified, separately from the authenticated official sender; direct Reply from the private mailbox would disclose its address.
4. Keep D1 rows until the response objective plus a bounded audit window, then expire; retain aggregate non-content counters longer if needed. Record scheduled-run time, oldest unalerted age, failed sends and Worker errors in Cloudflare observability without payloads or destination. The existing mail API's `abuse_contact_verified` boolean is a **manual attestation**, not a health check. Bind the isolated role D1 to the mail API for a second, read-only-in-code send-policy check: the sole monitor-health row must have `lease_until > now`; a missing row, query error or expired lease denies sends. A healthy scheduled run renews a short lease (e.g. 30 minutes) only after checking the four exact rule IDs/actions/destination equality through a Rules-Read-only credential, outbox age, and alert-send outcomes. If Cron stops, D1 is unavailable, a rule drifts, or alerts keep failing, the lease expires and user sending automatically fails closed even if the manual boolean remains 1. Do not infer lease health from sampled GraphQL counts. A Cron job running every five minutes is a target, **not** a five-minute delivery guarantee; Cloudflare says new/changed triggers can take up to 15 minutes to propagate. [Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/), [scheduled-handler outcome](https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/).
5. Restrict the binding to official `mail@moesegfault.dev` as sender and the verified destination as recipient. Cloudflare supports binding-level sender/recipient restrictions and sending to verified routing destinations. Since the recipient is confidential and a literal `destination_address` in committed Wrangler config would expose it, generate the binding config only in a protected deployment job or enforce the single secret recipient in code and document the residual broad-binding capability. Prove the selected route live; an API `send()` success alone does not prove Outlook Inbox placement. [Send bindings](https://developers.cloudflare.com/email-service/configuration/send-bindings/), [verified destinations](https://developers.cloudflare.com/email-service/configuration/email-routing-addresses/).

The table is an **at-least-once notification outbox**, not a promise of exactly-once mail delivery or of detecting messages rejected *before* the Email Worker runs. The lease detects programmatic monitoring failure; it **cannot** prove Outlook Inbox placement or owner attention. That remains an external acceptance test and continuing ownership commitment. Use sampled routing analytics only as an independent reconciliation signal: unexpected failures or a divergence between approximate provider counts and D1 arrivals demand investigation, but equal counts cannot prove no report was missed. Sender complaints are untrusted evidence; no automatic account hold, appeal outcome, data disclosure or reply follows merely from a report. The existing provider-authenticated outbound complaint event path remains separate.

## Rollout, acceptance, and release gate

Keep the four current direct-forward rules until a staging-only synthetic role route proves: real external SMTP → Email Worker → D1 metadata → original at the external destination (including Junk) → official-sender digest in Inbox; duplicate/redelivery handling; D1 unavailable, `forward()` failure, scheduled-run failure, alert-send failure, **lease expiry causing send denial**, and safe rollback. Deploy the mail API's additive lease check before attesting the role contact; an unset lease must deny, preserving existing held behavior. Then switch each exact production rule under a reviewed, conflict-detecting provider update, read back the action/Worker and send one real canary before switching the next. Do not deploy a Wrangler `addresses` list over the API-owned rules: Wrangler reconciliation can take over or delete managed routes. On regression, restore the exact old `forward` action/destination, audit all four, let the lease expire or explicitly clear it, and keep sending held during the incident. [Wrangler rule ownership warning](https://developers.cloudflare.com/email-service/configuration/email-routing-addresses/).

For `abuse_contact_verified=1`, require **all** of the following: four exact role addresses still work; an independent previously unknown sender's report is forwarded and its corresponding content-free digest reaches **Inbox** within the declared objective; the owner acknowledges the digest, locates the original in Inbox **or Junk**, and demonstrates a separate controlled response path; failure injection proves both undelivered and unalerted cases are visible and lead to a held gate; ongoing channel checks have an accountable owner. The initial response objective is one business day for routine reports and faster for credible urgent risk, not an invented guaranteed SLA. Safe-listing the official alert sender and marking the four canaries “Not Junk” is a sensible one-time Outlook.com setup, but it cannot guarantee arbitrary future reporters avoid Junk. Do not use a broad spam bypass or assume an Inbox rule rescues Junk. [Outlook.com safe senders](https://support.microsoft.com/en-us/outlook/safe-senders-in-outlook-com), [mark Not Junk](https://support.microsoft.com/en-us/outlook/mail-goes-to-the-junk-folder-by-mistake).

If no one or no future agent service is willing to own the notification/response objective, forwarding plus a Worker is still **not** a monitored abuse contact. Leave `abuse_contact_verified=0` and public sending held rather than converting a successful provider delivery status into an operational attestation.

## Automatic observability privacy review (2026-09-29)

**Decision implemented in source, not yet verified on a deployed Worker:** `workers/role-monitor/wrangler.toml` now explicitly sets `observability.traces.enabled=false` in both production and staging. Cloudflare's current [automatic span attribute inventory](https://developers.cloudflare.com/workers/observability/traces/spans-and-attributes/) includes `cloudflare.email.from`, `cloudflare.email.to`, and `cloudflare.email.size` on **Email Handler** root spans. The former 100%-sampled tracing configuration would have stored every reporter envelope sender even though application D1 intentionally contains no sender. Lowering the trace sample would merely make disclosure probabilistic; it is not a privacy boundary. Do not enable automatic traces until an explicit data-handling decision and a live redaction/canary inspection justify them. The D1 arrival/outbox and scheduled health lease remain the reliable per-arrival path; sampled telemetry must never drive that gate.

Cloudflare [Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/) says default invocation logs include request/response metadata and the Email invocation message is the recipient address. The four production recipients are public role aliases, but recipient telemetry is still unnecessary and the exact full event schema may include other enriched fields. The source now explicitly sets `observability.logs.invocation_logs=false` in both realms. Application logs remain enabled at full rate: source inspection of `workers/role-monitor/src/lib.rs` found only fixed role labels, random local UUID references, aggregate counts, fixed phase names and static failure text in `console_log!`, `console_warn!` and the Cron panic. Those records support diagnostics without sender, subject, destination, raw MIME or token. Do not add provider errors or serialized `message`, `env`, HTTP responses, D1 bindings or mail headers to logs. Configuring a staging environment independently matters: [Cloudflare's environment instructions](https://developers.cloudflare.com/workers/observability/logs/workers-logs/) show observability under `env.staging`, so validate each deployed realm rather than assuming the top-level setting propagates.

The [automatic span inventory](https://developers.cloudflare.com/workers/observability/traces/spans-and-attributes/) lists D1 `db.query.text` and outbound Fetch `url.full`/selected HTTP headers, but **does not document D1 bound argument values, Authorization headers, Email `forward_email`/`send_email` attributes, raw MIME, Subject, or custom `X-Amail-Role-Ref` as automatically captured**. Here SQL text is static with `?` placeholders; provider request URLs contain zone/account IDs and page numbers, while the routing token is in an Authorization header. Absence from the documented list is not proof of exclusion in every runtime/version or exception path. Before any future trace enablement, plant independent canary values in sender, subject, body, forwarding reference, destination-like header and staging secrets; inspect the actual Cloudflare dashboard/API logs and span attributes for one successful Email event plus D1/forward/send/Cron failures. Avoid displaying or exporting the confidential destination or canary payload in test artifacts. This is a staging-only verification, not a reason to replay the already-completed production forwarding canaries.

No third-party telemetry export (OpenTelemetry, Logpush, Tail Worker) should be configured for this role monitor without a separately reviewed recipient, redaction and retention policy. Cloudflare currently describes Workers Logs as account-stored with plan-specific retention and traces as additionally billable from **2026-10-01**; automatic full traces also create a cost/volume risk unrelated to the correctness of the 5-minute lease. [Logs retention/pricing](https://developers.cloudflare.com/workers/observability/logs/workers-logs/), [traces pricing](https://developers.cloudflare.com/workers/observability/traces/).

## Follow-up audit: custom-log context is not a proven Email privacy boundary (2026-09-30)

**Review disposition: hold production role-Worker cutover pending containment and
live privacy acceptance. This is an unverified confidentiality boundary, not a
demonstrated Email-envelope leak.** No production code/configuration, deployed
settings, mail route, private record or live telemetry query was changed or read
by this follow-up. No local tests were run.

The API-only historical classifier in run `36723490687` found a synthetic path
marker in indexed request context and `$workers.event.request`, with a reviewed
application-shaped `source`; event-type attribution remained unrecognized. See
[the exact result and limitations](mail-trace-sink-remediation-options.md#second-historical-result-request-context-retention-located).
This invalidates the general inference that reviewing `console` arguments alone
proves the complete retained event is content-free. It does **not** establish
that an Email-triggered record has identical enrichment, or that a reporter,
private forwarding destination, Subject, MIME, or token has been retained.

### Evidence from this source audit

| Location | Established behavior | Limit |
| --- | --- | --- |
| `workers/role-monitor/wrangler.toml`, both observability blocks | Logs remain enabled at 100%; invocation logs and native traces are explicitly disabled. No HTTP route, workers.dev or preview exposure is configured. | Custom capture remains enabled in the original Email/Cron context. Disabling invocation logs does not document a field-level suppression guarantee for custom records. Source settings do not prove currently serving settings. |
| `workers/role-monitor/src/lib.rs:73-130` | Email wrapper replaces errors with static text; arrival log contains only a fixed role and server-generated random UUID. Raw MIME and sender are not read or logged by this handler. | `message.to()` is read for exact role matching and the runtime necessarily receives envelope/MIME data; absence from application log arguments does not constrain platform context. |
| `workers/role-monitor/src/lib.rs:135-174,224` | Cron emits fixed phase failures, bounded aggregate counts and static panic text. Provider errors are not formatted. | Exceptions and enriched outbound-binding/Fetch context are separate collectors, not proved safe by static text. The Cron panic preserves failure outcome and should not simply be removed to hide it. |
| `infra/deploy/verify_role_monitor_staging.py:120-134` | Readback verifier checks effective invocation/traces settings and **requires custom Logs enabled**. | This is a configuration acceptance check, not a complete retained-record privacy oracle; it must evolve with sink containment rather than preserve an unsafe assumption. |
| `infra/tests/test_role_monitor_config.py:58-75` | Test fixes the same current flags in both realms. | The docstring's claim that no invocation metadata is retained exceeds what those flag assertions prove. No test here inspects retained Email/Cron records. |

Current official [Workers Logs documentation](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)
describes invocation-log enrichment, Email recipient invocation messages, and
separate custom-log capture. The [telemetry query schema](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/)
allows `$workers` enrichment, `eventType=email`, and an optional generic `event`
map without an Email-specific confidentiality promise. [Automatic span attributes](https://developers.cloudflare.com/workers/observability/traces/spans-and-attributes/)
explicitly list Email envelope sender/recipient/size; native traces must remain
off. These documents justify an unresolved-boundary finding, not an assertion
that a particular Email field leaks. The existing
[USENIX Security 2023 logging study](https://www.usenix.org/conference/usenixsecurity23/presentation/lyons)
also supports auditing collectors and complete retained records; it does not
supply Cloudflare-specific runtime evidence.

### Conservative containment decision

Keep the existing four production direct-forward rules and held public-send gate;
do not deploy/cut over the role monitor with its present custom-Logs capture and
call that private. Reuse the reviewed private Queue sink being designed for Mail
rather than introducing a second ad hoc logger: typed role diagnostics may carry
fixed realm/component/event/phase/role enums, bounded aggregate counts, times and
server-generated opaque references only. Do not pass `EmailMessage`, report
headers, envelope values, digest body/destination, provider URL/response/error,
secrets or arbitrary strings. Role D1 arrival/outbox and the health lease remain
the delivery/alert correctness mechanism, not Queue telemetry receipts.

Switch the producer's typed handoff **and all retained Logs/native-trace settings
off together** at a reviewed staging version, with no console fallback or unsafe
dual logging. A Queue failure must not make accepted forwarding falsely fail,
renew a failed health lease, or restore original-context retention. Preserve the
static failure outcome for Cron independently of retained diagnostic payloads.
The sink's own queue-context enrichment, envelope/DLQ retention, duplicate handling
and failure behavior still require review and deployed acceptance; Queue isolation
is a testable hypothesis, not a privacy attestation. Coordinate schema and failure
semantics with the Mail Queue-sink architecture rather than copying its Fetch
operation enum into Email-specific events.

### Evidence needed before production cutover

Use isolated staging role routes and synthetic values, not the owner's original
reports or another production role canary. Record the exact producer/sink serving
versions, effective retained-settings/destination/tail readbacks and bounded time
window. Inspect complete, pagination-complete retained sink records and queued
payloads for separate synthetic sender, Subject, body, header/reference and
forwarding-destination-like values, and unexpected source-service records. Do not
print raw values/records or publish recipient, credential or MIME artifacts.
Absence without a positive sink event and a bounded complete query is unverified.
Exercise normal Email forwarding and Cron digest plus before-insert,
before/after-forward, alert-send and Cron/provider/D1 failures; verify static
failure outcomes, arrival/outbox/lease semantics and safe diagnostics. A synthetic
staging destination fixture is preferable to copying the actual confidential
address into canary output. An authorized private check may compare the actual
configured destination in memory and report only a fixed pass/fail bin.

Keep separate acceptance claims: original arrival/forwarding, digest Inbox notice,
lease expiry/fail-closed behavior and complete-record privacy. None implies the
others. Source and hosted tests may authorize a staging experiment; only the
pinned deployed experiment can justify production privacy/cutover. Reverting to
direct forwarding is the production availability rollback; do not re-enable
original-context Logs as a telemetry rollback.

## Typed Queue remediation source contract (2026-09-30)

Status: **implemented in source; independent review, hosted compilation/tests,
coordinated rollout and live privacy/operations acceptance are pending**. No
local build/test, live read, route mutation, deployment or push was performed
for this change. Offline Cargo lockfile generation changed only the role
package's references to already-locked schema/JSON crates. Rust formatting and
static diff checks are not acceptance evidence. Earlier custom-log findings
above remain historical; they do not describe the new source configuration.

### Data boundary and causal model

The role monitor now shares the existing Mail trace Queue/sink, rather than
introducing a second collector, but uses a **distinct closed `RoleEvent` schema**
in `crates/trace-schema/src/role.rs`. The existing Mail `Event` wire fields and
semantics remain unchanged. The sink decodes the untagged closed `Record` union,
validates it, and serializes the typed variant without adding a wrapper. Unknown
fields, arbitrary labels, malformed identifiers, oversized records and invalid
field combinations are dropped/acked without formatting the rejected body.

| Role field | Invariant | Purpose |
| --- | --- | --- |
| `schema_version`, `service` | Version 1, only `role_monitor` | Distinguish the reviewed producer without dynamic labels. |
| `event_id` | Canonical server UUIDv4 | Stable retained identity on Queue redelivery. |
| `trace_id`, `span_id` | Fresh lower-case nonzero W3C-shaped IDs | One causal root per Email or Cron invocation; no incoming Email parent accepted. |
| `parent_span_id` | Present only on fixed phase events, distinct from child | Correlate phase failures/digest success to the original Cron root, not Queue transport. |
| `code` | Closed Email accepted/rejected/failed, monitor healthy/failed, digest accepted/failed, destination/routes/lease failed vocabulary | Preserve useful diagnostics without raw SDK/provider errors. |
| `role` | Present only for accepted Email; one of five fixed categories | Locate the affected public category without retaining an address. |
| `count_bucket` | Only healthy monitor/digest success; powers of two ≤2^32; digest ≤8 | Bounded aggregate pending/group evidence, not precise arrival content. |

No report ID, sender, Subject, raw MIME/body, header, confidential destination,
provider URL/response/error, token, D1 binding or incoming context crosses the
handoff. A fresh trace root is independent of the random D1 arrival reference.
There is no need to retain report references merely to diagnose system phases.
The new schema does not pretend Email/Cron operations are HTTP status classes.

`workers/role-monitor/src/diagnostics.rs` owns at most **eight** events per
invocation, reserving the last slot for the root result. Each serialized record
must be ≤**1,024 bytes** before Queue publication. A single bounded batch is
therefore below provider count and batch-size limits. Counts are coarsened and
clamped before rounding; callers cannot inject dynamic metadata. Both producer
and sink independently validate the contract. All optional phase events share
the invocation trace and point to its original root span.

The Email wrapper preserves existing acceptance/rejection/error behavior and
attaches only an owned Queue handle plus safe event vector to `ctx.waitUntil`;
neither `Env` nor the Email message is captured. Missing binding/send failures
produce no fallback console record and do not turn an accepted forward into a
mail failure. Cron records fixed failed phases, awaits its bounded handoff, then
preserves the existing static panic on failed monitor work because workers-rs
0.8.7 discards a returned scheduled `Result`. A Queue send failure neither
renews a failed lease nor invalidates already successful business work. D1
arrival/outbox and lease logic remains the correctness mechanism; telemetry is
best-effort, can duplicate or be lost, and must never certify delivery/attention.

### Capture-off configuration and readback

Both role realms explicitly disable `observability.enabled`, Logs capture,
invocation Logs, retained Logs preference, native traces and retained traces
preference, and `observability.issues.enabled`; query redaction is set as defense
in depth, not an exemption to enable capture. Issues has an independent switch:
Cloudflare documents failure occurrences with invocation context, and supports
its Wrangler configuration from 4.134.0 onward. Parent and nested collector
switches must be read back; TOML intent alone is insufficient.

The role-only readback verifier reuses the reviewed pure
`effective_api_settings` policy in `crates/mail-worker/check_observability.py`.
It requires the exact Worker name and positive current-resource Logs/traces/
Issues-off, Logpush off and no tail consumer, with no contradictory legacy
settings. Missing/null legacy observability may be unsupported, but is never
positive evidence. The verifier additionally requires an exact private Queue
binding ID and brackets readback with the same expected **single-100%** serving
deployment/version. New non-secret required inputs are
`AMAIL_EXPECTED_ROLE_WORKER_VERSION` and `AMAIL_EXPECTED_TRACE_QUEUE_ID`. Old
deployment jobs without these pins now fail closed rather than accept the old
custom-log model; workflow integration is deliberately a separate owned change.

Independent source review of the initial implementation found two preflight
defects, corrected before rollout: serving capabilities were incorrectly checked
from unversioned `/settings`, and the SMTP driver's old verifier calls had not
been migrated to the new required pins. Both deployment audit and SMTP preflight
now share `inspect_deployment`: it reads `/versions/{expected_version}`, requires
the matching response ID, and checks exact D1/Queue/sending capabilities from
`resources.bindings` (only direct-list or reviewed `{result:list}` forms). Legacy
settings are used solely to reject observability contradictions. Synthetic
orchestration tests cover safe unversioned bindings with wrong/missing/version-ID
mismatched serving resources, split/drifting traffic, explicit pin absence, and
the actual SMTP preflight call through the shared parser. These tests are authored
for hosted execution, not locally run or evidence of deployed acceptance.

### Coordinated rollout proposal (not performed here)

1. Source review and hosted tests compile role/schema/sink and test strict union,
   backward Mail wire shape, phase/root parentage, buffer bounds, source capture
   flags and positive/negative role readback. Keep role routes direct-forward.
2. Deploy/review the shared sink with this decoder while only the existing
   reviewed Mail API producer is admitted. Preserve the original Queue/DLQ IDs,
   bounded retention/retries and sole queue-only consumer restrictions. Never
   weaken the topology into an arbitrary producer list.
3. Extend `ensure_trace_queues.py` topology policy through an explicit **role
   rollout phase**, admitting exactly `amail-mail[-staging]` and
   `amail-role-monitor[-staging]` after role binding deployment, and rejecting
   duplicates, other Worker names and cross-realm resources. Existing pre-role
   phases must continue to attest their original sole producer; do not make
   absence of either post-role producer look like full post-role readiness.
4. The guarded role deployment lane must obtain the exact version pin without
   printing unrelated provider/secret output, supply the approved Queue ID,
   attest no synthetic SMTP route before/after replacement, and run the
   positive Worker-resource readback. No workflow changes are included here.
5. Inspect a bounded complete retained-record Email/Cron canary with separate
   synthetic sender, Subject/body/headers and secret/destination-like markers;
   require positive role sink events and absence of source-service records,
   inspect every retained record field and Queue/DLQ payload, and suppress raw
   artifacts. Include existing before-insert/forward/alert failures, real Cron
   failure outcome, provider/D1 failures and Queue-unavailable cases.
6. Separately close original-forward, official-digest **Inbox**, response-path,
   fail-closed lease and finally-block synthetic-route cleanup evidence. Only
   then consider one-by-one production role cutover and public-send attestation.

The source binding is not authorization to auto-roll out the second producer;
the existing strict single-producer topology checker will deliberately reject
it until the coordinated policy is implemented. **No production privacy,
monitor health, Inbox notice or public-send readiness is claimed.** Availability
rollback remains exact direct-forward actions plus held sending; a telemetry
incident must never re-enable original-context Logs/traces/Issues. Removing the
role Queue binding is a reviewed topology transition, not a shape-only retry.

### External grounding and limits

- [Cloudflare Workers production practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/)
  support request-local state, native bindings and tracked async work rather than
  floating promises; this Rust implementation uses the locked 0.8.7 Queue and
  Context APIs, not a JavaScript wrapper or unpinned SDK assumption.
- [Queue batching/retry behavior](https://developers.cloudflare.com/queues/configuration/batching-retries/)
  makes duplicates and finite retry/DLQ retention part of the contract, not an
  exactly-once business delivery guarantee.
- [Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)
  separates custom/invocation collectors; [Issues](https://developers.cloudflare.com/workers/observability/issues/)
  independently detects failures. Neither document proves complete Email context
  exclusion just because application arguments are static.
- [Lyons et al., USENIX Security 2023](https://www.usenix.org/conference/usenixsecurity23/presentation/lyons)
  studies sensitive logging in Android, a different runtime. It motivates
  checking collector boundaries and retained records, but provides **no**
  Cloudflare leak evidence or Queue confidentiality guarantee. The decisive
  evidence remains the pinned deployed full-record canary, not analogy.
