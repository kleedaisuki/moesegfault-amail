# v0.2.0 integration acceptance scenarios

## Basis and evidence boundaries

The owner's contract is Free/Lite/Plus; only recipient sends, storage bytes and
address occupancy are commercial meters. Inbound message count and semantic
search are not commercial meters. Existing accounts become Free without losing
any registered address. Agent CLI initiates subscription, but a human approves in
a browser. v0.1 clients are intentionally unsupported. Staging is the deployment
target; production is outside this workstream.

Use the tariff and service boundaries in `billing-integration-contract.md`.
Billing originally supported activation grants, not monetary settlement. A local
mock, a calculated invoice, or a successful plan grant does not prove payment
collection. Record those outcomes separately.

Existing hosted entry points are `infra/tests/staging_hosted_e2e.py` and
`infra/tests/staging_mail_e2e.py`. The workerd suite executes compiled production
Rust/Wasm with local D1 and strict no-provider egress. New scenarios should extend
these boundaries, not replace the implementation with a JavaScript billing model.

## Local compiled simulation

| Scenario | Expected observable outcome |
| --- | --- |
| Upgrade pre-v0.2 database with ten active owned addresses | Exactly the same addresses, ownership, rule IDs and state survive; effective plan is Free; existing addresses do not require immediate payment |
| New empty account | Free defaults: 100 monthly recipient deliveries, 200,000,000 bytes, one included address; no paid consent |
| Request Lite from authenticated CLI | A pending session and human URL are returned; entitlement and spend budget remain unchanged |
| Agent calls completion or alters session owner | Cannot authorize payment/paid entitlement; cross-owner session reads fail without leaking URL or receipt |
| Human denies or session expires | Typed terminal state; old plan and budget remain unchanged; polling cannot renew authorization |
| Human approves and receipt is temporarily unavailable | CLI can resume the same session; exactly one grant applies after retry; no duplicate charge or extension |
| Concurrent identical activation/usage submissions | One logical grant/debit; retry returns its original result; same key with changed payload is rejected |
| Free final included send with two concurrent attempts | Reservation prevents exceeding authorized budget; rejected attempt never reaches mail provider |
| Provider accepted, client response lost | Same send key replays original receipt, no second provider call and no second debit |
| Provider outcome unknown | Reservation retained until authoritative recovery; new requests cannot reclaim it merely by timeout |
| Provider definitively rejects before acceptance | Reservation released once; no accepted-send charge |
| Same account, different aliases/Agent processes | One shared monthly send/storage/address budget, not per-address free allowances |
| Receiving many tiny messages | No message-count meter or stored-count rejection; only byte capacity and technical safety limits apply |
| Exact byte capacity / one byte over | Exact included limit is accepted; overage without human consent is explicitly rejected; no silently dropped accepted message |
| Delete stored mail and repeat deletion | Bytes released exactly once; previous mail remains exportable until the normal deletion action |
| Repeated semantic queries on each plan | No commercial search quota or charge; ordinary bounded CPU/concurrency protections remain allowed |
| Month boundary and plan switch | Calendar/time basis is explicit; same send retry cannot move into a fresh bucket or be charged twice |
| Invalid or v0.1 client version | Typed upgrade-required response before any billing/mail mutation |
| Billing unavailable | Existing reads/exports remain available; paid authorization fails closed; accepted/unknown sends are not resubmitted |

## Staging user loop

1. Admit exact same-run CLI and Worker artifacts through the existing hosted gate.
2. Log in as a controlled staging identity; record only sanitized account/plan
   outcomes, never tokens, activation codes, browser URLs or mailbox contents.
3. Verify Free status and retained registered addresses with the admitted CLI.
4. Start a subscription session from the CLI. Open its returned URL in a browser
   using the normal human flow; no agent-side bearer-token handoff or direct grant.
5. Exercise pending, cancellation and resume before completing one legitimately
   authorized staging activation. Assert CLI status changes only after the
   authoritative receipt. A preexisting activation code is not a payment proof.
6. Reuse the existing controlled inbound ZIP/search/delete loop. Add a scoped
   owned send only under the current staging grant/policy authorization; inspect
   usage delta and same-key recovery. Never invent live provider feedback rows.
7. Verify linkage across CLI request, amail API, Billing session and browser
   receipt; each service uses its own span, preserving trace ancestry/correlation.
   Assert private payloads, authorization capabilities and credentials are absent
   from retained telemetry. Correlation IDs alone are not proof of native tracing.
8. Preserve sanitized run/source/artifact/version references in the canonical
   `docs/validation.md` ledger. An unavailable browser or Billing capability is an
   unverified requirement, not a pass and not automatically an amail defect.

## Execution status

2026-10-07: scenarios derived from the owner request, existing maintainer runbook,
staging harness and inspected Billing contract. Implementation is in progress;
none of the new compiled or hosted scenarios is claimed passed by this document.

### Executable migration fixture

`python -m unittest infra.tests.test_v020_migration -v` builds the real 0012
schema, inserts ten active aliases, an inbound message/storage reservation and an
unknown send under a local-only scoped grant, then applies subsequent migration
files. It compares every legacy column in those tables and runs foreign-key and
integrity checks. Python 3.14 / SQLite on Windows: baseline passed on 2026-10-07
before a v0.2 migration existed. This is harness readiness, **not v0.2 acceptance**;
Free/default/grandfather assertions will be added against the actual new schema.

After 0013/0014 landed, all three migration tests passed: legacy column
preservation; existing Free defaults with ten live addresses grandfathered and
zero backdated liabilities; new Free owner with no payer/spending consent.

`infra/tests/worker-boundary/billing-human-loop.test.mjs` now executes the compiled
API against synthetic signed OIDC and an allowlisted Billing transport. It covers
pending-to-approved receipt projection, denial/expiry, cross-owner rejection,
wrong-owner binding, same-key replay and retry after service failure. It asserts
the outgoing Billing `traceparent` retains the incoming trace ID and service
credentials never enter public error bodies. Syntax checks pass; compiled hosted
execution is still pending. This is not a browser, real payment, native trace-sink
delivery, or deployed Billing acceptance claim.

The causal trace case additionally captures actual Rust-produced Queue bodies
with a native local consumer, then checks CLI parent -> API server -> Billing
dependency -> exact propagated upstream span ID, source time/duration and absence
of raw subject, authorization URL and service credential. Queue delivery uses a
positive arrival barrier with a 10-second failure deadline, not a blind sleep.
Execution is pending; even a pass will prove local compiled production behavior,
not deployed Cloudflare sink retention or real browser service traces.

`python -m unittest infra.tests.test_v020_migration infra.tests.test_v020_resource_concurrency -v`
passes four tests against actual 0013/0014 on local Windows Python 3.14. The
concurrency test opens two SQLite connections to a task-local `.temp` database,
uses a barrier to race the last included recipient unit and observes exactly one
reservation winner, one quota rejection, 100 total reserved units and no liability
outbox. It proves SQLite trigger serialization, not hosted D1/provider delivery.
The first harness execution exposed SQLite connection-context cleanup on Windows;
connections now close explicitly, without changing the quota assertion.

Existing workerd direct-SQL fixtures explicitly initialize their synthetic Free
owners/current resource periods through `seedResourceAccount`; production resource
guards remain installed. Current protocol headers are shared via `api-version.mjs`.
The telemetry fixture separately exercises missing/old/wrong protocol rejection
and unversioned public health, so defaults cannot hide the intentional v0.1 break.

### Scheduled usage delivery simulation

`billing-outbox.test.mjs` is included in the compiled workerd test command. It
creates a synthetic human-bound Free account and reserves/accepts 101 recipient
units using real 0013 triggers, yielding exactly one 5,000-micro overage event.
The real maintenance entry dispatches it to a strict Billing fixture. Assertions
cover original authorization ID/time, immutable event body, identical retry key,
propagated W3C context and no private mailbox/credential payload. Cases include
normal delivery followed by a no-op sweep, HTTP 503 with retained liability and
backoff, and Billing acceptance followed by a deliberately failed local ACK SQL
update. The final case requires the next sweep to replay the same event and the
synthetic receiver to retain one liability, not two. No real send or payment is
performed. JavaScript syntax is checked; compiled hosted execution is pending.
