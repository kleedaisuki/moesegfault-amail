# One bounded offline classifier implementation

Date: 2026-10-01. Status: implemented; independent security review and hosted
synthetic execution required before any owner-only retained-capture invocation.
No local test/build, real key generation, provider request, workflow dispatch,
private session access, decryption, or cleanup was performed by the implementer.

## Contract and scope

Implements the source-backed proposal in
[offline classifier research](private-provider-offline-graphql-classifier-research-2026-10-01.md).
The 19 raw patterns are frozen in `private_provider_crypto.ps1::OfflineTemplates`
with exact spelling and order from `staging_worker_r2_history_error.py::TEMPLATES`.
No network module is invoked to obtain or apply them. Only exact ordinal
`extensions.code == "budget"` adds a cause; contradictions produce `mixed`.

The distinct native `classify-offline` mode is used only by operator `classify`.
The live `inspect` path retains its legacy native classifier and original output
allowlist. Encryption, authenticated decryption, fixed framing, ciphertext size,
provenance validation, local ACL checking, environment isolation and expiry
remain unchanged. No retry, HTTP request, new credential or lifecycle extension
was added. The local result gains `http=<fixed-bin>` before `errors=<fixed-bin>`;
this intentional bounded public format extension applies only to `classify`.

The native interpreter requires a duplicate-free JSON object at depth <=64 and
UTF-8 projection <=128 KiB. Unknown provider siblings remain in memory only and
are recursively checked for duplicate keys. Status must be a JSON integer
100–599; malformed status/JSON/projection causes the existing fixed failure.
Malformed error arrays/messages produce `errors=invalid`, overriding partial
recognition. Valid error arrays have 1–8 object entries, each with a string
message <=2,048 UTF-16 code units. Native regex suffix limits count UTF-16 code
units as well (a supplementary character consumes two units), not Python code
points. Full-string anchors, case-sensitive matching and a 100 ms per-match
safety timeout prevent prefix recognition and unbounded processing.

The parent accepts only exact ASCII strings from the 7 x 12 enum alphabet,
with a 128-byte output cap, no stripping/normalization, and no stderr. Public
serialization remains fixed order, with retained-local and unverified-delivery
labels. Provider text, arbitrary codes, identifiers, paths, numbers, counts,
lengths, hashes and timestamps cannot be serialized by this interpreter.

## Synthetic verification added (not executed locally)

- Native `SyntheticOffline()` exercises all 19 public patterns, prefix/newline/
  carriage-return/case near-misses, fixed-template suffix near-misses, every
  variable suffix at 512/513 units, non-ASCII suffixes, 2,048/2,049 message units,
  surrogate-pair boundaries, all HTTP bins and endpoint statuses, unknown and
  malformed codes/extensions, budget-only and contradictory causes, homogeneous
  and heterogeneous aggregation, malformed/missing messages, error array bounds,
  duplicate keys at root/error/extension/private siblings, excessive depth,
  malformed fragments and plaintext size rejection. Hostile synthetic markers
  inhabit messages, keys, paths and nested extensions; every admitted result
  must equal a fixed literal. This method has no keys, files, sessions or network.
- Existing native synthetic crypto interoperation now also checks the encrypted
  offline path with its in-memory synthetic key. It is still synthetic-only.
- Python operator tests cover all 84 admitted enum pairs, rejected arbitrary
  stdout/non-ASCII/extra fields/whitespace/stderr/process failure, fixed exception
  output, frozen-table equality without importing a network entry point, and the
  updated actual local-ciphertext/provenance fixture with network mocked.

Only source inspection and `git diff --check` were performed. Added tests must
be run in the existing authorized hosted synthetic workflow, including Windows
and Ubuntu; no passing runtime claim is made here. Independent review must cover
both child and parent plus the legacy-path isolation before root uses the richer
interpreter on retained private ciphertext. If review/test cannot complete within
the existing retention deadline, skip classification and follow authorized cleanup.
