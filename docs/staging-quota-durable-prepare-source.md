# Durable quota preparation source seam

Date: 2026-10-01. Status: dormant source implementation, not live admission.

## Contract

`infra/tests/staging_ten_address_acceptance.py::prepare_escrow(args)` is a
prepare-only composition boundary. A future reviewed hosted wrapper supplies
`mode="prepare"`, empty `artifact_id` and `prior_run`, the existing exact source
CI run and service phase coordinates. It reuses all existing manual Windows
GitHub-hosted dispatch, source, identity, global-hold, complete baseline, effective
privacy and native PKCE checks. The fixed generation is `ten-address-v1`; a
mismatch fails before checkout/provider/native work.

The module does not add a CLI option. `main()` and `execute()` retain their
existing file-only preparation, artifact campaign and recovery contracts. No
workflow, secret, repository variable or provider deployment is changed.

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

## Required follow-up (not implemented by this slice)

- A separately reviewed workflow must expose prepare-only durability without
  immediately invoking the legacy artifact-only campaign. The present workflow
  `accept` path must not merely substitute this function and proceed: its campaign
  does not yet require a durable arm ACK or accountable intake.
- Exact independently downloaded artifact attachment, verified distinct Agent
  intake/freshness and known `changes=1` arm ACK must precede **every** campaign
  allocation. No one may infer permission from observing an armed parent.
- Bind the complete retained-ciphertext D1 recovery finalizer to a restricted
  registered workflow only after original-run settlement/provenance admission.
  Do not wire the artifact finalizer's per-chunk purge.
- Implement and exercise metadata-only watchdog delivery, real Agent ACK/task,
  freshness monitoring and escalation. A GitHub cron or this interactive session
  is not an independent 24-hour commitment.
- Review and host-test the assembled contract, then conduct a separately admitted
  bounded staging run. Effective privacy remains an independent gate.

See `staging-quota-accountable-agent-recovery-path-2026-10-01.md`,
`staging-quota-d1-recovery-escrow-design.md`, and
`staging-quota-d1-native-provider-proof.md`. This seam does not attest cleanup,
complete ten-address acceptance, deploy Mail, enable public sending, or release
v0.1.0.
