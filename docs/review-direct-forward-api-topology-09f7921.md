# Independent review: direct-forward Mail API topology, 09f7921

Date: 2026-10-01. Scope: commit `09f7921041a9bff4fd4b62836f7215eca14f1fad`
and its binding/runtime/deployment integration obligations. This review grants
no deployment, contact adoption, human attestation, public-send authorization,
or private-mailbox access. No local tests/builds, provider calls, route mutations,
or sends were performed. Public Cloudflare documentation was read.

## Decision

**GO to execute hosted source-only checks on a coherent candidate.** This is
permission to obtain evidence, not a claim that the checks passed. **NO-GO to
accept 09f7921 alone as an integrated direct-only implementation.** Its existing
pin contract still indexes the removed database, and its committed runtime
still requires the old lease. Neither condition opens public sends; both must
be reconciled before integrated acceptance. Live deployment and public release
remain outside this decision and held.

## Prioritized findings

### F1 — High confidence: standalone config removal breaks the source pin contract

Location: `crates/mail-worker/wrangler.toml` removal of both `ROLE_MONITOR`
entries; existing `infra/deploy/pin_staging_mail.py::expected_bindings` at the
reviewed commit.

The committed `expected_bindings` always evaluates
`stage["d1_databases"][1]["database_id"]` for `ROLE_MONITOR`. Each realm now
contains exactly one database. Any call therefore raises `IndexError` before
resource matching. `infra/tests/test_pin_staging_mail.py::bindings` calls this
function to construct fixtures, and the hosted infrastructure job discovers
the entire `infra/tests` suite. This is a concrete source-check/integration
failure, established by inspection, not an executed test result. The added
TOML-only tests do not exercise this consumer.

Necessary correction: change the pin's exact expected binding set to Mail D1
only, reject extra/duplicate/renamed bindings, and update its callers/tests.
Do not turn the old binding into an optional accepted extra. Review production
bootstrap/maintenance predicates together with the pin.

Resolution status at review time: the shared worktree already contains a
candidate `mail_resources` validator and an `expected_bindings` set without
`ROLE_MONITOR`. Inspection shows that this removes the identified indexing
failure and preserves exact binding-set matching. These are **uncommitted
companion edits**, not part of 09f7921 and not verified by execution. Include
the reviewed companion change in the hosted candidate before marking F1 closed.

## Accepted scoped behavior

| Contract | Inspection result |
| --- | --- |
| Existing Mail resource identity | Both Mail D1 IDs/names and migration directories are unchanged; only API access to isolated role D1 is removed. No storage deletion or data migration occurs in this commit. |
| Realm isolation | Production and staging remain explicit, distinct Mail D1 bindings with unchanged realm-specific HTTP domains, R2 buckets, ingress names and Queue names. |
| User-mail capabilities | Email bindings, official production sender restriction, R2, search Cron, compatibility date and Worker names are unchanged. |
| Trace privacy | API producer and private sink parameters are unchanged; new tests require the exact API Queue and sink consumer shapes and disabled capture categories. |
| Four operational contacts | No role Email routing, destination, rule ID, destination address, reconciliation write, receipt replay or Wrangler-managed contact is added. HTTP custom-domain routes are unchanged and are not Email Routing rules. |
| Public-send hold | No SQL/operator allow, gate attestation or health write occurs in this commit. The old runtime's missing lease denies public readiness rather than relaxing it. |
| Dormant role resources | Removing a Mail binding does not retire the role Worker, revoke its independent credentials, remove its Queue producer, or delete isolated D1. Separate exact hosted graph evidence remains necessary. |

No further substantive defect was found in the TOML delta or held deployment
document within this review's scope.

## Runtime, SQL and deployment coupling

At 09f7921, `check_send_policy` still calls `role_monitor_healthy`, whose absent
`ROLE_MONITOR` lookup returns false. A deployment of that exact revision cannot
implement direct-forward public admission. This is explicitly acknowledged by
the new deployment document's requirement to deploy the new runtime and TOML
together after the additive Mail migration; it is not evidence of a public
unhold. One-use canaries retain their existing held-state policy.

Current uncommitted runtime edits replace that lookup with the Mail D1
`direct_role_contact_ready` view. This review does not certify the view's SQL
definition, admission-trigger race handling, attestation identity, operator
mutation discipline or release predicate; those require their independent
runtime/SQL/operator review and hosted boundary cases.

The held sequence is appropriate: retain old role data; install additive Mail
schema; deploy matching runtime/config; read back immutable serving bindings,
capture-off and exact API-only Queue topology; separately establish adoption,
freshness, operational coverage and release evidence. Rollback must remain
held and restore old code with matching old bindings. A direct configuration
observation must never manufacture a legacy role lease. In-flight provider
sends and ambiguous delivery cannot be undone by a binding change.

At review time, production workflows still contain `api-role` maintenance
targets, while uncommitted companion graph code is becoming direct-only.
Consequently workflow reconciliation remains an integration prerequisite, not
something the three-file config commit proves. Run source-only checks, not the
production/staging/role-rollout deployment targets, to obtain initial evidence.

## Static test adequacy and limits

The added tests meaningfully enforce one Mail D1 per realm, different database
IDs, unchanged HTTP domains, exact API/sink Queue shapes, no sink public routes
or cross-resource bindings, and explicit disabled API capture categories.
Full hosted test discovery includes this filename.

The new database test checks separation, not the production database's exact
historic identity: two distinct wrong IDs would pass it. Existing
`check_staging.py` independently pins the staging Mail D1 ID. Optional hardening
is an explicit reviewed production/staging identity assertion in the source
contract suite; this is a coverage observation, not an actual identity defect.

TOML tests cannot prove effective provider attachments, active role-Worker
dormancy, routing destination verification, human Inbox/Junk review, contact
freshness, SQL admission, or actual release safety. The document correctly
separates those claims. No speculative academic redesign is needed for this
small capability-removal review; the material question is executable contract
coherence and production readback, not a new automation mechanism.

## External grounding

Cloudflare's current [Wrangler configuration documentation](https://developers.cloudflare.com/workers/wrangler/configuration/)
distinguishes inheritable and non-inheritable configuration; resource bindings
must be explicitly supplied per environment. Its
[bindings overview](https://developers.cloudflare.com/workers/runtime-apis/bindings/)
describes bindings as the interface through which Workers access resources.
Thus removing a binding removes that runtime interface, not the resource itself.
The [Workers best-practices reference](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/)
was consulted; generic observability advice does not supersede this project's
explicit request-context privacy contract. These references support the
capability/environment interpretation, not any claim about live deployment.

Internal decision basis:
[direct-only architecture appendix](direct-forward-role-release-gate-architecture.md#complexity-decision-v01-is-direct-forward-only),
[conditional product scope](role-mail-release-scope-decision.md), and
[held API deployment contract](direct-forward-api-deployment.md).
