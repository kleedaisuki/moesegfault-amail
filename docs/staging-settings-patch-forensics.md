# Staging settings PATCH: response contract and bounded audit discriminator

Investigated 2026-10-01; preflight revision `fbbce73` reported by parent,
with current helper source inspected at `82c9af1`. Scope: public documentation
and local source reading only. No private account query, mutation, test, build,
or deployment was performed.

## Answer

The helper's HTTP-200 / `success=true` / object-`result` requirement matches
the published successful PATCH example. No documented alternative empty-204
success, Issues-false-to-omission normalization, or settings propagation deadline
was found. Thus neither loosening response validation nor treating missing
Issues as false is justified by the retrieved contract.

The failed settings run `36742914068` (2026-09-30 16:16:01–04 UTC) reports only
aggregate UNVERIFIED. The later read-only preflight `36748417146` passing all
normalized pre-correction phases does not reconstruct that historical execution.
Likewise missing Issues after the attempt does not establish whether PATCH was
sent, accepted, rejected, or never reached. These live facts are reused from the
parent, not independently re-queried.

## Contracts examined

| Boundary | Published contract / source observation | Consequence |
| --- | --- | --- |
| PATCH `/accounts/{account}/workers/scripts/{name}/script-settings` | JSON script-level operation; requires Workers Scripts Write. Its successful example is HTTP 200 with `success=true` and a ScriptSetting object in `result`; Issues is an optional object containing optional enabled. | `apply_staging_capture_off.py::request_result` has no demonstrated success-shape defect. An API success is still not a readback attestation. |
| Current Worker GET `/accounts/{account}/workers/workers/{name}` | Current observability Issues and its enabled member are optional. | Omission is schema-permitted but its Boolean meaning is unspecified; preview observability is a separate field and cannot substitute. |
| Audit Logs v2 GET `/accounts/{account}/logs/audit` | Requires Account Settings Read or Write, independently of Workers Scripts permissions. Time bounds, limit and cursor are documented. Raw request method/URI/status and action result are available but optional. | An existing deployment token may be unable to query audit history. A denied audit read is not evidence about PATCH. |

Primary references retrieved 2026-10-01:
[PATCH API](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/edit/),
[current Worker GET](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/get/),
[Audit Logs v2 API](https://developers.cloudflare.com/api/resources/accounts/subresources/logs/subresources/audit/methods/list/).

The [Audit Logs v2 overview](https://developers.cloudflare.com/fundamentals/account/account-security/audit-logs/)
describes automatic user API/dashboard action capture, approximately 95% product
coverage, and create/update/delete capture. It does not name a script-settings
event code or guarantee delivery latency for this endpoint. Therefore a positive
exact-path event is useful; no matching event cannot prove no request occurred.
Do not assume Workers Issues telemetry and account audit history are the same
product or privacy boundary.

## Proposed diagnostic, not executed

One reviewed hosted, read-only job can obtain historical evidence without another
PATCH. Use one GET with immutable bounds `since=2026-09-30T16:16:00Z`,
`before=2026-09-30T16:16:06Z`, `limit=100`, `direction=asc`. This deliberately
covers the complete reported correction step rather than an invented request
timestamp. Do not query today's preflight interval or widen the window on failure.

Select records privately by exact `raw.method == PATCH`, and exact `raw.uri`
equal to `/accounts/{validated account}/workers/scripts/amail-mail-staging/script-settings`.
No substring matching, action-description guess, product-name guess, or actor
email filter is necessary. The current reference and Python SDK expose several
filter objects only with `not`; do not invent equality syntax. Narrow time bounds
plus local exact matching avoid that ambiguity.

Require HTTPS fixed host, no redirects/retries, finite timeout and byte cap,
HTTP 200, typed provider envelope/list, and record cap. Never dump rows, response
bodies, exceptions, URI, account/actor/token IDs, emails, IPs, request/response
payloads, or cursor. Keep any cursor in memory only. A nonempty cursor, malformed
record, oversized response or exceeded cap makes completeness UNVERIFIED; stop
rather than silently treating the first page as exhaustive. No pagination is
needed for the first bounded discriminator.

Safe output can be fixed fields: `audit_read=ok|denied|transport|http_other|shape`,
`audit_complete=yes|unverified`, `patch_matches=zero|one|multiple`,
`patch_http=200|2xx_other|4xx|5xx|missing|mixed`, and
`patch_action=success|failure|missing|mixed`. Zero records must explicitly mean
`historical_patch=unresolved`, not `not_attempted`. Nonmatching rows stay private.

A unique exact-path success/200 event supports server receipt and reported success,
not successful client parsing, Issues state, or effective privacy. A failure event
supports a provider-reported failure for that request. Missing optional matching
fields remain unresolved. Only explicit positive effective state can permit the
settings attestation; historical evidence must not weaken that gate.

Exact path, method and time do not alone attribute a matching event to this
GitHub helper: an out-of-band same-path write could coincide. Preserve the
external settings freeze, and establish any actor/source correlation privately
before attributing the event. Never print actor, token or IP identifiers.

If the root authorizes implementation, add synthetic contracts and independent
review before hosted execution. Do not fetch audit resource-change history in
this first pass: it can contain full configuration, is unnecessary to distinguish
request receipt/status, and expands the privacy surface.
