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

## Disabled settings evidence and bounded artifact reuse

Run 36868563346 used fully successful exact-main CI 36867766344 for
source dcc4eed6b2dd27120940d79484ae7d9ddc0cb051. Probe capture readback was
three explicit true booleans. The freshly deployed disabled caller returned no
object (`parent_NoneType` at the root), not the three false booleans required by
the guard. Both source-owned scripts were again deleted with absence readback;
receipt cleaned_at is 2026-10-01T13:25:57.619782+00:00. No trigger occurred.
Previous diagnostics did not distinguish a missing key from explicit null;
next readback records that distinction. This is a concrete provider representation
mismatch, not native API failure. The official Settings shape makes the entire
observability object optional. Admission recognizes the absent/null disabled
representation only for this freshly source-owned caller; it still rejects
explicit enabled/invalid overrides and requires exact serving version and endpoint
readback. Collection queries both fixed scripts and refuses any caller record,
rather than equating a normalized setting with an observed no-capture verdict.

Repeating all Rust/native builds for orchestration-only changes adds no new
compiled-product evidence. The experiment lane now separates two proofs:
(1) fully successful original-main source CI and fixed original compiled artifact;
(2) mandatory hosted current-source infrastructure checks in the experiment
workflow before provider capabilities, plus ancestor and diff
proof allowing only enumerated experiment orchestration files and Markdown docs.
Rust/lockfile/compiler/config/native fixtures/artifact helper/CI workflow and
unknown files cannot borrow old evidence. No second checks-run input or manual Secret ceremony is needed.
Original compiler/source/run/hash checks
remain intact and receipt keeps both build and orchestration identities. Fetch
history is bounded to 100 commits; missing ancestry fails closed. This reuse
policy admits only this infrastructure experiment, never Mail sending or release.

References:
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/get/
- https://github.com/cloudflare/workers-sdk/blob/wrangler%404.142.0/packages/deploy-helpers/src/deploy/helpers/create-worker-upload-form.ts

## Executed unchanged-build admission and public-trigger boundary

Experiment 36870838693 (13:43:46–13:44:36 UTC, 50 seconds total) executed the
new lane without waiting for another full original-main build. It passed current
hosted infrastructure tests, ancestry/narrow-input admission, original artifact
11164304271 hash/source/compiler/run restoration (compiled source dcc4eed6,
full CI 36867766344), and pair deployment/version/isolation readback under current
orchestration source e9a56069898f74be7cda15ad4cc9ca42f41487c4. Caller observability
was specifically a missing key; probe flags were three true booleans. Both
identities are in its public receipt. This is real reuse evidence, not a cache
inference or general release admission.

The first public POST returned HTTP 403 before any valid case receipt. This does
not prove the Rust native API failed: caller source returns a JSON aggregate,
not this status. Native trace collection remained skipped. No raw challenge body
or authentication data was captured; the old trigger also omitted useful status/
CF-Ray/content-type boundary facts. A bounded repair persists those operational
facts, distinguishes a bare Forbidden reply and managed challenge, and always
records the request time window even on failure. It does not retry the POST or
attribute the refusal to a token/WAF/propagation issue without evidence.

Source-owned caller version ec89d865-d235-4a09-9c51-7e962ca1438d and probe version
6b6ef8ac-4779-46a1-a6e4-5011da759a90 were deleted; receipt cleaned_at is
2026-10-01T13:44:32.718360+00:00 and both absence GETs were verified. No Mail data,
identity, route or sending state changed. Native API and retention acceptance
remain pending.
