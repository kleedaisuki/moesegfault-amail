# USD-only new billing cutover (2026-10-07)

## Owner-approved tariff

The owner explicitly replaces new CNY billing with fixed USD prices, not spot FX:
Free $0/month, Lite $1.50/month, Plus $4.50/month; excess accepted distinct
envelope recipients $0.001 each, storage $0.15/decimal GB-month, addresses
$0.50/address-month. Included quotas stay 100/1000/5000 recipients,
200MB/2GB/10GB and 1/3/5 addresses. Inbound and semantic search stay unmetered.
One USD = 1,000,000 integer micros. Rates are 1000/150000/500000 USD micros.
Production/Identity deployment remains out of scope.

## Historical pre-cutover baseline and invariants

The accepted pre-cutover staging source was Mail d1291b8 (then docs-only HEAD
b0c596b), Billing runtime c77b7dd (then docs-only HEAD 6ab8aa7). API version
1f4a056f-5342-46a5-8e32-7eebaea5f7a2; maintenance
eb38afe1-51fe-4d6b-8e82-661b5932dcbf; sink
56c17824-679f-4427-bcc9-4584d2510208. Final readback37634410400 found
zero registered addresses, zero approved cap, no undelivered usage, six CNY
events totaling22 CNY micros, no unresolved test send. Previous native/real
acceptance remains CNY evidence, never relabeled USD.

- Preserve all existing addresses, content, usage counters, unknown provider
  journals and one-use activation/grant receipts. Do not rewrite applied0013/0014
  or Billing0003/0004 migrations.
- New amounts always carry USD; existing immutable money records retain CNY.
- Approval currency is immutable. Existing CNY approval never grants USD spend.
- Billing summaries and budget sums partition by currency; no implicit FX.
- Missing legacy wire currency must retain old CNY interpretation, not silently
  become USD. New service consumers explicitly send/request USD.
- New contract: amail-v0.2.0-usd-v1. Historical CNY receipts remain
  amail-v0.2.0. Current public product currency is USD.

## Bounded Mail migration design

Prefer a single USD active metering state plus immutable legacy CNY snapshots,
not a general-purpose FX engine. Guard the additive cutover atomically: old
spending caps must be zero, all prior outbox delivered, and no reserved/unknown
resource sends. If those predicates fail, deployment stops without deleting or
reinterpreting data; resolve the original journal/consent normally first.
Archive old period monetary amounts/fractions as explicitly CNY before resetting
active USD accrued/fractions to zero; preserve included/accepted/reserved quota
counters, periods, plan rights, grandfather floors and data. Tag old outbox and
terminal reservations CNY; all new reservations/events explicitly USD. Applied0015 keeps old terminal rows
in place and snapshots only historical period monetary balances/fractions in
resource_legacy_cny_periods; it does not rename every business table. Replace
rate-dependent views/triggers in a new migration, never old migration files.
Require fresh USD human authorization before nonzero USD spending; preserve
existing paid grant access independently from old CNY spending consent.

## Billing migration design

Add persisted currency to authorization/binding/event records, defaulting old
rows to CNY. New authorizations are USD. Approval persists that same currency;
old pending CNY requests cannot silently approve a USD form. Immutable event
replay compares currency, and historical receipt checks require matching currency.
Period totals, overlap checks and budget enforcement are currency-scoped;
legacy unqualified usage GET stays CNY, new callers explicitly request USD.
Historical authorization/status reads label currency and contract truthfully.

## Engineering grounding

TigerBeetle separates currencies into distinct ledgers/accounts and requires
explicit linked transfers for exchange, supporting no implicit denomination
rewrite: https://docs.tigerbeetle.com/coding/recipes/currency-exchange/ .
Stripe's currency/minor-unit boundary is not our internal micro scale:
https://docs.stripe.com/currencies . No processor is being introduced.
The research Resources: A Safe Language Abstraction for Money (OOPSLA2020;
https://arxiv.org/abs/2004.05106) establishes resource conservation/type boundaries,
not a ready-made billing migration. Our inference is to encode denomination and
receipt invariants in types/SQL; no Move runtime or blockchain machinery is needed.

## Acceptance

Native tests: actual migration chain, preserved CNY history and quota counters,
zero-budget cutover and guarded refusal, new USD rates, no cross-currency budget
or retry mixing, same historical/new receipt behavior, exact integer/decimal UI.
Real staging: preserve six CNY events22micros, normal browser fresh USD approval,
zero default cap, tiny real USD address overage, normal Cron delivery, exact USD
summary and separate CNY summary, retained trace links, normal cleanup/zero cap.
No monetary payment is claimed: settlement remains pending_settlement.

## Wire and acceptance integration decisions

Billing new create explicitly requires currency USD; an omitted legacy currency
retains CNY only for historical idempotent replay. Its original CNY request-hash
serialization must remain unchanged. New human approval submits currency USD.
Binding/authorization currency and contract version are persisted/interpreted
by denomination, never a global label. USD GETs explicitly include currency=USD;
legacy unqualified GET preserves CNY. Both currency summaries stay separately
inspectable.

The controlled metering test authorizes $0.50 through the normal UI, keeps four
addresses active at least6.1 real seconds to guarantee a positive sub-dollar
address charge, retires them and restoreszero before normal Cron polling. It
requires zero existing USD accrual/reservations to prevent blind charged reruns.
It also verifies the original CNY summary remains exactly6 events/22micros.
Three network reads reserve135seconds inside the unchanged810second envelope.
No raw currency-conversion receipt or exchange rate is invented.

## Actual initial delivery (2026-10-07)

Billing/Subscribe source86bb06e70a9ba98153230ed25d185031d221e6c2 fully passed
[37641220454](https://github.com/kleedaisuki/moesegfault-subscriptions/actions/runs/37641220454).
Billing now7a85d66d-b33a-42f2-bc30-5c6e1cafc2c4; Subscribe
dd8b046a-8f9e-4c3a-9947-3cf96e6cffbb. Migration0006, native/domain/UI tests,
immutable packaging, staging deployment, capture readbacks and public smoke passed.

Mail source27c58183485e90e544a1ee89dad926cfe38e24e0 passed all compiled/native
workerd/three-platform/site/performance gates in
[37641189250](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37641189250).
Its sink submit succeeded and retained readbacks passed at version
b088f203-25f3-4497-bea6-8d3c03e79686. API/maintenance/migration/adapter/site
deployment jobs were never created. The overall run failed at GitHub's workflow
dispatch service, not a failed application job: public run annotation reports
Internal server error, correlation60a99e0c-f632-4248-a3bb-fb7d4880933e.
The jobs/check-run APIs omit that workflow-level annotation; the public summary
page exposes it. No USD Mail migration or charged test ran in this failed run.

Recovery is a fresh same-source normal staging workflow with a fresh exact graph
preflight and new immutable same-run artifacts, not a failed-attempt artifact
provenance override or blind replay of an unknown submit. The previous sink
submit and complete readback are known, and remaining API/schema submits never
started. Its CLI bundle11492886825 is compiled evidence only because the run
was not overall successful; do not use it as a successful E2E producer.

The first fresh dispatch attempt returned HTTP500 and a bounded run listing
confirmed no new run existed. After backoff, a new same-source normal staging
run [37642433233](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37642433233)
completed SUCCESS, including actual0015 migration and exact graph/adapter
readbacks. No failed-attempt provenance override was added. Current versions:

| Surface | USD serving version |
| --- | --- |
| Mail API | c33b65b1-d2a4-4902-9fa3-15e74baf1819 |
| Scheduled maintenance | acbf4790-6e80-4bd3-aab2-095c9937759d |
| Private Mail trace sink | f70bf19f-8f08-45a3-b142-244d34890db7 |
| Ingress | 7ef1314c-1d4d-418e-8c3e-44025854271f |
| Lifecycle | bbf2df6b-ceb7-433c-90da-b9ee459cf5b6 |
| Staging site | b69e4782-9ce6-4ff4-a8a3-8b06e217f57c |

Successful exact-source candidate bundle11492059864 belongs to37642433233.
Controlled real USD acceptance37644087065 completed the browser and monetary
portion successfully, then failed at mail_sending_status_overage_budget: the
pre-existing mail probe still asserted CNY. Safe artifact11494520444 proves
14 actual excess address-seconds,2USDmicros in2delivered events, zero restored
budget, all4metering addresses retired, and unchanged6CNYevents/22CNYmicros.
It also proves ordinary14-span human/CLI ancestry and18charged-origin spans
linked to one exact retained scheduled root. The native/application contract
correctly returned USD; the remaining failure is a stale harness assertion.

The helper now explicitly requires USD and its focused test positively covers
USD while rejecting CNY as current status. Runtime bytes are unchanged. A fresh
checks producer and ordinary full mail/browser/self-send acceptance will complete
the remaining journey WITHOUT another real-meter confirmation. The fixture
refuses nonzero USD accrued money, so blindly repeating a charged run is not
permitted. Keep both runs as evidence rather than claiming the first was green.
