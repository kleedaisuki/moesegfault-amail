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
