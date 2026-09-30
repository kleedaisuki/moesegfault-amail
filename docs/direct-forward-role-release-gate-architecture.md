# Conditional architecture: direct-forward operational contacts for v0.1.0

Date: 2026-10-01. Status: **conditional design and acceptance plan only**.
The owner has not yet confirmed continuing Inbox **and Junk** review and
coverage for Cloudflare notices requiring a response within 24 hours. This
document does not adopt the product proposal, implement a policy, authorize a
deployment, attest a gate, or permit public sending. No source/CI/provider state
or test was changed or executed for this architecture work.

The private destination is intentionally absent. Its selection and four
successful historical receipts need not be requested or replayed.

## Decision

If the owner adopts [the product contract](role-mail-release-scope-decision.md),
use four provider-managed direct forwards, one explicit operational-contact
mode, a short-lived machine configuration-health record, and a separately
audited human operational attestation. Keep the existing global/account holds,
recipient blocks, outbound feedback and one-use held-state canary contract.

For `direct_forward`, put configuration and freshness in **MAIL_DB**, so public
send admission can recheck them atomically with the existing send-request SQL
trigger. Do not write or reinterpret `ROLE_MONITOR.role_monitor_health`.
Remove the unused `ROLE_MONITOR` binding from the direct-mode Mail deployment;
do not introduce another Worker, frontend, mailbox OAuth integration, MIME
store, per-arrival queue or automatic complaint model.

Use a small, separate, main-branch-only GitHub Actions hourly health workflow,
not full CI or a deployment, to GET the provider configuration and update only
the adopted contract's health row. The existing project Secrets are sufficient
in principle. Scheduling is **not guaranteed**; missing execution expires
permission to send rather than granting eternal success. This is a deliberate
availability trade-off, not a reliable-notification promise.

```text
Operator: selected contract + explicit review/response commitment
                                  |
                                  v
                         MAIL_DB contact policy
                                  ^
                                  |
Hosted hourly check -- bounded GETs --> four exact rules + verified destination
       |                          |
       +-- scoped SQL result -----+--> MAIL_DB direct-configuration health
                                        |
Mail: four release attestations + global/account/recipient policy
                                        |
                 explicit mode -> exact contract -> fresh health
                                        |
                   atomic send-request admission -> existing send path
```

No arrow from provider delivery/configuration means that a person read a
report. No scheduler result may mark the human release gate verified.

## What current source enforces, and what must change together

Inspected source baseline: `2d0855605888391419de1fea09ceb23975a570c7`.

| Current surface | Actual contract | Required direct-mode reconciliation |
| --- | --- | --- |
| `crates/mail-worker/src/lib.rs::check_send_policy` | Four static release flags, global allow and independent `ROLE_MONITOR` lease; account holds and recipient blocks remain separate. | Dispatch on a closed two-variant contact mode. Require attestation-contract equality and direct configuration freshness instead of the role lease **only in direct mode**. Unknown/missing mode fails closed. |
| `role_monitor_healthy` | Reads only `lease_until` from isolated role D1; absence, failed read or equality at expiry denies. | Preserve the genuine Worker-owned lease for `worker_monitored`; never manufacture it from provider GETs. No fallback between modes. |
| `0006_outbound_abuse.sql::send_request_policy_guard` | At INSERT, rechecks global/static attestations and account hold, and consumes held-state canaries. It does **not** recheck role health. | Add a direct-contact admission guard using same-database policy/health. A Rust precheck alone leaves a check-to-admission race. Preserve existing guard and audit semantics; do not rewrite old migrations. |
| `infra/operator/attest_gate.py` | Can independently set `abuse_contact_verified`; records an opaque evidence case. | Bind that attestation to the currently selected contract. Its case must cover receipt/protocol/intervention evidence and the explicit operational commitment, not merely provider configuration. |
| `infra/operator/send_control.py` | Global allow SQL requires four flags; hold is unconditional. | Require the chosen contract and current mode-specific health before allow; direct-mode checks can be in the same SQL statement. Never let the periodic checker set global allow. |
| `infra/release/check_send_gate.py` | Production `/health` and four flags/global allow only. It does not prove role freshness or serving topology. | Publication requires the same contract/freshness and independently pinned production API/sink/strict topology evidence. `/health` is not an operational-contact oracle. |
| `pin_staging_mail.py::expected_bindings` and Mail `wrangler.toml` | Both realms assume a second D1 `ROLE_MONITOR`. | Derive exact bindings from an explicitly reviewed contact-mode deployment contract; direct-mode expected set excludes the role binding, not an optional arbitrary-extra binding. |
| `prepare_production_graph.py` / `check_production_role_graph.py` / production CI | Even initial `api-only` bootstrap assumes pristine role storage; later maintenance hard-requires the `api-role` graph. | Introduce a strict **direct-mode api-only bootstrap/maintenance** path which does not provision/read unused role storage or require role acceptance. Preserve the existing separate worker-mode phase transitions. |
| `role-forwarding.yml` / `ensure_role_forwarding.py` | Manual main-branch exact direct-forward reconciliation, bounded inventory and conflict rejection. | Reuse shape predicates, but use a GET-only, redirect-rejecting client for scheduled health. No automatic repair/reverification mail. Explicit mutations invalidate health before changing provider state. |

The current [GET discriminator](staging-role-token-permission-discriminator.md)
positively establishes readable Addresses and Rules, a verified confidential
destination and four direct-forward shapes. Its independent role-Worker pin
drift makes the aggregate inconclusive **for the old worker contract**, not a
reason to invent a fresh lease or replay those four receipts. That diagnostic's
historical coordinates and disposable-route checks must not be copied into a
production cron; extract its bounded client and contract predicates.

## Smallest coherent data/state model

Add one additive MAIL_DB migration; names below are proposed, not existing
tables. There is one active contact contract, not a general workflow framework.

### 1. Operator-owned `role_contact_policy`, singleton `id=1`

| Field | Meaning and constraint |
| --- | --- |
| `mode` | SQL `CHECK` and Rust enum: exactly `direct_forward` or `worker_monitored`. No default mode and no optional/auto choice. |
| `contract_id` | New opaque UUID on every mode, destination, route-identity or operational-commitment change. Never reuse an old contract ID. |
| `destination_id` | Provider destination-record identifier, not the mailbox address. Required for direct mode; validated privately against the Secret and provider record. |
| `rule_ids` | Exact four role-to-provider-rule-ID associations, encoded as a fixed four-key object and strictly validated. Public role names are fixed source constants. No rule body or mailbox value is persisted. |
| `actor`, `case_ref`, `updated_at` | Privileged operator and opaque decision/evidence reference; database time in Unix seconds. Never report content or confidential mailbox details. |

Direct configuration identity is pinned once at explicit adoption, then checked,
not adopted from each latest inventory. Destination Secret rotation to a
different mailbox therefore cannot silently move an accepted operational
contract. Recreating an equivalent provider rule is a deliberate contract
change, not an automatically accepted identity update. This is slightly stricter
than structural audit, and makes configuration/attestation races ordinary
contract-equality checks. Do not store a mailbox address or an unsalted mailbox
hash as the commitment; a low-entropy address hash invites guessing.

For the existing worker-mode deployment, the separate rollout/version/route
pins remain authoritative; no new worker-mode readiness is granted by this
table. Pin-field constraints must distinguish the two mode variants rather than
accept arbitrary partially populated JSON. The v0.1 direct implementation need
not construct a new worker rollout manager.

### 2. Checker-owned `role_contact_health`, singleton `id=1`

| Field | Meaning and constraint |
| --- | --- |
| `contract_id` | Exact active direct contract checked; it is never meaningful for a different contract. |
| `state` | `healthy` or `unverified`. Permission denial, drift, malformed/truncated response, timeout and every unclassified outcome are `unverified`, not success. Fixed failure code may distinguish these in private diagnostic metadata. |
| `checked_at` | Database timestamp obtained **before** the bounded provider reads. Do not timestamp stale observations at eventual commit time. |
| `expires_at` | For healthy: exactly `checked_at + 21600` seconds; otherwise zero. No externally supplied TTL or arbitrary future deadline. |
| `run_ref` | Opaque hosted run/attempt reference and reviewed checker contract version. No mailbox value, rule payload or provider error body. |

Only the active `direct_forward` contract can be updated. Conditional SQL
requires unchanged `contract_id` and an observation timestamp not older than
the current row; a delayed obsolete checker cannot renew a replaced contract.
An initial/missing row is unverified. Preserve a compact audit of policy changes
and health **state/contract transitions**, not 24 copies of identical successful
configuration each day. A small retention limit must be explicit in source.

### 3. Bind the existing human release attestation

Add nullable `abuse_contact_contract_id` to `send_release_gates`, default NULL;
include it in an additive audit extension. Public readiness requires existing
`abuse_contact_verified=1` **and** contract-ID equality. The migration must not
infer a contract from a historical boolean or copy an old role lease.

The operator-owned contact attestation records the acceptance of Inbox/Junk
coverage, timely response, safe attribution/intervention and official reply
handling. It remains a truthful statement of responsibility, **not** an
automatically renewing claim that the mailbox was visited. Lack of coverage
requires an operator hold/revocation. No mailbox-reading authority is assumed.

Updating/revoking the selected contract invalidates health and abuse attestation
and holds global sending in one database transaction/trigger path. None of
these operations erase independent feedback/delivery/preview evidence.

## Readiness predicate and failure behavior

At database time `t`:

```text
direct_health(t) =
    policy.mode == direct_forward
    && health.contract_id == policy.contract_id
    && health.state == healthy
    && 0 < health.checked_at <= t < health.expires_at
    && health.expires_at - health.checked_at == 21600

role_ready(t) =
    abuse_contact_verified == 1
    && abuse_contact_contract_id == policy.contract_id
    && match policy.mode {
         direct_forward  => direct_health(t),
         worker_monitored => actual_ROLE_MONITOR_lease_current(t),
       }

public_ready = global_allowed && four_release_flags && role_ready(t)
```

Equality is expired. Policy/database/binding/read errors and unexpected values
deny. Do not cache a success past its expiry or switch to another mode because
one dependency is unhealthy. Mail read/search/retrieve remain usable.

For direct mode, add a separate same-database BEFORE INSERT guard to public
send requests, using SQL database time and the identical contract/freshness
predicate. It should also reject an unknown/missing policy on the public branch.
Keep the existing static/admission/account guard; do not depend on trigger
execution order. **No guard may treat an expired role check as permission to
use a canary while global state is allowed.** Held-state canary consumption and
its account/recipient/idempotency restrictions retain their existing semantics;
explicitly assert global `held` on the canary admission alternative.

The Worker must still recheck policy at the existing pre-provider-call points,
including retries of existing send requests. Do not claim a SQL insertion guard
alone stops previously admitted requests. An in-flight provider call cannot be
recalled atomically with D1/Cloudflare routing changes; document that boundary,
reuse existing idempotency/ambiguous-delivery handling, and never retry blindly.

For worker mode, same-database contract/static checks plus the genuine isolated
lease check preserve the existing cross-database behavior; SQLite cannot join
the isolated role D1 in the Mail admission trigger. This plan does not claim to
solve the pre-existing cross-database lease race by copying a lease into MAIL_DB.
Mode changes are held, reviewed transitions, not live concurrent fallbacks.

| Failure | Required result |
| --- | --- |
| Provider read fails/drifts and health update succeeds | Write `unverified`, expiry zero, and atomically set global hold. Public requests fail immediately after that write. |
| Provider read succeeds, later D1 write fails/has ambiguous outcome | Do not announce renewal; privately read back only the scoped row once if needed. Old health can remain usable only until its original expiry. This is **not** immediate invalidation. |
| GitHub does not start a run / runner canceled / workflow disabled | No renewal; gate expires at last observation + six hours. This may hold otherwise healthy sending. |
| D1 unavailable on public send | Deny; do not fall back to the last process-memory health value. |
| Successful health recovery after a recorded failure | Fresh health only; global state stays held. Explicit operator re-enable requires all release/contact predicates. |
| Expiry without a checker write | Effective public readiness is held even if stored global state is still `allowed`; it must not wait for a cron to flip that bit. |
| Emergency/coverage failure/operator hold | Existing global/account hold is unconditional and cannot be undone by a health checker. |
| Route changed just after a valid check | Not detected until a later check or expiry. This is a periodic configuration observation, not continuous route integrity. |

Hourly checks/six-hour expiry are proposed operating defaults from the product
proposal, not a measured SLA. The maximum stale-permission window when updates
cannot be written is six hours from the last observation, not “immediately fail
closed.” Material route drift detected during a successful check is invalidated
at its scoped database write. If that window is unacceptable, reduce TTL/check
interval or adopt another scheduler **explicitly**; adding a Worker does not
prove that someone responds to reports.

## GitHub Actions cron: feasible without new Secrets, not guaranteed uptime

Use `schedule: '17 * * * *'` and a main-only manual `workflow_dispatch` refresh
with no arbitrary database/recipient/SQL/mode inputs. Check out trusted default
branch code; no PR event or untrusted artifact supplies executable checker code.
One Linux/Python job, ten-minute timeout, minimal `contents: read`, no Rust/Wasm
build, no full CI dependencies, no deployment and no mail send. Scheduled runs
use the repository's already selected project-level Secrets:

| Existing Secret | Actual use |
| --- | --- |
| `CF_EMAIL_ROUTING_TOKEN` | GET complete bounded Addresses/Rules inventory using the existing zone/account grants. |
| `ROLE_FORWARD_DESTINATION` | In-memory equality comparison to the unique verified provider destination and exact four forwards; never output/persist it. |
| `CLOUDFLARE_ACCOUNT_ID` | Fixed account coordinates, validated against deployment contract. |
| `CLOUDFLARE_API_TOKEN` | Existing privileged D1 query API to read policy/time and conditionally update only the scoped health/hold state. Existing operator/release code already uses this path. |

“Scoped update” means fixed SQL, target database constant, singleton and
contract-ID predicates, strict bounded values and verified affected-row count.
It is **not** a database-table authorization boundary: the existing Cloudflare
API credential is broader than this row. No new table-scoped token is invented.
Trusted workflow code and repository controls are part of the security model.
If current production D1 write access has not been positively demonstrated,
verify the actual existing token's capability through the approved held rollout;
do not assume source use or staging success proves production access. Missing
permission blocks the adoption; no automatic token creation or widening.

Provider algorithm:

1. Privately read the unique policy, matching release-contract coordinates and
   database time; require direct mode. Never publish this row or mailbox value.
2. With the existing GET-only redirect-rejecting client, read all bounded Rules
   and Addresses pages. Require well-typed stable pagination and one unique
   provider-verified destination whose ID **and** address match the active pin
   and Secret. Require four distinct pinned API-owned enabled literal rules,
   each with exactly one expected matcher/action/destination, with no duplicate
   or conflicting role match. Reuse existing `matched_roles`/`expected_rule`
   predicates; broad catch-all/mixed matcher rules must not be mistaken for the
   four exact rules.
3. Repeat the relevant inventories to bracket identities, destination state and
   role shapes across the check. Compare the four relevant snapshots privately;
   unrelated user-route churn need not invalidate identical role snapshots.
   Pagination instability or missing completeness fails closed. This bounds
   observed drift, not an atomic transaction across the provider and D1.
4. Commit healthy/unverified for that exact contract and start timestamp;
   failure invalidates and holds, success never allows. Require one affected
   scoped row and bounded readback. Avoid retrying an ambiguous write without
   first reading its exact state. Emit fixed result codes only.

All contact-check and contact-mode/routing mutation workflows use one
non-canceling workflow-level contact-writer concurrency group. Operator route
mutation first invalidates contact health while global sending is held.
External/dashboard writers cannot be locked by GitHub; require reviewed writer
coordination and rely on contract equality/bracketed readback to detect observed
changes. Use conditional SQL even with the lock. Never make an emergency global
hold wait behind a stuck health/deployment job; the existing stop path remains
independently available and cannot be overwritten by a checker.

GitHub documents delayed/dropped schedules at high load, default-branch-only
execution, and automatic disablement after 60 days of inactivity for public
repositories. Scheduling away from minute zero helps contention, not delivery
guarantees. A disabled or failed schedule must be visible to the operational
owner and restored before explicit public-send re-enable. Do not maintain fake
repository activity or auto-extend expired evidence to hide this failure mode.
[GitHub scheduling contract](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Use primary D1 reads for send-policy decisions; the current non-session API
uses primary queries. If read-replication Sessions are later introduced, start
the policy session at `first-primary`, not `first-unconstrained`. Same-database
SQL trigger/write checks remain the authoritative direct-mode admission barrier.
[D1 database API](https://developers.cloudflare.com/d1/worker-api/d1-database/).

## Deployment, upgrade and rollback

1. **Decision first:** obtain the one outstanding human Inbox/Junk/24-hour
   coverage commitment and adopt or reject direct mode. If unresolved, keep
   everything held and do not implement this as a unilateral policy relaxation.
2. Add migration/source/operator/checker/graph changes together; independent
   review and hosted tests. Migration creates no healthy record or accepted
   contract, and leaves abuse-contact binding NULL. Never edit migration 0006.
3. While global sending is held and old abuse gate is revoked, apply the additive
   migration. The old Worker sees its old lease contract and remains held. Do
   not update direct mode or re-enable until the new pinned Worker is serving.
4. Deploy the new direct-mode API with no ROLE_MONITOR binding and the unchanged
   strict api-only trace graph: exactly Mail producer and one private trace
   sink, reviewed Queue/DLQ IDs, all original-context capture switches off.
   API privacy acceptance remains mandatory. Deployment/readback helpers must
   accept precisely this variant, not arbitrary optional extra bindings.
5. Explicitly pin the chosen direct contract from verified provider IDs while
   held; scheduled checker proves fresh state. Verify deployed mode/bindings,
   zero role producer attachment, the intervention drill and human evidence;
   then record the contract-bound contact attestation. Reuse established
   permission/four-receipt facts, adding only missing protocol/intervention
   evidence. A newer GET alone does not prove Inbox attention.
6. Only after every independent production release gate is accepted may an
   operator allow sending or tag/publish. Release checker and manual global
   allow use the same contact predicate, not the old four-booleans shortcut.

Add a direct api-only maintenance path for later API/sink upgrades. Keep strict
`worker_monitored`/api-role rollout separately callable but non-default and
ineligible to authorize v0.1 direct release. Existing staging role resources
must be inventoried and left explicitly dormant or retired in a **separate
reviewed transition**; this plan does not authorize deletion or erase failed
history. Production's four forwards need no Worker cutover.

Rollback always starts with explicit global hold and contract/abuse revocation.
Do not drop additive data or return to an old binary while global is allowed:
an old binary/trigger has no knowledge of direct freshness. Rolling back the
new API to its old lease-bound version without ROLE_MONITOR fails closed, not
success; restore a legacy binding only as a separately pinned worker-mode
transition. Mode changes invalidate attestation and health before routing or
graph changes, require fresh mode-specific acceptance, and preserve CLI/API/ZIP,
`send_held`, idempotency, account holds and received data. Never infer worker
acceptance from direct configuration health or direct acceptance from a lease.

## Executable hosted/deployed acceptance matrix

No local tests are needed for this plan. Implemented tests run on Actions.

| Area | Discriminating evidence required |
| --- | --- |
| Data/enum contract | Missing/unknown mode, absent/multiple/ill-typed policy or health, wrong contract ID, invalid TTL, future timestamp, exact expiry boundary, NULL legacy contact binding all deny. |
| SQL admission race | Policy replacement/revocation/health failure between Rust precheck and new send INSERT denies. Expired direct health denies even with stored global `allowed`; a previously consumed canary cannot authorize that state. |
| Existing sends | Retried/admitted requests encounter the existing last-moment policy checks; completed idempotent results do not resubmit mail. Account/recipient/global holds and one-use held canary remain tested. |
| Checker completeness/privacy | Redirects, 401/403/5xx, timeout, malformed/oversized JSON, truncated/changed pagination, duplicated IDs, unverified/mismatched destination, disabled/repointed/multi-matcher role, stale contract or timestamp all fail. Seed confidential values and assert none appears in logs/artifacts/SQL values. |
| Scheduler/hold behavior | Delayed/canceled/skipped/disabled run cannot extend TTL; DB write/readback failure cannot claim renewal; good health cannot auto-clear a hold; manual stop remains usable while checker is locked. |
| Release/operator parity | Global allow and tag gate reject stale/wrong-contract health, missing commitment and invalid topology even when legacy four flags are true. Revocation atomically holds and produces only opaque audit references. |
| Migration/rollback | Old held source -> additive migration -> new held source has no unlocked interval. New -> old rollback is held. Empty/unknown legacy state never defaults to direct success. |
| Deployed direct contract | Privately read stable production API/sink pins, strict api-only Queue graph, no ROLE_MONITOR binding/active role producer, actual bounded provider/D1 checker success while send is held. Then force a scoped synthetic/staging expiry/failure and verify `send_held`, without editing live production routes. |
| Human/process and protocol | Explicit Inbox/Junk coverage; targeted case-insensitive/Postmaster protocol evidence where absent; controlled known-sender intervention/official-response drill. No reply from the private forwarding mailbox. No duplicate four-receipt replay for cosmetic aggregate success. |

The Mail trace/Issues privacy gate, independent external outbound oracle,
multi-principal isolation, quotas/reserved aliases, native feedback/suppression,
production DNS/deployment, site/release assets remain independent blockers.

## Alternatives and evidence limits

* **Chosen:** scheduled direct-configuration checker plus explicit human process.
  Fewest new runtime dependencies; safe expiry under scheduler failure; may
  cause availability holds. Appropriate only if the operational commitment is
  accepted and periodic configuration observation is an adequate control.
* **Rejected:** fake role lease, perpetual `abuse_contact_verified` bypass, or
  accepting any surviving mode. These destroy the meaning of existing gates.
* **Deferred:** Cloudflare scheduled checker Worker. It can reduce dependency
  on GitHub scheduling, but adds deployed privileged runtime, secrets, trace
  privacy and fault acceptance. Choose it only if measured scheduling
  availability is unacceptable; it still does not read Inbox/Junk or respond.
* **Deferred:** full role Email Worker/outbox/digest. Useful if unattended
  per-arrival alerts become an explicit requirement, not evidence of attention
  and not needed merely because its source exists.

The production-experience research on **differential observability** explains
why a healthy control-plane probe can coexist with a broken user outcome:
[Huang et al., *Gray Failure*, HotOS 2017](https://www.microsoft.com/en-us/research/publication/gray-failure-achilles-heel-cloud-scale-systems/).
Here that lesson motivates separate configuration, deployed intervention and
actual Inbox/Junk evidence. It does not prove Cloudflare behavior, validate the
six-hour default, or require a new operations platform. No academic mechanism
or sampled analytics substitutes for the missing accountable actor.

Provider inventory/verification field contracts:
[destination list](https://developers.cloudflare.com/api/resources/email_routing/subresources/addresses/methods/list/),
[rule list](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/list/).
Normative contacts, transactional scope and the exact human-coverage question
remain in [the conditional product decision](role-mail-release-scope-decision.md).
