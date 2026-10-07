# Fixed USD production release — 2026-10-08 Asia/Singapore

## Authority and scope

The owner explicitly authorized production rollout and updating the installed
CLI plus matching agent Skill. The completed staging evidence is in
`usd-cutover.md`: Mail runtime27c5818, Billing86bb06e, complete ordinary acceptance
37646418030 and independent monetary/trace evidence11494520444. This supersedes
the earlier staging-only restriction for this new release, not for historical runs.

Publish the five-platform v0.2.0 release before switching the production API's
required client version. Existing v0.1 clients receive a typed upgrade requirement;
the default local production realm and encrypted credentials remain unchanged.
This does not add a payment processor: authorized variable usage remains pending
settlement and existing activation grants retain their one-use semantics.

## Production configuration and credentials

Billing/Subscribe use their existing independent production D1s, Identity issuer,
OAuth client/sector and domains. Add the three amail USD plans without changing
the existing platform product. Exact return is
`https://amail.moesegfault.dev/billing/return`. Public HTTP capture is disabled as
in the accepted staging bridge; only closed typed trace records are retained.

A new create-only production service capability lives in ignored, user-only
Subscriptions `.secrets/amail-service.production.key`. It is independent from the
staging capability and administrator/OAuth keys. Provision the same unchanged
value as protected Billing `cloudflare-production` AMAIL_SERVICE_KEY and Mail
`production` BILLING_SERVICE_KEY. Neither value nor ciphertext enters source,
command arguments, public logs or artifacts. GitHub Secrets writes initially
returned HTTP500; after backoff both normal environment writes succeeded and
name-only reads confirmed them. GitHub status reported operational, not a verified
global incident. No broader repository-secret fallback was adopted.

## Exact Mail predecessor and ordering

Source-owned successful upgrade37104468990, artifact11267970678, source805ac273:

| Role | Deployment | Version |
| --- | --- | --- |
| API | 4eee1ec6-8f70-47ee-98d8-e7ba4feb3f19 | 50bd330d-2f9b-4102-8c8e-9bbaada927fe |
| Maintenance | 411db6fb-3028-44bd-98db-cb354bfbe922 | 293d4049-c56a-40ee-8bc3-ef345a7a4eb7 |
| Trace sink | e4c4cc87-48e7-44d3-9cb0-390764e2ee34 | d372b6f0-42ed-4536-b7ee-15273b50d6a3 |

`production_v020.py` keeps the historical controller frozen. It accepts these
exact predecessors, verifies unchanged retained SMTP/lifecycle adapter source and
serving versions, preserves the complete current send-policy row and private
forward/subscription fingerprints, and requires exact queue/capture brackets.
Only the two pinned old API/maintenance UUIDs may omit the new Billing bindings;
all replacement versions require the complete production contract. Mixed-version
rolling reads apply the exception independently to each unchanged old role.

The compatible typed sink must precede new linked-span producers. Then apply
forward-only migrations0013/0014/0015, compare every original address ownership
tuple in memory, verify initial Free/USD/zero-cap resource accounts, replace API,
then scheduled maintenance at the unchanged five-minute cadence. Mail D1/R2,
addresses, messages, provider journals, queues, retained ingress/lifecycle workers,
Identity subjects and sending policy are not replaced or reset. No database
restore or synthetic usage event is used. Each exact tested same-run artifact is
checked before submit. A failed/unknown write records coordinates and stops;
never replay a production workflow as recovery without reconciling its journal.

## Focused verification

Local infrastructure239tests passed, including exact predecessor capabilities,
real config-derived production issuer, ownership loss/concurrent additions,
sink/schema/API/maintenance ordering, dependency failure before any mutation and
no replay after an ambiguous API submission. Billing deployment54tests passed,
including production catalog/isolation, protected production provisioning and
fixed production capture readback. Hosted build/release/production evidence will
be recorded here after actual delivery; local fixtures do not establish rollout.

Industry and academic rationale remains the accepted currency design in
`usd-cutover.md`: denomination-preserving integer accounting, typed money/resource
invariants and explicit boundaries rather than FX or a general payment engine.
