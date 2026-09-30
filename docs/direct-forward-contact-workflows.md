# Direct-forward contact operational workflows

Date: 2026-10-01. **Source wiring only, not operational adoption or activation.**
The owner's continuing Inbox/Junk review and Cloudflare-notice response within
24 hours remain pending. Actual contact adoption, affirmative attestation and
public unhold remain **NO-GO**. No private destination, receipt, provider reply
or mailbox content belongs in this document or Actions inputs/artifacts.

This document extends the held-only contract implemented in `a93fe58` and
`212cfe0`, not the earlier rejected two-mode architecture. See
[implementation](direct-forward-role-release-gate-implementation.md) and
[independent contact-gate review](review-direct-forward-contact-gate-a93fe58.md).

## Deliberately separate capabilities

| Workflow | Entry and capability | What it cannot establish |
| --- | --- | --- |
| `direct-contact-adopt.yml` | Explicit `main` manual dispatch; protected staging/production Environment; exact current contract (`NONE` for absence), provider destination ID and four rule IDs. New UUID, held state, stale-input rejection. | No human commitment, provider configuration proof, deployment, route mutation or public allow. |
| `direct-contact-attest.yml` | Explicit `main` manual dispatch; same protected Environment. Verification requires exact adopted UUID and `ACCEPT_INBOX_JUNK_AND_24H_CLOUDFLARE_RESPONSE`; default is unconditional revoke. | The phrase records a human assertion, not proof of mailbox visits. No machine lease, route repair or public allow. |
| `direct-contact-health.yml` | Every hour at UTC minute 17 for production; optional manual staging/production observation on `main`. GET-only bounded routing/destination reads and scoped D1 health update. | No human acceptance, mailbox access, verification request, routing write, SMTP probe, deployment or automatic unhold. |

All three use existing **repository-level Secrets**. Manual jobs retain the
existing Environment protection boundary, but this source does not prove that
required reviewers or deployment branch restrictions are configured. Do not
create/move/duplicate Secrets into Environments; an existing same-named
Environment override must be resolved before operational execution. The hourly
checker deliberately has no approval-dependent Environment: it must not queue
for a human review each hour. Its authorization is the trusted default-branch
code and existing repository Secrets, not a new approval or new credential.

Hourly health takes only `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`,
`CF_EMAIL_ROUTING_TOKEN` and `ROLE_FORWARD_DESTINATION`. The destination stays
in memory through the reviewed helper. Manual adoption takes only record/rule
identifiers, not an email address. Helpers emit fixed status labels, never pins,
UUIDs, destination addresses or provider bodies. There is no artifact upload or
step-summary export. Review opaque case references before dispatch; GitHub
inputs are not an appropriate place for confidential text.

## Quiet before adoption, strict after adoption

The scheduled helper receives `INPUT_SKIP_UNADOPTED_HELD=true`. It succeeds with
`direct_contact_health=unadopted_held` only after positively distinguishing a
supported pre-0009 schema or empty valid v1 policy and proving **exactly one
global send-policy row, held**. It does not treat SQL errors, provider outages,
malformed/partial schemas, missing global state or allowed state as absence.
The no-adoption path performs no routing GET and no D1 mutation. This is a
safe idle result, not health, adoption or release evidence.

With an adopted policy the existing strict checker observes both bounded
provider inventories twice, compares exact pinned identities/shape and writes
only the unchanged contract. Healthy expiry is six hours from database
observation start. All routing failures become unverified and hold when D1 is
reachable. Missing/delayed/dropped/disabled/canceled runs cannot renew. D1
outage cannot guarantee immediate revocation: old permission ends at its
original expiry. A later successful refresh **never** unholds global sending.

Minute 17 avoids GitHub's documented top-of-hour load peak; it does not make a
schedule reliable. GitHub schedules run on the default branch, may be delayed
or dropped, and public-repository schedules can disable after 60 days without
repository activity. The release operator must own missed-run/expiry response;
Actions completion and provider configuration are not evidence of human
attention or Inbox delivery.
[GitHub scheduled events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Provider mutation containment and shared exclusion

All six contact-related workflows share `amail-direct-contact-{realm}`:
adoption, coverage attest/revoke, health refresh, old send control, old release
attestation, and reserved role forwarding (fixed production). They use
workflow-level `cancel-in-progress: false`; non-contact gates/account-control
also share this lock conservatively. Staging and production remain separate.
No lock includes a workflow name that would accidentally split writers.

Reserved role forwarding now requires an opaque `case_ref` before either
`apply` **or** `request-verification`. The reviewed D1 invalidation helper runs
before any provider mutation; it clears adopted contact health and human
acceptance, establishes global held and demands scoped
readback before continuing. Failure/ambiguous invalidation denies before the
provider step. `audit` remains GET-only and skips invalidation.

This intentionally changes the unsafe pre-0009 mutation path: `apply` and
`request-verification` require the supported direct-contact migration and D1
credentials; unavailable schema/credentials deny rather than mutate under an
old fresh lease. Historical routes and code are not deleted. Policy identity
pins remain: a changed destination/rule identity or operational commitment
requires explicit new adoption and a fresh UUID; an equivalent no-change
operation can retain that contract. Both cases require new machine health
and explicit human acceptance, never automatically restored. Failed/canceled
mutations remain held/invalidated.
Never blindly retry ambiguous provider side effects.

The old `attest-send-gate.yml` interface remains unchanged: contact verification
without the new exact contract/coverage fields fails closed in the helper;
other gates and unconditional revocation retain their original interface.
The old send-control interface remains the only explicit unhold path, now
serialized with contact mutations and protected by the direct SQL predicate.
No new CI inputs or routine full-CI deployments were introduced.

GitHub's default concurrency queue retains at most one pending run; a later
run may replace a pending one even with `cancel-in-progress: false`. Running
mutations are not automatically canceled, but pending work must not be
reported as executed. Operators must verify the particular run/attempt and
outcome; this lock is not durable FIFO dispatch or an emergency-response SLA.
The group is repository-scoped: dashboard changes, other repositories and raw
D1 writes remain external, and manual cancellation is still possible.
Freeze external provider mutation during acceptance; invalidate/hold before
changing outside GitHub. The admission/pre-provider interval cannot recall an
already in-flight send.
[GitHub concurrency semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency).

## Default-branch registration and held rollout sequence

1. Complete independent source review and the exact integrated SHA's full
   non-mutating hosted CI plus independent workflow syntax guard. Static source
   tests are not D1/runtime acceptance; do not dispatch operational workflows
   to test syntax.
2. Register the reviewed files on default `main` through the normal protected
   change process. GitHub requires a default-branch file for manual dispatch
   and schedules; a feature-branch file alone is not an operational entry.
   Selecting another branch cannot bypass the explicit `main` job/helper guard.
   [GitHub manual workflow registration](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).
3. Verify existing repository Secret names/source and actual Environment
   protections privately. Run the supported held migration/runtime acceptance;
   prove held before/after changes. The newly registered hourly lane should
   report only the positive unadopted-held idle result until adoption.
4. **Stop here while human coverage is pending.** Registration is not adoption.
   After explicit owner acceptance and independent operational review, select
   exact existing rule/destination record IDs privately and dispatch adoption
   with the current contract ID (`NONE` only if truly absent), opaque case and
   `ADOPT_DIRECT_CONTACT_HELD`. Read the new UUID through the authorized private
   D1 operator path; do not add it to public logs or request the mailbox again.
5. Obtain exact-contract machine health and evidence for the human obligations:
   Inbox and Junk review, notice-response ownership within 24 hours, attribution,
   intervention and separate official replies. Record the exact contract/phrase
   only after that evidence/commitment exists. Configuration success does not
   substitute for the four historical receipts or the missing human commitment.
6. Preserve held until every independent privacy/outbound/publication/topology
   gate passes. Public allow remains a distinct explicit operator action. A
   held-only old-binary rollback must not inherit permission to send.

## Acceptance evidence still required

Added `infra/tests/test_direct_contact_workflows.py` to existing hosted infra
discovery. Source contracts cover main-only protected manual entry, exact env
wiring, coverage/revoke separation, hourly production fallback, noncanceling
shared locks, no broad failure suppression, privacy exports and invalidation
before provider mutation. The operator suite separately covers actual SQL,
safe idle discrimination and conditional contract replacement/invalidation.

**No local tests/builds, hosted dispatch, live provider calls, policy adoption,
attestation, mailbox retrieval, routing changes, send, deployment or unhold was
performed for this wiring.** Static source inspection is not a claim of hosted
test success, scheduled execution or actual Environment protection.
