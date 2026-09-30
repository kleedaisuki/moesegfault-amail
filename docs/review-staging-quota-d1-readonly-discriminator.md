# Independent review: staging D1 read-only incident discriminator

Date: 2026-10-01. Base: `242b5ab`. Scope: the existing
`.github/workflows/staging-ten-address-d1-proof.yml`, modified
`infra/tests/staging_ten_address_d1_proof.py`, new
`staging_ten_address_d1_inspect.py`, and new test source
`test_staging_ten_address_d1_inspect.py` in `.temp/d1-proof-readonly-discriminator`.

## Decision and boundary

**Source GO: no substantive outstanding blocking defect found in this bounded
slice. This is not hosted/provider evidence, permission to dispatch, or authority
to apply schemas, replay a failed operation, or run live quota acceptance.**

Reviewed the diff, surrounding checkout/source/HTTP/deployment/query parsers,
prior native-proof design/review, and test source by tracing. Static checks:
Python AST parsing passed for all three scoped Python files; YAML BaseLoader
parsing passed and confirmed the four exact dispatch modes; `git diff --check`
passed (Git emitted only existing CRLF normalization warnings). No unittest,
build, project runtime, account/provider API, secret access, push, dispatch,
deploy, migration, or other operational action was performed. Only this review
artifact was written. Public Cloudflare API documentation retrieval is not an
account/provider observation.

## Evidence-backed assessment

| Contract | Source assessment |
| --- | --- |
| Strict inspect capability | `execute('inspect')` branches before the existing writer construction. The separate facade admits only fixed DB/deployment/version GET endpoints, the exact global-hold SELECT, and exact namespaced sqlite_master SELECT with one of four fixed parameter pairs. It has no apply/DDL/mirror/receipt/purge method. Each parsed query must report integer zero changes. |
| Admission | `guard('inspect')` preserves hosted runner, repository, feature branch, attempt 1, staging environment and exact `INSPECT_STAGING_D1_READ_ONLY`; exact historical prior run and valid source coordinates precede capabilities. Workflow guard precedes Secrets-bearing execution. Checkout is independently compared to `GITHUB_SHA`, current dispatch metadata to that checkout, and successful six-job/real-crypto source evidence to the same SHA. |
| Original incident | `failed_apply()` binds the fixed run `36787173756`, attempt 1, manual proof workflow/repository/branch, exact SHA `242b5abfee461d04188757e8b365d387d46fcdf9`, completed status and failure conclusion. It does not interpret an absent CREATE ACK as success or permission to retry. |
| Phase distinctions | DB UUID/name, single 100%-serving Worker deployment, exact version/sole D1 `MAIL_DB` binding (also no duplicate `MAIL_DB` name), and exactly one held global singleton have separate stop labels. Readable formal and mirror schemas are independently classified absent/exact/partial_or_drift. Extra or altered namespaced objects cannot become exact. |
| Parameter hypothesis | Native integer and exact decimal-string lengths are separately labeled read-only probes using unchanged SQL/equality parsing. If both parse successfully but disagree, the namespace remains unverified. Neither success nor string-only success changes the writer implementation or grants retry authority. Successful shapes alone are rechecked. |
| Stability and output | Serving pin, held singleton and successful schema shapes are rechecked before complete evidence. Exceptions become fixed stage labels; raw response bodies, DDL, bindings, credentials and private errors are never printed. Output contains fixed labels, public run identity and validated source SHA. Partial/drift or unverified execution returns nonzero. All paths deny mutation/real-cleanup authority. |

## Test-source assessment and limits

All 13 authored test methods were inspected (including the two subsequently
added discriminator/stability methods); none was run. Inspected fixtures route below JSON encoding/native query parsing and compare
in-memory database dumps before/after inspect; writer seams are explicitly
forbidden. Source covers absent/exact/partial combinations, extra object drift,
admission failures, historical metadata mismatch, failed source gate, distinct
DB/Worker/binding/held stops, arbitrary SQL/endpoint rejection, zero-change
enforcement, malformed schema rows, string-only transport hypothesis and private
error suppression. The added recheck method injects a changed second Worker
deployment read, changed second held read, and changed fifth schema read (the
first final schema recheck), each requiring its specific unverified phase and
the failure result. The added parameter-shape method injects formal-only
successful disagreement or failure of both shapes, requires formal unverified
while mirror remains independently absent, and forbids schema recheck/success.
The updated test-source AST still parses and confirms exactly 13 methods.
These are inspected assertions, **not executed results**.

The updated operational document was also reviewed: the original mode table
is explicitly historical/not a retry plan; prior apply/write/read-terminal
command examples were removed; its incident section explicitly prohibits
rerunning those modes as diagnosis. The only conditional next command uses
`inspect` with separate administrator authorization and exact new source CI.
Historical apply authorization is not presented as a standing retry permit.

The [official D1 query API](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/)
uses POST for query transport and currently documents `params` as an optional
array of strings. This supports investigating the parameter-shape hypothesis,
not a finding that it caused the historical failure. The same API documents
`meta`/`changes` as optional: rejecting their absence is intentional fail-closed
behavior, not assurance that every provider response supplies them.

Deployment/hold/schema rechecks are observations rather than an atomic snapshot;
existing operational exclusion from external staging writers still applies.
No hosted success, live schema state, permission availability, historical failure
cause, or actual provider parameter acceptance was established by this review.
