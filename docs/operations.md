# Mail operations and release

Current delivered state is in [validation](validation.md); this runbook is not the
[public manual](https://amail.moesegfault.dev/manual/). Do not reuse old held-state
snapshots as present policy or dispatch authority.

## Active topology

| Component | Source/configuration | Boundary |
| --- | --- | --- |
| Public API mail.moesegfault.dev | crates/mail-worker/wrangler.toml + entry/api.mjs | HTTP/RPC, no Cron |
| Private maintenance | crates/mail-worker/wrangler.maintenance.toml + entry/maintenance.mjs | Scheduled only, no HTTP/RPC/send binding |
| Email ingress | workers/mail-ingress | Bounded MIME to private API binding |
| Lifecycle consumer | workers/mail-events | Delivery/bounce/complaint Queue to Mail D1 |
| Private trace sink | workers/trace-sink | Queue only; exact API + maintenance producer pair |
| Release site amail.moesegfault.dev | site | Introduction/manual/changelog |

Production API and maintenance share response-owned fresh Mail D1
`d9be9bb4-5a73-4223-85d6-b04763e6f03b`,
`moesegfault-mail-production-708b6d6c734779d657f5abb3`, and R2
`moesegfault-mail-raw-production-708b6d6c734779d657f5abb3`.
Current checked-in configurations are authoritative for bindings.
Original production D1 `ad06f7f3-8897-4150-b9a9-7a46a8e55b30` and R2
`moesegfault-mail-raw-production` were retained, not silently migrated/deleted.
Staging uses separate D1 `74f35f95-42ce-482c-86e6-dffbdd35cbbe` and R2
`moesegfault-mail-raw-staging`. Never cross-bind realms.

An HTTP Custom Domain is not SMTP MX. User addresses end in @mail.moesegfault.dev;
official site sender is mail@moesegfault.dev. Identity production/staging issuers
and clients are distinct. HTTP health does not establish message delivery.

## Supported hosted lanes

ci.yml pushes/PRs validate source without deployment. Manual targets:
checks, staging, staging-e2e, production, production-api-only-maintenance,
production-fresh-bootstrap and production-fresh-online.
The actual workflow input/confirmation schema is authoritative; no historical
incident document may restore a removed dispatch mode. staging-e2e retains the
normal native-login/two-SMTP/ZIP/search journey and RUN_STAGING_E2E confirmation.

Keep actual-production-users for separately authorized owned production journeys,
send-control/attest/direct-contact/role-forwarding/grant workflows for explicit
operator actions, fresh-mail-bootstrap-recovery for read-only recovery, and the
standalone Identity test inbox for its protected narrow use. Release/site workflows
remain separate. Queue capability probe is manual only, not normal-source traffic.
Do not build a new incident workflow around every provider failure.

## Deploy and rollback

1. Admit exact source and full hosted gates, then restore/reverify the same-run
   Worker artifact. [Artifact rules](deployment-artifact-foundation.md) apply before
   secrets, migrations or provider mutation. Serialize production graph writers
   using the existing shared lock; never nest the same lock and deadlock.
2. Use scoped existing credentials: CLOUDFLARE_ACCOUNT_ID/API_TOKEN for deployment,
   CF_EMAIL_ROUTING_TOKEN for literal rules, OPENROUTER_API_KEY for indexing, stable
   realm-specific INGRESS_SECRET for ingress/API. No browser/global-key fallback.
3. Apply forward-compatible migrations before dependent runtime. API stays fetch-
   only with empty Cron; maintenance owns scheduling. Deploy compatible sink/readers
   before producers. Preserve direct forwards and lifecycle attribution.
4. Independently read serving version/deployment, exact immutable bindings, Queue
   producers/consumer/DLQ, capture flags, public surfaces and schedules. Names or
   TOML intent alone do not prove the active graph.
5. For rollback hold new sending first when required, retain additive state and
   replay/idempotency evidence, restore only compatible prior runtime/configuration,
   and read back actual graph. Never restore API Cron, purge queues, drop migrations,
   delete stores or resend an unknown provider submission.

Timeout/failed read is UNKNOWN, not resource absence. Capture exact owned response/
receipt coordinates before further work. Do not repeat a write after a lost watch.
Fresh bootstrap is not ordinary maintenance; see [recovery](fresh-mail-bootstrap-workstream.md).

## Durable mail invariants

Address creation spans D1 and Routing, not a distributed transaction. Reserve
ownership/quota first; confirm the exact enabled API-owned literal worker rule
before activation. Disabled rules are not active mailboxes. An ambiguous activation
write may have committed: use exact owner/rule readback as positive evidence and
preserve the route for state-aware reconciliation. Never inline-delete or issue a
second provider create to compensate for uncertain D1 state. Failed readback proves
nothing. Active state must not be marked for a reconciler branch that deletes routes.
Retired names remain reserved; route retirement precedes ownership release.

Outbound provider acceptance and delivery differ. Keep accepted/unknown journals,
one-submission idempotency and fenced HTTP/maintenance projection. Publish content/
chunks/storage-ledger/terminal state only when the matching owned projection is
complete. Deferral preserves drafts/reservations; it cannot resurrect deleted mail
or authorize a second send. Maintenance phases have bounded budgets/deadlines and
fair scheduling; do not bypass resource permits with compensation SQL or hide
deferred work as success. See [indexing](semantic-indexer-operations.md).

## Release and maintenance discipline

Release tags build five native archives, skill bundle and SHA256SUMS; verify exact
published bytes and provenance. Published site state requires a real nondraft
Release with expected assets. Candidate site deployment cannot imply release or
send authorization. Keep user manual, command help and packaged skill aligned.

Prefer a small static set of product-contract tests and existing platform lanes.
Document durable semantics/decisions here, not a new per-task audit ledger. Delete
unused experiments; Git history is the archive. This follows production
[SRE simplicity](https://sre.google/sre-book/simplicity/): maintenance machinery must
serve user value, not become the product.

Recent [pipeline-aware test optimization research (ICST 2025)](https://arxiv.org/abs/2501.11550)
also separates fast feedback from costly acceptance. Its learned selection system
addresses large industrial pipelines; this project uses a small explicit suite
instead of adding another selection or coverage platform.
