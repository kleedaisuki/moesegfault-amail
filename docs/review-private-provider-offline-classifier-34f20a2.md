# Security review: one-shot retained-capture offline classifier

Date: 2026-10-01. Reviewed implementation: `34f20a29ce9c400e68e9d5a8dea91fbc8c5db93e`.
Independent static review of the full child/parent/test diff, surrounding capture
and operator paths, frozen historical templates, and the research contract.

## Verdict and execution gates

**GO for the existing secret-free hosted Ubuntu/Windows synthetic workflow. No
substantive source defect found in this bounded change. Retained-local invocation
is presently NO-GO until both hosted synthetic jobs pass for the exact reviewed
implementation source (or a descendant whose relevant source is unchanged).**

After that evidence is recorded, this review gives a **conditional GO for one
owner-authorized offline interpretation of the already-retained ciphertext**,
not another capture, provider request, deployment, key generation, or secret
mutation. The original retention deadline must still be valid, and the owner
must use the existing provenance/expiry/ACL checks and cleanup lifecycle. If the
deadline cannot accommodate verification, skip interpretation and clean up.
Unknown, invalid, mixed, or coarse status-only outcomes do not authorize new
adaptive patterns, another query, or longer retention.

This reviewer ran no local tests/builds, generated no keys, accessed no private
session directory, decrypted nothing, queried no provider API, and deployed
nothing. Public documentation browsing and source inspection are the only
external investigation. Only this English review artifact is changed.

## Contract evidence

Internal knowledge reused:

- [Bounded offline research](private-provider-offline-graphql-classifier-research-2026-10-01.md).
- [Current capture design](private-provider-error-capture-design.md).
- [Operator lifecycle review](review-private-provider-operator-lifecycle-5728707.md),
  including its resolved recovery/ACL findings and existing scope limits.
- [Implementation record](private-provider-offline-classifier-implementation-2026-10-01.md).

Public source cross-checks were limited to official documentation. Cloudflare's
[error reference](https://developers.cloudflare.com/analytics/graphql-api/errors/)
documents the message families and states that successful HTTP responses can
still contain GraphQL errors. Its examples are not a complete cause taxonomy.
The [account-based rate limit reference](https://developers.cloudflare.com/analytics/graphql-api/account-based-rate-limiting/)
specifically documents the `budget` extension code. Neither reference licenses
arbitrary code disclosure or inferring precise permissions from coarse bins.
Microsoft's [.NET anchor reference](https://learn.microsoft.com/en-us/dotnet/standard/base-types/anchors-in-regular-expressions)
confirms the strict end-of-string semantics used here, including rejection of
an otherwise matching message followed by a newline.

## Boundary-by-boundary assessment

| Boundary | Source evidence | Assessment |
| --- | --- | --- |
| Frozen public grammar | `private_provider_crypto.ps1::OfflineTemplates`; historical `TEMPLATES` | All 19 category/pattern pairs retain their spelling and order. The AST/source fixture compares exact literal pairs without invoking the historical module's network entry point. |
| Matching | `ErrorBin` | Case-sensitive strict full-string anchors, bounded non-CR/non-LF suffixes, 2,048 UTF-16 code-unit message limit, and per-match timeout. No substring search, truncation, recursive message hunting, or caller-supplied grammar. |
| Additional code predicate | `ErrorBin` | Only an object entry with object `extensions`, string `code`, and ordinal equality to `budget` contributes a rate/resource cause. Unknown/type-invalid codes are ignored, not coerced or emitted. |
| Cause aggregation | `ErrorBin`, `Interpret` | Contradictory recognized message/code causes are `mixed`; recognized plus unknown entries are `mixed`. Any malformed entry makes the whole result `invalid` rather than preserving a partial recognized cause. |
| HTTP interpretation | `HttpBin`, `Interpret` | Integer-only 100-599 validation precedes exactly the documented seven status bins. Status and message evidence remain separate; no enforced provider-specific correlation. |
| Bounded parsing | `Interpret`, `Unique` | Projection <=128 KiB, depth <=64, exact two root fields, recursive duplicate rejection including private siblings, and a nonempty array of <=8 object entries. Malformed JSON/status fails closed; malformed error structure yields the fixed invalid bin. |
| Parent-child output | `child`, `offline_result`, `main` | <=128 bytes, exact ASCII, exact two fields and order, no normalization, no stderr, successful exit required. Only the 84 predeclared pairs survive. The public status adds fixed retained-local and delivery-unverified fields. |
| Retained-only routing | `classify_local`, PowerShell mode branch | Only the explicit local classify command selects `classify-offline`. Its call graph reads the existing bounded ciphertext/receipt/public-key metadata and starts the isolated native helper; it does not call token acquisition or HTTP transports. |
| Legacy and protection | `inspect`, `Classify`, ACL branch | Live inspect still calls legacy `classify` with the old allowlist/output. Authenticated decryption, fingerprint binding, fixed frame/tail checks, key/frame clearing, envelope validation, session path policy, local ACL checks and 24-hour age gate are not replaced. |

The root field restriction is appropriate: the capture projection retains exactly
`http_status` and `errors`. Unknown siblings *inside* error objects remain private
and uninterpreted, apart from defensive duplicate validation. This is not a
claim that unknown fields are safe to disclose.

The offline method returns only source-owned category literals, including on
aggregation and structural errors. It does not serialize provider strings,
arbitrary keys, paths, codes, counts, lengths, numeric status, hashes, identifiers,
or timestamps. Native exceptions terminate without error prose; the parent
captures child output and collapses ordinary failures to the existing fixed
failure line. No new plaintext filesystem writer or credential propagation was
introduced. As in the original design, fixed bins are intentional bounded
declassification, not zero-information disclosure or a memory-forensics defense.

## Synthetic coverage and evidence limits

Source includes positive/negative cases for all 19 patterns; prefix, suffix,
case, CR/LF near-misses; every variable suffix at 512/513 units and non-ASCII
suffixes; 2,048/2,049 message limits and surrogate-pair boundaries; all HTTP
bins and valid endpoint statuses; unknown/null/non-string/nested code cases;
budget alone and contradictions; homogeneous/heterogeneous aggregation;
invalid entries and eight/nine entry boundaries; duplicates at root, message,
extension and private sibling levels; deep JSON, malformed fragments and
oversized projection rejection. Hostile markers occur in message, keys, path
and nested extension values; admitted outputs must equal fixed literal results.

The actual encrypted synthetic native path now also calls the offline interpreter
with its existing in-memory synthetic key. Parent fixtures cover all 84 allowed
pairs, extra stdout/whitespace/non-ASCII/NUL/unknown fields, child stderr and
failure exit, and ordinary exception suppression. The retained-file fixture
executes real local validation with the fixture path locator/native child
substituted and asserts no HTTP transport call. Those substitutions are useful
boundary tests, not proof of actual operator private-file execution.

The existing `private-provider-crypto-tests.yml` runs the Python suite with its
hosted synthetic flag on Ubuntu and Windows, no provider secret binding, and
read-only repository permission. `HostedCryptoTests.test_native_crypto` executes
native synthetic mode and requires its fixed PASS result and empty stderr. The
new classifier matrix is wired into that mode. Source coverage is therefore
present, but passing execution is not established by this review.

`git diff 34f20a2^ 34f20a2 --check` returned clean; this is formatting evidence
only, not a test/build/crypto result. No finding is manufactured from speculative
threats outside the declared model. No previously resolved lifecycle concern is
reopened. This verdict does not establish provider delivery, production
readiness, actual private error contents, deletion completion, or permission
to continue diagnostics after the one-shot result.
