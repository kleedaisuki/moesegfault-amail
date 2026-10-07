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

2026-10-07: production Rust/Wasm/workerd contracts and isolated runtime deployment
passed in `37617246563`; complete native/browser/mail and 14-span retained human
authorization/CLI tracing passed in `37621170985`. Canonical exact source/run,
component versions and evidence boundaries are in `../validation.md`. The
additional explicitly opted-in positive address-overage and asynchronous retained
acceptance passed in `37630962022`; neither authorization nor usage accrual is a
claim of monetary collection.

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
credentials never enter public error bodies. Compiled hosted execution passed in
`37617246563`. This simulation alone is not a browser, real payment, native trace-sink
delivery, or deployed Billing acceptance claim.

The causal trace case additionally captures actual Rust-produced Queue bodies
with a native local consumer, then checks CLI parent -> API server -> Billing
dependency -> exact propagated upstream span ID, source time/duration and absence
of raw subject, authorization URL and service credential. Queue delivery uses a
positive arrival barrier with a 10-second failure deadline, not a blind sleep.
Compiled execution passed in `37617246563`; that case proves local compiled
production behavior, while the separately accepted `37621170985` retained witness
establishes actual deployed sink retention and browser-service trace ancestry.

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
performed. Compiled hosted execution passed in `37617246563`; this is not the
additional live positive-liability acceptance below.

## Executable hosted browser extension

The existing `infra/tests/staging_hosted_e2e.py` now optionally calls
`staging_billing_e2e.execute` immediately after its normal admitted-CLI native
login and before the existing inbound/search/delete/send loop. It reuses the
same protected staging identity and `staging_identity_cdp.Browser`; no additional
identity registration, provider deployment or activation issuance is embedded.

Required runner inputs (secret values must not appear in commands/logs):

| Input | Contract |
| --- | --- |
| `AMAIL_STAGING_E2E_CONFIRM` | Existing `RUN_STAGING_E2E` admission |
| `AMAIL_STAGING_BILLING_CONFIRM` | Explicit `RUN_STAGING_BILLING_V020` |
| `AMAIL_STAGING_BILLING_PLAN` | `free` (default) or `lite` |
| `STAGING_E2E_USERNAME` / `STAGING_E2E_PASSWORD` | Existing protected synthetic account, never a customer |
| `STAGING_E2E_AMAIL_ACTIVATION_CODE` | Only needed for Lite's first redemption when no matching active Billing grant exists; inject privately, then delete after consumption |
| Other artifact/mail/provider inputs | Unchanged existing hosted harness contract |

Invoke the existing runner entry, not a parallel deployment command:

```powershell
python infra/tests/staging_hosted_e2e.py
```

The hosted workflow must explicitly pass the new confirmation/plan and, only when needed, private code
before this optional branch runs. The runner retrieves its credentials through
the already stored same-user DPAPI blob, navigates the exact staging authorization
path, completes normal Subscribe→Identity→Subscribe SSO and types only at checked
first-party origins. It first cancels a fresh Free intent, verifies the CLI's
cancelled receipt, then approves a new Free/Lite intent through the visible
checkbox/form. Lite first reads the current authorization's minimal subscription
projection through the authenticated same-origin BFF GET. An active, unexpired
matching amail-lite grant is reused without typing or redeeming a code, including
when Mail is still Free because a prior redemption succeeded before approval.
Only a genuinely missing matching grant permits one ordinary UI redemption of a
legitimate private code; the helper then verifies the authoritative grant again.
This is synthetic-human validation, not consent
from a real paying customer. Approved budget is deliberately zero.

CLI reads back the effective plan and `payment_collection_available:false`.
Telemetry is enabled for these bounded CLI commands, then flushed; the helper
reads only actual billing trace IDs from the local diagnostic SQLite journal.
The safe result is `.temp/staging-billing-evidence.json`, containing plan, phase
outcomes, time bounds and trace IDs, never URL, owner identity, code or mail body.
Upload this sanitized file separately if durable hosted evidence is required;
the existing parent cleanup removes all private browser/profile/credential files.
Retained cross-service witness queries must still prove the collected IDs; local
journal presence is not remote retention evidence.

Mail baseline may be Free or the requested Lite plan. The helper refuses to
downgrade a different paid plan merely to make a rerun pass. A successful Lite
run is not permission to redeem another code or reset the account. Repeated
validation uses the existing grant; it does not require another activation code.
Activation codes are single-use: retrying the original redemption with its same
idempotency key only returns the original result, never another grant or period.
Delete the temporary `STAGING_E2E_AMAIL_ACTIVATION_CODE` GitHub staging secret
after the first confirmed redemption. A stale configured code is ignored when
the matching grant is already active. Missing/uncertain subscription readback
never triggers automatic code issuance, hidden approval or a new-key retry.
The safe evidence's `grant_source` distinguishes `existing`, `redeemed` and
`not_required`; no activation material is included.

Legitimate issuance is the existing subscriptions command
`node scripts/admin-issue.mjs --plan amail-lite` after the staging catalog exists.
It uses the ignored local administrator key and sends only to configured
`ADMIN_EMAIL`; the raw code is not returned. Retrieval must use the authorized
amail mailbox workflow, bounded by issuance time and exact message ID. No D1 code
minting, provider-store reads or public transcript of the code is permitted.
Subscriptions has no persisted reusable synthetic credential fixture; its prior
2026-10-05 manual Beta acceptance is historical evidence, not current credentials.

Local harness verification: `python -m unittest discover -s infra/tests` passes
183 tests on 2026-10-07; the new two tests check exact URL routing/privacy and
bounded object-only CLI JSONL parsing. Python compile checks pass. These results
do not execute Chrome, SSO, activation, hosted Mail or retained trace retrieval.

The grant-recovery revision adds offline helper-flow cases for Mail Free with an
already redeemed Billing grant, already projected Lite with a stale code, first
redemption exactly once, missing grant/code, conflicting paid baseline and
expired/mismatched subscription metadata. The helper's eight tests pass, and the
full infrastructure checkpoint passes 199 tests. These mocked branch tests assert
code removal before child execution and no duplicate UI redemption; they are not
new hosted activation evidence.

## Hosted compiled checkpoint and concrete fixture correction

Checks run [37614032629](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37614032629)
at source `b07646e` is **failed**, not release admission. Its actual workerd log
(`.cache/v020/mail-checks-37614032629.log`) records 119 passes and five failures.
The Billing human-loop, native causal Queue capture, outbox success/backoff/lost
ACK and incompatible-version negative cases passed at that source. All five
failures were the accepted HTTP/Cron race suite, which exited before the fixture's
committed-acceptance pause. This is compiled simulation evidence, not deployment
or hosted browser acceptance.

Inspection found the exact acceptance SQL still matched the production operation,
but the fixture required D1 `meta.changes===1`. New atomic accounting triggers
make one accepted journal mutation produce multiple total changes. The actual SQL
reproduction `test_acceptance_trigger_changes_are_not_direct_row_identity` proves
`SELECT changes()=1`, `total_changes` delta greater than one, and the expected
reserved→accepted accounting transition. The corrected test-only adapter reads
the exact owner/idem row before and after the native commit, verifies
`submitting→accepted` plus the submitted provider ID, then pauses. No race
assertion, barrier or production implementation was weakened. Its syntax and SQL
reproduction pass; the corrected compiled race still requires a new hosted run.

The hidden-accepted deletion case also contained an eight-phase rotation fixture.
v0.2 adds Billing as phase nine, so its old timestamp no longer made GC precede
outbound recovery. The test now uses `1680000600000` and explicitly asserts
`floor(timestamp/300000)%9==4` (Deleted first), preserving the original ordering
scenario and all source-retention/terminalization assertions.

The next outbox test revision also captures actual native scheduled records:
persisted original send context must parent the usage HTTP dependency, while its
explicit span link points to the actual new scheduled root. This new assertion
passed compiled execution in `37617246563`. Its real positive-liability scheduled
delivery and retained asynchronous-link counterpart subsequently passed the
explicit real acceptance below, independently of that compiled checkpoint.

## Explicit real address-meter acceptance

`billing_metering_confirm=RUN_STAGING_BILLING_METERING_V020` is an additional
opt-in, not a change to normal subscription acceptance. The existing staging
confirmation, Billing browser confirmation, Lite selection and retained-trace
selection must all also be present. Normal jobs retain their 40-minute timeout;
only this explicitly requested path receives 50 minutes.

The protected synthetic account must have a real existing Lite grant, exactly
three included addresses, no grandfathered addresses, no registered addresses and
zero budget and zero current USD accrued/reserved money. Historical CNY balances
remain separate and are not a reason to replay a charged test. Storage must remain
within its included allowance, outbound
reservations must be zero, and entitlement/month boundaries must be more than
1,200 seconds away. Fixed read-only Mail D1 counts and normal provider rule lists
must leave four slots within the 198-user-address / 200-provider-rule ceilings.
No activation material is accepted by the metering helper.

The normal Manage browser UI temporarily authorizes a USD 0.50 spending ceiling.
The normal CLI creates four nonce-scoped task addresses, observes all four active,
and holds them for at least 6.1 real seconds. Normal CLI retirement closes every
task address; the same browser restores zero budget and checks the authoritative
receipt/readback **before** delivery polling. A lost creation acknowledgement
still triggers retirement of the attempted task address if listed. Cleanup and
budget restoration are independent mandatory recovery actions: failure of either,
or both, is an explicit failure and cannot become a successful evidence artifact.

The helper does not send mail, seed usage, write D1, invoke a synthetic scheduler,
mint codes, or exercise a payment processor. It waits for the existing five-minute
Cron to deliver actual durable outbox liabilities. Its provider adapter accepts
only fixed SELECT statements. Delivered markers, the exact period, positive
address-seconds, an original trace context, and the authoritative Billing usage
amount/event count must agree. Task liability must be positive and at most 10,000
USD micros ($0.01); the $0.50 ceiling is not the expected charge. Billing must
report zero current budget and `pending_settlement`, never payment collection.

Polling is bounded by 660 seconds and the shared 810-second Billing evidence
envelope. Last-poll admission reserves 75 seconds for its three bounded reads and
60 seconds for the parent's final telemetry flush; the outer retained-reader
15-minute window consequently retains its 90-second reserve. Long setup can
shorten the polling opportunity rather than silently widening the evidence scope.

Offline checkpoint (2026-10-07): the 21 focused tests in
`test_staging_billing_metering`, `test_staging_billing_e2e`, and
`test_staging_billing_workflow` pass. They cover the full controlled helper flow,
partial creation/lost acknowledgement, independent cleanup/restore failures,
late evidence-window admission, default-zero behavior, and optional trace union
before final flush. These simulations do not establish live Cron delivery or a
hosted metering pass; that requires the explicitly confirmed staging run.

### Historical CNY hosted result (superseded tariff, preserved evidence)

[37630962022](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37630962022)
passed the full optional path at exact source `d1291b80923d7d463e596bcd702a6e251039797f`;
producer [37628260838](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37628260838)
and native CLI/Skill artifact `11485896406` were admitted before use. Safe artifact
`11486684051` records four created/retired addresses, seven actual excess
address-seconds, seven newly accrued CNY micros, six acknowledged period events,
zero restored budget and `pending_settlement`. All period outbox events, including
the three preserved earlier liabilities, matched authoritative Billing totals.

The initial optional run `37625486364` exposed a real source/config mismatch:
maintenance omitted the Billing bridge's issuer while the native fixture supplied
it manually. The existing five-minute scheduler retained events and applied normal
backoff; no event or timer was manually edited. The staging-only correction
`37628266417` replaced only maintenance and passed config-derived positive/negative
native regressions plus exact graph readbacks. See `staging-delivery.md`.

The final real run independently proved 20 retained charged-origin spans plus an
exact linked scheduled root, as well as the ordinary 14-span human/CLI witness.
It then repeated actual two-SMTP/archive/search/read/delete and self-send receipt
recovery/same-key replay/delivery-feedback/inbound acceptance successfully.
The code was not redeemed again (`grant_source=existing`), and no production
deployment, Identity-sector change or monetary collection occurred.


## Final fixed USD acceptance

The complete ordinary browser/native/mail/self-send journey passed in
[37646418030](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37646418030)
at exact candidate `aae6029`, successful producer `37645057615`, CLI/Skill bundle
`11493832761`, and safe authorization artifact `11495350924`. This run deliberately
omitted the real-meter flag and reused the existing Lite grant, not an activation
code. Actual USD liability/asynchronous evidence remains separate artifact
`11494520444` from `37644087065`; the latter's overall failure is not relabeled.
Final readback
[37646496526](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37646496526)
confirmed zero current cap/registered addresses, USD 2 micros in 2 events and
unchanged CNY 22 micros in 6 events, all delivered. Both remain pending settlement.
Runtime versions above are unchanged. See `usd-cutover.md` for the consolidated
source, artifact, actual-mail, trace and cleanup evidence. No production/Identity
or monetary-payment action was introduced.
