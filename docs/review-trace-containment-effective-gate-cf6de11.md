# Review: effective capture-off Queue rollout gate

Reviewed 2026-09-30. Source under review: `cf6de111371a24a86d042868d00f222f818fe031`.
Decision: **GO for hosted source CI under the existing deployment-only evidence
contract**. No substantive defect was found in this migration. This is not a
live containment, Queue provisioning, or production release authorization.

## Scope and evidence

Inspected the commit diff, `infra/deploy/require_trace_containment.py`, its
synthetic contracts, the shared `check_observability.py` predicate, serving
deployment parsing, rollout documentation, and the staging sink/API workflow
call sites. Reused `observability-effective-readback-decision.md` and the pinned
Wrangler investigation. Retrieved current official [Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/),
[Workers Issues](https://developers.cloudflare.com/workers/observability/issues/),
and [Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/).
No local tests/builds, private provider calls, deployments, pushes, or mutations
were performed. Hosted execution of the new tests remains required.

## Contract assessment

| Boundary | Source evidence | Assessment |
| --- | --- | --- |
| Historical provenance | `require_trace_containment.py:36-56` requires exact first-attempt completed-success run, branch/workflow/SHA, complete job listing, one successful named deploy job, and exactly one matching emitted version | Preserved; no diagnostic/settings-only run can replace deployment provenance. |
| Immutable source intent | Lines 57-65 fetch TOML at the run SHA, require literal staging script name, and apply strict source observability policy | Strengthened. Missing/true Issues or wrong staging identity is rejected. Current config cannot retroactively change historical intent. |
| Effective no capture/export | Lines 81-85 use exact-name Worker resource and shared full-boundary predicate, with both legacy reads checked for contradictions | Positive explicit parent/Logs/traces/Issues-off required. Missing legacy representation does not supply evidence. No preview-object or historical-source fallback exists. |
| Serving stability | Lines 78-80, 86-88 bracket settings with the same deployment/version pair and exact expected single-100 version | Split/unexpected traffic, deployment drift, and readback failure deny before Queue/sink mutation. |
| Sink isolation | Staging sink invokes gate before queue provisioning and again after sink deploy; API invokes it before D1 migration/build/deploy | Queue ownership, sink isolation, and stricter enabled-sink checks are not weakened by this change. |

Synthetic additions exercise immutable missing/true Issues and wrong-name
source, malformed environment shape, current Issues/logs/traces omission or
enablement, wrong identity, preview substitution, exports/tails, legacy conflicts,
Worker readback failure, wrong expected version, and deployment drift. The
successful fixture correctly describes explicit full-boundary source intent;
it does not upgrade any historical live run whose source lacked Issues-off.
Mocks deliberately separate source provenance and live-state contracts; they
are not proof of hosted/live behavior.

## Consequences for the next attestation design

The documented previous containment runs without immutable Issues-off cannot
pass this gate. A settings-only run cannot pass its required deploy-job/version
log contract either. That is an intentional fail-closed limitation, not a reason
to accept missing Issues or relabel a narrow Logs-off observation as safe.

A later settings-only evidence path must be a separately reviewed contract:
preserve immutable successful run/source/job identity, bind the observed serving
version, distinguish settings provenance from code-deployment provenance, and
retain the same explicit full-boundary current-resource predicate and stable
single-100 bracket. Do not merely skip `immutable_evidence`, change its deploy
job name to a generic diagnostic, or repin an old source SHA to current intent.

The deployment bracket does not create an atomic lock over non-versioned
settings. Existing serialized hosted deployment policy and an out-of-band
operator freeze remain assumptions, not guarantees provided by this helper.
Whole-retained-record synthetic non-retention and causal sink-event acceptance
remain separate requirements after rollout; neither source review nor settings
readback substitutes for them.
