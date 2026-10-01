# Cron resource observation: measurement plan and schema-only discriminator

Date: 2026-10-01. Base: main `13b2c28`, **not a deployed Mail revision**.
Status: source candidate; independent review and hosted synthetic CI required.
No local project tests/build, private provider call, deployment, mutation,
workload generation, dispatch, push or PR performed here.

## Evidence now available

The operator confirms Workers Paid for the reviewed account and provider-default
CPU Limits for `amail-mail-staging`. This establishes applicable assumptions by
**operator attestation**, not an observed CPU value or enforced stress ceiling.
No precise UTC attestation timestamp was supplied here; do not invent one.
This updates the uncertainty in [tier preflight](workers-tier-cron-preflight-2026-10-01.md).

The [specific limits contract](https://developers.cloudflare.com/workers/platform/limits/)
for Paid `*/5 * * * *` is **30,000 ms CPU / 900,000 ms wall time**.
The [D1 policy](https://developers.cloudflare.com/d1/platform/limits/) is
**1,000 queries/invocation**; the reviewed source adapter caps submissions at
**800 D1 statements**. These are distinct budgets, not measured workload fit.
**Issues privacy gate is unchanged**. Schema, missing/null settings, sampling,
or successful deployment cannot prove Issues disabled or authorize rollout.

## Why a runtime admission gate is premature

| Source | Useful evidence | Not established |
| --- | --- | --- |
| GraphQL introspection | Exact named type/member visibility | Data permission, metric units, filter value semantics or measurements |
| Scheduled-invocation dataset | Cron slot/status/CPU when actual schema supports them | Wall/memory/version fields that are absent |
| Adaptive exact-version Cron population | Provider CPU/wall/memory quantiles after filter semantics are verified | Per-invocation maxima or peak RSS |
| D1 database/time aggregates | Query/row costs | Each Cron's submitted statements or exclusive attribution |
| Hosted native D1 observer + source adapter | Exercised statement budget and transition correctness | Deployed Cloudflare CPU/wall/memory fit |

[Worker metrics](https://developers.cloudflare.com/workers/observability/metrics-and-analytics/)
use reservoir-sampled quantiles. Memory is shared V8 isolate memory at invocation
time, **not peak resident set size (RSS)** or peak within-invocation allocation.
[Cloudflare's memory update](https://developers.cloudflare.com/changelog/product/workers/3/)
documents `memoryUsageBytesP99` in GraphQL as bytes. The
[Cloudflare-maintained schema guide](https://github.com/cloudflare/skills/blob/main/skills/cloudflare/references/graphql-api/api.md)
mentions scriptVersion dimensions, but the main metrics tutorial does not prove
Cron-only filtering. [MCP issue #435](https://github.com/cloudflare/mcp-server-cloudflare/issues/435)
reports missing Cron CPU/wall telemetry fields; do not assume logs fill this gap
or enable raw invocation capture. No empirical staging baseline exists here, so
no extra CPU/wall/memory admission margins are selected yet.

## Minimal implemented discriminator

`infra/provider/probe_cron_metrics_schema.py` makes **one fixed GraphQL query**
with eight `__type` aliases: adaptive dimensions/filter/quantiles, scheduled
rows/filter, D1 dimensions/filter/sum. Exact names are hypotheses until readback.
There is no `viewer`, account/resource selector, dataset read, description, raw
log, mutation, fallback or discovery query. Introspection cannot filter members
by name; only those eight types' member names are requested. Unknown valid names
are discarded. Output contains fixed keys with `present`, `absent`, `unavailable`.
A null type is unavailable, not absent. Scalar types/units are deliberately not
certified by this name-only discriminator.

Strict bounds: 262,144 response bytes, 500 members/type, 20-second HTTP timeout,
no redirect/retry, duplicate-key/nonstandard-constant rejection, exact aliases
and type identity/kind validation. Partial or malformed responses print only a
fixed failure category; no provider text, identifiers or traceback escapes.
Every classification ends with `cron_resource_admission=UNVERIFIED`,
`runtime_measurement=not_performed`, `issues_privacy_gate=unchanged`.

The separate `.github/workflows/cron-metrics-schema.yml` runs synthetic contracts
without credentials on relevant PRs and before a manual read. Its only secret
job requires `main`, staging Environment and exact `READ_CRON_METRICS_SCHEMA`;
only existing `CF_OBSERVABILITY_TOKEN` is used. No account/deployment token or
artifact upload; existing CI/deploy jobs are untouched. Schema availability
alone does not establish token access to runtime data. Permission failure stays
UNVERIFIED; no credential expansion is implied.

After independent review and hosted tests, root may separately authorize:

```sh
gh workflow run cron-metrics-schema.yml --ref main -f confirm=READ_CRON_METRICS_SCHEMA
```

No dispatch was performed. Retain immutable run ID/attempt/head SHA and fixed
bins only. Hosted success means classified schema, never release admission.

## Actionable next measurement, after future safe deploy

1. Independently verify existing capture-off policy, **including explicit Issues
   false**, and record the exact safe deployment source SHA and Worker version.
   Freeze deployments/settings across the observation period. Recheck unchanged
   100% serving identity/privacy before and after; the current serving bracket
   alone cannot attribute a historical window or delayed old-version invocation.
2. If adaptive schema has both version and Cron-event fields in dimensions
   **and filters**, verify accepted event value, scalar types and units from
   official schema/docs. Then review one static exact-Worker/exact-version/
   bounded-window CPU/wall/isolate-memory projection. If not, Cron wall/memory
   attribution stays UNVERIFIED; Worker-wide P99 cannot admit rare Cron work.
   Scheduled rows without version provide diagnostics only, never an implicit
   timestamp join to a deployment. No adaptive private endpoint probing.
3. Read **already completed natural Cron executions** passively. The observer
   cannot seed data, invoke Cron, send email or change holds. Any representative
   synthetic setup requires separate authorization. Include service-valid
   maximum archive/HTML expansion, complete routing inventory, embedding cap,
   cleanup/backlog, realistic concurrency and cold/warm repetitions. Cover all
   eight phase-rotation positions and repeated complete maximum-item executions;
   an empty fast tick does not measure useful workload fit.
4. Report provider CPU/wall units, exact revision, workload coverage, delivery
   lag/completeness, sampling and status failures separately. Missing/empty,
   duplicate/truncated/partial data is non-admitting. Do not average bucket P99s
   or call quantiles maxima. Compare repeated comparable windows to establish
   a staging baseline, then select explicit operational headroom below 30 s CPU,
   15 min wall and stated 128 MB memory limits. Shorter-than-5-minute completion
   is an overlap objective to evaluate, not a measured guarantee here.
5. Per-Cron D1 count remains a separate required <=800 condition. Database totals
   divided by tick count or synthetic observer counters are not deployed proof.
   Require a separately reviewed allowlisted per-invocation counter channel or
   keep that runtime condition UNVERIFIED. Preserve native complete-item/fence
   correctness tests; success status alone does not prove intended work finished.

The [D1 metrics contract](https://developers.cloudflare.com/d1/observability/metrics-analytics/)
and [GraphQL sampling contract](https://developers.cloudflare.com/analytics/graphql-api/sampling/)
explain these attribution limits. [ServiceLab (OSDI 2024)](https://www.usenix.org/conference/osdi24/presentation/chow)
provides a production research precedent for controlled repeated pre-production
performance testing; this small probe does not inherit its statistical power.
The [Cron contract](https://developers.cloudflare.com/workers/configuration/cron-triggers/)
and [introspection contract](https://developers.cloudflare.com/analytics/graphql-api/features/discovery/introspection/)
were also retrieved on 2026-10-01. All cited sources are primary.

## Verification here

Python AST parsing and staged whitespace review passed. Candidate synthetic
tests were authored, **not run locally**. No hosted CI, YAML lint, authenticated
schema, runtime measurement or speedup is claimed. Independent source review is
required before any hosted CI/secret use; root controls PR and dispatch decisions.
