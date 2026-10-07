# v0.2.0 staging delivery contract

## Scope and admission

The active candidate branch is `codex/v0.2.0-billing`. Hosted `checks` validates
source and produces unpublished native candidates. `staging-inspect` uses
`INSPECT_STAGING_V020`; `staging` requires `RUN_STAGING_V020`. No tag, Release,
production promotion or production send-policy mutation is authorized by this work.
The unchanged workflow-wide staging graph writer lock serializes provider writers.
Historical V012 interruption recovery remains bound to its original immutable
runs and branch; it is not a general V020 recovery receipt.

Worker builds remain credential-free and occur once in hosted `worker-build`.
Every staging mutator restores the same-run exact artifact, verifies source/run
identity and file hashes, and refuses changed bytes. API is fetch-only with empty
Cron; private maintenance alone owns scheduled work. Trace sink is Queue-only,
and realm-isolated lifecycle/ingress graphs remain independently read back.
Production admission and confirmations are unchanged. Initial V020 predecessor
admission may omit the four API Billing bindings (and the maintenance issuer) only for the exact source-owned
V012 API `01f14a8e-d5b1-41f9-9f8c-325c2e288ba7` and maintenance
`3d23d537-6379-4fcb-84c2-2c1b8a9f4857` cohort. Every other graph and all
post-deploy readbacks require the full desired binding set; there is no generic
optional-binding or arbitrary historical fallback.

## Billing realm

Staging API configuration fixes:

- `BILLING_BASE_URL=https://billing-staging.moesegfault.dev`
- `BILLING_SUBSCRIBE_ORIGIN=https://subscribe-staging.moesegfault.dev`
- `BILLING_RETURN_URL=https://amail-staging.moesegfault.dev/billing/return`

Scheduled maintenance uses the same fixed staging Billing URLs to flush the durable
usage outbox; it gains no HTTP or user-mail-send capability.

The staging GitHub environment must contain `BILLING_SERVICE_KEY`, equal to
Billing staging's `AMAIL_SERVICE_KEY`. Provision through secret-tool stdin from
an ignored local secret source; never print it or put it in artifacts. Both API and scheduled-maintenance
submissions include this key through a mode-0600 repository `.temp` secrets file,
removed on success and failure. Production delivery does not inherit this key.

The return route is static and script-free: it does not consume query parameters,
change account state or claim payment success. The next action is a fresh
`amail billing status` authoritative read. `site/scripts/check-billing-return.mjs`
checks the built route during hosted site validation. Real human authorization
and Billing-state convergence still require integrated staging acceptance.

## Version and migration

All workspace package versions and local-package Cargo.lock coordinates are
0.2.0. Site candidate/current coordinates match. Vendored MoeSegfault Style
remains independently pinned at v0.1.2. Historical changelog entries remain.
Old CLI requests are rejected by the v2 API contract; hosted direct HTTP owner
probes send `x-amail-api-version: 2` rather than accidentally testing only 426.
Existing account addresses must survive additive migration and be classified
Free; source migration tests and live readback, not this document, prove this.

## Initial local checkpoint (superseded by actual delivery below)

On 2026-10-07 the infrastructure suite passed all 161 tests, including 20 staging
rollout, 16 adapter, 7 realm-secret, 6 canary and 4 candidate-selection contracts.
Node release-state contracts passed 27 tests. Source-only staging adapter and
realm-isolation checks passed. No local heavy Rust/Wasm/site build or provider
write was performed. Root coordinates secret provisioning, immutable source
commit, one hosted workflow dispatch, live observation and actual user/Billing
end-to-end verification; this note is not evidence that deployment has occurred.

## Initial V020 preflight failure and verified correction

Hosted staging run `37615319193`, source `00acf56749fe2cd9af9ac0ab827d46f4a9921eb1`,
passed compiled acceptance but stopped before the first mutator. Both staging
GitHub Queue ownership variables were empty. Inspection temporarily projects
observed identities for diagnostics, then preflight intentionally restores
caller-reviewed ownership values. The subsequent exact graph check therefore
refused missing pins; an incomplete diagnostic vocabulary rendered this safe
failure as `reason=unknown`. This was configuration admission failure, not proof
of an unsafe or absent live resource, and grants no replay of any provider write.

A local authorized, bounded provider inspection on 2026-10-07 used the existing
Wrangler OAuth cache in memory (with proxy variables removed). Its content-free
snapshot is `.temp/v020-staging-inspection.json`. API, maintenance, sink and both
adapters exactly match the source-owned historical cohort; full split and adapter
checks both returned `exact_graph=true`. Trace Queue
`fcee510036af42c189e28c0b6ff9508e` has exactly API and maintenance producers;
DLQ `f023f804b7bd4d8691fbfcb60416a001` has no producer. Both retain the reviewed
bounded Queue settings. No resource, policy, code or secret was changed.

The operational correction is to provision those independently verified IDs as
staging environment variables `AMAIL_TRACE_QUEUE_ID_STAGING` and
`AMAIL_TRACE_DLQ_ID_STAGING`, not to adopt arbitrary observed IDs automatically.
Preflight now reports `staging_trace_ownership_pins_missing` before graph reads,
and preserves fixed downstream failure labels without exposing provider text.
A focused regression reproduces successful inspection with missing caller pins,
proves refusal and zero snapshot writes, and confirms observed IDs remain unable
to replace reviewed ownership. All 21 staging-rollout tests pass locally.


## Missing maintenance issuer repair (2026-10-07)

The real extra metering run `37625486364` retained three positive address-second
liabilities but could not deliver them. Fixed diagnostic run `37627785234`
observed 15 accrued micros (7 + 4 + 4), zero Billing events, zero active task
addresses, and the human budget restored to zero. `billing::Configuration::load`
requires `IDENTITY_ISSUER`; the deployed maintenance TOML omitted it, while the
native outbox fixture independently injected it. Thus scheduling and durable
metering succeeded, but bridge configuration failed before the dependency call.
This is a deployment-contract defect, not evidence that the event was paid or
that lowering the cap should erase an already-authorized liability.

The desired staging maintenance vars now include the same explicit issuer as
the API. Production config is unchanged. The native outbox fixture loads the
actual staging TOML vars rather than independently inventing a configuration;
a negative case removes only the issuer and asserts that pending liability
survives with no Billing egress. Normal immutable readback requires the issuer.

`verify_missing_issuer_predecessor(account, token, queue_id)` admits only active
staging maintenance version `5281d8ef-f3c0-42d4-8331-bafa01923b40`, absent exactly
`IDENTITY_ISSUER`. It still requires all Billing URLs, the Billing service secret,
D1/R2/Queue/version bindings, private scheduled-only surface, capture-off metadata,
five-minute cadence and empty API Cron. Its caller must bracket the full graph,
including unchanged API `1f4a056f-5342-46a5-8e32-7eebaea5f7a2` and sink
`56c17824-679f-4427-bcc9-4584d2510208`, before a maintenance-only submit of the
same-run tested artifact, then perform strict normal graph readback. This
exception grants no production, other-version, queue, secret or generic missing
binding fallback. Source adoption alone was not treated as a deployed repair.

Actual fixed diagnostic [37627785234](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37627785234)
confirmed Lite, zero budget, zero registered addresses, accrued 15 CNY micros,
three undelivered address events (quantities 7/3/4, amounts 7/4/4 micros), two
attempts each, zero Billing events/amount, and no Billing usage-request spans.
This matches configuration failure before a dependency span/request is created.
The repair uses an explicit staging-only CI target, same-run compiled/workerd
artifact and infrastructure gates, full graph brackets, one existing maintenance
submit and strict post-readback. API, sink, queue graph, public send hold and
five-minute cadence must remain unchanged. No backlog is seeded, edited or deleted.

### Actual corrective deployment and final acceptance

[37628266417](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37628266417)
completed successfully from `d1291b80923d7d463e596bcd702a6e251039797f` after
credential-free compiled/workerd and infrastructure gates. Maintenance now serves
`eb38afe1-51fe-4d6b-8e82-661b5932dcbf`. Safe artifact `11485846948` records
unchanged API `1f4a056f-5342-46a5-8e32-7eebaea5f7a2`, unchanged sink
`56c17824-679f-4427-bcc9-4584d2510208`, and the retained five-minute Cron.
Full immutable graph brackets also preserved queue/resource ownership, public
send hold and private surfaces. No production or Identity resource was written.

The successful final [37630962022](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37630962022)
used the exact candidate admitted through successful producer `37628260838`,
bundle artifact `11485896406`. Its six delivered period events included all
three preserved failed-run liabilities and seven additional CNY micros from seven
real excess address-seconds. Budget returned to zero and all four metering
addresses retired through normal UI/CLI paths before polling. Safe artifact
`11486684051` independently proves normal human/CLI ancestry, actual asynchronous
usage client/server ancestry and the exact linked scheduled root. Real mail and
self-send recovery acceptance also passed again. No scheduler invocation, outbox
mutation or fictitious usage was used to obtain that result.

Final fixed readback `37634410400` confirmed six delivered events, 22 accrued
CNY micros in both Mail and Billing, zero registered addresses and zero budget.
Every retained Billing usage server reported HTTP 200/success. This includes the
15-micro historical backlog plus the seven-micro final test; all remain liabilities
marked `pending_settlement`, never a claim of monetary payment.


## Current fixed USD staging delivery (2026-10-07)

Owner-approved tariff: Free $0, Lite $1.50, Plus $4.50/month; excess accepted
recipient $0.001, decimal GB-month $0.15, address-month $0.50. Included resources
and unmetered inbound/semantic search are unchanged. This is not FX conversion.

Billing/Subscribe source `86bb06e` deployed successfully in
[37641220454](https://github.com/kleedaisuki/moesegfault-subscriptions/actions/runs/37641220454).
Mail source `27c5818` deployed successfully in
[37642433233](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37642433233),
including additive migrations0006/0015 and exact private graph/capture readbacks.
All original applied migrations and production/Identity resources stay unchanged.

| Surface | Current USD serving version |
| --- | --- |
| Mail API | `c33b65b1-d2a4-4902-9fa3-15e74baf1819` |
| Maintenance | `acbf4790-6e80-4bd3-aab2-095c9937759d` |
| Mail trace sink | `f70bf19f-8f08-45a3-b142-244d34890db7` |
| Ingress | `7ef1314c-1d4d-418e-8c3e-44025854271f` |
| Lifecycle | `bbf2df6b-ceb7-433c-90da-b9ee459cf5b6` |
| Staging site | `b69e4782-9ce6-4ff4-a8a3-8b06e217f57c` |
| Billing | `7a85d66d-b33a-42f2-bc30-5c6e1cafc2c4` |
| Subscribe | `dd8b046a-8f9e-4c3a-9947-3cf96e6cffbb` |

The preceding failed Mail run `37641189250` had a GitHub workflow-level Internal
server error after a known successful sink submit/readback; all later mutator jobs
were never created. A fresh same-source workflow used fresh exact graph brackets
and same-run artifacts, without failed-artifact provenance exceptions. See
`usd-cutover.md` for the bounded incident and recovery facts.

Actual USD monetary/trace acceptance `37644087065` acknowledged 2 USD micros in
two normal-Cron events, retired all four metering addresses and restored zero
budget. Original 6 CNY events / 22 CNY micros remained unchanged. A stale CNY
assertion later stopped the ordinary mail probe; the helper-only correction
`aae6029` changes no deployed runtime bytes and must not replay charged usage.
