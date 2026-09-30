# Independent review: immutable quota binary/recovery artifacts

Date: 2026-10-01
Reviewed change: `04c1391b159006aa7dcb8f35e4142fcd4dbdabe5`.
Decision: **GO for hosted source verification only. Live quota/recovery dispatch remains NO-GO.**

## Scope and method

Reviewed the three-file increment, quota acceptance design, source admission in
`staging_ten_address_provenance.py`, controller/manifest recovery contracts,
Windows artifact producer in `ci.yml`, and shared nonredirecting HTTP readers.
Static inspection only: no local tests, executable invocation, provider probe,
artifact download, alias mutation or deployment was performed. Other concurrent
worktree changes were not reviewed or staged.

## Findings

No substantive defect found within the dormant artifact transport's stated
contract. This is not an integrated live acceptance approval.

| Boundary | Evidence and assessment |
| --- | --- |
| Exact selection | `Artifacts.binary` lists only the original run in the fixed repository; bounded `total_count <= 100`, exact list-length equality and dict members are required before a single exact SHA-named match is selected. Missing/truncated/duplicate matches fail without downloading a fallback. |
| Run and artifact identity | `metadata` binds numeric artifact ID, exact name/run/SHA/feature branch, same-repository head relation, explicit nonexpired status, bounded size and SHA-256 metadata. Fixed-repository GET URLs avoid trusting returned URLs. Caller must first execute independently observed `successful_source`; this prerequisite is explicitly documented rather than falsely implemented here. |
| Recovery retention | Both modes require future expiry and valid aware timestamps. Recovery additionally requires at least 30 days between creation and expiration. This means original retention, not 30 days remaining at every later recovery; allowing older nonexpired recovery artifacts is consistent with not abandoning cleanup. |
| Content authentication | SHA-256 is computed on actual downloaded ZIP bytes before content use. Whole metadata is independently reread and canonically compared after download, catching ID relation, digest or ancillary metadata drift. |
| Archive containment | A single exact root entry is required; directories, encrypted entries, symlinks, other names and additional entries are rejected. Bounded declared and actual sizes, `ZipFile.read`, CRC validation and no `extractall` avoid archive-driven filesystem paths. |
| Bearer confinement | Authenticated URL is constructed at `api.github.com`. Nonredirecting opener exposes only the expected initial 302. Its location must be HTTPS port 443/no userinfo/no fragment and an allowed Actions storage origin. The second request has no Authorization header and uses the same redirect rejection. There is no automatic retry, alternate artifact lookup or storage redirect. |
| Local materialization | Resolved destination must remain under the physical repository `.temp`, with basename `amail.exe`; final symlink is rejected. Exclusive `xb` creation prevents replacement. This module does not create/claim ownership of a fresh directory: that remains an explicit wrapper prerequisite, not a demonstrated property of a future runner. |
| Privacy and ambiguity | Provider/parser/transport failures are converted to fixed contract labels; no raw URL, metadata, artifact filename, secret or response body is printed. Ambiguous download fails rather than replaying campaign mutation. This reader cannot upload/delete artifacts or execute a binary. |

## Tests and limits

Synthetic source tests inspect exact metadata/digest readback, foreign coordinates,
retention, changed metadata, rejected archive shapes, unsigned redirect boundary,
exclusive materialization and incomplete/ambiguous inventories. These tests were
read, not run locally. Hosted source checks on a containing SHA remain required.
A hostile concurrent filesystem actor is outside the current isolated-runner
contract; the integrated wrapper must allocate its own fresh private directory
and not permit other steps to alter its parents between path check and creation.
The current archive predicate does not accept or extract multiple entries.

Before live composition, independently validate the successful source run before
`binary`, current effective capture-off and held state, current service/binding
pins, original recovery workflow/run/attempt authorization and authenticated
manifest coordinates. Pin the uploader, upload ciphertext before campaign
credentials, use immutable exact artifact ID and verify retained readback. The
unused recovery workflow constant is not evidence that original workflow
admission has been implemented. No live entry point exists in this increment;
that remaining admission cannot be bypassed by supplying synthetic readers.

## External contract checked

GitHub's official [artifact REST API](https://docs.github.com/en/rest/actions/artifacts)
documents the bounded run-artifact listing, ID/digest/relation metadata and
one-minute 302 download URL. The official
[upload-artifact action](https://github.com/actions/upload-artifact) documents
immutable v4 artifacts and archive SHA-256 output. These support the transport
model; actual hosted download compatibility and retention are not proved by
this static review.
