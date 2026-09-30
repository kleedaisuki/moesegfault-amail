# Direct-forward-only Mail API deployment contract

Date: 2026-10-01. Status: **conditional source implementation; not deployment,
operational adoption, human attestation, or public-send authorization**.
No local tests/builds, provider calls, deployment, routing mutation or mail send
were performed for this configuration change. All public sending stays held.

## Ownership and exact topology

The [v0.1 complexity decision](direct-forward-role-release-gate-architecture.md#complexity-decision-v01-is-direct-forward-only)
selects one direct-forward contract, not a selectable direct/Worker mode.
The Mail API's contact policy, observation health and attestation identity live
in `MAIL_DB`. Production and staging each bind only their existing Mail D1;
neither API binds `ROLE_MONITOR` or imports its lease. Missing contact adoption,
freshness, human commitment or release evidence denies public sending.

| Surface | v0.1 contract | Migration effect |
| --- | --- | --- |
| Mail API D1 | Exactly `MAIL_DB`, independently configured per realm | Remove API access to isolated role D1 only after the runtime no longer reads it |
| Four operational contacts | Existing Cloudflare-managed direct forwards to the confidential destination | No routing write, receipt replay, destination change or Wrangler-owned addresses |
| Trace events | Exact API producer -> existing events Queue -> private queue-only sink | Keep `api-only`; do not accept a role producer as an arbitrary extra |
| Role Worker / isolated role D1 | Dormant implementation, outside v0.1 admission | No deletion, migration, deployment or fake lease; source existence is not active-graph acceptance |
| HTTP, R2, Email, search Cron | Existing Mail realm bindings and routes | No external API/protocol or user-mail topology change |

The sink still has one consumer per realm, batch 10, wait one second, three
retries, retry delay 30 seconds, concurrency two and the existing realm DLQ.
Its private retention boundary and all API capture-off settings are unchanged.
TOML proves intended attachments only: independent hosted readback must prove
the actual **exact API-only** producer/consumer graph and stable serving pins.
The dormant role TOML still declares its future producer; it must not be deployed
into this graph by a leftover role-rollout target.

## Held rollout and rollback

1. Keep global public-send hold and all account/recipient holds. Do not translate
   an old role lease or historical `abuse_contact_verified` boolean into a new
   accepted direct contract. Owner coverage for Inbox and Junk and Cloudflare's
   response obligation remains a separate explicit adoption/attestation.
2. Independently review and run hosted source contracts for the additive Mail
   migration, runtime/operator/release predicates, configuration and workflows.
   Reconcile the staging binding pin and production graph bootstrap/maintenance
   checks with a strict `api-only` lifecycle that does not depend on role D1.
   Do not bypass a failing old role prerequisite and call that acceptance.
3. Through a separately authorized held rollout, apply the additive Mail
   migration and deploy the runtime **together with** this TOML. Deploying old
   role-dependent code without its binding is unsupported. Read back exact
   immutable version bindings, capture-off settings and Queue identities before
   claiming the API/sink graph accepted. Preserve all four direct rules.
4. Configuration-health success permits neither automatic global allow nor a
   human attestation. Public release still requires the exact adopted contract,
   fresh bounded observation and all independent release evidence. This document
   grants none of those permissions.
5. Rollback is held and reviewed: retain additive Mail data, never destroy role
   storage, and restore an older runtime only with its matching old TOML and
   independent dependency evidence. An absent/expired genuine role lease must
   keep that old runtime denied; never populate one from direct-forward reads.

Already in-flight provider sends cannot be recalled by removing a binding or
holding D1 state. Preserve existing ambiguous-delivery/idempotency handling.

## Evidence and source references

`infra/tests/test_direct_forward_api_config.py` guards the source D1 shape,
realm separation, unchanged API/sink Queue parameters, capture-off settings and
absence of Wrangler-owned operational addresses. It does not inspect live
Cloudflare rules or prove that a human reviews mail. It was authored but not
executed locally, in accordance with this assignment's hosted-only validation.

Cloudflare describes bindings as runtime resource capabilities and notes that
bindings are non-inheritable per environment; both realms are therefore explicit.
References: [Wrangler configuration](https://developers.cloudflare.com/workers/wrangler/configuration/),
[bindings](https://developers.cloudflare.com/workers/runtime-apis/bindings/),
[Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/).
The existing privacy contract takes precedence over generic observability advice.

## Active graph gate interfaces

`pin_staging_mail.py` now derives the sole `MAIL_DB` and `MAIL_BODIES` resource
by their exact binding names. Its config guard rejects missing, duplicate,
additional or renamed D1/R2 entries and malformed D1 IDs; immutable deployed
bindings must still equal the reviewed realm's complete allowlist. Removing
`ROLE_MONITOR` never permits an arbitrary substitute database. `pre-queue`
remains a strict historical pin phase, not an optional-bindings variant; the
active deployed graph uses `queue-api` and the exact events Queue ID.

The active production interfaces are:

| Stage | Command / confirmation | Required contract |
| --- | --- | --- |
| First preparation | `prepare_production_graph.py --phase bootstrap`; `RUN_PRODUCTION_API_ONLY_BOOTSTRAP` | Main branch, writer freeze, held send/unset contact attestation, successful complete API/role absence inventory, four unchanged verified direct forwards, reviewed Mail resource config |
| Maintenance preparation | `prepare_production_graph.py --phase api-only-maintenance`; `RUN_PRODUCTION_API_ONLY_MAINTENANCE` | Main branch, writer freeze, full strict current api-only graph |
| Pre/post replacement or bootstrap post-deploy | `check_production_role_graph.py --phase api-only` | Exact single-100 API/sink version pins; distinct reviewed Queue/DLQ IDs; `AMAIL_TRACE_TOPOLOGY=api-only`; exactly one API producer and private sink; independent API and sink capture-off; role Worker absent; held policy; four exact unchanged forwards |

No active command reads isolated role D1 schema, arrival state, health or lease.
No role Worker version pin is required: a nonempty role version or nonzero
role-routed count is rejected as contradictory input, not silently ignored.
Provider role absence is required to rule out accidental active infrastructure,
but no role Worker is installed or required. The exact API-only Queue readback
independently rejects any role/unknown/duplicate producer. Unrelated staging
resources remain preserved; no retirement/deletion is authorized here.

The graph checker brackets API/sink deployments, Queue ownership, role absence,
direct-forward shapes and held policy. It emits only fixed outcome labels; all
provider bodies, bindings and destination values stay private. These are bounded
observations, not a provider/D1 transaction or proof of human Inbox attention.
The existing Gray Failure lesson applies: configuration health does not prove
the outcome users rely on; retained-record privacy and intervention evidence
remain separate. See [Huang et al., HotOS 2017](https://www.microsoft.com/en-us/research/publication/gray-failure-achilles-heel-cloud-scale-systems/)
and the [direct-only architecture decision](direct-forward-role-release-gate-architecture.md).

Historical `before`/`after`/`maintenance` graph helpers retain their strict role
schema checks for separately scoped future research. They cannot prepare current
production promotion: `prepare_production_graph.py` rejects
`api-role-maintenance` and its old confirmation. The production role-rollout
workflow must also be disabled, not simply hidden from the default dispatch.

### Required CI integration (separate ownership)

At source authoring time the workflow is being independently changed; this list
defines the coordinated handoff rather than authorizing a dispatch:

1. Replace every active `production-api-role-maintenance` target/condition with
   `production-api-only-maintenance`, including build dependencies and shared
   workflow-level `amail-production-graph-writer` concurrency. Keep non-canceling
   production writer serialization and the external-writer freeze requirement.
2. Set both production sink and Mail job topology to literal `api-only`; remove
   role version and routed-count environment inputs from these jobs. Maintenance
   confirmation becomes `RUN_PRODUCTION_API_ONLY_MAINTENANCE` and preparation
   phase becomes `api-only-maintenance`.
3. In `deploy-trace-sink`, only bootstrap uses
   `ensure_trace_queues.py --phase queues --topology api-only`. Maintenance uses
   `--phase readback --topology api-only` and preserves the exact configured
   Queue/DLQ identities, never provision/recover/recreate. Old/new sink and Mail
   replacement rechecks use `check_production_role_graph.py --phase api-only`.
4. Bootstrap post-Mail deployment also uses `--phase api-only`, with captured
   new API/sink version IDs and step-linked Queue/DLQ outputs. Do not pass
   `--lifecycle first-bootstrap` or `--migrated`, apply isolated-role migrations,
   or deploy a role producer as part of either current path. Emit the existing
   exact `production_trace_graph_attestation=api-only-v1` marker after successful
   full graph readback, preserving evidence-consumer meaning for either path.
5. Disable the executable production role rollout in
   `deploy-role-monitor-production.yml`; preserve its history/source without
   leaving a dispatch capable of attaching the future role producer. Staging
   research is outside this promotion, not implicitly accepted by it.
6. Update `infra/tests/test_production_role_workflow.py`: replace the old target
   assertion with `production-api-only-maintenance`; replace required
   `--phase readback --topology api-role` with strict `api-only`; assert all
   current graph checks use `--phase api-only` and no role D1 migration/producer
   occurs. Replace old executable production-role ordering assertions with a
   fail-closed dormant-job assertion. Preserve writer-lock, dispatch-limit,
   no-routing-write, and independent evidence assertions.

`infra/tests/test_production_api_only_graph.py` contains synthetic behavioral
contracts for the direct graph/preparation and named resource guard: successful
bootstrap and maintenance without role storage reads; exact Mail D1 identity;
rejection of unexpected role bindings, contradictory role inputs, missing pins,
Queue drift, failed role-absence proof, hold failure, deployment/forward changes
and independent API/sink privacy failure. These tests were authored but **not
run locally**; hosted execution and independent review are required before any
operational adoption. No provider mutation, deployment or send was performed.
