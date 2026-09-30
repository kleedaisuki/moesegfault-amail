# Security review: encrypted provider error capture

Review date: 2026-10-01. Source: `70589cc26c26e465185782598df860ee897aadcc`
and corrections `9a8b65aa1f73ecee86c1281c4d20a6158fe9fb9f` and
`d6ca3d1b7aaca309920d8a2edf9d3cffb4e923af`.

## Verdict and scope

**GO for hosted synthetic checks only. Live capture remains NO-GO.**
Static review found no demonstrated cryptographic confidentiality defect in the
reviewed encryption implementation. This is not a claim of executable Windows
or Linux verification. No local test, live request, key generation, provider
artifact, deployment, or production modification was performed by this review.

Reviewed: Python projection/transport/child environment/envelope/path validation,
PowerShell and embedded C# encryption/synthetic decryption, manual `ci.yml` job,
independent synthetic workflow, imported exact query and historical provenance
validator, design and implementation documents. Local operator key lifecycle,
authenticated artifact download/decrypt/classification/deletion is not present
and was not reviewed as implemented behavior.

## Findings

### Resolved P2: hosted native tests did not traverse the production binary pipe

Location: `infra/tests/test_private_provider_capture.py:118-126` and
`infra/tests/private_provider_capture.py:59-70` (at correction `9a8b65a`).

The hosted native test invokes `private_provider_crypto.ps1 -Mode synthetic`.
That mode exercises `PrivateProviderCrypto.Encrypt` and decryption within one
C# process. It does not execute the PowerShell binary stdin reader, Python's
restricted child environment, stdout encoding, or `validate_envelope()` on a
real native envelope. The new one-POST test in `9a8b65a` mocks `encrypt()`;
the malformed-envelope test checks rejection only. Therefore a passing Linux/
Windows suite does not yet establish the exact production encryption boundary.

Impact: a platform/pipe/serialization problem could discard the sole live
response after the provider request, defeating the intended capture-once/offline
diagnosis mechanism. This is an evidence/coverage gap, not demonstrated plaintext
disclosure. Confidence: high.

Correction required before live use: hosted synthetic keys held only in process memory,
invoke the real Python `encrypt()` function with synthetic UTF-8 error data,
validate its real returned envelope, and independently decrypt/check payload and
authenticated provenance with the same synthetic key. Include wrong-key/header/
tag/ciphertext rejection and no arbitrary diagnostic output. Do not create an
operator key or call Cloudflare to test this boundary. Existing checks may run
now; they must not be promoted to live acceptance on their own.

`d6ca3d1` adds `PrivateProviderCrypto.Boundary()`: an in-memory ephemeral RSA
key remains in the parent .NET process; only its public key enters a credential-
free Python process. The Python `synthetic-boundary` branch calls actual
`encrypt()`, which invokes the PowerShell binary stdin reader and validates its
real envelope. The returned ciphertext is independently decrypted in the
original parent with the synthetic private key; existing payload, GCM component
tamper and wrong-RSA-key checks run on that returned envelope. Python also checks
the exact synthetic provenance through `validate_envelope()`. Only a fixed PASS
leaves the native test; arbitrary child output/errors are suppressed on failure.
This resolves the source coverage gap. Actual hosted execution is still pending,
and this review neither ran nor claimed those checks. No new substantive defect
was found in the narrowly reviewed correction.

### Resolved: authenticated workflow identity named the wrong workflow

At `70589cc`, `private_provider_capture.py:19` used
`.github/workflows/private-provider-error-capture.yml`, although capture is a
job in `.github/workflows/ci.yml`. A successfully encrypted record would therefore
authenticate inaccurate workflow provenance, preventing an exact trustworthy
match against its Actions artifact/run metadata. Confidence: high.

`9a8b65a` changes the constant to `.github/workflows/ci.yml` and asserts it in
the mocked one-POST test. The concrete mismatch is resolved. A future local
operator must still verify the actual run/workflow/source through authenticated
GitHub APIs; public-key encryption is not sender authentication.

## Positive security properties verified by inspection

- Exact imported content-free two-dataset `__typename` query and immutable
  original run/window validator; no caller-supplied query/window. One GraphQL
  POST, no redirect handler follow-up, bounded response, no retry loop.
- Projection retains only HTTP status and the full nonempty error subtree;
  duplicate JSON keys/nonfinite numbers/non-JSON/oversize input fail closed.
  Unknown provider fields stay confidential rather than becoming public labels.
- Standard RSA-3072 OAEP-SHA256 wrapping of a fresh random 32-byte AES key;
  random 12-byte nonce, AES-GCM 16-byte tag. Exact serialized header bytes are
  associated data, including query SHA and source/run provenance. Canonical
  RSA SPKI and key size are checked before the live request via synthetic
  encryption. There is no algorithm downgrade.
- Fixed 256-KiB frame contains a big-endian payload length and zero padding;
  ciphertext size does not expose projected error length. Key/frame/projection
  buffers are cleared on the normal encryption boundary; immutable copies and
  process memory are correctly not claimed to be securely erased.
- Plaintext crosses only an anonymous stdin pipe; child environment excludes
  provider/GitHub credentials. Child stdout/stderr are captured and suppressed
  on failure. Only validated ciphertext is written with exclusive create to
  the exact ignored path; no plaintext filesystem API was identified.
- Manual branch/source/confirmation/first-attempt checks; read-only GitHub
  permissions; provider secret only in the capture step; pinned checkout/upload
  actions, no persisted checkout credentials; success-only exact-file upload,
  one-day retention, no overwrite, final exact ciphertext cleanup attempt.
- Synthetic workflow has no provider credentials and push/PR triggers. Unlike
  a new manual capture workflow, it does not depend on default-branch dispatch
  registration: capture reuses registered `ci.yml` with no added inputs.

## Unmet live prerequisites, not hidden source findings

The implementation explicitly defers current-user-only private-key ACLs and
reparse refusal, fingerprint/session binding, safe exact-member ZIP download,
artifact run/SHA/digest authentication, strict decryption/provenance validation,
offline content-free interpretation, exact remote deletion, and local 24-hour
cleanup. They are genuine live NO-GO prerequisites, not reasons to reject the
secret-free synthetic lane. Do not populate live capture variables or dispatch
until those mechanisms are reviewed and hosted checks cover the real boundary.

`run_attempt == 1` rejects retries of a run, not a second new manual dispatch;
the one-capture operational constraint still requires recording the first run
and disabling/removing the manual target after use. Encryption cannot protect
against a compromised trusted runner or malicious reviewed helper/action.

## Primary-source cross-checks

- [.NET AES-GCM Encrypt](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.aesgcm.encrypt?view=net-9.0): nonce uniqueness per key and associated-data authentication; matches fresh key/nonce and stored-header use.
- [GitHub upload-artifact](https://github.com/actions/upload-artifact): exact-file upload, hidden-file opt-in and explicit retention are necessary artifact controls; encryption, not artifact naming, supplies confidentiality.
- [GitHub rerunning workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs): a retry and a distinct dispatch are different lifecycle events; first-attempt checks do not globally enforce one-shot use.

No academic novelty is claimed: this bounded diagnostic uses mature native
authenticated encryption rather than a new cryptographic construction.
