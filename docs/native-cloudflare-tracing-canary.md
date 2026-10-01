# Native Cloudflare tracing canary

Status: Rust source accepted by hosted validation, not deployed/native trace
acceptance. The owner prioritizes infrastructure/debt before mailbox debugging.

## Concrete experiment

One infrastructure-only Rust/Wasm product has two deployments: a private probe
with native traces and safe console events, and an untraced caller that constructs
four fixed synthetic requests. Caller input URL/query/header/body is never read
or forwarded. Probe has no workers.dev/preview/custom route and only the caller
has its service binding. No Mail DB/R2/Queue, account/SMTP/send capability or
runtime secret exists in the pair. Deployment overrides a public random run ID.

Cases are baseline/redacted crossed with success/fixed-failure. Distinct source
markers stand in for protected path, query, user-agent and body. Rust imports the
platform tracing namespace directly through wasm-bindgen, exercises getActiveSpan,
setAttributes, startSpan, fixed recordException and explicit child end. It checks
active context again across a real asynchronous delay. Redacted cases replace
url.full/path/query and user_agent.original on the root, without assuming that
this changes other automatic request/log records or survives finalization.

A fixed safe console receipt tests enrichment outside spans too. The source
receipt does not echo original URL/headers/body or JS exception prose. Native
failure reports a specific API/lifecycle stage; missing API/sampling/context is
not accepted as successful tracing. Baseline must establish the relevant markers
and actual native child/error records. Collect the complete pair-scoped window,
compare both policies, verify actual native parentage and inspect all retained
marker locations. Public operational IDs/schema keys are evidence, not privacy
violations. No raw real-mail record is involved or permitted.

The untraced caller's incoming request has no retained logs/traces and its data
never reaches the probe; it does not provide a general forwarding/mail endpoint.
This narrow public trigger is only infrastructure experiment control and must be
removed after collection. It is not an authentication mechanism or product UI.

## Source versus deployed acceptance

Miniflare 4.20260730.0 predates the active-root getter update. Hosted tests prove
that actual compiled Rust service dispatch generates four controlled requests
without caller data and truthfully reports unsupported new API on that runtime.
They **do not prove** current Cloudflare runtime support or redaction. Normal CI
builds the product once, includes its module tree in the verified artifact, and
assigns both native files to core (107 core / 156 total minimum). Actual controlled
deployment/readback, trace collection and cleanup are still required.

Use tested original artifact bytes for the pair, no hidden Rust rebuild on deploy.
Do not change Mail/maintenance capture settings, service graph or send hold to
run this experiment. Capture source/run/Worker versions and readback; ambiguous
writes require existing-state inspection rather than automatic resubmission.
If root replacement leaves private markers in other fields, retain the safe
application event boundary and use native tracing on suitable platform surfaces.

## Primary references

* https://developers.cloudflare.com/workers/observability/traces/custom-spans/
  — getActiveSpan is request-context-dependent; undefined attribute values are
  no-ops, manual spans must end, recordException can expose error message/stack.
* https://developers.cloudflare.com/workers/observability/traces/spans-and-attributes/
  — automatic URL/user-agent/Email/D1/R2 fields have distinct privacy origins.
* https://developers.cloudflare.com/workers/best-practices/workers-best-practices/
  — service bindings and invocation-owned state instead of public forwarding.
* https://wasm-bindgen.github.io/wasm-bindgen/reference/attributes/on-js-imports/module.html
  and js_namespace — bind native module functions without a hand-written JS mail
  implementation or guessed exported Span constructor.

## Checked-source result and isolated lifecycle lane

PR 49 source 8bf3f5097de0edafec8b9171c797e34f1a3023a0, actual merge checkout
383052f832e2d7a9e02279c42f040f0ec0bae314, passed CI 36861601016 and syntax
36861600039. All 156 native tests, three CLI platforms, Astro, Rust/Wasm/unit and
infrastructure checks passed. Artifact has 35 files across seven product trees.
Merged main 7b04df8425cf277c339042c06bea1faf42e43e39 retains the tested tree.
No provider operation occurred. Unsupported-getter behavior on old workerd is
explicit evidence for doing the actual current-runtime experiment, not a waiver.

The isolated experiment workflow admits only a fully successful exact-main source
run and its fixed artifact ID, verifies every original compiled byte, and removes
the custom Rust build from temporary Wrangler configs. It deploys only absent
source-owned probe/caller scripts, tags their public run ownership, checks serving
versions, endpoint isolation and capture settings, invokes once without provider
credentials, collects the complete probe-scoped window, and removes receipt-owned
scripts with readback. Failed/unknown writes are not automatically resubmitted.
Public state receipt survives failure so a retained/replaced resource can be
inspected rather than guessed absent. No business deployment or send admission
is granted by this lane. Additional exact-main source/artifact admission is
stronger than diagnostic fixture replay, which intentionally admits failed whole
runs with a successful unchanged producer.

Collection preserves native span/parent/trace IDs and per-invocation marker paths,
not arbitrary raw provider data. Baseline must contain the path marker, four safe
source receipts map the four request cohorts, and four real custom children must
have observed native parents. Redacted marker leakage is an experimental outcome
rather than something to suppress or waive. This result cannot by itself prove
all Mail/Email/D1/R2 surfaces safe; those have separate content/metadata origins.
Actual controlled deployment/collection/cleanup is still pending.

## First deployed lifecycle result (2026-10-01)

Exact-main full source CI 36865492327 passed for 9d0a9599723a0887cc05a49376be54552252d64b.
Experiment 36866726157 consumed that checked artifact without a Rust rebuild,
created probe version 705c7bcb-553d-4993-90a8-ca70c19b28ff and caller version
5a8b33a3-071e-47d4-b290-617d1a48d5af. Probe ownership, trace enablement,
serving version and endpoint isolation passed. Caller ownership passed but its
capture readback failed before trigger. No synthetic runtime cases or native
records were collected: this is lifecycle evidence, not tracing acceptance.

Always-cleanup verified ownership, deleted caller then probe and observed both
GET settings as 404. Public receipt artifact 11164052040 records cleaned_at
2026-10-01T13:10:49.477215+00:00. There is no retained canary resource to retry or
inspect. No Mail resource, routing, identity, user account or sending was changed.

The original guard required explicit false for both optional signal objects and
the root flag, but did not persist their returned shape. The failure alone does
not establish which field differed. Repair records only reviewed boolean fields,
missing/type information before admission. The official Script Settings contract
defines logs/traces as optional: explicit root disable may omit these objects;
any returned signal enable or invalid shape is still refused. Actual returned
configuration and runtime acceptance remain to be verified on the next admitted
experiment. Do not attribute this failure to token permissions or native Rust API.

Reference: https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/get/
