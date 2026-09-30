# Review: page-only historical Audit classifier correction (4da9aa4)

Date: 2026-10-01 Asia/Singapore.
Verdict: **GO for hosted source checks, then one bounded historical read if those checks pass.** No substantive defect was found in this scoped correction. This is not permission for a settings mutation or privacy/rollout acceptance.

## Scope and evidence

Independently inspected commit `4da9aa4f1e75c1bfc841d12b046d5fa94e610b61`, the complete classifier and synthetic tests, its unchanged manual workflow caller, and filename-relevant prior reviews/forensic notes. Retrieved the official [Cloudflare Audit v2 API reference](https://developers.cloudflare.com/api/resources/accounts/subresources/logs/subresources/audit/methods/list/) on 2026-10-01. No local test/build, private provider request, historical workflow log retrieval, deployment, mutation or production-source edit was performed.

The fixed shape observations from run [36756914170](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36756914170) are supplied evidence, not independently reconstructed here: integer numeric count matching returned rows, omitted cursor and known typed row fields. They justify accepting that observed count representation for a page observation, not declaring complete query coverage.

## Assessment

| Contract | Evidence and conclusion |
| --- | --- |
| Count representation | `valid_count` accepts canonical documented strings and exactly typed nonnegative integer JSON counts, equal to the bounded result length. Booleans, floats, negative/oversized values, missing values and alternate string encodings are rejected. Row length remains capped at 100. Numeric acceptance is grounded in supplied hosted evidence rather than claimed to be the published string schema. |
| No exhaustion/uniqueness claim | The API defines count as records returned in the response and cursor as a pagination token; it does not establish missing/empty cursor as exhaustion. The correction removes `complete=yes` on all paths. Omitted and empty-string cursors allow one page to be inspected; populated/null cursors and unknown result-info fields stop without continuation. `matches=one` means this returned page only. |
| Positive evidence remains fail-closed | A single fully validated matching returned row can produce only `page_reported_success` or `page_reported_failure`. Zero/multiple matches remain unresolved. Every classifier return is UNVERIFIED; `main` always exits 1, including positive observations. No historical observation can satisfy a successful attestation gate. |
| Exact historical scope retained | Shared reader still issues at most one fixed GET for the six-second historical interval with limit 100, ascending order, timeout and byte bound. No retry, redirect, pagination, new endpoint or widened window is introduced. Exact method/path, in-window timestamp, optional account match and known-field validation remain unchanged. |
| Privacy retained | Only fixed labels and closed categorical values reach stdout. Actor/record IDs, account/path, numeric HTTP status, body, cursor and exceptions are not emitted or persisted. Existing HTTP parser normalization and private-output tests are retained. The diff does not add artifacts, credential access or workflow inputs. |
| Tests check semantics | New tests explicitly assert positive page outcome together with UNVERIFIED and unverified completeness for numeric/string counts and omitted/empty cursors; they reject numeric type drift and distinguish zero-page observation from proof of absence. Existing main test now requires failure exit even for a known positive fixture. Exact-query, private-output, parser-exception and first-attempt guards remain covered in inspected source. |

The amended forensic note explicitly supersedes its older completeness/CLASSIFIED descriptions. Current source does not use those obsolete descriptions as an executable acceptance policy.

## Limits and next gate

Tests were inspected, not executed. Hosted source checks must pass before a new bounded read. This review does not verify any historical PATCH outcome, attribute a row to the GitHub helper, establish successful client parsing, prove current Issues-off or authorize retrying the mutation. The effective-state privacy gate remains independent. A diagnostic job failing with a positive page observation is intentional, not a reason to weaken its exit contract.
