# Maintenance operational lanes and bounded historical retirement

Status: source policy and first reversible cleanup; hosted acceptance is recorded
below when available. Inventory baseline: main
`d593d1a20fa2bbf59b997e13343373614aa7fcf7` (2026-10-01).
The [infrastructure foundation](infrastructure-foundation.md) is the authoritative
status/priority ledger. Historical reviews describe evidence, not permission to
resume their campaigns. No deployment, provider query, login, mail action, sending
grant, Secret change, or resource deletion accompanies this cleanup.

## Operational decision rule

1. For source work, open a focused PR and inspect hosted infrastructure and syntax
   checks plus the source suites selected by the conservative scope classifier.
   Full exact-source CI is still required by promotion consumers. Diagnostic
   artifact replay and the isolated native-tracing reuse exception do not admit
   ordinary deployment or release.
2. For an explicitly requested provider operation, locate the exact supported
   workflow/helper and current runbook. Preserve source/artifact/run/version
   provenance, first-attempt/confirmation rules, writer serialization and readback.
   A failed read is not resource absence; an ambiguous write is not permission to
   retry. Do not substitute an old probe for a current incident diagnosis.
3. Keep supported recovery callable while receipts, aliases, objects or escrow may
   still need reconciliation. A historical experiment label is not evidence that
   its cleanup obligations ended. Recovery requires original identity and its own
   authorization; it does not authorize a new campaign.
4. Keep the current send hold. Foundation source acceptance alone is not runtime
   privacy acceptance, production readiness or a business-debug resumption gate.
   Actual user mail remains in the `amail` CLI skill, not operator store edits.

## All workflow files: executable classification

The table accounts for all 28 workflow files at the baseline. "Supported" means
retain the source contract, not that production is deployed or execution is
authorized. "Held" is operational policy while foundation work is incomplete;
it does not claim that every historical job has a new technical disable switch.

| Workflow(s) | Lane and execution surface | Provider/business boundary and disposition |
| --- | --- | --- |
| `ci.yml` | Push/PR source checks; manual checks, deployment, acceptance and legacy diagnostics | Source jobs and dispatch classes are inventoried below; remove only the three completed fixed-window reads |
| `workflow-lint.yml` | Independent push/PR inert YAML/dispatch-limit parser | No project Secrets or provider calls; mandatory source guard, retain |
| `private-provider-crypto-tests.yml` | Push/PR synthetic encryption tests | Credential-free source verification, retain |
| `site-ci.yml`, `site-browser-acceptance.yml` | Candidate-site source/browser checks; manual/reusable source checks | Hosted source acceptance, not public deployment; retain |
| `release.yml` | Version-tag publication; manual main bundle verification | Attestation/published-byte/send-release gates remain supported; do not retire or weaken |
| `site-candidate.yml` | Manual candidate-site source/deploy graph | Calls `site-ci.yml`; candidate deployment is not production release; retain |
| `deploy-identity-test-inbox.yml` | Manual staging Identity inbox deployment | Supported private native-login dependency, not a research probe; retain its identity and strict exact-main artifact admission from the separate deployment workstream |
| `send-control.yml`, `attest-send-gate.yml`, `grant-send-canary.yml` | Manual policy/control/attestation and one-use grant | Operator D1/sending controls, not CI; preserve hold and explicit admission |
| `role-forwarding.yml`, `direct-contact-adopt.yml`, `direct-contact-attest.yml` | Manual role/contact operations | Provider routing/verification and adopted-policy/coverage contracts; public release consumers depend on them; retain |
| `direct-contact-health.yml` | Manual refresh; hourly schedule gated by `AMAIL_CONTACT_HEALTH_ACTIVE` | Provider configuration reads plus scoped D1 health state; not a read-only source check and not an unhold; preserve opt-in schedule/expiry contract |
| `held-production-inspection.yml` | PR synthetic contracts; separately admitted manual inspection | Production provider/D1/resource verification, not ordinary PR execution; preserve bootstrap/hold safeguards |
| `native-fixture.yml` | Manual checked-artifact fixture replay | Credential-free diagnostic fast path only; unchanged compilation inputs required, not full CI/promotion |
| `native-tracing-canary.yml` | Manual isolated infrastructure experiment/diagnosis | Current active foundation experiment; source-owned temporary probe/caller only, checked artifact and receipt-owned cleanup; **retain**, not replaced by old Mail canaries |
| `cron-metrics-schema.yml` | PR synthetic contracts; manual fixed schema metadata read | Current schema diagnostic, not workload/capture/privacy acceptance; retain separate guarded lane |
| `probe-queues.yml` | Historical capability read; manual **and legacy-branch path-filtered push** | Cloudflare Queue list read with project token; automatic provider surface exists, but no provider or repository disable action is taken here; do not treat as ordinary CI |
| `staging-issues-create-probe.yml` | Manual code-free historical discriminator | Provider capture/Issues settings write and restoration; held research, preserve until lifecycle/cleanup obligations are explicitly resolved |
| `staging-ten-address-acceptance.yml` | Manual campaign, retained escrow and exact recovery | Account/quota/alias/SMTP/provider state; held research with durable recovery obligations, preserve all recovery modes |
| `staging-ten-address-d1-proof.yml` | Manual D1 synthetic proof | Real staging D1 writes/cleanup, not a unit test; held diagnostic, retain ownership/cleanup contracts |
| `staging-worker-r2-capability.yml` | Manual one-use probe or exact-object recovery | Worker-created object/send grant and R2 deletion; keep recovery callable, do not repeat probe |
| `staging-trace-canary.yml` | Reusable `ci.yml` call and manual preflight/canary | Mail settings/retained-record reads and native login in canary mode; held Mail privacy acceptance, not replacement for infrastructure native-tracing experiment |
| `staging-trace-sink-canary.yml`, `staging-trace-http-compare.yml` | Reusable calls from `ci.yml` | Live staging retained-log acceptance/transport requests, not synthetic source CI; held diagnostics, retain caller contracts |
| `staging-outbound-canary.yml` | Dormant `workflow_call` only; **no checked-in caller** | Unfinished one-send/native-login/IMAP acceptance hook; not executable via dispatch, not accepted production delivery evidence; do not add a caller while foundation/hold remain incomplete |

## `ci.yml`: every job belongs to one lane

These lists name exact jobs, not broad filename or `staging-*` deletion rules.
`staging-r2-object-capability` implements both capability and original-artifact
recovery dispatch targets; `staging-second-principal` likewise preserves its
recover target. Removing a job by name without inspecting its modes would break
recovery. Normal source jobs never depend on the three retired reads.

| Class | Exact jobs | Boundary |
| --- | --- | --- |
| Normal source checks | `changes`, `cli`, `worker-build`, `worker-native`, `worker`, `site`, `dns` | Build once, independent artifact-verified native suites and stable `Rust Worker (Wasm)` aggregate; `dns` is synthetic infrastructure/Identity/config validation despite its historical name |
| Explicit promotion provider check | `provider-live` | Real OpenRouter embedding request; manual deployment targets only, not PR/push/checks |
| Supported production/deployment/release graph | `deploy-worker`, `deploy-ingress`, `deploy-events`, `deploy-trace-sink`, `release-ready`, `deploy-site`, `staging-site`, `staging-worker`, `staging-ingress`, `staging-events`, `staging-identity-test-inbox`, `staging-trace-sink` | Preserve dependency identities and artifact admission work; `release-ready` reads published/attested assets, it is not a historical probe |
| Held acceptance and recovery | `staging-e2e`, `staging-r2-object-capability`, `staging-second-principal-preflight`, `staging-second-principal`, `staging-semantic-query-only`, `staging-prior-alias-reconcile`, `staging-hosted-alias-reconcile`, `staging-fifth-mail-cleanup`, `staging-routing-write-probe`, `staging-routing-write-recover`, `staging-routing-write-audit` | Native login/mail/alias/provider state and recovery; no retirement based only on age or branch guard |
| Privacy/settings containment and state readback | `staging-containment-settings`, `staging-current-worker-capture-off`, `staging-capture-preflight`, `staging-settings-patch-audit`, `staging-settings-audit-shape`, `staging-containment-readback`, `staging-worker-resource-readback`, `staging-serving-pin`, `staging-routing-policy` | Some are settings writers, others reads; retain existing confirmations, freezes and containment evidence consumers |
| Held provider/incident research | `staging-worker-r2-delivery-history`, `staging-worker-r2-history-shape`, `staging-worker-r2-history-error`, `staging-private-provider-error-capture`, `staging-fifth-mail-audit`, `staging-routing-diagnostic`, `staging-current-address-diagnostic`, `staging-fourth-invocation-metrics`, `staging-role-smtp`, `staging-role-timeout-audit`, `staging-role-token-phase-probe`, `staging-role-phase-logs`, `staging-trace-canary`, `staging-trace-sink-canary`, `staging-trace-http-compare` | Not ordinary CI or release prerequisites; retain for bounded separately admitted diagnosis/recovery and evidence continuity, not as a recommendation to run |
| Retired completed historical reads | `staging-trace-marker-location`, `staging-trace-marker-discriminator`, `staging-trace-security-events` | Dispatch options **and** executable jobs removed; classifiers/tests/evidence retained below |

## First cleanup: completed historical reads, not recovery

| Retired target | Immutable incident/result | Retained classifier and evidence |
| --- | --- | --- |
| `staging-trace-marker-location` | Read run `36713163067`; exact failed canary window 2026-09-30 10:42:00–10:42:37 UTC; result could not distinguish the producer | `infra/tests/staging_trace_marker_location.py`; [original canary evidence](staging-trace-canary.md) |
| `staging-trace-marker-discriminator` | Read run `36723490687`; same immutable window; request-context carriers located, privacy still unverified | `infra/tests/staging_trace_marker_discriminator.py`; [second result](staging-trace-marker-second-discriminator.md) |
| `staging-trace-security-events` | Incident run `36671177226`; exact 2026-09-30 04:58:42–05:00:42 UTC window; subsequent reads `36675301214`/`36678625568` both `graphql_unverified` | `infra/provider/probe_staging_trace_security_events.py`; [Security Events evidence](staging-trace-security-events-probe.md) |

The original documents explicitly forbid repeating or broadening these queries.
They cannot prove current runtime privacy after the incident window has expired.
None is a writer, recovery tool, reusable workflow, normal CI prerequisite or
promotion dependency. Source references are only the three `ci.yml` invocations,
classifier imports/tests and historical documentation/reviews. The discriminator
imports the first classifier; preserving both prevents breaking that contract.

Delete the executable job/dispatch edges rather than add `if: false`, rename
jobs, duplicate workflows or rely on a prose warning. The prior reviewed wiring
is recoverable from immutable baseline [ci.yml source](https://github.com/kleedaisuki/moesegfault-amail/blob/d593d1a20fa2bbf59b997e13343373614aa7fcf7/.github/workflows/ci.yml).
No supported CLI/HTTP/ZIP/Identity/storage/binary contract changes. Existing
classifier behavior stays available for synthetic tests; it is not an approved
live runbook. No historical evidence or original run is deleted.

Current replacement is the foundation's isolated `native-tracing-canary.yml` for
the platform tracing/redaction question, and the runtime ledger's reader-first
Queue/source coverage for application diagnostics. These are related questions,
not retroactive privacy passes or drop-in reuse of the old Mail incident tools.
Any new Mail acceptance needs fresh independently reviewed scope and explicit
admission after the foundation; do not widen an archived query as a shortcut.

## Reversal, residual surfaces and verification

* Reversal is a reviewed source revert of this focused cleanup, with hosted source
  checks. It does not itself authorize a historical provider read. Use a newly
  scoped current diagnostic for a new incident instead of reenabling expired
  fixed-window probes by default.
* This change affects new executions of the updated source, **not** historical
  branch refs or already-created GitHub run attempts. Old source/run replay can
  still carry its original jobs. The maintainer policy forbids replaying retired
  provider reads; no GitHub remote disable/cancel/delete is claimed or performed.
* GitHub supports whole-workflow disabling without deleting source, but disabling
  `ci.yml` would also disable required userspace/build/deployment gates. Job-level
  source retirement is therefore the right boundary here. The legacy branch,
  supported recovery files, automatic Queue capability probe, unconsumed outbound
  hook, compiler drift inside held diagnostic workflows and unfinished provider
  acceptance remain explicitly inventoried debt, not silently declared solved.
* Replace the three obsolete workflow-presence assertions with one repository-wide
  retirement contract in `infra/tests/test_retired_trace_workflows.py`. It rejects
  target/script resurrection in any checked-in workflow, protects supported CI,
  deployment and recovery identities, and checks evidence/tool retention. Keep
  all synthetic classifier privacy/scope/error tests in normal infrastructure
  discovery. Infrastructure and independent YAML guard run on GitHub Actions;
  `ci.yml` edits continue selecting full source CI, not a new exemption.

Primary platform references:

* [GitHub: disabling and enabling workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows)
  — remote whole-workflow disable is reversible but not an appropriate per-job
  boundary for the shared CI/deployment workflow.
* [GitHub: reusable workflow contracts](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations)
  — caller edges and rerun source semantics matter; removing one dispatch option
  alone is not a whole-graph retirement proof.

This is evidence-led maintenance, not a novel research orchestration system.
The active native-tracing experiment owns the actual unresolved platform
mechanism; this cleanup isolates completed diagnostic questions without erasing
the evidence or disturbing supported userspace.
