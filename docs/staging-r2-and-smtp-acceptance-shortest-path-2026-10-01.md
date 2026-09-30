# Shortest safe staging R2 and SMTP acceptance path

Date: 2026-10-01. Scope: architecture/source inspection and public primary
documentation only. No provider request/mutation, hosted dispatch, secret
inspection, local test/build, registration, deployment or mail send was made.
Historical run outcomes below are reused repository evidence, not newly
re-attested live observations. This document grants no new live authorization.

## Decision

**Do not conflate two buckets, two claims, or two kinds of evidence.**

1. The normal staging Mail SMTP-to-owner-ZIP journey already passed narrowly.
   Keep that evidence; do not repeat it to diagnose the private Identity inbox.
2. The private Identity verification bucket still has no attested same-token
   GET/DELETE of an existing attributable synthetic object. Its list-only
   preflight and absent-object recovery do not close that gate.
3. There is no currently authorized immediate live R2 acceptance path. The
   Worker-created probe's one-send grant was consumed. Repeating GraphQL,
   changing raw REST PUT encoding, or sending again unchanged would not be a
   safe substitute. No new HTTP probe endpoint or production Worker change is
   necessary to prepare a better future investigation.

The single concrete R2 blocker is **lack of an attributable existing synthetic
object against which the actual B token has exercised GET and DELETE**. Empty
inventory is a good recovery state but cannot supply this missing experiment.
There is no provider-read-only test that can prove deletion of an existing
object when none is available; token policy labels are not execution evidence.

## Evidence ledger and claim boundaries

| Repository evidence | Supported narrow claim | Unsupported inference |
| --- | --- | --- |
| `docs/validation.md`, run [36682429638](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36682429638/attempts/1), source `3dbc961`, preceding serving pin [36681988920](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36681988920) | Native authorization, two provider SMTP submissions, owner-scoped ZIP/content/assets, bounded semantic/search/read/delete and exact route cleanup passed for one staging corpus | Independent external-provider sending, production readiness, current serving/privacy state, B isolation, or direct REST access to the separate verification bucket |
| `docs/staging-second-principal.md`, preflight [36769969573](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36769969573), attempt 1, source `7ea4e5b` | At that observation: private inbox readback, verified A/absent B, absent exact routes, complete verification-prefix inventory | GET/DELETE of an existing object, Worker delivery, future permission validity, standing send/provision permission |
| REST capability probe [36740526559](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36740526559) and recovery [36740708407](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36740708407) | One PUT received fixed `r2_put_http_other_5xx`; exact derived sentinel was absent at recovery readback | PUT cause, never-persisted history, or existing-object GET/DELETE success |
| Worker-created probe [36751791789](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36751791789), attempt 1, source `15b50a5`, and recovery [36752557576](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36752557576) | No candidate in bounded initial poll; final recovery inventory empty and owned route absent | Accepted submission, no historical/late object, intended Worker execution, or direct token GET/DELETE acceptance |

The last recovery marker intentionally does not reveal whether its internal
`reconcile()` found/deleted a late candidate or found none. Do not retrospectively
infer one branch from the aggregate marker or request private logs to guess it.

Permission proof and Worker behavior are separate:

```text
Same B repository token: GET existing owned bytes -> DELETE same key ->
GET 404 + complete LIST absence -> final settled absence
                         = narrow REST object-operation evidence

Verified submission -> intended route -> intended Email Worker -> R2 object
                         = end-to-end delivery evidence

Mail SMTP receipt -> owner-scoped Mail GET/ZIP -> fixture byte comparison
                         = normal Mail product evidence, a separate bucket/path
```

## Exact reusable source/workflow inventory

| Responsibility | Existing source and workflow | Use now / boundary |
| --- | --- | --- |
| Private object creation without REST PUT | `infra/tests/staging_worker_created_r2.py`; `.github/workflows/staging-worker-r2-capability.yml`, target `staging-worker-r2-get-delete`, confirmation `RUN_STAGING_WORKER_R2_GET_DELETE`, attestation `ATTEST_ONE_SYNTHETIC_APEX_SEND` | Dormant existing route-first one-send mechanism. Its previous grant is spent; do not dispatch unchanged. No B secrets supplied. |
| Exact route-first recovery | Same script/workflow, target `staging-worker-r2-recover`, confirmation `RECOVER_STAGING_WORKER_R2_GET_DELETE`, original run ID/attempt 1/reviewed full SHA | Recovery is not a license to resend. Current provenance reader accepts only a bounded recent originating failed/cancelled/timed-out run; do not weaken its 24-hour window for historical archaeology. |
| Private settings/route/contact/list preflight | `infra/tests/staging_second_principal.py`; existing `ci.yml` target `staging-second-principal-preflight`, confirmation `READ_STAGING_SECOND_PRINCIPAL_PREFLIGHT` | Existing successful read-only result is reusable within its recorded scope. Fresh same-window preflight is required only before separately approved mutation, not to repeatedly mask a different missing gate. |
| Production-grade private ingress | `workers/identity-test-inbox/src/lib.rs`, `check_config.py`, `ensure_route.py` | Existing email-only bounded raw-MIME writer, configured recipients, UUID object keys. Do not add public fetch/self-test surface, public bucket domain, OTP traffic, or a second alias to manufacture evidence. |
| Normal Mail product acceptance | `infra/tests/staging_hosted_e2e.py` -> `infra/tests/staging_mail_e2e.py`; `ci.yml` target `staging-e2e`, confirmation `RUN_STAGING_E2E` | Already passed narrowly. Keep optional semantic/exact-cosine/isolation switches off unless their own new oracle is the purpose of an explicitly approved run. |
| Independent SMTP receipt oracle | `staging_mail_e2e.py::smtp_send_receipts` and `provider_receipt`; source review `review-current-run-smtp-receipt-08a0fc7.md` | Existing strong normal-Mail oracle. Preserve legacy `smtp_send` contract used by role/isolation probes. Do not silently change all callers. |
| Current Mail serving/privacy discriminator | `ci.yml` targets `staging-serving-pin` / `staging-worker-resource-readback`; related documents | These are independent gates, not GET/DELETE capability tests. Issues omission remains unresolved under the existing policy; no missing-as-false shortcut or fresh private-Mail exception is justified. |

## Smallest useful source changes before a future R2 investigation

These are proposals, not implemented production changes. Keep the existing
Worker and topology unchanged. Edit only the private acceptance harness, its
synthetic tests, and any exact workflow guard text required by its contract.

### A. Preserve submission evidence instead of returning one Boolean

`staging_worker_created_r2.py::send_once()` currently collapses HTTP rejection,
invalid envelope, transport uncertainty and missing accepted-recipient evidence
to `False`. `probe()` reports `synthetic_delivery_missing` before testing that
Boolean. Replace the Boolean with a small source-owned enum/record:

* `accepted`: validated provider acceptance for the exact synthetic recipient;
* `rejected`: positively recognized definite rejection under the documented
  response contract, not merely an unfamiliar error status;
* `unverified`: transport uncertainty, unsupported envelope or unknown outcome.

Retain the finite original send count (one) and fixed labels. Report a fixed
pair such as submission category plus candidate presence; never serialize HTTP
body, address, subject, marker or arbitrary provider prose. **An unverified or
rejected submission must still follow route-first closure and bounded late-object
reconciliation.** It must not skip cleanup because an object could arrive later.
No automatic retry, second send, fallback transport or window widening.

This fixes the demonstrable observability loss, not the historical delivery
cause. Tests must cover accepted/no-object, rejected/no-object, ambiguous/late
object, cleanup failure, and exactly one send under every branch.

### B. Distinguish cleanup-only recovery from an observed existing-object proof

`reconcile()` already returns whether a matching existing object was found and
removed, but `recover()` discards it. After successful final route/inventory
readback, keep the established `staging_worker_created_r2_recovered_absent`
marker for compatibility and optionally add **one fixed separate evidence line**:
`existing_object_get_delete=verified|not_observed`.

The verified branch requires the actual same token's bounded GET of matching
MIME, exact-key DELETE, GET/LIST absence and final settled route/inventory
gate. If any stage is ambiguous, denied, mismatching or unclean, emit no success
evidence. A merely absent key always yields `not_observed`. Do not rerun the old
recovery to obtain this line: a new label cannot reconstruct a past branch.
Tests must enforce no verification on absent initial inventory, no repeated
DELETE after definite denial, and no partial-pass marker after late delivery
or route/inventory failure. Adapt fixed-label consumers deliberately.

This costs no additional provider operation for a future genuine recovery and
keeps safe recovery useful without silently turning every cleanup into a pass.

## Next discriminating test and shortest future live sequence

**No live step below is presently authorized.** The next decisive R2 test, if
the owner chooses to authorize it after interpreting available offline historical
diagnostics, is one instrumented Worker-created non-OTP message using the
existing harness, not another GraphQL POST and not raw REST PUT.

1. Review A/B changes above, run their synthetic suite in hosted source CI at
   the exact intended SHA, and retain only run/SHA/fixed test status. No local
   test/build is required. Recheck dedicated workflow registration/branch and
   confirmation contracts; do not merge its inputs back into an oversized
   `ci.yml` dispatch schema.
2. Obtain **new explicit one-send authorization**. Freeze inbox deployments,
   routing/settings and overlapping staging mutations. The shared
   `staging-native-mail-acceptance` group serializes acceptance jobs but does
   not globally lock external operators or separate deploy jobs.
3. Immediately before that approved run, require the existing deployed-private
   inbox settings/binding/lifecycle checks, absent owned A/B routes, A verified
   and B absent, empty complete inventory, enabled exact sender and actual
   send grant. Preserve current strict privacy gates. Never delete unknown
   baseline objects to achieve the empty-inventory simplification.
4. Use the existing A-only exact route, original finite propagation and poll
   budget, one tiny synthetic send and new submission enum. Close/read back
   the exact route **before** object mutation. A single validated existing
   candidate then supplies same-token GET/DELETE and final GET/LIST absence.
5. On any uncertainty/cancellation: no new send and no B. Perform the existing
   route-first exact originating-run recovery within its accepted provenance
   window, or privileged reconciliation when that window/ownership is unavailable.
   A new recovery evidence line can establish existing-object operations only
   if they actually occurred; empty recovery remains cleanup-only.
6. Only after genuine capability success, use B's fresh read-only contact/route/
   inventory preflight and separate one-shot provisioning approval. Keep product
   outbound, role-monitor/public sending, production promotion and retained-log
   privacy gates held. R2 success must not unhold them.

The diagnostic split is useful even if delivery again fails: accepted plus no
candidate localizes the uncertainty downstream of submission, whereas rejected
or unverified submission cannot be called a Worker/R2 failure. It does **not**
claim intended Worker identity from a route control-plane read or sampled
analytics event. Further unchanged sends remain forbidden after that one run.

## Why SMTP is not a magic bypass

The current official [Cloudflare SMTP reference](https://developers.cloudflare.com/email-service/api/send-emails/smtp/)
states that SMTP, REST and the Workers send binding share the delivery pipeline.
SMTP DATA acceptance normally supplies a Message-ID, but an accepted reply may
omit it when every recipient is dropped. Thus moving the private probe from REST
to SMTP only changes submission observability; it is not an independently proved
fix for Routing/Worker/R2 delivery. Do not switch transport or start an external
sender campaign merely to evade the failed historical discriminator.

The [R2 GET](https://developers.cloudflare.com/api/resources/r2/subresources/buckets/subresources/objects/methods/get/)
and [DELETE](https://developers.cloudflare.com/api/resources/r2/subresources/buckets/subresources/objects/methods/delete/)
references document separate object operations. Keep the experiment focused on
their actual effect on an owned existing object rather than inferred permission
from absent keys, a Worker binding write, or unrelated Mail ZIP retrieval.

## Result of this investigation

No acceptance, permission, serving-state or privacy gate was changed. The
actionable progress is: retain the passed normal Mail journey, identify the
single missing direct-R2 oracle, and prepare two tiny harness changes that
prevent another one-shot experiment from losing its decisive branch evidence.
There is no reason to add a production endpoint, relax compatibility/privacy,
repeat GraphQL, or perform another speculative PUT to make progress.
