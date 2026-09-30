# Worker-created R2 delivery history interpretation review

Reviewed 2026-10-01: docs-only commits `42fdd05` and correction `12e8644`, the executable probe,
reconciliation and recovery paths in `infra/tests/staging_worker_created_r2.py`,
and prior source/wiring reviews selected by filename. This review did not run
local tests, query private provider data, dispatch workflows, push, or alter
production implementation. The two run outcomes below are supplied recorded
evidence, not independently re-fetched private run logs.

## Decision

**GO for designing a historical read-only discriminator; NO-GO for its live
dispatch until the actual query/parser/output/workflow source is independently
reviewed and hosted checks pass. No retry send or B provisioning is justified.**
The failed probe interpretation correctly refuses to infer send acceptance,
Routing success, Worker persistence or existing-object REST capability.

The documentation correction below was verified resolved in `12e8644`.
No outstanding substantive defect was found in the revised historical-only
design direction; the implementation conditions below remain applicable.
No production-code defect is asserted here.

## Resolved P2: recovery success does not imply initially empty recovery inventory

Location: `docs/staging-second-principal.md:96`; executable evidence:
`infra/tests/staging_worker_created_r2.py:402-424,509-519`.

The wording that the inventory "showed no candidate at recovery's checks"
is too strong. `recover()` ignores the Boolean returned by `reconcile()`.
If a candidate is present, `reconcile()` can validate its synthetic MIME,
GET/read it, DELETE it, wait and confirm absence; `recover()` then prints the
same `staging_worker_created_r2_recovered_absent` label as an initially empty
inventory. The fixed label alone cannot distinguish these two paths.

Correction: say that the exact owned route was closed/read back absent and
the inventory was empty at the final bounded checks, **possibly after removal
of a validated owned candidate**. Unless separate reviewed evidence establishes
the empty branch, do not claim no candidate was seen during recovery. Even
successful final absence is not perpetual absence, an atomic snapshot, or a
standalone existing-object GET/DELETE capability attestation.

Confidence: high, direct control-flow evidence. Impact: avoids incorrectly
excluding delayed delivery or overinterpreting the recovery outcome when
choosing the next diagnostic.

**Resolution verified at `12e8644`:** the runbook now explicitly states final
bounded empty inventory, allows a uniquely matching late candidate to have
been deleted by reconciliation, and rejects both no-delivery and attested
existing-object capability inferences. Its following paragraph also limits
the recovery readback to residual-state risk. This satisfies the correction;
do not reopen it without new evidence.

## Probe timing: interpretation is correct

`send_once()` at lines 256-275 performs one submission and returns true only
for HTTP 200, `success=true`, an intended recipient in delivered/queued, and
no reported permanent bounce or suppression. Otherwise its handled response
or transport failures return false without a distinct output category.

`probe()` at lines 464-479 records that Boolean, performs bounded inventory
polling, closes the route, and raises `synthetic_delivery_missing` if no
candidate was observed **before checking `accepted`**. Thus the recorded
failure from run `36751791789` cannot identify whether submission was rejected,
ambiguous, queued or accepted. The later reconciliation can also remove a
late candidate without replacing the original failure label. It is not
sound to infer that the Worker never received or ever failed to write mail.
Run `36752557576` narrows residual-state risk at its checks, not delivery cause.

## Historical discriminator: conditions for the next source review

The proposed datasets and narrow window are appropriate. Official
[Email metrics](https://developers.cloudflare.com/email-service/observability/metrics-analytics/)
documents zone-level Sending/Routing individual events, their identity fields,
Analytics Read, and a 31-day retention window. This supports querying the
recent experiment, not indefinitely postponing retrieval.

The implementation must preserve these boundaries:

1. Derive marker and exact subject from the immutable run/attempt in memory;
   bind time bounds to the reviewed originating step. Match the exact expected
   sender/recipient/subject, not a prefix or domain-wide approximation. If a
   provider display-address representation cannot be strictly validated,
   classify inconclusive rather than loosening the comparison.
2. Query only necessary fields. Do not request `errorDetail`, MIME or extra
   account-wide fields just to drop them afterward. Neither GraphQL errors,
   HTTP bodies nor exception formatting may print provider data. Store no raw
   event artifacts. Emit fixed categories and bounded cardinality only.
3. Schema availability is not enum semantics. The cited
   [Routing tutorial](https://developers.cloudflare.com/analytics/graphql-api/tutorials/querying-email-routing/)
   shows `status` and `action` fields but does not establish a `handled` enum
   or certify a particular Worker target. Use separately evidenced exact
   status/action allowlists; unknown values are inconclusive. A matched-rule
   UUID alone is not proof of the intended Worker. Without independently
   bound expected-rule identity, prefer a generic observed Routing outcome
   and do not label the intended Worker invoked or handled.
4. Both datasets expose `messageId`; the docs reviewed do not promise a
   universal cross-dataset join for all paths. A populated exact matching ID,
   plus all expected message fields/time, can support a positive correlated
   observation. Missing or unequal IDs must not be silently replaced by
   fuzzy subject/time linkage. Correlation still does not prove R2 persistence.
5. Require unique unambiguous matching evidence, and reject contradictory
   lifecycle rows. Multiple rows can reflect one message's lifecycle, not
   necessarily multiple sends. Reporting `multiple/inconclusive` is safe;
   do not conclude duplicate submission from raw row cardinality.
6. Reject truncated responses/full limits or unresolved timestamp boundaries.
   [Pagination](https://developers.cloudflare.com/analytics/graphql-api/features/pagination/)
   describes filter/order/limit pagination, not a lossless unbounded cursor.
   Do not call a short finite page universally complete without the exact
   selected query/shape contract.
7. [Adaptive sampling](https://developers.cloudflare.com/analytics/graphql-api/sampling/)
   prevents treating missing rows as proof of no send or route. A positive
   allowlisted failure may localize one observed stage; sampled absence,
   unavailable grants/schema, ambiguous matches or errors remain inconclusive.

No substantive issue was found in keeping B NO-GO, rejecting automatic resend,
or using historical positive evidence before considering a new experiment.
This assessment does not verify the actual provider outcomes, grants, current
fixture state, a specific enum mapping, or any not-yet-written discriminator.
