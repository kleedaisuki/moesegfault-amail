# v0.2.0 resource metering

## Contract

Free/Lite/Plus share all mailbox/search features. Account pools are keyed by immutable
Identity `(issuer, subject)` and are independent of address deletion, client process,
or Idempotency-Key. Decimal bytes and UTC calendar months are intentional.

| Plan | Outbound canonical distinct recipients/month | Retained bytes | Concurrent addresses |
| --- | ---: | ---: | ---: |
| free | 100 | 200,000,000 | 1 |
| lite | 1,000 | 2,000,000,000 | 3 |
| plus | 5,000 | 10,000,000,000 | 5 |

Variable tariffs: 5,000 CNY micros per excess accepted recipient, 1,000,000 micros
per excess decimal GB-month, 3,000,000 micros per excess address-month. One CNY is
1,000,000 micros. Byte-seconds and address-seconds are integrated against actual
calendar-period seconds; fractional micros carry between observations. Final invoice
cent rounding belongs to Billing, not per-send or per-observation rounding.

Inbound has no count/byte-per-day commercial quota. Message count and semantic-query
count have no plan quota. Global scan/embedding and outbound capacity guards remain
service-safety protections, returning temporary capacity errors rather than upsells.
All tiers share the same two-send/minute abuse burst bound and global send cap.

## Migration and expiry

Migration 0013 copies no mailbox or provider journal. Every existing owner defaults
to free, and `grandfathered_addresses` snapshots all non-retired registered addresses.
The address allowance is the greater of that floor and current plan inclusion.
Existing addresses, slots, IDs, mail, reservations, and accepted/unknown provider
states survive unchanged. No pre-v0.2 send becomes a retroactive billable receipt.
The floor is permanent: deleting a protected address can free a grandfather slot.
The independent ten-slot owner/198-global routing platform ceilings remain atomic.

Paid expiry settles authorized stock only through `valid_until`, then sets Free and
zero variable budget without deleting mail/addresses. A downgrade preserves already
accepted and reserved recipient allowance, not unused higher-plan allowance. Refresh
of an unchanged tariff never grows the allowance; upgrades never reset counters.
The current allowance can exceed the Free marketing allowance after a downgrade to
avoid charging again for earlier accepted or unresolved sends.

## Concurrency and failure semantics

Production SQLite triggers execute in the same serialized writer transaction as
storage/address mutations and provider-journal acceptance/rejection. No read-then-write
budget preflight is authoritative. New stock reserves its *remaining period* liability,
so a one-byte admission cannot silently authorize a month of uncontrolled growth.
Overage is disabled by default even on a paid subscription. When a human lowers the
cap below existing stock liability, new paid growth is denied and accrual stops at the
approved cap; retained mail stays readable/deletable, with no unapproved debt.

`resource_send_reservations` holds canonical recipient units before provider calls.
Shared period holding is computed from accepted+reserved usage, not fixed per-request
free slots. Consequently reversed provider acceptance order cannot release funds
needed by another unresolved attempt. Acceptance creates exactly one durable usage
outbox event for newly chargeable units; definitive rejection releases the hold.
Unknown/submitting provider outcomes retain their holds and never authorize resending.
R2/pre-submission failures release commercial quota and allow same-key safe retries;
uniform safety counters remain conservative and are not charges.

`resource_periods` retains old periods and their unresolved holding across calendar
rollover. `resource_outbox` records immutable event ID, opaque Billing owner, original
human authorization receipt/time, period, meter, quantity, micros, observation time,
and delivery acknowledgement. Outbound consent is captured on reservation, not late
provider acceptance. Stock consent is captured at the integrated interval's start.
A later lower cap/expiry does not rewrite already authorized receipts.

The optional server-owned `origin_traceparent` is a strictly validated W3C version-00
context (55 bytes), never an address, payer ID, token, arbitrary request header, or
request prose. Send reservations retain their first originating server context across
same-key retries, unknown outcomes, consent changes and month rollover. Outbox receipt
replay preserves the same causal context. Stock receipts retain the human authorization
context from the account snapshot; refreshing the same authority never overwrites it
with an unrelated status or maintenance trace. Scheduled delivery continues that
original context while separately linking its executing maintenance span.

Only successful Billing ingestion marks outbox delivery. That means
`pending_settlement`, not collected money; Billing currently has no live payment
processor and the service must not pretend otherwise.

## Integration API

`resource::Snapshot` contains lowercase plan, opaque billing_owner_id,
authorization_id, origin_traceparent, overage_budget_micros, valid_until, authority_updated_at.
Only server-verified Billing authority may construct it. `apply_snapshot` ignores
older authority updates and refuses a different already-bound opaque owner.
`status` reconciles expiry and period state and returns the current local account.
`ensure_account` is five D1 statements; maintenance Billing has a distinct sixteen-
statement grant. Two oldest linked owners plus three receipt deliveries consume at
most fifteen statements, retaining the overall 800-statement invocation ceiling.

Stock reservations include raw MIME plus immutable agent ZIP, as in the established
storage ledger. Physical recovery/orphan copies retained by that ledger remain
accounted until successful cleanup; GC failures never release quota before object
recovery is confirmed. Search indexes, diagnostics and embeddings are not additional
billable stock meters. Future representation changes must explicitly migrate logical
storage attribution, not silently charge two differently counted copies.

## Evidence

`python -m unittest infra.tests.test_resource_metering infra.tests.test_v020_migration -v`
passes twenty deterministic real-SQL tests (2026-10-07), covering decimal thresholds,
no mail-count guard, stock integration before deletion, fractional carry, lowered cap,
concurrent recipient holds/reversed acceptance, replay, consent capture, grandfather
migration, byte-for-byte preservation of legacy owner/provider state, exact shipped entitlement-refresh SQL,
upgrade/downgrade quota-farming prevention, calendar rollover, and direct-cleanup paid expiry.
Hosted Worker simulation and release checks remain required; native SQLite alone does
not prove workerd, remote D1 trigger splitting, provider integration, or staging health.

References: repository `docs/subscription` proposal in the orchestration workspace;
Cloudflare D1 serialized transactions and batch guarantees:
https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
(verified 2026-10-07: batched statements are sequential transactions; any failure rolls
back the complete batch, which grounds atomic expiry/period and snapshot updates).
Billing consumer authority and pairwise-subject boundary:
`.agents/skills/moesegfault-billing/references/consumers.md`.


### Hosted acceptance-race fixture correction

The first integrated hosted check (run 37614032629, source b07646e) passed 119/124
workerd checks but five accepted HTTP/Cron race fixtures skipped their barrier.
The SQL text still matched. Their `meta.changes === 1` hook incorrectly treated
D1's aggregate `total_changes()` delta as a top-level matched-row count. Provider
acceptance now atomically changes the journal, resource reservation, and period
(three writes for an included Free recipient); paid overage additionally creates
its receipt. This is expected accounting, not duplicate acceptance.

A targeted real-SQL regression executes the shipped acceptance UPDATE and verifies
aggregate changes=3, top-level SQLite changes()=1, one accepted recipient and no
remaining hold. Projection-token-only UPDATE and final accepted-to-sent UPDATE
remain aggregate changes=1: the former does not name `state`; the latter sees an
already committed resource reservation. The simulation hook must verify the exact
owned journal's committed pre/post state, not require aggregate changes=1. The
production projection CAS semantics do not need to be weakened.


### Agent-facing resource introspection

`GET /v1/addresses` reports `limit` as effective *included* slots, with
`limit_kind=effective_included_addresses`, `included_limit`, `grandfathered_limit`,
`effective_included_limit`, `platform_limit=10`, and `overage_enabled`. A new Free
owner therefore sees one included slot, not ten allegedly entitled addresses.
An old Free owner with seven registered addresses sees seven preserved included
slots. Paid overage does not remove the independent ten-slot platform ceiling.

`GET /v1/sending/status` keeps policy/canary semantics and distinguishes commercial
`billing.outbound` (UTC period, included/accepted/reserved/remaining recipient
units) from `billing.overage` (human-approved micros budget, accrued and unresolved
held micros). Its `quotas` lists only the actual two-submission/minute account
safety guard and 10,000-canonical-recipient/day global safety guard. Legacy 50/day,
20/day, five/hour and per-recipient/day observations are not active enforcement.
Shared constants drive both the actual admission and reported safety thresholds.
These observations are advisory, not a reservation or recipient authorization;
remaining budget does not promise a new stock allocation will fit its remaining-
period liability. Private payer, authority and trace IDs are excluded.


### Actual staging migration witness (2026-10-07)

For authoritative staging run 37617246563 / source 938de59, a fixed staging-only
Wrangler D1 SELECT captured pre-migration address tuples at 11:59:37 UTC and
compared them after migration at 12:01:49 UTC. Raw address/owner/rule tuples stayed
in one Python process's RAM; only whole-set commitments and aggregate counts were
saved to `.temp/v020-address-preservation.json`. `WRANGLER_WRITE_LOGS=false`
prevented the configured CLI from retaining private query output. No credential
cache was inspected; no D1 mutation or production query was performed.

Before: 15 historical address rows, one historical owner, every address already
retired, no non-retired allocations, and migrations through 0012 only. After:
0013 and 0014 present; every original tuple unchanged, zero missing/changed/new
rows. Canonical address+local-part+immutable-ownership+slot+rule+state+creation-time
set SHA-256 remained
`2a0b18e52b5bc806de30e1c7597917b51a07d737cc9c47ba748a402729342f7c`.
One resource owner has exact Free defaults (100 recipients, 200,000,000 bytes,
one included address, zero variable budget); non-Free owners=0,
grandfathered-address total=0 and effective included-address total=1.

Because all staging baseline addresses were retired, the *actual staging*
non-retired-grandfather preservation comparison is empty. Ten-active-address
preservation remains separately established by the real production-migration SQL
fixture, not falsely attributed to live staging data.

The exact official npm Wrangler 4.142.0 bundle's `splitSqlQuery` functions and
transition table were also executed without installing dependencies, then every
split statement was passed individually to SQLite. All 0001–0014 migrations
succeeded; 0013 produced 27 statements and 0014 six, integrity_check=ok.
Vendor CLI SHA-256:
`c69202296b8e562a8168fd1732b630c2ecec111e2eca9b4ef0b9f0e3f76b0e90`.
Content-free local evidence is `.temp/v020-pinned-splitter-evidence.json`.
This client-parser probe alone does not establish remote D1 parser behavior;
run 37617246563's successful Apply D1 migrations step and the independent
post-migration SELECT above provide that stronger remote evidence.
