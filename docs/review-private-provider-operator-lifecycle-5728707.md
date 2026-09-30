# Security review: local private provider capture lifecycle

Date: 2026-10-01. Reviewed source: `5728707` plus
`15ea7119b1b2f8208e6839e78c9f956794b7b53e` (the native classifier coverage
correction). This extends, rather than replaces,
`review-private-provider-capture-security-70589cc.md`.

## Verdict

**GO to run the existing secret-free hosted synthetic checks. Live capture is
NO-GO.** The original source corrections are resolved by the follow-ups below;
additional lifecycle coverage and hosted evidence are still required before
this operator implementation can satisfy the documented live contract.
The existing checks are safe to execute; their success must not be described as
end-to-end operator lifecycle acceptance.

No local tests, key generation, provider requests, private downloads, deployment,
or production changes were performed. This is static source and contract review.
Only this English review artifact was added.

## Follow-up review at `285a77a`

Reviewed corrections `bc8df06` and `285a77a` without running tests, generating
keys or making live requests. **Existing hosted synthetic checks remain GO;
live capture remains NO-GO.**

The original two source findings below are resolved in their stated forms:

- `inspect()` now atomically records run/source intent before its first API
  request and authenticated artifact ID before download. A missing receipt
  refuses cleanup instead of claiming remote deletion. `record_receipt()` uses
  exclusive staging-file creation, file flush/fsync and atomic replacement;
  POSIX directory fsync and the Windows power-loss limitation are explicit.
  Interrupted replacement retains the previous valid intent. New hosted-only
  filesystem fixtures inject failures at multiple inspect boundaries and assert
  preservation of coordinates/key; they use synthetic non-key bytes in root
  `.temp`, not an operator key.
- The shared native ACL policy inspects raw descriptor DACL presence/null/count,
  rejects foreign/non-allow/callback ACEs, checks owner, and requires protected
  directory inheritance. Key creation verifies its resulting directory ACL.
  Windows hosted synthetic mode tests good, null, empty, foreign, deny and
  unprotected synthetic descriptors without creating an operator key.

### Remaining P2: recovery treats artifact absence on a running run as final

Location at `285a77a`: `private_provider_operator.py`, `retire_remote()` run
authentication and its `if not matches: return` branch. Confidence: high.

An operator can call `inspect` before the manual capture run completes. The new
intent receipt is persisted, then `provenance()` rejects the nonterminal run.
`cleanup` authenticates that same run's ID/SHA/branch/attempt/event but does not
require terminal status. If the capture job has not uploaded its artifact yet,
the complete artifact listing is empty; recovery returns and local cleanup
destroys the private key while reporting `CLEANED`. The capture job can upload
the encrypted artifact afterwards. This is a concrete late-creation race, not
a reason to reject recovery of failed or cancelled *terminal* runs.

Require authenticated `status == "completed"` before either an absence claim
or retirement cleanup; do not require successful conclusion, because failed or
cancelled terminal runs can legitimately leave uploaded artifacts. Preserve the
key/receipt on queued, requested, waiting, pending or in-progress runs. Add a
hosted fixture proving nonterminal absence cannot delete the key, and terminal
failed/cancelled runs can retire their exact authenticated artifact.

The broader successful download/digest and DELETE/recovery fixture gaps remain
acceptance work, not claims that those mechanisms were run. The source additions
improve coverage but actual hosted results are owned by the parent delivery
record. No live acceptance is granted by this follow-up.

## Follow-up review at `a05d374`

Reviewed `bae215a` and `a05d374` by inspection only. **GO for secret-free hosted
synthetic checks; live capture remains NO-GO.** No new substantive source defect
was found in these narrow corrections. No local tests, keys, artifact access or
provider requests were performed.

The remaining late-upload race is resolved: `retire_remote()` now requires the
authenticated attempt's `status == "completed"` before listing/accepting
artifact absence or deleting local evidence. Successful conclusion is not
required, correctly preserving cleanup of terminal failed/cancelled attempts.
The new fixtures reject queued/in-progress/waiting/pending/requested runs before
artifact listing and allow complete empty listings for terminal failed/cancelled
runs. Existing main-command ordering keeps local cleanup after remote recovery,
and a remote failure fixture asserts the local cleanup routine is not called.

`bae215a` separates remote retirement from local interpretation completion.
Successful `inspect` verifies DELETE/404 remotely but retains the bounded
ciphertext/private-key session and emits `LOCAL_RETAINED remote=CLEANED`, not an
incorrect all-cleaned status. Explicit `classify` checks the 24-hour local age,
bounded receipt/ciphertext, exact provenance and public fingerprint before
calling the existing native authenticated classifier. That implementation has
no network call; repeated classification does not dispatch or contact
Cloudflare/GitHub. Unknown results can now be interpreted offline without
discarding the only diagnostic. Explicit `cleanup` still authenticates remote
coordinates/absence before enumerated local deletion. Deadline enforcement
remains an operator procedure, not a background task.

The new `test_local_classifier_never_contacts_provider_or_github` mocks the
entire `classify_local` function, so it verifies command routing/output, **not**
execution of the retained-file validation/native boundary. Similarly, the
terminal cleanup fixtures cover authenticated absence but not a successful
exact-artifact DELETE/404 recovery sequence. The broader positive download,
digest, recovery-deletion and retained-classify fixture gaps noted above remain
evidence limitations to close before live acceptance, not new demonstrated
defects. Native synthetic Classify and raw Windows descriptor policy checks are
already wired; their hosted execution is not claimed by this static review.

All three reported source findings are now resolved in the reviewed tip.
No source finding is being kept open merely to maintain a finding count.

## Original necessary corrections (resolved by follow-ups)

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
