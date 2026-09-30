# Security review: local private provider capture lifecycle

Date: 2026-10-01. Reviewed source: `5728707` plus
`15ea7119b1b2f8208e6839e78c9f956794b7b53e` (the native classifier coverage
correction). This extends, rather than replaces,
`review-private-provider-capture-security-70589cc.md`.

## Verdict

**GO to run the existing secret-free hosted synthetic checks. Live capture is
NO-GO.** Two source corrections and additional lifecycle coverage are required
before this operator implementation can satisfy the documented live contract.
The existing checks are safe to execute; their success must not be described as
end-to-end operator lifecycle acceptance.

No local tests, key generation, provider requests, private downloads, deployment,
or production changes were performed. This is static source and contract review.
Only this English review artifact was added.

## Necessary corrections

### P2: early interruption loses the only remote cleanup receipt

Location: `infra/tests/private_provider_operator.py:220-229`, `174-179`,
`256-259`. Confidence: high; established control-flow defect.

`inspect()` authenticates the remote artifact, downloads it, reads the ZIP,
validates the envelope and writes ciphertext **before** writing `receipt.json`.
A download/network failure, invalid archive, or cancellation between these
operations leaves the remote artifact intact without a cleanup receipt.
`cleanup` then sees no receipt, silently skips all remote verification and
deletes the local key/session, reporting `CLEANED`. This does not meet the
documented interruption-recovery guarantee; artifact retention expiry is not
verified immediate deletion. Cancellation during the non-atomic receipt write
can also leave malformed state that the sole cleanup command cannot recover.

Remedy: persist public run/source binding before remote retrieval and atomically
record authenticated artifact coordinates as soon as provenance succeeds,
before download or any interpretation. Preserve a bounded recovery path for
interruption before artifact discovery, including a failed/cancelled capture
run that still uploaded an artifact. A potentially dispatched session must not
report remote cleanup success merely because its receipt is missing. Keep the
recovery path GitHub-only: no second Cloudflare query or workflow replay.

Add hosted fault-injection tests at each lifecycle boundary, including partial
receipt write, download failure, ZIP/envelope rejection, cancellation, DELETE
failure, and cancellation after successful DELETE but before local cleanup.
Assert exact authenticated artifact deletion/absence and preservation of the
key when remote cleanup is not established.

### P2: Windows ACL validator accepts a null DACL

Location: `infra/tests/private_provider_crypto.ps1:224-230` at `15ea711`.
Confidence: high for the validator condition; conditional impact.

The validator enumerates access rules and checks the owner but does not require
a present, non-null discretionary ACL. A current-user-owned object with a null
DACL has no enumerated entries, so the loop succeeds; ownership also succeeds.
A null DACL grants access to every user, not current-user-only access. Normal
key generation creates a restrictive DACL, so this is **not** evidence that its
normal output is exposed; it is a fail-open validation path if the ACL has been
cleared or damaged before inspection. The implementation explicitly promises
to refuse broadly accessible existing keys.

Remedy: inspect the security descriptor's DACL presence/null state explicitly;
require a present non-null protected directory DACL and a effective user-only
key DACL with usable current-user access. Reject null/empty, foreign allow rules
and incompatible owner states with the same fixed failure output. Test the
policy independently using synthetic descriptors, without an operator key.

Primary semantics: [Microsoft: null DACLs and empty DACLs](https://learn.microsoft.com/en-us/windows/win32/secauthz/null-dacls-and-empty-dacls).

## Acceptance coverage still missing

`test_private_provider_operator.py` covers exact ZIP member rejection, invalid
session names, a single bad run-attempt fixture, credential exclusion and
exception suppression. It has no successful authenticated
run/job/artifact/digest/download fixture, DELETE/404 verification fixture,
receipt recovery fixture, real ACL policy check, or native session-path/key-file
inspection fixture. The workflow's glob collects those tests but cannot create
coverage they do not contain.

`15ea711` usefully calls `Classify()` on the real synthetic envelope with an
in-memory synthetic private key and asserts only `unclassified` is returned.
That resolves the earlier *complete absence of native classifier execution*;
it does not exercise all supported classes, malformed payload framing, actual
PowerShell classify stdin/file/ACL handling or operator lifecycle recovery.
Do not reopen the resolved production encryption-pipe coverage finding.

Before live acceptance, add hosted synthetic coverage for the missing boundary
contracts. Prefer isolated policy/helper tests and in-memory keys; if native
filesystem/permission fixtures are necessary, use only explicitly synthetic
hosted fixtures in repository `.temp`, never the live local operator key or
provider credentials. Keep `GITHUB_ACTIONS` refusal on the real keygen path.

## Positive properties observed

- Private provider plaintext stays inside native decryption/classification;
  no plaintext disk write or provider prose output was identified. The returned
  category is a closed allowlist and top-level ordinary exceptions print only
  fixed failure text. Child stderr is captured and never forwarded.
- Python validates exact expected header/provenance/fingerprint before native
  decryption; native code verifies the private-key fingerprint and GCM before
  parsing the bounded frame. No plaintext is interpreted before authentication.
- Run/SHA/branch/manual-event/first-attempt/workflow/job and artifact metadata
  are checked via authenticated fixed-repository GitHub APIs. Pagination is
  rejected rather than guessed. Artifact age and digest are checked.
- Artifact download follows one approved HTTPS redirect without bearer
  credentials; a second redirect is rejected. ZIP remains in memory and only
  one exact regular encrypted member is read, with bounded archive/member sizes.
- Normal Windows key creation protects inheritance before key bytes are
  written; normal Unix creation uses directory 0700 and exclusive file creation
  0600. Paths are session-name constrained and symlink/junction checked; deletion
  enumerates exact known files, never recursively removes a calculated path.
- The operator makes GitHub lifecycle calls, not Cloudflare provider queries;
  it does not implement dispatch or automatic replay. Global one-shot dispatch
  and 24-hour expiry still require the explicit operator procedure, as the
  documentation already states. Encryption is not protection from a compromised
  operator or hosted runner, and file deletion is not physical secure erasure.

## Scope limits

No executable Windows/Linux ACL or crypto results are claimed here. No claim
about historical provider delivery, B readiness, privacy settings, public-send
readiness or production acceptance follows from this review. The null-DACL
issue does not demonstrate compromised local files. Source-only TOCTOU checks
are not a defense against an already compromised operator account; that threat
is outside the declared model. No unrelated architecture redesign is proposed.
