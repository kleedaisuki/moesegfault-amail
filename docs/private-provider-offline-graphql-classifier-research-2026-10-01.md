# Retained GraphQL error: bounded offline interpretation

Date: 2026-10-01. Status: **research and design only**. No production code,
provider request, key/artifact/session access, decryption, synthetic execution,
or cleanup mutation occurred in this investigation. The owner reports one
approved encrypted capture and the existing local result `errors=unclassified`.
That report is not evidence that any particular message or structure was returned.

## Decision

A single independently reviewed **offline-only** expansion is defensible because
the local native classifier demonstrably implements only five of the existing
repository's documented message recognizers and ignores the retained HTTP status
and the documented budget extension. Reuse those known public recognizers; do
not invent GraphQL-js/Apollo-style messages or a Cloudflare code taxonomy.

There is **no reliable general structural discriminator** for schema vs arguments
vs authorization vs internal failure in the official material reviewed. If the
expanded fixed classifier does not recognize a documented template or code, stop
with unresolved evidence and execute the already-authorized cleanup lifecycle.
Do not follow the unknown result with adaptive phrase guesses, arbitrary code
disclosure, another capture, a provider request, or an extended retention deadline.

This is a recommendation to root, not permission for this agent to access the
private session. Implementation, independent review, synthetic tests, and the
owner's offline invocation remain separate decisions.

## Existing knowledge and actual implementation gap

Relevant internal documents were selected by filename before reading:

- [Capture design](private-provider-error-capture-design.md).
- [Live readiness / local lifecycle](private-provider-error-capture-live-readiness-2026-10-01.md).
- [Historical schema investigation](worker-r2-history-schema-diagnostic.md).
- [Earlier fixed GraphQL classifier review](review-trace-graphql-error-c4419c2.md).

Source inspection establishes:

1. `infra/tests/private_provider_capture.py::project` retains exactly
   `http_status` and the complete bounded nonempty error subtree, dropping data,
   headers, and request variables. This means an offline interpreter can inspect
   errors and status, but cannot infer anything from the discarded data envelope.
2. `infra/tests/private_provider_crypto.ps1::Classify` parses `http_status` but
   does not use it to classify. It recognizes exact authentication/account-access
   messages, anchored unknown-field and argument-parsing patterns, and exact
   internal-error text. Other shapes/text become `unclassified`; heterogeneous
   entries become `mixed`.
3. `infra/tests/staging_worker_r2_history_error.py::TEMPLATES`, lines 25-45 at
   inspection, already has the wider official recognizer table. Its
   `message_class` also recognizes `extensions.code == "budget"`.
4. The private operator allowlist currently does not include the larger table's
   query-invalid, dataset-limit, rate/resource, service-unavailable, or invalid
   labels. Updating only the native child would therefore fail the public
   boundary. Any later implementation must review child and parent together.

The prior public historical request and the encrypted capture are separate
observations. An earlier wider classifier returning unknown does not prove that
the captured response contains the same text. It nevertheless lowers the expected
payoff of message-only expansion; status and a documented extension are the
strongest additional signals available without arbitrary text interpretation.

## Official evidence and limits

### Cloudflare's own contract

The current [GraphQL error reference](https://developers.cloudflare.com/analytics/graphql-api/errors/)
(page updated April 23, 2026; consulted today) explains that HTTP success may
contain GraphQL errors and provides example messages for malformed queries,
authentication/access failures, limits, unavailable service, and internal errors.
These are examples, not a complete language or a stable discriminated union.
Its example nests timestamp in extensions even though the preceding field list
is less precise; timestamp must not be treated as a root-level cause code.
The exact existing recognizer table below is based on those public examples.

The newer [account-based rate-limiting reference](https://developers.cloudflare.com/analytics/graphql-api/account-based-rate-limiting/)
(page updated August 25, 2026; consulted today) explicitly assigns the string
`budget` to `extensions.code` for quota exhaustion. Its messages contain resource
identifiers, making code equality substantially safer and simpler than extracting
an account/zone from prose. This is one documented code, not evidence that other
code spellings have known semantics. The reference also says a single-zone query
does not require conversion to account nesting; do not change this query's scope
merely because the rate-limiting model is newer.

### Why general GraphQL structure cannot provide the requested four-way split

The [September 2025 GraphQL specification, errors](https://spec.graphql.org/September2025/#sec-Errors)
requires developer-readable message text and describes source locations and
response paths. Request errors can arise from several pre-execution causes;
execution errors include both argument coercion and service failures. Extension
metadata is implementation-defined, with no universal cause-code vocabulary.
Therefore path/location presence is not a schema/argument/auth/internal classifier.
Further, Cloudflare documents a null-path rate error and a string list index in
its older example, whereas the general specification uses integer list indices.
Applying a generic GraphQL implementation's serialization assumptions would be
unsafe for this provider-specific historical evidence.

No code for schema, arguments, authentication, or internal errors was documented
in the official pages reviewed. A targeted official-domain search for GraphQL
extensions/codes found the budget documentation but no broader taxonomy. This
is a limit of verified evidence, not a claim that undocumented codes cannot exist.

## Exact recognizers: reuse a reviewed public table, not guessed new regex

**Normative message patterns for this proposal are the exact raw-string literals
in `infra/tests/staging_worker_r2_history_error.py::TEMPLATES` as inspected, in
their current order.** The following one-based indices enumerate the complete
mapping. This source reference preserves exact spellings, suffix bounds, and
escaping without creating a competing copied vocabulary in this document.
A later implementer must freeze/copy this exact table into the review diff, not
depend on an unreviewed future version or invoke that module's network entry point.

| One-based table entries | Fixed output category | Existing local native coverage |
| --- | --- | --- |
| 1 | `authentication` | Covered |
| 2-4 | `authorization_or_dataset_access` | Entry 2 only |
| 5-7 | `schema_or_field` | Entry 5 only |
| 8 | `arguments_or_filter` | Covered |
| 9 | `query_invalid` | Missing |
| 10-13 | `dataset_limit` | Missing |
| 14-16 | `rate_or_resource` | Missing |
| 17-18 | `service_unavailable` | Missing |
| 19 | `internal` | Covered |

All comparisons must be **case-sensitive full-string matches**. The existing
variable suffix expressions are bounded by 512 non-CR/non-LF characters. Use
the same bound, not unbounded `.*`, substring detection, case folding, stripping
prefixes, searching nested messages, or recursively hunting for a code. Full
message strings remain bounded at 2,048 UTF-16 code units in the native C# path.
Do not quietly substitute Python character-count semantics on real data; document
and synthetically test the chosen native limit.

The only additional exact extension predicate is:

```text
error is an object
AND error.extensions is an object
AND error.extensions.code is a JSON string
AND error.extensions.code equals the literal "budget" with ordinal equality
```

This adds `rate_or_resource` to the set of recognized causes for that entry.
Unknown extension codes are ignored, not printed, hashed, or coerced to strings.
An extension code contradicting a recognized message yields `mixed`; never let
one branch override a contradictory recognized cause.

## Bounded offline output contract

Keep the native authenticated-decryption, framing, provenance, permissions,
expiry, ciphertext-size checks, and original local lifecycle unchanged. No new
HTTP-capable command or credential is needed. Interpret only the same ciphertext
in memory and send a small fixed ASCII result to the existing parent boundary.

Recommended two-field result, avoiding an arbitrary feature vector:

```text
http=ok|authentication|forbidden|bad_request|rate_limited|server_error|other
errors=authentication|authorization_or_dataset_access|schema_or_field|
       arguments_or_filter|query_invalid|dataset_limit|rate_or_resource|
       service_unavailable|internal|unclassified|invalid|mixed
```

The parent emits these in one fixed order alongside the existing retained-local
and delivery-unverified status. Enum serialization must be explicit, with exact
field set, output length cap, ASCII check, and rejection of any other stdout or
any stderr. No dynamic labels, source paths, session names, identifiers, timestamps,
provider text, numeric status, message lengths/counts, raw keys, hashes, or arrays
of per-error results may be emitted.

### Status mapping and inference boundary

Use the existing `http_bin` mapping exactly: 200 -> `ok`; 401 ->
`authentication`; 403 -> `forbidden`; 400 -> `bad_request`; 429 ->
`rate_limited`; 500-599 -> `server_error`; other valid HTTP status -> `other`.
Validate integer status is 100-599 first; do not accept JSON booleans or numeric
strings. Retain the status and message result separately, without trying to make
every combination conform to an expected provider example.

| Offline result | Useful interpretation | Not established |
| --- | --- | --- |
| Authentication/forbidden status, unknown message | Credential/access-layer hint | Which permission/resource or token defect |
| Bad-request status, unknown message | Request rejected | Schema versus arguments versus dataset limits |
| Server-error status, unknown message | Server-side transport/service hint | Specific internal failure or retry success |
| Recognized field/argument message | Documented query-error family | Exact offending identifier or correct repair |
| Budget code | Documented rate/resource family | Throttled resource or safe time for another request |
| `ok` and unknown error text | GraphQL rejection remains unresolved | Absence of auth or service failure |

None of these diagnoses delivery, validates the historical event classifier,
authorizes resend/deployment, or weakens any fail-closed gate.

### Bounds and aggregation

- Retain the existing 128 KiB plaintext and JSON depth bounds; reject duplicate
  keys during native parsing too, including inside errors/extensions. The original
  projection rejects duplicates, but a defensive parser should not rely on this
  when interpreting adversarial synthetic envelopes.
- Require a nonempty error array of at most eight object entries. More entries or
  malformed types yield a single fixed `invalid` result, no partial interpretation.
  Eight is an explicit offline diagnostic cap, not a claim about the captured
  count or provider maximum.
- Missing/non-string/oversized message is invalid diagnostic structure. Never
  truncate it and then match a prefix. Valid unknown messages are `unclassified`.
- Compute each entry's cause-set from all applicable exact recognizers. Empty
  set -> `unclassified`; singleton -> that cause; multiple -> `mixed`.
- Aggregate only if every entry has the same bin; otherwise `mixed`. In
  particular, recognized + unknown -> `mixed`, not the recognized cause.
- Ignore unknown provider siblings in memory because this is an error hint,
  not an attestation that all private fields are safe. Never bless or serialize
  them. Do not emit dataset path scope: it does not solve the cause question.

## Privacy threat model and validation obligations

The confidential error subtree can contain addresses, account/zone/rule IDs,
arbitrary keys, reflected arguments, URLs, timestamps, unexpected nested text,
and attacker-influenced values. Encryption does not make decrypting it through
assistant tools safe. The native process and existing owner-only key/session
lifecycle are the decryption trust boundary; assistant context, tool output,
stdout/stderr logs, exception messages, debugger dumps, transcripts, and plaintext
files remain outside it. Cloudflare capture authenticity still depends on trusted
CI; local classification cannot create independent provider attestation.

Fixed bins are intentional bounded declassification, not information-theoretic
zero leakage. Two fields have at most 7 * 12 = 84 combinations (less than seven
bits per result). Repeated adaptive predicates can cumulatively reconstruct
private text even when each answer is a Boolean. Freeze this one source-backed
interpreter before execution, do not add substring/prefix probes after observing
its result, and forbid caller-supplied patterns or extension keys. The numerical
bound is an output-alphabet bound, not a formal privacy guarantee.

Before any private invocation, independently review the complete child/parent
diff and run **synthetic-only** tests. Required cases: each referenced pattern;
prefix/suffix/newline/case near-misses; 512/513 suffix and 2,048/2,049 native string
limits; non-ASCII and surrogate pairs; duplicate properties; deep nesting;
oversized/error-array/non-object bounds; missing/null/non-string extensions/code;
budget alone; recognized/budget contradiction; recognized/unknown aggregation;
integer versus Boolean/string status; unexpected child stdout/stderr; every
exception returning only the existing fixed failure label. Insert private markers
in message, arbitrary keys, path, nested extensions, and malformed fragments;
assert none appears in any emitted output. Tests must not inspect or discover
actual session directories and must use in-memory synthetic keys/envelopes or
isolated root-local `.cache`/`.temp` fixtures outside the private session subtree.

## Stop condition and cleanup

One completed offline result is the end of this interpreter experiment. A known
bin supports a repair hypothesis that can be analyzed using source/schema docs,
not another provider read. Unknown, invalid, mixed, or coarse status-only results
do not justify raw disclosure or a regex search campaign. Preserve only the fixed
outcome and explicit unresolved status, then have the owner execute the existing
cleanup procedure and verify its fixed completion result plus capture-variable
absence. Do not claim that this research performed cleanup or extend the original
deadline to finish optional implementation.

If independent review or synthetic coverage cannot be completed within the
existing deadline, skip the richer classifier and clean up. Retention of private
evidence is not more important than the approved privacy lifetime.
