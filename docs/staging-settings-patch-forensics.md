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

## Implemented bounded classifier (source only)

`infra/tests/staging_settings_patch_audit.py` implements the authorized
read-only discriminator. The existing `ci.yml` dispatch schema gains only
`target=staging-settings-patch-audit`, using its existing `confirm` input with
`READ_STAGING_CAPTURE_SETTINGS_PATCH_AUDIT`; no new workflow input or separate
default-branch workflow is required. The job is manual/development-branch-only,
uses staging Environment, requires first attempt, runs focused synthetic tests
without credentials, then supplies the project account/deployment credential
only to the final read-only step. It shares non-cancelable staging serialization.

The reader performs at most one GET to the fixed Audit Logs v2 account endpoint
with exactly the six-second bounds above, ascending direction and limit 100.
It rejects redirects, uses a 15-second timeout and 1 MiB body bound, never
retries, and never persists a response, cursor or raw exception. The classifier
does not fetch resource-change history, invoke any Mail request, mutate any
setting or emit a settings-v1/deployment marker.

Positive page completeness requires an explicit canonical string count matching
the bounded result length and an explicitly empty string cursor. Missing/null
cursor is not fabricated exhaustion; nonempty cursor, unknown pagination fields,
shape/count drift or more than 100 rows stays UNVERIFIED without continuation.
This conservative rule may reject a legitimate optional representation, but
the retrieved schema does not establish omission as positive exhaustion evidence.
It does not reinterpret incomplete pages as zero matches.

Rows must have typed known raw method/URI and an action timestamp strictly
inside the immutable query interval. Any present account identity must match
the requested account. Exact matching uses only the documented URI shape
`/accounts/{account}/workers/scripts/amail-mail-staging/script-settings` and
literal PATCH; no substring, URL decoding, path prefix/suffix, alternative realm
or guessed URI representation is admitted. Unknown/missing matching status or
action outcome denies classification. Actor and request/response payload fields
are neither used for attribution nor printed.

Output is six closed fields prefixed `staging_settings_patch_audit_`, plus a
`CLASSIFIED`/`UNVERIFIED` aggregate. HTTP outcomes are fixed named categories
`expected_success`, `other_success`, `client_error`, `server_error`, `other`
or `mixed`/`unverified`: no raw numeric status is printed. Match counts are
`zero`, `one`, `multiple` or `unverified`, never actual counts/record IDs.
Only one fully shaped matching record can produce a provider-reported outcome.
Zero, multiple, unknown, denied, transport or incomplete observations stay
UNVERIFIED; zero still explicitly means historical outcome unresolved, not
no PATCH attempt. CLASSIFIED is historical provider evidence, **not** helper
attribution, successful client parsing, present Issues-off or rollout approval.

`test_staging_settings_patch_audit.py` covers exact scope/request count, no
redirect/retry, byte/time bounds, URI near-misses, zero/multiple records,
missing/unknown fields, pagination/count/time/account drift, invalid statuses,
private output, first-attempt guards and credentials-after-tests wiring.
Only static AST/YAML and whitespace checks were performed locally. Independent
source review and hosted tests must pass before one historical audit dispatch.

Do not fetch audit resource-change history in this first pass: it can contain
full configuration, is unnecessary to distinguish request receipt/status, and
expands the privacy surface. Nothing in this implementation authorizes retrying
the historical mutation or loosening effective capture-off acceptance.

### Protocol-exception privacy correction

Independent review of `182535f` identified that Python `HTTPException` is not
covered by OSError/URLError: malformed status lines or truncated HTTP reads
could escape the fixed output boundary. The reader now normalizes that family
to `transport` with exception-context display suppressed. Focused synthetic
tests drive the real main/reader path through BadStatusLine during open and
IncompleteRead during bounded read, requiring exactly the seven fixed failure
lines, empty stderr and one request. No query, pagination, matching or acceptance
policy changed. These are source changes awaiting hosted execution and re-review,
not a claim that the exception occurred in any historical live run.

## First live audit result and second shape-only discriminator

The parent reports bounded audit run
[`36754040787`](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36754040787)
at source `b74130f` produced fixed `read=shape`, `complete=unverified` and
`historical=unresolved`. This was not an observed permission denial and does not
identify a PATCH outcome. The result was reused, not independently repeated.
`shape` can arise from a JSON/container/envelope discrepancy, a count/type
contract, or unsupported result-info representation; another identical outcome
classifier run would not discriminate those cases.

The approved next source slice is
`infra/tests/staging_settings_audit_shape.py`, invoked by existing `ci.yml`
`target=staging-settings-audit-shape` and
`confirm=READ_STAGING_CAPTURE_SETTINGS_AUDIT_SHAPE`. It retains the same literal
historical six-second window, account Audit v2 endpoint, ascending order and
100-row limit. There is still at most one GET, no retry, redirect, pagination,
expanded time range, Mail call, PATCH or persisted response.

A shared `read_audit_payload` transport now returns only the bounded parsed JSON
value so this diagnostic can distinguish envelope types. The original
`read_audit` wrapper retains its object guard and original outcome classifier's
strict envelope/string-count/cursor/row policy. Existing parser exception
normalization and original focused tests remain in the manual job alongside
the new shape contracts, all before credential-bearing execution.

All emitted keys are fixed source enums. Type bins are missing/null/object/array/
string/boolean/number/other, with mixed/no_rows for bounded row aggregates.
Predetermined envelope fields include success/errors/result/result_info and the
standard `messages` type only; unknown provider keys are reported merely as
`unknown`, never printed. The discriminator reports count representation and
relation to bounded rows, cursor representation/empty-versus-populated state,
and aggregated row/action/raw known-key/type bins. Selected action time/result
and raw method/URI/status fields are inspected for **type only**. Actor, ID,
timestamp, URI, method, status number, arbitrary names and payload values are
never emitted or used to match a historical request.

The conservative frame rejects oversized rows, unknown continuation/container
fields, mismatching/unusable count, nonempty/missing/null cursor, failed original
envelope intent and malformed/unknown row containers. Only safe bounded frame
observations can produce `SHAPE_DIAGNOSED`; rejected frames still show approved
type bins under `UNVERIFIED`, with no record inspection beyond the 100-row cap.
A numeric count can be reported as `integer_number` and compared privately to
the row length solely to expose the original **string-only** mismatch; this does
not change or satisfy original audit acceptance. Neither aggregate is audit
coverage, PATCH receipt, helper attribution, settings success or privacy proof.

Synthetic tests cover scalar/malformed envelopes, string versus numeric count,
unknown standard envelope shape, cursor/pagination/count drift, bounded mixed
row shapes, fixed private output, original object-policy preservation and real
HTTP parser failure normalization. Static AST/YAML/whitespace checks are the
only local verification; source review and hosted CI must precede one live
shape discriminator. No new live request is claimed here.
