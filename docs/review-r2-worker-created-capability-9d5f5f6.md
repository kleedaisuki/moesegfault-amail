# Worker-created R2 capability alternative — independent design review

Reviewed 2026-10-01. Scope: docs-only commit `9d5f5f6`, the existing private
Email Worker, exact-rule helper, R2 inventory/transport helpers, historical
route-propagation record, and current official Cloudflare API documentation.
No production edits, local tests, live requests, workflow dispatch, or push were
performed. Historical run outcomes are documented inputs, not independently
re-attested by this review.

## Decision

**GO to implement a separately gated one-shot harness and recovery path.
NO-GO for live dispatch or B registration until that implementation receives
independent source review and hosted tests.** No substantive defect was found
in the docs-only change's claim boundaries. The proposed sequence is a useful
discriminating investigation, not an unchanged retry of the failed REST PUT.

The decisive result must be a successful GET of an existing, validated synthetic
object using the same repository token B will use, followed by that token's
exact-key DELETE and GET/LIST absence. Worker binding PUT success does not prove
REST write permission; conversely, the REST PUT 5xx does not establish GET or
DELETE denial. An absent-key recovery establishes neither existing-object
operation. A green probe remains time-bounded evidence, followed by B's fresh
read-only preflight and separate approval.

## Required implementation contracts

### 1. Keep the route and account state machine small

- Use only the existing A verification alias and existing private Worker/bucket.
  Do not open B, start Identity verification, register/change A or B, modify user
  Mail data, deploy a new probe Worker, or lift outbound product holds.
- Require the reviewed source/hosted CI revision, current private settings,
  explicit staging bindings, both exact routes absent, complete empty inventory,
  A verified/B absent, and sender/send-token prerequisites before route mutation.
  Serialize with both verification and relevant deployment jobs; a concurrency
  group is not protection from dashboard/external mutation.
- Install the route-cleanup `finally` **before** calling route creation. A POST
  timeout or malformed creation reply can still leave an active rule. Cleanup
  must attempt exact owned-rule reconciliation even when creation never returned
  a success flag. No broad alias deletion or rule enumeration output.
- Wait the observed 60-second propagation margin, re-audit the exact route, then
  make at most one send request. The historical 60 seconds is an empirical guard,
  not a provider delivery SLA. Use a finite route-open deadline, poll bound,
  request timeout, and explicit no-redirect/no-automatic-send-retry transport.
- Close/read back the exact route as soon as a candidate or terminal error is
  observed, **before** MIME parsing or object deletion. If closure is unverified,
  suppress capability success and further mutation; preserve the need for
  restricted recovery. A still-open route is the more urgent failure.

### 2. Treat a marker as correlation, not provenance

A marker derived from public Actions run ID/attempt is reconstructable, not an
unforgeable nonce. Visible From/To/Date are also spoofable. This does not defeat
the narrow authorization experiment: reading and deleting a validated existing
synthetic object demonstrates the token's operations, irrespective of whether
Cloudflare delivery is independently authenticated. It **does** forbid claims
of authenticated sender, external SMTP acceptance, Identity-code integrity, or
the absence of malicious interference.

Require the full versioned synthetic text template, exact run marker, a single
expected recipient, expected synthetic sender/subject, bounded MIME and one
decoded non-attachment text part. Reject duplicate singleton headers, parser
defects, unexpected attachments/parts, excess text, OTP-like messages, and marker
substring matches. Use standards-aware transfer decoding rather than byte equality
against pre-send MIME: routing legitimately adds headers/encoding. Never reuse
`verification_code()` for this probe. A deliberately text-only send keeps this
contract simple. Enforce a plausible **original send/run window**, not merely
recovery's current clock; MIME Date is supplementary correlation, not authority.

Select only one object from complete bounded inventory after the empty baseline.
An unreadable object, foreign body, multiple candidates, or inventory overflow
fails closed. No arbitrary key is deleted to restore emptiness. Before deleting,
retain the exact validated key and body identity in memory; ambiguous DELETE
requires GET reconciliation before a conditional repeat. Definite denial is not
an invitation to retry. An absent-key DELETE is not a passing capability test.

### 3. Make recovery possible without the UUID or runner memory

The Worker chooses the UUID, so a killed runner cannot reconstruct the exact key
from run metadata. Empty baseline plus strictly bounded private inventory is an
acceptable recovery discovery model for this one-shot experiment. Recovery must:

1. Independently validate the prior Actions run ID/attempt, reviewed source,
   correct probe target, and original time window; reject a fresh send, rerun,
   wrong workflow, or guessed originating run.
2. First close only the exact owned A route and read back absence. This cleanup
   must **not** depend on A/B contact-state checks, sender permission, empty
   inventory, successful GET, or the failed probe's ordinary preflight: those
   conditions may be precisely what failed or changed after interruption.
3. Privately discover a single candidate, GET and validate the entire synthetic
   identity, then DELETE only that candidate. Multiple/foreign/unreadable objects
   require restricted operator reconciliation; no catch-all cleanup. No raw key,
   inventory, MIME, provider reply, or token belongs in Actions output/artifacts.
4. Read back exact absence plus complete inventory, and perform the bounded
   post-close settle observation for late delivery. A runner death during DELETE
   is reconciled by readback, not guessed completion.

The same template/run identity must remain reconstructable for recovery without
publishing recipient or storing an OTP. A random secret marker would need a
durable protected recovery mechanism and is unnecessary for the narrow permission
claim. Do not introduce that machinery merely to imply authenticated SMTP.

No finite settle interval proves that an already queued send can never arrive
later. A successful result therefore describes the final observation time; every
subsequent B preflight still requires reconciled route/object state. Lifecycle is
only a backstop, not immediate cleanup. A timeout must never trigger a second send.

### 4. Prove failure behavior in hosted tests

Include exact call-order cases for route-create timeout, failed readback/settle,
send 5xx/timeout without retry, zero/multiple/late objects, GET denial, foreign MIME,
duplicate headers, unexpected MIME parts, DELETE denial/ambiguity, route-delete
failure, recovery with missing runner state/wrong originating run, and final
inventory ambiguity. Assert route cleanup precedes object mutation and fixed
failure labels do not interpolate captured addresses, bodies, UUIDs, or replies.
Ensure the manual workflow has its own confirmation, branch/environment guard,
attempt-1 rule, shared non-canceling mutation concurrency, and secrets only in the
final guarded step. Recovery cannot depend on ordinary preflight success.

## Simpler alternatives and why this is proportionate

An independently created, disposable non-OTP object would remove routing/sending
exposure and is preferable **if one is already available with known ownership**.
The currently empty bucket supplies no such object. Grant inspection alone,
nonexistent-key GET/DELETE, another API's credentials, or a Worker-only delete do
not exercise the same REST token operations B requires. A new public/private
probe endpoint adds deployment and authentication contracts; changing the
verification Worker to derive keys adds a production change under test. Neither
is simpler than reusing this bounded existing path for one investigation.

The residual costs are a short publicly reachable exact alias, possible hostile
or duplicate delivery, and manual reconciliation after a crash. These are real
but bounded by empty baseline, single send, fast route closure, strict identity
validation, and fail-closed recovery. They are not reasons to broaden the design
into a standing verification mailbox or generalized mail harness.

## Official API evidence

- [Email Sending REST](https://developers.cloudflare.com/email-service/api/send-emails/rest-api/)
  documents the account-scoped JSON send endpoint, send-token permission, and
  recipient-grouped delivered/queued/bounce results. Provider reply alone is not
  proof that this Worker persisted an object; inspect the object independently.
- [R2 GET Object](https://developers.cloudflare.com/api/resources/r2/subresources/buckets/subresources/objects/methods/get/)
  and [R2 DELETE Object](https://developers.cloudflare.com/api/resources/r2/subresources/buckets/subresources/objects/methods/delete/)
  are the exact operations whose live existing-object behavior needs exercise.
- [R2 consistency](https://developers.cloudflare.com/r2/reference/consistency/)
  describes immediate observation of writes/deletes. The late-delivery settle is
  for asynchronous mail creating a **new** object, not to mask stale R2 reads.
  No CDN/custom-domain caching is involved in private authenticated REST readback.

This review does not establish current token grants, live binding/observability,
sender onboarding, successful cleanup, or readiness to provision B.
