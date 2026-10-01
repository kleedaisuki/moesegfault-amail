# Durable quota preparation source seam

Date: 2026-10-01. Status: explicitly workflow-wired supervised source, not live admission.

## Contract

`infra/tests/staging_ten_address_acceptance.py::prepare_escrow(args)` is a
prepare-only composition boundary. The explicitly selected hosted workflow supplies
`mode="prepare"`, empty `artifact_id` and `prior_run`, the existing exact source
CI run and service phase coordinates. It reuses all existing manual Windows
GitHub-hosted dispatch, source, identity, global-hold, complete baseline, effective
privacy and native PKCE checks. The fixed generation is `ten-address-v1`; a
mismatch fails before checkout/provider/native work.

Legacy `prepare`, `campaign`, `recover` and `execute()` retain their existing
file-only preparation, artifact campaign and read-only recovery contracts.
New explicit `prepare-escrow`, `campaign-escrow`, `recover-escrow` selectors choose
only their named durable coordinator. The separately reviewed workflow exposes explicit supervised modes; legacy
`accept` remains file-only. No secret, repository variable or provider deployment
is activated by source wiring. Live admission remains separately required.

The sequence is:

1. Build and encrypt the complete pre-mutation manifest after existing baseline
   and provenance checks. The adapter receives forbidden add/delete callbacks.
2. Reject an existing upload directory (including a dangling symlink), without
   attempting to replace a previous local envelope.
3. `Escrow.put` verifies the reviewed schema, writes exact ciphertext chunks,
   authenticates them and seals the parent using its existing strict ACK rules.
4. A separate `Escrow.read` authenticates every chunk and independently confirms
   the same sealed parent and exact ciphertext, with no artifact, arm time or
   cleanup receipt. No readback-derived arm capability is manufactured.
5. Only then create the exact private `manifest.bin` upload file. The fixed
   `ten_address_escrow_prepared` label is returned after the existing native
   context exits and binary scratch cleanup returns normally.

A write exception, lost ACK, schema/key/chunk failure or changed readback leaves
provider evidence untouched and does not expose an upload file or fall back to
file-only preparation. A later local file-write/teardown failure may leave a
sealed provider record or local evidence: it does not return success, delete
ciphertext, authorize a campaign, or create a cleanup receipt. An externally
interrupted invocation remains accountable under the proposed intake design.

## Tests and verification boundary

Synthetic hosted composition tests cover sealed exact-byte publication, no
artifact download, no attach/arm/finalize/purge capability, no add/delete calls,
lost-write ACK, changed parent readback, corrupt chunk, wrong phase/coordinates,
and unsupported retained-key generation. The harness verifies the upload file
is absent during every put/read operation. Existing tests continue to assert
file-only preparation and artifact campaign/recovery compatibility.

Only Python AST parsing and `git diff --check` were performed locally; project
tests/builds were not run on the development machine. Hosted tests and independent
review are required before integration. No claim of provider acceptance is made.
The existing native D1 synthetic provider proof is separate evidence and does
not exercise this new concrete native-account composition.

## Workflow integration and remaining live admission

- The explicit `prepare-escrow-only` workflow mode exposes prepare-only durability,
  uploads and independently checks the immutable ciphertext receipt, then stops
  without campaign/arm/add/delete. Legacy `accept` is not substituted or upgraded.
- The explicit `campaign_escrow(args)` source seam now independently validates
  the downloaded artifact/local envelope, authenticates the same sealed D1
  record, attaches the exact artifact ID, repeats admission, and obtains a known
  `changes=1` arm ACK plus complete readback before the first add. It is wired
  only by explicit `supervised-escrow`. No one may infer permission from an armed parent.
- The explicit `recover-escrow` selector now chooses the complete retained-
  ciphertext D1 finalizer. Its explicit workflow mode requires
  the original completed run and exact source. Do not wire the artifact
  finalizer's per-chunk purge.
- Before one supervised experiment is armed, record a specific capable primary
  supervisor, actual watch window and acknowledged interruption/handoff path.
  Same-day restricted intervention is the target; 24 hours is an escalation
  objective, not expiry or proof of autonomous operations. A general watchdog
  and issue-ACK platform are not prerequisites for this one staffed experiment.
  Unattended operation requires its own independently exercised intake design.
- Review and host-test the assembled contract, then conduct a separately admitted
  bounded staging run. Effective privacy remains an independent gate.

See `staging-quota-d1-recovery-escrow-design.md` and
`staging-quota-d1-native-provider-proof.md`. This seam does not attest cleanup,
complete ten-address acceptance, deploy Mail, enable public sending, or release
v0.1.0.

## Explicit supervised campaign seam

`campaign_escrow(args)` requires `mode="campaign"`, empty `prior_run`, a nonempty
exact immutable `artifact_id`, the source run and service coordinates. Existing
environment confirmation remains `RUN_STAGING_TEN_ADDRESSES`; generation remains
`ten-address-v1`. It shares the normal artifact provenance and source-built
binary/native authentication path. The supervisor/handoff is a separately
reviewed workflow admission obligation, not a caller `passed=true` value.

`hosted.campaign_escrow(..., client)` shares the legacy campaign's complete
manifest/freshness/owner/service/storage/empty-prefix validation. It then reads
and authenticates the full sealed D1 envelope, attaches the unique artifact,
rechecks independent admission, and calls `Escrow.arm`. A valid returned Arm
must bind original run, ciphertext digest, artifact ID and integer server time.
The underlying arm method requires this invocation's conditional `changes=1`
and independently authenticated complete readback; already-armed, zero-change,
lost ACK and mismatched bytes are failures. These failures occur outside the
mutating `finally`, so neither add nor cleanup DELETE is attempted. After a
successful arm, the normal serial quota controller and exact same-process
cleanup own mutation capability. No per-chunk purge or receipt is performed by
campaign. Its retained armed parent is deliberately distinct from an independent
verified cleanup receipt.

Hosted synthetic contracts cover exact attach/arm/first-add order, complete
ciphertext retention, legacy compatibility, pre-arm failures, already-armed,
lost arm ACK and a mismatched permit. Tests remain unexecuted locally.

## CLI interface selected by explicit supervised workflow modes

All modes still require the existing exact manual attempt-1 GitHub-hosted Windows
staging dispatch environment and independent source CI. These examples are
hosted-wrapper arguments, not locally runnable commands or live authorization:

```text
python infra/tests/staging_ten_address_acceptance.py prepare-escrow --source-run SOURCE_RUN
python infra/tests/staging_ten_address_acceptance.py campaign-escrow --source-run SOURCE_RUN --artifact-id EXACT_ID
python infra/tests/staging_ten_address_acceptance.py recover-escrow --source-run CURRENT_SOURCE_RUN --prior-run ORIGINAL_RUN
```

The common optional `--mail-phase pre-queue|queue-api` and `--queue-id` retain
existing exact service admission. `prepare-escrow` and `campaign-escrow` use
`AMAIL_QUOTA_CONFIRM=RUN_STAGING_TEN_ADDRESSES`; `recover-escrow` uses
`RECOVER_STAGING_TEN_ADDRESSES`. Retained recovery requires an empty artifact ID,
a distinct completed original run, the retained generation/key, original source
provenance and complete fresh read-only/native/teardown/postcheck evidence.
It neither downloads an artifact nor purges any chunk. The fixed success label
is `ten_address_escrow_receipt_retained`, not the three quota acceptance labels.
An artifact transport exception never selects D1 recovery implicitly.

The workflow owner must preserve exact supervision/handoff admission, global
concurrency/writer exclusion, original workflow provenance registration, complete
real-cipher/source checks, protected capabilities and privacy validation. Existing
`accept` does not call these selectors and must not be described as durable.

See `staging-quota-supervised-workflow-admission.md` for mode-specific confirmations,
actor attribution and mandatory external supervision/handoff admission. Source
wiring does not demonstrate a completed rehearsal or live campaign.
