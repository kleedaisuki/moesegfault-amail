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
The deployed capture state consequently remains **UNVERIFIED**, not established
unsafe and not established safe.

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
documented contract. Availability for this account is still untested.

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
