# Billing integration contract for amail v0.2.0

## Established service contract (2026-10-07)

- Staging Billing: `https://billing-staging.moesegfault.dev`; Subscribe: `https://subscribe-staging.moesegfault.dev`.
- Identity issuer: `https://identity-staging.moesegfault.dev`.
- Billing accepts exact OAuth audiences configured in `BILLING_AUDIENCES`; currently only `subscribe-staging`.
- `GET /v1/plans` returns deployment-owned plan records. `GET /v1/me` accepts a verified Identity access token and returns account plus product-scoped subscriptions.
- `POST /v1/activations` accepts `{code}` plus `Idempotency-Key`; activation atomically grants one product subscription snapshot. Different active plans cannot be switched until expiry.
- Subscribe holds bearer tokens server-side, uses same-origin CSRF protection, and redirects only to exact configured return URLs. Existing hosted activation requires a legitimately issued activation code; it is not a payment checkout.
- Before this integration, Billing had activation grants but no amail spending consent or metered usage ledger. v0.2.0 adds those two capabilities below. It still has no payment processor, recurring debit or automatic settlement; activation and accrued liability must never be represented as successful monetary collection.

## Identity integration constraint

Billing keys accounts by `(issuer, sub)`, and Identity issues pairwise subjects. Existing amail CLI staging client `amail-cli-staging` uses sector `amail-staging.moesegfault.dev`; Subscribe uses `subscribe-staging.moesegfault.dev`. Adding an audience alone cannot join these accounts. Changing the deployed CLI sector would change every subject and can orphan existing addresses. Preserve existing subjects unless a deliberate migration proves ownership and preserves addresses.

Preferred bridge: amail creates a service-authenticated, short-lived authorization intent bound to its immutable local account ID; a human authenticates and approves through Subscribe; amail retrieves the authoritative receipt over the service boundary. No editable email joins, browser bearer exposure, agent-granted paid plan, or agent-raised spend cap. The implemented session API is specified below; actual staging acceptance is recorded at the end of this contract.

## Accepted community tariff

| Plan | CNY/month | Outbound recipient deliveries/month | Storage bytes | Active addresses |
| --- | ---: | ---: | ---: | ---: |
| Free | 0 | 100 | 200,000,000 | 1 |
| Lite | 9 | 1,000 | 2,000,000,000 | 3 |
| Plus | 29 | 5,000 | 10,000,000,000 | 5 |

Shared overage: outbound CNY 0.005/recipient delivery; storage CNY 1/decimal GB-month; addresses CNY 3/address-month. No inbound-count, stored-message-count, or semantic-search commercial quota. Human authorization is required for paid grants and a nonzero overage budget. Existing addresses are grandfathered intact while existing users become Free.

## Release boundaries

Staging only. Do not alter production configuration, keys, audiences, catalog, or service state. Public docs and simulation must identify the unavailable monetary collection separately from real hosted authorization and durable usage accounting. Activation-code grants can exercise paid-plan semantics on staging but cannot prove recurring collection.

## Source files inspected

- Subscriptions `README.md`, `docs/api-contract.md`, `docs/subscribe-bff.md`.
- Subscriptions `crates/billing/src/{domain,lib}.rs`, `crates/subscribe/src/lib.rs`.
- Subscriptions staging Wrangler configurations and `infra/subscribe-staging-client.json`.
- amail `.agents/skills/moesegfault-billing/` and `infra/identity/client-staging.json`.

## Concrete v0.2.0 bridge API (implemented in subscriptions repository)

Service requests use a dedicated `Authorization: Bearer <AMAIL_SERVICE_KEY>` secret. This key does not authorize activation-code issuance or human approval. The existing amail OAuth sector and subject mapping stay unchanged. Service owner IDs must be opaque URL-safe hashes of the immutable local account identity, 16–128 characters; no raw email or issuer/subject claims are sent.

### Create a human consent request

`POST /v1/service/amail/authorizations`, required original UUID `Idempotency-Key`:

```json
{"owner_id":"opaque_account_hash_here","plan_id":"amail-lite","overage_budget_micros":0,"return_url":"https://amail-staging.moesegfault.dev/billing/return"}
```

```json
{"authorization_id":"opaque_192_bit_handle","authorization_url":"https://subscribe-staging.moesegfault.dev/amail/authorize/opaque_192_bit_handle","expires_at":1791388800}
```

The request lasts 30 minutes. Exact retries preserve the original result; different payload with the same key returns 409. Parameters are proposed defaults only. The browser must explicitly choose its plan and spending cap after authenticating to Subscribe; the machine key cannot approve them.

### Receipt / authoritative account projection

`GET /v1/service/amail/authorizations/{authorization_id}`:

```json
{"authorization":{"id":"opaque_192_bit_handle","owner_id":"opaque_account_hash_here","product_id":"amail","plan_id":"amail-lite","overage_budget_micros":5000000,"return_url":"https://amail-staging.moesegfault.dev/billing/return","status":"approved","expires_at":1791388800,"approved_at":1791387100,"currency":"CNY","contract_version":"amail-v0.2.0"},"binding":{"owner_id":"opaque_account_hash_here","account_id":"opaque_billing_payer_id","product_id":"amail","plan_id":"amail-lite","overage_budget_micros":5000000,"currency":"CNY","contract_version":"amail-v0.2.0","valid_until":1793979100,"entitlements":["amail.plan.lite","amail.outbound.monthly.1000","amail.storage.bytes.2000000000","amail.addresses.3"],"authorization_id":"opaque_192_bit_handle","updated_at":1791387100},"settlement_mode":"activation_code_and_accrual"}
```

Pending/cancelled/expired receipts have no binding. Routine authoritative refresh: `GET /v1/service/amail/accounts/{owner_id}` returns `{binding,settlement_mode}`; unbound account returns `binding:null`. Expired paid grants project to `amail-free` with budget 0 without deleting the payer association or any amail address. A paid projection is bounded by its real activation subscription period. Free `valid_until` is null.

One CNY equals **1,000,000 integer micros**, not cents and not floating-point currency. Maximum human-selected budget is 1,000,000 CNY. Product is always `amail`; contract version is `amail-v0.2.0`.

### Hosted human API (Subscribe BFF only)

Authenticated same-origin browser calls `GET /api/amail/authorizations/{id}` and CSRF-protected `POST /api/amail/authorizations/{id}/approve` with:

```json
{"acknowledge":true,"plan_id":"amail-lite","overage_budget_micros":5000000}
```

Billing verifies the current user's real active matching amail subscription for paid approval; otherwise returns `409 activation_required`. Existing activation-code form remains available. Free requires no code. Approval and payer binding commit atomically; a different payer cannot replace an existing association. Cancel uses the corresponding `/cancel` POST. The stored approved fixed return URL is offered as an explicit navigation, never treated as proof of payment.

### Usage accrual

`POST /v1/service/amail/usage`:

```json
{"event_id":"stable_unique_event_id","owner_id":"opaque_account_hash_here","period_start":1790812800,"period_end":1793491200,"meter":"outbound_recipients","quantity":1,"amount_micros":5000,"occurred_at":1791387100}
```

Meters: `outbound_recipients`, `storage_byte_seconds`, `address_seconds`. Root amail owns resource counters, reservations, exact rate computation and durable outbox; Billing owns consent ceiling and immutable idempotent liability ledger. Positive liabilities require existing human payer binding and cannot exceed the approved period budget. Identical event replay returns its existing receipt; payload mutation returns 409. Quantities can exceed JavaScript's safe integer limit internally and are preserved as SQLite integers by textual binding. Monetary amounts stay below safe integer limits. Charges remain `pending_settlement`, never falsely `paid`.

`GET /v1/service/amail/accounts/{owner_id}/usage?period_start=...` returns `{owner_id,period_start,amount_micros,overage_budget_micros,settlement_status:"pending_settlement",events_count}`. Overlapping periods for the same owner are rejected to prevent changing a period key to reset budget.

### Deployment additions (staging only)

- Billing secret `AMAIL_SERVICE_KEY`, shared only with the staging amail worker through its environment.
- Billing vars `SUBSCRIBE_ORIGIN` and `AMAIL_RETURN_URL_ALLOWLIST` pinned to the fixed staging hosts above.
- Billing D1 migrations `0003_amail_authorizations.sql`, `0004_amail_usage.sql`.
- Staging catalog `amail-free`, `amail-lite`, `amail-plus`; production catalog and audience/Identity registrations are unchanged.


## Final usage DTO amendment

Usage ingestion additionally **requires** `authorization_id` and `authorized_at` on
all events, including zero-charge fractional stock events:

```json
{"event_id":"stable_unique_event_id","owner_id":"opaque_account_hash_here","period_start":1790812800,"period_end":1793491200,"meter":"outbound_recipients","quantity":1,"amount_micros":5000,"authorization_id":"opaque_192_bit_handle","authorized_at":1791387000,"occurred_at":1793491300}
```

The original resource-admission timestamp and human receipt are captured before the
external side effect. Observation can be after the original accounting period or at
period_end. Historical consent is checked at admission; lowering a newer cap does not
invalidate previously admitted liabilities. Total period liability remains shared
across receipts, never reset per receipt. New admissions under a lower cap cannot use
the old receipt. Future observation tolerance is 300 seconds. No fallback to current
consent is accepted, because v0.2.0 has no legacy usage producer contract.

## Actual staged service acceptance — 2026-10-07

Billing/Subscribe runtime source is `c77b7ddf19d64e5c71c281fd378cfb774d19a559`:

| Service | Actual 100% serving version |
| --- | --- |
| Billing | `2fa3e271-3e93-4b03-a67d-2332f14f0e1d` |
| Subscribe | `f4682841-2008-4a0f-8b6e-9016c64ca9ca` |

[Delivery 37617117905](https://github.com/kleedaisuki/moesegfault-subscriptions/actions/runs/37617117905)
passed builds, security/domain tests, artifact verification and deployed both
versions, then ended failure at an overly strict normalized capture-settings
checker. Do not characterize that workflow as green. No code writer was replayed.

[Pure-read privacy acceptance 37618095870](https://github.com/kleedaisuki/moesegfault-subscriptions/actions/runs/37618095870)
completed successfully at 2026-10-07 12:01:57 UTC / 20:01:57 UTC+8. Checker source
`4fc22988e6e7e90c9d62de74b85259bed27caa0c` matches the independently established
Mail canonical capture contract and official Cloudflare opt-in Issues semantics.
Actual current-resource root/Logs/Traces switches were explicitly false; inactive
invocation_logs preference was true; Issues section was absent under its documented
opt-in-off rule. The checker rejects unknown root/Logs/Traces and present
unknown/enabled Issues. Legacy views did not contradict the authoritative resource.
Serving versions stayed unchanged across both read-only diagnosis and verification.
No build, package, deploy or production job ran in that acceptance workflow.

Actual public staging smoke subsequently passed Billing health, Subscribe HTML/CSP,
guest session and protected personal-API boundaries. This removes the service
privacy/readiness prerequisite for the controlled human OAuth test; subsequent
full integration acceptance is recorded below rather than inferred from smoke tests.
Detailed evidence and the previous migration/dependency repairs are retained in
Subscriptions `docs/deployment/staging.md` and its linked incident notes.

### Final real integration acceptance

[Mail 37630962022](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37630962022)
completed successfully with exact candidate `d1291b8`, a real existing Lite grant,
normal browser cancellation/approval/return and authoritative CLI projection.
Safe artifact `11486684051` records real positive address usage, budget restoration
to zero, six delivered period events and retained human plus asynchronous ancestry.
The same workflow repeated actual inbound/archive/search/delete and controlled
outgoing receipt recovery/replay/delivery-feedback acceptance.

Final fixed readback [37634410400](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37634410400)
confirmed Mail accrued 22 CNY micros, Billing accrued the same 22 micros across
six events, every outbox delivered marker present, budget zero and address count
zero. All six retained Billing usage servers reported HTTP 200/success. Three
events originated before subsequent consent reductions; their valid historical
receipts survived and normal Cron/backoff delivered them without editing usage.
The new seven-micro test is included in that 22-micro period total. This proves
actual pending-settlement accrual, not automatic monetary collection.
