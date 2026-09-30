# Review: historical staging settings audit classifier (182535f)

Date: 2026-10-01 Asia/Singapore.
Original verdict at `182535f`: **NO-GO pending one scoped exception-boundary fix**.
Current verdict after `7e5ae7b`: **GO for hosted source checks, then one bounded
read-only historical Audit query if those checks pass**.
Confidence: high in the source failure path; no claim that it occurred in a live run.

## Scope and method

Independently inspected commit `182535fed8610e363f09ead6737f86565e506bab`,
the helper, synthetic tests, workflow diff and existing forensic decision.
Retrieved the official Cloudflare Audit Logs v2 reference and Python 3.12
HTTP client documentation/source. No local tests/builds, private account
requests, deployment, mutation, workflow dispatch or push were performed.
Historical job facts in the task are context supplied by the parent, not
independently reconstructed evidence.

## Original finding (resolved in source)

### P2: HTTP parser exceptions escape the fixed privacy output boundary

Location: `infra/tests/staging_settings_patch_audit.py:54-62,180-185`.

`build_opener(...).open()` and `response.read()` use Python's HTTP parser.
The reader catches `HTTPError`, `URLError`, `TimeoutError` and `OSError`,
but `http.client.HTTPException` is an independent `Exception` subclass.
For example, a malformed response status line can raise `BadStatusLine`;
a malformed/truncated chunked response can raise `IncompleteRead`.
The outer main handler also does not catch these. They therefore terminate
the process with an uncaught traceback rather than the seven fixed output
lines. `BadStatusLine` carries the raw received status line, violating the
explicit no-raw-provider-exception output contract. This is conditional on
a protocol failure, not an allegation of present credential exposure.

Normalize `HTTPException` at the existing reader boundary to the fixed
`transport` category, using `from None`; do not print or inspect its detail.
Extend focused synthetic tests with `BadStatusLine("PRIVATE...")` during
open and `IncompleteRead` during read, checking the complete main output
and no private stdout/stderr. Keep exactly one request, no retries and the
immutable query. No unrelated architecture change is necessary.

### Resolution review: 7e5ae7b

Independently inspected commit `7e5ae7bfec9de6c860c03ea2ce20a945420ec68e`.
The helper imports `HTTPException` and adds it to the existing transport catch
around both open and read, preserving `from None`. The new synthetic test
injects a private `BadStatusLine` at open and a private `IncompleteRead` at
read through the real main/reader boundary; it asserts all seven exact output
lines, failure exit, empty stderr, no private marker and one request. The open
failure additionally checks no response read; the read failure checks the exact
byte bound. This resolves the original P2 in source without widening the query,
adding a retry or weakening ambiguity/containment gates. No new substantive
issue was found in this scoped correction. Tests were inspected, not executed.

Evidence:
[Python HTTP exceptions](https://docs.python.org/3.12/library/http.client.html#http.client.HTTPException),
[CPython urllib request implementation](https://github.com/python/cpython/blob/3.12/Lib/urllib/request.py),
[CPython HTTP exception implementation](https://github.com/python/cpython/blob/3.12/Lib/http/client.py).

## Sound boundaries found

| Contract | Source assessment |
| --- | --- |
| Historical query only | Helper lines 16-22,47-58 construct one fixed HTTPS GET, exact six-second interval, ascending order, limit 100, 15-second socket timeout and 1 MiB response cap. No PATCH, request body, retry, continuation or caller-controlled endpoint/time exists. |
| Exact match | Lines 128-149 use literal staging script-settings URI, literal PATCH, strict in-window action timestamp and matching account when supplied. Near-matches are not silently normalized. |
| Incomplete or ambiguous evidence | Lines 111-127 reject failed/malformed envelopes/count drift/unknown pagination; only explicitly empty cursor is accepted. Lines 150-164 leave zero/multiple matches unresolved. Unknown outcome/status cannot authorize a result. |
| Private data stays private on normal paths | Actor/resource payloads are not emitted, selected statuses are reduced to named bins, and result lines contain only closed categories. No raw URI, record/actor/token/account identifier or numeric HTTP status is printed. |
| Credentials after tests | Workflow lines 506-545 restrict manual dispatch to the development branch/staging, first attempt, exact confirmation, focused synthetic tests before the final credentialed read step. No secret is supplied to tests. |
| Dispatch compatibility | The existing target choice is extended; existing 23 inputs are unchanged. Non-cancelable staging job serialization is preserved. Hosted Infra discovery also includes the new tests. |
| No live approval implied | CLASSIFIED reports a historical provider outcome, not helper attribution, client parsing, effective Issues-off or rollout permission. Documentation keeps the settings freeze and independent effective-state gate. |

The [official Audit v2 API](https://developers.cloudflare.com/api/resources/accounts/subresources/logs/subresources/audit/methods/list/)
supports this endpoint, RFC3339 time bounds, ascending direction, bounded limit
and cursor pagination. Its record schema exposes optional action and raw
method/URI/status; result-info count is a string. Account Settings Read or
Write is required independently of Worker deployment permissions. The strict
empty-cursor rule can reject a legitimate omitted optional representation,
but cannot create a false positive; omission was not proven exhaustion by
the retrieved contract. The rule is already disclosed, so this is not a
required correction.

## Limits and next gate

Synthetic tests were read, not executed. The scoped correction has now passed
independent source review; run focused tests on GitHub-hosted infrastructure
before one historical audit dispatch. Permission failure,
missing data or zero matches must remain unresolved; none authorizes a
mutation retry, broader query or relaxation of effective privacy acceptance.
