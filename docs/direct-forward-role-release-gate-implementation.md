# Direct-forward-only contact gate implementation

Date: 2026-10-01. **Source implementation, not deployment or acceptance.**
Inbox/Junk review and Cloudflare-notice response within 24 hours remain pending.
Public sending must remain held. No confidential destination appears here; the
four historical receipts are retained evidence, not repeated by this change.

## One contract, one database, one readiness predicate

The direct-only appendix of
[the architecture](direct-forward-role-release-gate-architecture.md) governs
this implementation; its earlier two-mode design is not implemented. Mail no
longer reads `ROLE_MONITOR` or manufactures/copies a role-Worker lease. The
future role Worker remains outside the active v0.1 contact contract.

Migration `0009_direct_role_contact.sql` is additive. It preserves mail,
idempotency, account/recipient policy and held one-use canaries. It explicitly
holds global sending, clears only historical abuse-contact acceptance, and
creates **no adopted policy or health row**. The other independent release
attestations are not inferred or erased.

| Owner | State | Invariant |
| --- | --- | --- |
| Operator | `role_contact_policy` | Singleton version 1, fresh UUID per adoption, provider destination ID and four distinct fixed rule IDs; no mailbox value/hash. |
| Human operator | Existing gates + `abuse_contact_contract_id` | Coverage/intervention acceptance binds to the exact contract; machine success never updates it. |
| Configuration checker | `role_contact_health` | Same contract, database observation start time, healthy expiry exactly start + 21600 seconds or unverified expiry zero. |
| Every admission reader | `direct_role_contact_ready` view | Human binding + healthy exact contract + `0 < checked_at <= unixepoch() < expires_at`. |

The view is reused by Rust pre-provider-call checks, global allow SQL, release
publication readiness, and an independent `BEFORE INSERT` admission guard.
The guard does not depend on trigger order. A second guard closes the legacy
consumed-canary SQL alternative whenever global state is not held. Neither
allows an allowed-but-expired public gate to fall back to a canary. Existing
account holds, exact-recipient Rust canary checks and recipient blocks remain.

Policy insertion/replacement/removal atomically clears health and human contact
acceptance and holds global sending. Contract UUIDs are never reused: a small
permanent policy-adoption ledger retains their identities and opaque evidence.
Health audit retains only the most recent **256 state/contract transitions**;
identical successful renewals do not accumulate daily audit copies. Failure at
the same second as a healthy observation wins; equal/older healthy observations
cannot overwrite a recorded failure. A later healthy observation never allows
sending automatically.

## Trusted hosted interfaces (not invoked by this implementation)

`infra/operator/direct_contact_policy.py` requires main-branch GitHub Actions,
`INPUT_TARGET` (`staging` or `production`), `INPUT_CONFIRM=ADOPT_DIRECT_CONTACT_HELD`,
`INPUT_CASE_REF`, `GITHUB_ACTOR`, existing account/API-token Secrets,
`INPUT_DESTINATION_ID` and the four `INPUT_*_RULE_ID` pins corresponding to the
four fixed schema columns. It generates a new UUID and adopts only held state.
Retrieve the resulting contract ID privately; the script prints no IDs/pins.
A change in destination, route identity or operational commitment requires new
adoption, not editing a still-attested contract in place.

`infra/operator/attest_gate.py` retains its existing non-contact gate interface.
For abuse-contact `verified=true` it additionally requires the exact
`INPUT_CONTACT_CONTRACT_ID` and
`INPUT_CONTACT_COVERAGE=ACCEPT_INBOX_JUNK_AND_24H_CLOUDFLARE_RESPONSE`. The opaque
case must cover ongoing coverage, response ownership, safe attribution,
intervention and a separate official reply path. This phrase is an explicit
human statement, not proof of actual mailbox visits. Revocation needs neither
coverage phrase nor contract; it remains unconditional. The current operator
workflow does not supply these new fields, so it cannot silently bless the
pending commitment. Wiring/adoption requires subsequent reviewed work.

`infra/operator/direct_contact_health.py` requires main-branch GitHub Actions,
existing `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`,
`CF_EMAIL_ROUTING_TOKEN`, `ROLE_FORWARD_DESTINATION`, and hosted run/attempt IDs.
`INPUT_TARGET` defaults to production. It reads the scoped policy and database
time **before** provider reads, checks complete bounded inventories twice,
verifies the unique destination ID/address/verification and four pinned exact
API-owned forward rules with no literal-role conflicts, then conditionally
writes only the unchanged contract. It uses a GET-only routing client and
rejects redirects for both credentials. Rule `id` and legacy `tag` spelling are
accepted only when they do not conflict. Unrelated routing churn is not renewal
failure when the relevant identities/shape remain identical.

All unclassified routing outcomes write unverified when D1 is reachable, with
an atomic hold. A D1 failure performs one scoped readback, **no write retry**,
and cannot announce a renewal unless the exact expected row is read back.
If the write did not commit, old health lasts only until its original expiry;
there is no claim of immediate revocation during a database outage. Runner
cancellation, a missing scheduled run or a disabled workflow cannot renew.
**The hourly scheduler is not added here and continuing hosted coverage remains
a release blocker.** Six-hour expiry is an operating default, not a provider SLA.

`python infra/operator/check_send_hold.py --target staging` (or production)
reads only the pre-existing `send_policy` schema using the existing account/API
token. It proves exactly one global row and that exact row held. It works before
0009, without any contact policy, four-forward production evidence or role
resource. Missing schema/row, allowed state, malformed/provider replies deny.
This is the source interface for pre/post-mutation deployment hold readback.

The API token remains a broader D1 credential; scoped SQL is a trusted-code
boundary, not invented table-scoped authorization. No new Secrets or mailbox
access are introduced. Routing mutations must invalidate/hold the contract
before changing provider state; this checker does not repair provider routes.

## Verification and rollout boundaries

Added `infra/tests/test_direct_contact_gate.py` for the existing hosted infra
test discovery. It uses real migration/operator SQL with a deterministic clock
and synthetic complete provider inventories. Tests cover held migration,
pre-migration held readback, missing/expired/equal/future observations, no
canary fallback under allow, one held canary, contract replacement/reuse,
conflicting human evidence, provider/shape failure, bracketed drift, no blind
retry after D1 failure, distinct route identities and GET-only/no-redirect
capability. Release response tests now require `contact_ready=1`.

**No local tests, builds, hosted run, provider mutation or deployment was
executed for this source change.** Hosted execution and independent review are
required before acceptance. Source tests are not claimed as deployed D1 trigger
acceptance; the real D1 migration splitter and built Rust Worker must be tested
on the hosted lane before a held rollout. Existing legacy-only outbound tests
still test migration 0006 contracts; the new hosted suite tests 0009 directly.

Rollout must prove global hold before migration and before/after serving-version
changes. Keep hold through contact adoption, machine check, explicit human
coverage, independent route/protocol/intervention acceptance and remaining
privacy/outbound/publication gates. Rollback to an old binary is held-only: it
does not understand direct freshness. Historical role resources are not deleted.
API-only binding/trace graph reconciliation is a separate coordinated change;
publication requires its exact serving pins as well as this database predicate.

Admission and pre-provider checks cannot atomically recall an already in-flight
provider send after a hold or external routing change. Existing ambiguous-send
and idempotency handling remain authoritative; never blindly retry such a send.
Periodic configuration evidence is not continuous integrity, mailbox attention,
guaranteed Inbox placement, or automatic complaint resolution.

## Primary references

- [Cloudflare Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/): direct bindings and explicit failure behavior, without re-enabling retained request telemetry.
- [D1 SQL statements](https://developers.cloudflare.com/d1/sql-api/sql-statements/): actual D1 SQL support; hosted acceptance remains necessary for trigger migration splitting.
- [Routing rules API](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/list/) and [destination addresses API](https://developers.cloudflare.com/api/resources/email_routing/subresources/addresses/methods/list/): provider identity/verification shapes. These are configuration evidence, not human operational coverage.

These normative admission and operational obligations do not need speculative
academic automation to be credible. The deferred agent operations center is a
future authorization/ownership design, not a second present runtime mode.
