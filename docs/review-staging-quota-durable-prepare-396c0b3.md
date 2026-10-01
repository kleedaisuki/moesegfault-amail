# Review: dormant durable quota prepare seam

Date: 2026-10-01
Candidate: 396c0b3, against origin/main snapshot 89ce49f.
Scope: source diff, surrounding acceptance/escrow composition, synthetic tests,
existing hosted test discovery and quota Agent recovery architecture document.
No project tests/builds, provider calls, push or live dispatch performed.

## Verdict

No substantive defect found within the candidate's explicitly dormant,
prepare-only contract. GO for hosted source checks only. This review does not
approve live execution, integration into the legacy accept workflow, campaign
allocation, durable arm, independent Agent intake or release.

## Evidence

- `prepare_escrow` rejects campaign/recover and attached/original-run arguments
  before reading environment capabilities. `_execute` repeats the phase gate and
  restricts the durable key generation before checkout/provider/native work.
- Baseline, exact source/run provenance, held service pins, effective privacy and
  native owner checks are reused. Prepare gets forbidden alias add/delete
  callbacks. New composition calls only Escrow construction, put and read; no
  attach, arm, receipt, purge, account registration or workflow activation.
- `_publish_prepared` checks the exact repository path and rejects an existing
  parent/dangling symlink before escrow writes. Escrow.put authenticates binding,
  writes exact chunks, verifies chunk aggregate/content, requires the known seal
  ACK where a transition occurs, and performs authenticated stable readback.
  The separate subsequent read reauthenticates exact ciphertext and compares
  the entire returned parent to put's result. It additionally requires sealed,
  null artifact/arm/receipt and exact blob. Final upload-path creation follows
  those checks; no fallback after ambiguous write/readback exists.
- A provider failure retains writing/sealed ciphertext intentionally; no automatic
  destructive repair is added. Returns inside the native context still execute
  context exit and the enclosing scratch-cleanup finally before success reaches
  the caller. Either teardown failure prevents a success tuple from returning.
- Existing execute/main and CLI argument choices remain file-only by default;
  no workflow changes. The file-only path now rejects existing/dangling-symlink
  parents and verifies complete write length; normal output/path contract remains.
- No new secret/plaintext rendering or persistence is added. Escrow receives the
  existing encrypted blob and key privately; output is a fixed result label.
  Exceptions at the future caller boundary must remain sanitized, as main does.
- Added tests use the real escrow state/query composition with synthetic SQLite
  and synthetic AEAD, forbid attach/arm/finalize/purge and alias calls, inspect
  unpublished path throughout put/read, and exercise lost ACK, changed parent,
  corrupt chunk, wrong coordinates and generation. General infra unittest
  discovery includes these tests. They are meaningful source invariants, not
  provider/native-account or cryptographic-strength evidence.

## Local publication concern: integration prerequisite, not current finding

Location: acceptance `_publish_prepared`, final mkdir/open/write, and its caller
inside the native context.

A short write, write/close exception, native teardown failure or scratch teardown
failure may leave `manifest.bin` or its directory after the operation fails.
The source document explicitly permits this as retained failure evidence.
Importantly, the path can only be created after authenticated D1 seal/readback;
a failed local publication does not violate the stated D1-before-file invariant,
and there is currently no new uploader or executable entrypoint to misuse it.

Any future hosted wrapper MUST gate upload on normal completion and the exact
`ten_address_escrow_prepared` outcome, not on file existence, and MUST NOT upload
this path under an `always()`/failure continuation. Even atomic local publication
would not replace this requirement: native/scratch teardown can fail afterwards.
The wrapper must neither advance directly to the legacy artifact campaign nor
interpret an observed sealed/armed row as a capability.

Optional hardening: stage to a sibling non-upload filename and publish atomically
only after complete write/close, with safe owned local cleanup. This reduces
ambiguous local leftovers but is not required to authorize hosted source checks
for the present contract. Do not delete provider evidence to compensate for a
local file failure.

## Useful next hosted tests (nonblocking for source-check GO)

1. Durable prepare with short write, write exception and close exception: no
   success outcome; ciphertext retained; forbidden capabilities unused.
2. Durable prepare with native and scratch teardown failure after successful
   local write: no success outcome, ciphertext retained, no alias/purge action.
3. Existing parent and dangling parent symlink: reject before Escrow.put.
4. The actual future wrapper: failed return/exception never triggers upload,
   and successful prepare never arms or invokes the legacy campaign.

## Limits

No hosted run results were fetched or asserted here. No privacy readback,
provider schema/transport, genuine native account, 24-hour Agent service or
live recovery has been independently verified by this review. The architecture
reference exists in the owning main worktree but is not part of this candidate's
origin/main ancestry; its referenced filename in the new source document should
be reconciled when documentation is integrated.
