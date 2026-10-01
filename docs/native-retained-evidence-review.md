# Native retained-record evidence review

Status: pre-run acceptance contract, not a deployed/API/privacy verdict.
Reviewed main: `6f63e1f`. Documentation-only ownership; no production edits,
provider operations, deployment, mail access, local runtime tests/build/install.
Updated: 2026-10-01.

## Scope and evidence hierarchy

This review connects `docs/native-cloudflare-tracing-canary.md`,
`docs/runtime-observability-foundation.md`, `workers/native-trace-canary/src/`,
and `infra/deploy/native_tracing_experiment.py`. Existing source/unit fixtures
prove their tested assumptions, not the current provider record representation.
A normal experiment must separate three conclusions:

1. **Source/API execution:** each controlled response reports the actual native
   operation completion and sampling.
2. **Retained native evidence:** independently observed native root/child,
   after-await attributes and fixed exception events agree with the case.
3. **Privacy outcome:** full pair-scoped retained records contain or omit each
   synthetic protected marker. A privacy failure can coexist with successful
   native API execution and useful causal evidence.

HTTP 404 with provider code 1042 on an absent hostname is not routing health.
Historical production/staging username mismatch is not an authentication defect
and is outside this review. No private-account investigation is authorized.

## Per-case acceptance matrix

Exactly one invocation of each row is required; preserve their public native
coordinates and source/run/version identity.

| Case | Observed service response | Safe report | Retained root | Retained manual child | Exception event |
| --- | --- | --- | --- | --- | --- |
| baseline.success | 200 | available=true, sampled=true, stage=complete | matching run/mode/kind; after_await=true | amail.canary.operation; kind=success; own native parent | no canary fixed exception |
| baseline.failure | 500 | same completion facts | matching run/mode/kind; after_await=true | same child name; kind=failure; own native parent | fixed canary exception on this child |
| redacted.success | 200 | same completion facts | same case attributes plus actual replacement outcome | same child name; kind=success; own native parent | no canary fixed exception |
| redacted.failure | 500 | same completion facts | same case attributes plus actual replacement outcome | same child name; kind=failure; own native parent | fixed canary exception on this child |

The safe report must have the exact run nonce, and its case tuple must be unique
across the four responses. This is already checked by `trigger()`. Native evidence
must be linked to the same request/case, not inferred from the aggregate count.
A fixed-failure response is intentionally constructed, not an unhandled exception
or Rust panic. Neither an ERROR span status nor `cloudflare.outcome=exception`
is implied by recording the exception and returning HTTP 500. Distinguish actual
HTTP status evidence from invocation-outcome metadata.

### Native context and lifecycle

- `startSpan` does not make its child active. After the real asynchronous delay,
  the `getActiveSpan()` annotation should be on the original invocation root,
  not on `amail.canary.operation`. Require retained `amail.canary.after_await`
  to be boolean true on the correct observed root; a string `"true"`, a safe
  console report, or the presence of any active span is not equivalent evidence.
- Root `amail.canary.run`, `.mode`, `.kind` must agree with the safe report.
  Child `.kind` must agree independently. Preserve IDs unchanged. Require the
  child's nonempty `parentSpanId` to name a native parent in the same invocation
  and same `traceId`, and reject self-parentage. Verify the observed parent is
  the annotated invocation root, not merely an arbitrary same-trace span.
- All four requests deliberately receive the **same** input trace ID (the run
  nonce) and input parent ID. Do not require four distinct trace IDs, or equate
  a shared trace ID with one invocation. Invocation identity remains essential.
  Do not require the resulting trace ID to equal the input nonce without actual
  platform propagation evidence; record the relationship instead of inventing it.
- Source explicitly ends the manual child before constructing the report. Native
  child retention and usable native end/timing evidence establish completion;
  returned API calls alone do not. Root completion is owned by the runtime.

### Fixed exception retention

For each failure child, independently observe the event containing the fixed
code `SYNTHETIC_FAILURE`, name `CanaryFailure`, and message
`Fixed infrastructure canary failure`, plus its native event timestamp when the
actual returned view exposes it. No stack is supplied. A known fixed message is
synthetic evidence, not arbitrary exception prose. Require the same child/case
link, not a global string match in the safe response or another record.
Success children must not contain this canary exception. Harmless extra platform
metadata is not grounds for rejection. If the first view does not expose exception
events, classify this dimension as unverified; do not guess where they are stored
or treat a missing wrapper as evidence that the runtime ignored `recordException`.

### Root replacement and whole-record privacy

The redacted root attempts exactly these replacements:

| Attribute | Intended retained value |
| --- | --- |
| url.full | https://synthetic.invalid/probe |
| url.path | /probe |
| url.query | empty string |
| user_agent.original | amail-native-canary |

Report actual retained value/absence/type, with attribute location and native root
ID. Attribute omission alone does not prove successful overwrite; compare baseline
visibility. Do not infer that overwriting one root eliminates other automatic
request/log/exception copies. Search the complete scoped retained record trees,
including keys and bounded decoded JSON strings, for each path/query/header/body
marker. Retain marker **locations**, not raw request payloads.

Both baseline cases must positively establish the path marker. For every other
marker, disclose baseline visibility separately: absent in both policies means
"not observed in this collection," not "root replacement removed it." Body
content is never consumed by the probe; a missing body marker is a bounded
non-observation, not evidence of a general body-redaction mechanism. Any marker
in a redacted case is a measured retained leakage outcome. An unassigned marker
record must not be silently excluded from a clean per-case verdict.

## Existing collector limitations and coherent remedy

At reviewed source, `summarize()` preserves native coordinates only when an
individual event's `$metadata.spanId` exists. It discards span attributes and
exception events. Thus current `available=true` and its summary cannot establish
after-await annotation retention, exact replacement retention, or fixed exception
retention. This is a concrete evidence gap, not proof of runtime malfunction.
The official query contract distinguishes views and describes `events` as matching
log lines with metadata; events are not guaranteed to enumerate all native spans.

Smallest useful next step after the root-owned normal run:

1. Inspect **only the isolated pair's** actual query shape; preserve safe schema
   keys, scalar types, reviewed synthetic facts, public causal coordinates and
   scope/count/view facts. Do not dump arbitrary provider records.
2. Identify the actual native span/attribute/event representation and the view
   that provides it. Add a narrow typed extractor only for this observed shape.
   No generic recursively guessed `attributes`/`spans`/`events` wrapper framework.
3. Join native facts to each case via actual request/causal identifiers; retain
   unassigned-record counts and marker locations. Do not silently derive case
   from a redacted URL that intentionally no longer names the case.
4. Collect to the actual per-case evidence predicate within a bounded ingestion
   deadline. The current global `>=8 spans` threshold can be reached while one
   case's root/child is still missing. Incomplete eventual ingestion should keep
   waiting within that bound; contradictory shape/foreign records remain refusal.
5. Persist the bounded summary and distinct verdicts before validation raises,
   so a failed acceptance does not erase the safe discriminator. Preserve existing
   pair isolation, no-caller-record check, no POST retry and ownership cleanup.

Do not add arbitrary sleeps, change compatibility flags, loosen scope/count echo,
recreate Workers or broaden mail capture to obtain evidence. A count below the
limit and exact echo establish query admission, not universal ingestion completion.

## Focused hosted regression contracts (after actual shape is known)

| Controlled fixture mutation | Expected behavior |
| --- | --- |
| complete four-case actual-shape fixture | all native dimensions verified; independent privacy outcome |
| drop after-await attribute or change true to string | retained context unverified/rejected, despite available=true |
| place after-await only on child | root-context proof fails |
| move fixed exception to other case/parent, or remove its fixed code | corresponding failure retention fails |
| add canary exception to success child | success/failure discrimination fails |
| same trace ID for four requests | accepted when invocation links and parentage are correct |
| parent exists only in another request, or self-parent | native causality fails |
| redacted replacement survives but request/log marker remains | API/context verified, privacy outcome negative |
| no baseline query/header/body marker | no claim of elimination for that marker origin |
| marker record has no case link | no clean per-case privacy verdict from silently dropping it |
| first response partial; later response complete | bounded collector waits; no retrigger or fixed extra delay |
| event view logs only | actual native extraction remains unverified; no fabricated span shape |

No local tests have been executed; these are recommended contracts for the parent
implementation owner's hosted tests, not a claim of verification.

## Primary external evidence

Retrieved 2026-10-01; facts concern the current native API and distinct query
surfaces, not a universal privacy guarantee.

- [Cloudflare custom spans](https://developers.cloudflare.com/workers/observability/traces/custom-spans/): async-context ownership, sampling, manual completion and exception events.
- [Cloudflare spans and attributes](https://developers.cloudflare.com/workers/observability/traces/spans-and-attributes/): automatic HTTP and dependency attribute origins.
- [Cloudflare telemetry query API](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/): query/view and event metadata contract.
- [Cloudflare Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/): invocation-owned state and explicit asynchronous lifetimes.

No academic mechanism or general tracing framework is needed to close this bounded
acceptance gap. Production practice here is to preserve native causal identities,
inspect the actual retention surface, and separate execution from observability
and privacy claims.

## Actual admitted normal run: no native evidence reached

Root dispatched **one** run `36884872446` at exact main
`6f63e1f559bc2d0a5c9d27c40294349fcf77dde1`, consuming successful full source CI
`36883747018` and checked build artifact `11172022967`. Reviewed safe receipt:
`.temp/native-tracing-retained-evidence/.temp/native-observation/run-36884872446/experiment.json`,
public receipt artifact `11174410747`.

- Both owned deployments passed capture/serving/isolation readbacks. Probe version
  `ff5ff33e-63bb-4ee6-b02b-c2edcf1dcba6`; caller version
  `b9d576c9-bd49-4e8f-a050-f9f0f4bbeaa7`.
- Fixed self-identified compatibility client POST returned **HTTP 404 / code 1042**,
  text/plain, 17 bytes, CF-Ray `a43c844c1c628c81-EWR`, no challenge indicator.
  This was not the source JSON aggregate. No case receipts were obtained.
- Collection was skipped. Therefore there is **no observed native provider
  representation**, no native API/context/error acceptance, and no privacy outcome
  from this run. Collector limitations above remain source-level evidence gaps,
  not a diagnosis of this failed trigger.
- Root verified deletion/absence of both owned scripts; receipt records cleanup
  `2026-10-01T15:31:53.852080+00:00`. The reviewed receipt has no retained resource
  to invoke again. No additional dispatch or provider operation by this reviewer.

Do not repeat the same admitted deployment to reinterpret 1042 as a healthy 404.
A transport change is a new reviewed experiment, not a retry of uncertain runtime
execution, and must preserve original compiled-product admission where applicable.

## Finite alternative trigger choices (design review, not authorization)

The public trigger is the failed boundary. The existing caller-to-private-probe
HTTP service binding is already the right separation; official documentation
supports manually constructed requests with fully qualified URLs. Do not replace
it with business forwarding or expose the private probe.

| Alternative | Benefit | New obligation / limitation | Assessment |
| --- | --- | --- | --- |
| Dedicated absent hostname on an owned zone, caller Custom Domain only | preserves the fetch-based product and returned four-case aggregate; removes reliance on shared workers.dev hostname | prove hostname/domain/DNS ownership and absence, no overlapping existing route; admission and cleanup for new zone resources; endpoint can still be denied | smaller source change; prefer if root already has authorized isolated hostname and lifecycle capability |
| Private scheduled caller, no public endpoint | avoids public HTTP admission entirely; private probe still receives controlled HTTP requests | adds scheduled Rust handler and a new verified product build; UTC execution window and retry/duplicate policy; caller response receipts have no synchronous external recipient | use only when avoiding public exposure matters enough to justify scheduling and receipt redesign |

A Custom Domain is not just a string replacement: Cloudflare creates DNS and a
certificate. Its current documentation explicitly says deleting the Custom Domain
does **not** automatically delete the associated Advanced Certificate. Receipt and
cleanup must therefore account for the domain, DNS ownership/readback and residual
certificate, or explicitly classify a retained owned certificate; no wildcard or
existing Mail/Identity hostname should be borrowed. Do not weaken WAF or add auth
capabilities merely to make the experiment reachable. Exact custom-domain matching
still permits an earlier zone route to intercept requests, so route overlap is a
preflight concern, not an inferred guarantee of direct reachability.

Cron is periodic, not a one-shot execution primitive. Cloudflare documents up to
15-minute propagation for additions, updates and deletion. A bounded source-owned
scheduled-time gate limits which invocation may call the probe but does not by
itself prove exactly-once delivery. Keep duplicate invocations visible/refused or
accounted for; do not fake uniqueness with isolate-global state. A four-case safe
completion receipt must be returned through an independently reviewed retained
synthetic channel because there is no external POST response. That changes the
current requirement that the caller retains zero records if the channel is caller
console logging; make that change explicit rather than silently waiving it. Do not
assume `/cdn-cgi/local/scheduled` is a deployed Cloudflare trigger endpoint: the
reference documents it only for local development, which is not current-runtime
acceptance. No scheduled option is presently implemented or admitted.

Primary references retrieved 2026-10-01:

- [Custom Domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/): domain matching, automatic DNS/certificate creation and residual certificate cleanup.
- [Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/): scheduled handler, UTC schedules and up-to-15-minute propagation.
- [HTTP service bindings](https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/http/): private bound requests and fully qualified constructed URLs.

Recommendation: choose one alternative on actual lifecycle authority, not a broad
transport matrix. Preserve the per-case retained evidence contract above. Do not
build a guessed native-record parser while no native record shape has been observed.
