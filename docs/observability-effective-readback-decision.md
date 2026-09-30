# Effective Worker observability readback: evidence and next discriminator

Investigated 2026-09-30. Status: architecture/evidence only, **not a deployed
containment attestation**. No private Cloudflare API call, Mail request, setting
mutation, local test/build, deployment, or push was performed here.

## Known observation and unresolved question

The parent reports read-only run `36730461386` observed stable 100% serving
version `c3f6401a-1e84-4f51-91df-ae77d90683e9`, with `/settings.observability`
missing and `/script-settings.observability` categorized `other` (not an object).
Logpush was false; tail-consumer categories were false/other. These are attributed
run observations, not independently re-queried by this investigation. The old
`other` category cannot distinguish JSON null, Boolean, number, string, or array.
That run alone left the deployed capture state **UNVERIFIED**, not established
unsafe and not established safe. The later explicit Worker readback below changes
the next action without retroactively upgrading that earlier diagnostic.

Reuse [the pinned Wrangler investigation](wrangler-observability-readback-research.md):
4.142.0 sends explicit false values unchanged, treats observability as
non-versioned, and can downgrade a settings PATCH failure to a warning. Version
upload/deployment success and absence of a recognized warning cannot prove that
the effective settings changed. Never substitute source intent or a healthy API
response for this missing evidence.

## A more informative official read-only endpoint

The current official [Get Worker API](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/get/)
documents:

```text
GET /accounts/{account_id}/workers/workers/{worker_id}
worker_id: either the immutable Worker ID or its name
```

It is under **Workers Beta** in the SDK/docs, but the REST path has no `/beta`
segment. Use the literal reviewed name `amail-mail-staging`; do not list all
Workers, discover unrelated resources, or guess a service/environment endpoint.
This GET uses the existing Workers Scripts Read/Write or Workers Tail Read
permission alternatives. It returns one Worker resource in `result`, not a page;
no pagination, list fallback, extra header, or new credential is needed by its
documented contract. The parent subsequently reports availability/name matching
in run `36736823997`; this investigation did not repeat the private call.

The official Python SDK at immutable revision
[`c9dd8956de93575640e06ea28e802951175099a0`](https://github.com/cloudflare/cloudflare-python/blob/c9dd8956de93575640e06ea28e802951175099a0/src/cloudflare/resources/workers/beta/workers/workers.py#L414)
uses a normal GET and unwraps `result` into the
[`Worker` model](https://github.com/cloudflare/cloudflare-python/blob/c9dd8956de93575640e06ea28e802951175099a0/src/cloudflare/types/workers/beta/worker.py).
That model makes top-level `id`, `name`, `observability`, `logpush`,
`tail_consumers`, and lifecycle timestamps required. The `observability` value is
an object, `logpush` a Boolean, and `tail_consumers` a list. However, observability
child objects and their Boolean fields are **optional**. A required top-level
object therefore does not guarantee enough child values for privacy acceptance.
Keep raw JSON distinctions: model defaults of `None` must not collapse absent
fields and explicit JSON null in the discriminator.

This is the current **Worker-level** resource, not a version-detail endpoint or
an immutable deployed-version configuration snapshot. It has no selected version
parameter. `deployed_on` is the time of the most recent deployment (or null if
never deployed), not the serving version ID. `updated_on` is a resource timestamp,
not an atomic settings/version lock. `previews_base_config.observability` applies
to newly created previews and must **never** be substituted for top-level
observability. Resource references/subdomain URLs are unrelated to this decision
and can disclose identifiers; do not print or persist them.

| Endpoint | What it identifies | Evidence limit |
| --- | --- | --- |
| `/scripts/{name}/deployments` | Serving version percentages and deployment identity | Needed to reject split/unexpected traffic; not effective observability. |
| `/scripts/{name}/versions/{uuid}` | Named uploaded version resources/runtime | Current documented [version response](https://github.com/cloudflare/cloudflare-python/blob/c9dd8956de93575640e06ea28e802951175099a0/src/cloudflare/types/workers/scripts/version_get_response.py) has no observability member. |
| `/scripts/{name}/settings` | Script/version metadata/config | Observability is optional; omission is not documented as off. |
| `/scripts/{name}/script-settings` | Non-versioned settings | Optional observability object; no published missing/null-equals-off contract. |
| `/workers/{name}` (under `/accounts/{account}/workers`) | Current Worker-level settings | Required observability object, optional children; potential positive evidence, not guaranteed. |

## Minimal next diagnostic: five GETs, no safety inference

Extend the existing
[containment discriminator](staging-containment-readback-discriminator.md), rather
than adding a second generic probe. Ordered requests:

1. Existing latest deployment GET: require exactly the supplied expected version
   at 100%, preserving its deployment/version pair privately.
2. Existing `/settings` GET.
3. Existing `/script-settings` GET.
4. New exact-name Worker GET above.
5. Existing latest deployment GET: require the identical pair. On change,
   discard collected categories and fail; do not print them as stable readback.

Bound response bytes/time and require HTTP success, a successful provider
envelope and object `result` exactly as existing safe readers do. The new
resource additionally requires `name == amail-mail-staging` and a nonempty typed
immutable `id` kept private; fixed `worker_name=match/mismatch` is sufficient.
Do not emit arbitrary response keys, IDs, lifecycle timestamps, nested unknown
values, exception strings, or provider error bodies. A 403/404/malformed response
is `unavailable`, not an absent Worker or disabled logging assertion.

Add fixed type bins for observability/logs/traces at each endpoint:
`missing`, `null`, `object`, `boolean`, `number`, `string`, `array`, `other`.
For reviewed Boolean fields preserve `missing`, `null`, `false`, `true`,
`other`; test Boolean identity before numeric checks. Preserve old fixed outputs
where compatibility matters. Tail shape should distinguish missing/null/list,
with empty/populated only for a typed list. Destination shape should distinguish
missing/null/list, with empty/Cloudflare-only/external/malformed classification
only after validating every element. Include a fixed `issues.enabled` category
if present in the current schema, without inventing missing-field defaults.

The top-level result remains `stable100`/`UNVERIFIED`: **none of these bins is a
containment pass**. Only a later independently reviewed policy can turn explicit
capture-off values into acceptance. The first diagnostic is useful even if Beta
GET is unavailable, provided its availability is fixed-category and the existing
deployment bracket still verifies; that outcome must not be reported as a full
successful effective-settings readback.

## Acceptance and next action from the discriminator

1. **Explicit safe values available:** if Worker-level readback gives literal
   false capture flags (top-level, Logs, native traces), Logpush false and a typed
   empty tail list, with no conflicting enabled/export settings, prepare an
   endpoint-specific API containment checker. Review the exact returned shape
   before changing production gates. Disabled capture makes sampling,
   persistence defaults and URL-redaction settings inert; they must not be
   mistaken for substitutes for disabled capture. Retain strict enabled-sink
   checks separately. Do not automatically accept missing child capture fields,
   enabled real-time Issues, unknown exports, malformed containers, or a conflict
   between endpoints. A missing legacy representation alongside explicit safe
   Worker values can be recorded as unsupported legacy readback, not silently
   rewritten to a fabricated false object.
2. **Explicit unsafe values:** prepare a narrowly reviewed settings-only
   correction using the official non-versioned PATCH with the existing reviewed
   disabled configuration. Fail on PATCH error rather than warning and read the
   resource back before authorizing rollout. Preserve unrelated bindings/routes
   and serving code; never enable logging to learn its disabled representation.
3. **All representations missing/null/ambiguous:** no published contract found
   establishes that these values mean off. Keep the gate UNVERIFIED. A direct
   PATCH may improve intent evidence but a successful response without explicit
   effective readback still does not resolve the state. Provider clarification or
   a separately reviewed empirical non-retention experiment is needed; blind
   redeployment/repetition does not add discriminating evidence.

An unchanged serving deployment is necessary but insufficient to prevent a
concurrent **non-versioned** settings change. Maintain the operator deployment/
settings freeze for these bounded checks. For a later retained-data canary,
compare the reviewed current capture settings before and after as well as serving
identity, and state that these are observations at a bracketed interval, not an
atomic transaction or future guarantee.

## Follow-up: explicit disabled capture versus dormant options

The parent reports read-only run `36736823997` held the same expected version at
100%, resolved the exact Worker name with a valid typed ID, and read these current
Worker settings:

| Field | Attributed observed value | Role in the proposed gate |
| --- | --- | --- |
| `observability.enabled` | false | Explicit general capture switch, required false. |
| `observability.logs.enabled` | false | Explicit Logs capture switch, required false independently. |
| `observability.traces.enabled` | false | Explicit native-trace capture switch, required false independently. |
| `logpush` | false | Independent export switch, required false. |
| `tail_consumers` | empty list | Independent export consumers, require typed empty list. |
| `logs.invocation_logs` | true | Dormant log-selection option while Logs capture is disabled. |
| `logs.persist` | true | Dormant storage choice while Logs capture is disabled. |
| `redact_query_string` | false | Dormant transformation while Logs and traces are disabled. |
| sampling fields | one | Dormant selection rates while corresponding capture is disabled. |

The legacy reads reported `/settings.observability` missing and
`/script-settings.observability` explicitly null. These remain unsupported legacy
representations, **not** Boolean false. This new observation justifies implementing
and independently reviewing an effective capture-off gate; no such checker or
retained-record test was executed by this investigation.

### What the current official semantics support

The [Worker GET schema](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/get/)
describes Logs/traces `enabled` as their enable switches and `persist` as
persistence, not a second enable switch.
[Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)
includes invocation records, custom messages and failures in the same logging
product, and requires enabling observability to write its retained logs.
[OTel export configuration](https://developers.cloudflare.com/workers/observability/exporting-opentelemetry-data/)
uses enabled Logs/traces and distinguishes persistence from export: turning
`persist` off can still export enabled telemetry, so persistence is not a safe
replacement for disabled capture.
[Tracing documentation](https://developers.cloudflare.com/workers/observability/traces/)
conditions its sampling description on tracing being enabled. Query-string
redaction transforms produced records; it cannot produce a record by itself.

**Contract-based inference:** with all three explicit capture switches false,
`invocation_logs=true`, `persist=true`, sampling one and redaction false describe
dormant configuration, not independent re-enablement. This inference is grounded
in the documented roles of those fields; the private provider/runtime capture
implementation was not inspected. Require the empirical test below to check
actual behavior rather than declaring a universal runtime guarantee.

Pinned Wrangler
[`normalizeObservability`](https://github.com/cloudflare/workers-sdk/blob/f96458cefb7eaffc611f38f59f41d573dfa8b112/packages/deploy-helpers/src/deploy/helpers/config-diffs.ts#L277-L295)
corroborates this interpretation: its comparison defaults intentionally combine
false top-level/Logs enablement with true invocation/persistence, sampling one,
and redaction false. Do **not** run this normalizer on provider data to invent
missing false values; it is client-side comparison logic, not authoritative
server state or an absent/null-equals-off contract.

### Exact proposed endpoint-specific contract

Keep local reviewed source intent and the enabled private-sink policy separate
from effective disabled-API readback. Do not alter the strict sink predicate or
fill provider objects from the local TOML. A future API checker should require:

1. Bounded successful envelopes/object results for all three current settings
   endpoints, bracketed by the identical expected single-100% deployment. No
   endpoint/API failure may be silently skipped. Exact Worker name/typed valid
   immutable ID and source/version provenance remain required. The known
   resource supplies **positive** safety evidence; legacy reads only check
   contradictions and supported shape.
2. In the Worker resource, literal Boolean false for `observability.enabled`,
   `logs.enabled`, `traces.enabled`, and `logpush`; object containers for
   observability, Logs and traces; and an actual empty `tail_consumers` list.
   Missing/null capture flags, numeric zero, empty object, malformed values or
   a missing resource do not satisfy any requirement. Never use preview settings.
3. Accept true or false typed dormant Boolean options `invocation_logs`,
   `persist`, and redaction. Their absent/null optional representation does not
   authorize capture and is not rewritten to false. If present non-null with an
   invalid type, reject as schema drift. Likewise optional sampling must, when
   present non-null, be a finite non-Boolean number in [0,1]; no fixed sampling
   value is needed for disabled capture. None can compensate for an enabled or
   unverified capture switch.
4. Preserve the conservative no-unreviewed-export rule: present non-null
   Logs/trace destinations must be typed string lists containing only the
   reviewed Cloudflare destination or no entries; external strings or malformed
   lists reject. Missing/null destinations are not declared an empty list;
   positive disabled capture is the safety premise, not guessed list defaults.
   Logpush/tails remain independent and need the explicit positive evidence in
   item 2. If `streaming_tail_consumers` appears in any settings result, require
   a typed empty list; absence/null is not a statement about its emptiness or
   universal live-tail access. This checker does not start a live-tail session.
5. Legacy missing/null observability may be recorded as unsupported, provided
   the positive Worker predicate succeeds. A legacy observability value of any
   other non-object type rejects. For a legacy object, any present non-null
   capture flag must be literal false; true/malformed values conflict and reject.
   Optional nested objects may be absent/null, but a non-null malformed parent
   rejects. Apply the same dormant-field type/export rules to present values.
   Legacy logpush true or malformed non-null, or a populated/malformed non-null
   tail list, rejects; missing/null cannot establish off, but does not contradict
   the explicit Worker proof. Do not require dormant options to be equal between
   endpoints: normalization of an inactive option is not a capture-state conflict.
6. Emit only fixed labels, distinguishing `effective_capture_off` from full
   `privacy_verified`; any unsupported/conflicting positive premise stays
   UNVERIFIED. Settings/version checks establish current documented capture-off
   configuration at an observed bracket, not eradication of historical records.

For a canary/rollout interval, read effective settings and serving identity before
and after, comparing the Worker ID and capture/export policy projection (not
arbitrary full resource fields). This detects observed drift, not all possible
A-to-B-to-A concurrent changes; keep the settings/deployment freeze. The existing
immutable successful containment-run provenance requirement must be reviewed and
updated explicitly to use this new positive endpoint predicate; a successful
diagnostic run is not a successful deployment run.

### Scope guard: Issues is not an invocation-log option

Current [Workers Issues](https://developers.cloudflare.com/workers/observability/issues/)
has its own `observability.issues.enabled` switch and records failures including
5xx/error logs. The docs do not establish that Logs-off makes Issues dormant.
Therefore reject explicit Issues enablement or malformed non-null Issues data;
do not label absent/null `issues` or `issues.enabled` as disabled. A narrow
**Logs/native-traces capture-off** predicate can leave missing/null Issues
explicitly outside its verified scope. An assertion that **all API observability
is disabled**, or a rollout prerequisite with that broader meaning, additionally
requires positive explicit Issues-off evidence or separate authoritative provider
evidence. Documentation that a deployment omitting Issues turns it off supports
source intent, not replacement of effective readback by a fabricated false value.

This distinction avoids a false result in either direction: a dormant invocation
option must not indefinitely block a demonstrated Logs-off configuration, while
an independent monitoring product must not disappear from the claim merely
because it shares the `observability` namespace.

## Empirical non-retention is a separate, bounded claim

Do not let an empty Logs query resolve optional settings by assumption: it can
also mean a wrong service, inaccessible dataset, indexing delay or sampling.
After readback is resolved (or after a separately reviewed diagnostic exception
that does **not** authorize Queue rollout), a controlled canary can send only
synthetic requests and then require a complete exact-service/window retained
query with a positive query-path control.

Reuse the complete dry-query pagination, echoed scope, event-wrapper validation,
whole-record marker scan, delayed same-window requery and pin checks in
[the sink canary](staging-trace-sink-canary.md). A contemporaneous already-logging
reviewed **non-HTTP-context** control sink, or a securely retained known historic
synthetic event within retention, can demonstrate that the query channel returns
the exact expected evidence. An unrelated service merely appearing in Values
is not that control. Never switch API Logs back on for the control. Historical
control proves retrieval of old data, not contemporary ingestion health; expose
that limit if it is the only available control.

Require zero complete retained API rows in the pinned fresh window, not just
absence of marker matches. Cover authenticated and denied paths, capture IDs
privately, avoid mutation/send/mail content, and reject any record truncation or
incomplete cursor. Allow only the existing bounded indexing-delay policy, never
widen or silently restart the window. Success attests that synthetic interval,
not universal losslessness/privacy, future retention, Security Events, Logpush
destinations, or queued envelope privacy. This empirical evidence supplements
effective-settings evidence; it does not by itself satisfy the existing
immutable containment-run rollout contract.

## Source provenance

Public API/docs and SDK files were retrieved on 2026-09-30. SDK main was pinned
to `c9dd8956de93575640e06ea28e802951175099a0`; Workers SDK main was
`89061a40fb20157acf6c947034a74ece357992f0`. Published Wrangler latest was
4.145.0; deployment remains pinned to 4.142.0, whose immutable source is reused
above. Main also retains the unchanged-object serializer/non-versioned PATCH;
no suggestion to upgrade a deployed toolchain follows from this investigation.
The [official Workers Logs documentation](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)
and [version/deployment model](https://developers.cloudflare.com/workers/versions-and-deployments/)
support separate configuration/serving/runtime evidence, not a server
normalization guarantee. No external benchmark or log-leakage paper can attest
this account's effective setting; existing privacy research motivates the
whole-record check but is not used to override missing provider evidence.


## Full-boundary checker implementation (source only)

`crates/mail-worker/check_observability.py` now separates strict local/sink
configuration policy from effective Mail API readback. API verification reads
latest single-100 deployment, both legacy settings representations, and the
exact current Worker resource, then rechecks the identical deployment/version
pair. A supplied `AMAIL_EXPECTED_WORKER_VERSION` is additionally enforced.
`infra/deploy/pin_staging_mail.py` uses the same effective-resource policy while
retaining its own expected-version and exact-binding checks.

The full-boundary policy requires literal `false` for parent, Logs, native
traces **and Issues** capture, literal false Logpush, a typed empty tail list,
and no configured streaming-tail consumer. Missing/null legacy observability
is unsupported compatibility readback, not evidence of disabled capture; any
explicit legacy capture/export conflict rejects acceptance. Exact-name current
resource and nonempty bounded typed immutable identity are required; preview
configuration is never substituted. Optional inactive preferences may differ
from source, but malformed values and unreviewed observability members fail
closed. The enabled private Queue sink retains the unchanged stricter isolation
policy; no sink capability is relaxed by this API-specific change.

In particular, the live `36736823997` category `worker_issues_shape=missing`
does **not** pass this full-boundary gate, even when Logs/native traces are
explicitly disabled. This resolves the old endpoint mismatch without inventing
an Issues-off default or relabeling a narrower observation as rollout safety.
Positive Issues-off evidence or a separately reviewed equivalent empirical
boundary is still needed before containment acceptance.

Focused synthetic coverage adds current-resource identity/transport, inactive
preferences, required capture fields (including missing Issues), legacy
conflicts, export/malformed rejection, optional expected-version enforcement,
and deployment drift. Source AST and whitespace checks were performed only;
unit tests are reserved for hosted CI. No live API request, deployment, local
build/test, setting mutation, or push was performed by this implementation.
