# Independent review: deployed trace sink isolation gate

Reviewed: `0216c47`, 2026-09-30. Scope: the new sink isolation module,
observability integration, tests/docs and the imported serving/Queue inventory
helpers. No local tests/builds, live requests, deployment or push were performed.

**GO for hosted synthetic CI. NO-GO for live rollout acceptance at this revision:**
two necessary corrections below remain. A safe CI run can expose these contract
problems; passing the existing mocked happy path must not override them.

## Prioritized findings

### P1 — Account Queue exclusivity can pass an incomplete inventory

Location: `crates/mail-worker/check_trace_sink_isolation.py:133-160`, delegating
to `infra/deploy/ensure_trace_queues.py:inventory`.

The imported inventory helper validates `result` as a list, the current page and
`total_pages`, but does not validate `count`, `per_page`, `total_count`, stable
totals, or completeness against those totals. The new gate subsequently checks
only details of returned queues. Thus a successful but contradictory/incomplete
response can omit another Queue subscribed to this sink and still establish
"exclusive subscription".

Concrete source-derived negative case (not executed locally): return the valid
reviewed main and DLQ rows with result_info `{page:1, per_page:100, count:2,
total_count:3, total_pages:1}`. Return valid details for the two returned rows.
The helper stops after page one, and `queue_trigger_exact` returns true despite
the advertised third Queue never being examined. The test's own main/DLQ detail
fixtures suffice for this path. This violates the documented fail-closed
incomplete-readback contract; it is not evidence that the current account
actually has an extra subscription.

Remedy: strengthen the shared inventory helper, or use an equally strict Queue
inventory implementation, to require endpoint-specific coherent integral
counts/page sizes/totals, stable totals across pages, unique valid IDs/names,
bounded pages and exact final cardinality. Test the real helper rather than
patching `queues.inventory` to a complete list in every gate test. Include
missing/inconsistent counts, a changing total, omitted last row and duplicates.
Confidence: high (explicit executable control flow).

### P2 — Worker Domains incorrectly requires a paginated per-page-50 contract

Location: `check_trace_sink_isolation.py:45-73,96`.

The generic inventory routine sends `page=N&per_page=50` and requires all
pagination metadata, including exact per_page 50. Cloudflare's official Worker
Domains SDK treats this endpoint as `SyncSinglePage`; its public request schema
lists environment/hostname/service/zone_id/zone_name, not page/per_page. The API
reference makes result_info and its members optional. Therefore a legitimate
complete unpaginated result, or a default metadata response with per_page 20,
cannot pass this gate even when the sink has no custom domain. This is a
deployment/readback availability defect, not a false privacy approval.

Remedy: split endpoint-specific contracts. Read Worker Domains unfiltered as
the documented single-page array, bound/validate unique rows, and reject any
supplied metadata explicitly contradicting completeness. Keep Zones on its
documented paginated contract. Do not loosen all inventory checks to compensate.
Use official-shaped domain fixtures with absent metadata and coherent optional
metadata; assert the request does not invent pagination parameters. Confidence:
high about the contract mismatch, not a claim about an unqueried live response.

## Checks that are materially sound within this scope

- Explicit expected sink UUID and Queue/DLQ IDs prevent implicit latest-resource
  substitution. Before/after serving tuples must match and use a sole 100%
  deployment, rejecting split traffic.
- Exact version resource readback requires the Queue handler and empty bindings;
  no fallback to unversioned settings hides missing binding resources. Additional
  named handlers are rejected. The optional absence of named_handlers follows
  the API's optional field schema, not a claim that local Wrangler proves it.
- Both live settings views require the safe sink Logs boundary and reject
  native traces, tail/export/logpush paths. Workers.dev/previews and Cron are
  checked independently of source intent.
- Worker Routes are documented as a single-page/unpaginated array. Checking
  every readable account zone's bounded route array without pagination is
  appropriate; contradictory metadata and malformed/duplicate rows fail.
- Queue details check actual consumer cardinality and main/DLQ identity, finite
  reviewed settings and ownership. Wrong expected IDs and extra **returned**
  sink subscriptions fail; the missing guarantee is inventory completeness.
- Failure paths emit fixed summaries and do not print provider bodies. Account
  inventory remains limited by token visibility. This is explicitly disclosed;
  a token silently scoped to fewer zones cannot independently prove account-wide
  absence. Use an independently reviewed account-wide capability for acceptance.

No point-in-time settings check prevents a later operator mutation. The stable
serving-version check is useful provenance, not an atomic snapshot of all
Cloudflare resources or a lasting public-exposure guarantee.

## Remaining live gate

After corrections and hosted tests: use the exact reviewed serving version and
resource identities, verify resource ownership/private surfaces/readback, and
then perform the independent complete retained-record canary. This source gate
does not establish absence of platform-enriched URL/message markers, successful
safe event retention, or production/public-send readiness.

## Official evidence retrieved 2026-09-30

- [Worker Domains API](https://developers.cloudflare.com/api/resources/workers/subresources/domains/methods/list/) and [official Python SDK](https://github.com/cloudflare/cloudflare-python/blob/main/src/cloudflare/resources/workers/domains.py): single-page request/return contract; optional generic result metadata.
- [Zones API](https://developers.cloudflare.com/api/resources/zones/methods/list/) and [official SDK](https://github.com/cloudflare/cloudflare-python/blob/main/src/cloudflare/resources/zones/zones.py): actual page/per_page parameters and paginated Zone return.
- [Worker Routes API](https://developers.cloudflare.com/api/resources/workers/subresources/routes/methods/list/) and [official SDK](https://github.com/cloudflare/cloudflare-python/blob/main/src/cloudflare/resources/workers/routes.py): single-page Zone route inventory.
- [Queue inventory API](https://developers.cloudflare.com/api/resources/queues/methods/list/): explicit Queue result counts and pagination metadata, which must not be ignored when asserting completeness.
- [Version resource API](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/get/): compiled default/named handler and binding resources.

## Follow-up recheck: `a85ed12` + `94f3d50`

The original P1 omission path is corrected: the shared Queue helper checks
integral metadata, exact page cardinality, stable totals, unique IDs/names and
final cardinality. The new integration denial test calls that actual helper
through `queue_trigger_exact`, rather than replacing it with an assumed complete
list. The original P2 Domain problem is corrected with an unfiltered bare
SinglePage request and coherent optional metadata; tests assert that exact path
and reject contradictory completeness claims. These findings are **resolved in
source**, not yet reported as hosted-test passes.

**GO for hosted synthetic CI; live checker acceptance still NO-GO pending the
new P2 contract mismatch below.** This recheck found no additional isolation
fail-open path in the changed code.

### P2 follow-up — Queue inventory also assumes undocumented pagination

Location: `infra/deploy/ensure_trace_queues.py:inventory` in `94f3d50`.

Rechecking the exact official Queue SDK, rather than only its generic metadata
example, shows that `QueuesResource.list` returns `SyncSinglePage[Queue]`, takes
only account_id plus transport overrides, and sends no page/per_page query.
The current API List Queues reference likewise has no declared query parameters
and marks result_info optional. The helper now demands per_page 100 and all five
pagination fields. Consequently a documented complete SinglePage response with
absent metadata or default per_page 20 is rejected. This is an availability and
API-contract problem; stricter denial closes the previous false acceptance but
does not establish that the healthy deployed checker can ever pass.

Correction guidance: use an endpoint-specific unfiltered Queue SinglePage
inventory with bounded validated unique IDs/names and reject any **supplied**
metadata contradicting completeness, including omitted rows or additional
pages. Preserve the new integration denial for explicit total_count mismatch.
Alternatively, retain a paginated path only with authoritative evidence for
that runtime contract and a deliberate safe strategy for the documented shape;
do not manufacture live evidence or replace completeness checks with a short
first-page heuristic. A hosted synthetic fixture matching the official SDK/API
shape should pass while an advertised omitted Queue must still fail.

Confidence: high for the current official schema mismatch; the actual deployed
account response was not queried. This refines the initial reference assessment:
generic pagination metadata does not itself establish support for page/per_page
request parameters, for either Domains or Queues.

Additional primary reference retrieved 2026-09-30:
[official Queue SDK list implementation](https://github.com/cloudflare/cloudflare-python/blob/main/src/cloudflare/resources/queues/queues.py)
(list method: SinglePage, no declared pagination parameters).

## Follow-up recheck: `813869e`

The Queue SinglePage P2 is resolved in source: the request is bare `queues`,
absent/empty/coherent optional metadata is accepted, IDs/names are bounded and
unique, and explicit advertised row-count/page contradictions still fail.
`queue_trigger_exact` continues to call this shared helper before inspecting
consumer details. No hosted test result is claimed by this source review.

**GO for hosted synthetic CI; source checker live acceptance remains NO-GO for
the small continuation-denial correction below.**

### P2 — Unknown continuation metadata still bypasses the completeness guard

Location: `ensure_trace_queues.py:inventory`, optional metadata block.

The helper ignores unknown result_info keys and checks only four known cursor
aliases. For example, a valid main/DLQ response with
`result_info={"cursors":{"after":"opaque"}}` passes the guard despite its
explicit unreviewed continuation signal. A top-level `next_cursor` is also
ignored. This is a source-derived denial-contract counterexample, not a claim
that Cloudflare currently emits these fields. The design explicitly requires
unknown/incomplete readback to remain unverified.

Correction: use a closed documented result_info key set (as the Domain helper
already does), and reject unknown top-level transport/continuation shapes
rather than assuming additional fields cannot mean truncation. An allowlisted
documented response-envelope set is preferable to indefinitely enumerating
cursor spellings; normal errors/messages/success/result fields remain allowed.
Add hosted negatives for unknown nested continuation, top-level continuation
and explicit truncation. A future provider schema extension can be reviewed
deliberately rather than silently establishing absence from incomplete data.

The Domain helper's result_info is closed, but it likewise does not currently
inspect top-level truncation/continuation claims. Apply the same completeness
boundary consistently to endpoint-specific single-page readers. Confidence:
high for the accepted synthetic control flow; unqueried runtime behavior remains
unknown. This does not reopen the already corrected request-shape findings.
