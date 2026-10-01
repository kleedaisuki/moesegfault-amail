# Supervised retained-escrow workflow admission

Date: 2026-10-01. Status: source-only; no dispatch, provider operations or live admission.

## Explicit modes and compatibility

The registered `.github/workflows/staging-ten-address-acceptance.yml` retains
`accept` as its default, and legacy `accept`/`recover` transport selection.
`prepare-escrow-only` selects only `prepare-escrow`, uploads the exact encrypted
artifact and independently reads its immutable receipt, then stops without
campaign/arm/add/delete. It requires `PREPARE_STAGING_TEN_ADDRESS_ESCROW_ONLY`
and the exact supervised actor. Successful source preparation/readback/outcomes,
not file existence, produce the preparation-only rehearsal label. A later
separate `recover-escrow` may finalize the completed sealed original with a null
D1 artifact link; uploading does not implicitly attach/arm the D1 parent.

`supervised-escrow` selects `prepare-escrow`, uploads the one encrypted
`manifest.bin`, then selects `campaign-escrow`. `recover-escrow` selects only
`recover-escrow`; it requires a distinct original run and an empty artifact ID.
It never falls back from a failed artifact download, performs campaign adds,
issues a per-chunk purge, or claims quota success from a cleanup receipt.

| Dispatch mode | Exact confirmation | Other coordinates |
| --- | --- | --- |
| accept | RUN_STAGING_TEN_ADDRESSES | prior_run, artifact_id, supervised_by empty |
| recover | RECOVER_STAGING_TEN_ADDRESSES | exact prior_run and artifact_id; supervised_by empty |
| supervised-escrow | RUN_SUPERVISED_STAGING_TEN_ADDRESSES | supervised_by equals actual GitHub actor; prior_run and artifact_id empty |
| prepare-escrow-only | PREPARE_STAGING_TEN_ADDRESS_ESCROW_ONLY | supervised_by equals actual GitHub actor; prior_run and artifact_id empty |
| recover-escrow | RECOVER_STAGING_TEN_ADDRESS_ESCROW | supervised_by equals actual GitHub actor; distinct prior_run; artifact_id empty |

New confirmations are translated only to the existing coordinator phase
confirmation. Source CI, original run and retained-key validation are not
relaxed. Eight dispatch inputs stay below GitHub's 25-input limit.

## Mandatory external operator decision, not a machine attestation

**Do not dispatch any escrow mode until the following admission is recorded
and reviewed for this specific experiment.** The protected staging Environment
and actor match establish capability control and attribution, not continuous
supervision. Neither a boolean, an Environment approval nor a successful source
check is proof that an operator is watching.

Before dispatch the root operator must record, without credentials or mail data:

1. Exact reviewed source SHA, successful six-job source CI run, workflow branch,
   reviewed service/binding phase, current global hold and effective privacy gate.
2. Specific named capable primary supervisor, actual start/end watch window,
   expected 80-minute maximum job duration and cancellation/failure intervention.
3. Acknowledged exception handoff: who accepts responsibility if the primary
   cannot continue, how they receive the original run coordinates, and how they
   acknowledge acceptance. No hypothetical future Agent intake counts.
4. Confirmed availability of protected staging Environment capabilities and the
   retained `ten-address-v1` key; key values remain private.
5. Exclusion of other staging writers throughout admission, preparation, arm,
   campaign and recovery. Job concurrency alone is not global writer exclusion.

Maintain active watch through completion and any required exact restricted
recovery. Same-day intervention is the target; 24 hours is an escalation goal,
not expiry or demonstrated autonomous operations. If a concrete supervisor or
acknowledged handoff is absent, the external decision is NO-GO: do not dispatch.
These facts are not inferred or automatically checked by this workflow.

## Enforced ordering and interruption behavior

Only manual attempt-1 dispatch on `refs/heads/codex/amail-v0.1.0` enters the
GitHub-hosted Windows staging job. Its hard timeout is 80 minutes, with shared
native acceptance concurrency and no automatic retry/cancel-in-progress.
Mode/confirmation/coordinate/actor guards and hosted synthetic real-cipher
checks precede any explicit private credentials. Existing coordinator checks
independently prove exact checkout/source run and dispatch provenance, complete
baseline, source lock, global hold, effective privacy and native identity.

Prepare success is mandatory before upload, and prepare plus upload success
and a nonempty immutable ID are mandatory before campaign. Upload is
non-overwriting, exact-path ciphertext-only with 30-day retention. Before
campaign the workflow GETs that exact artifact once, checks upload digest
against provider metadata, original run/name/SHA and expiry, with a 30-second
read timeout and fixed error labels. For campaign only, the coordinator separately downloads and
authenticates the exact bytes, verifies sealed D1 contents, attaches the ID,
repeats admission and obtains its own conditional arm ACK before the first add.
No provider response, signed URL, credential, account identifier or mail body
is printed by the workflow readback. Any failed preparation/upload/readback/arm
ends the path without a retry or fallback.

Interrupted preparation may leave sealed D1 ciphertext, even before artifact
upload. A lost arm ACK remains ambiguous and does not authorize another add.
Supervision must classify the actual original run and retained parent before a
fresh explicit recovery dispatch; the recovery coordinator requires a distinct
completed original attempt, exact source provenance, fresh checks, native
teardown/postchecks and retains all ciphertext with its independent receipt.
No original-run rerun or automated cleanup is created here.

## Verification boundary

Only local YAML loading, Python AST parsing, PowerShell AST parsing and
`git diff --check` are permitted/performed for this source slice. Project tests
and builds are not run locally. Hosted workflow contract tests cover new actor
and mode guards, upload-before-campaign ordering, mandatory prepare/upload
success, exact receipt digest/run/SHA readback, explicit retained recovery, preparation-only stopping without mutation,
legacy default and lack of automatic retry/fallback. Hosted existing composition
and real-cipher checks remain required; no hosted result or live success is
claimed by this document. Source wiring does not enable public Mail sending,
prove autonomous operations, release v0.1.0 or bypass privacy admission.

## Nonsecret zone coordinate and outstanding key admission

The quota workflow pins the same public Cloudflare zone ID already used by
`ci.yml` and `staging-worker-r2-capability.yml`. A zone ID is an identifier, not
an authentication credential; it does not require a repository or Environment
Secret, and the workflow does not print it as a secret. Account/token/native
credentials and the versioned recovery key remain protected capabilities.

The read-only secret-name audit preceding this correction found
`AMAIL_TEN_ADDRESS_RECOVERY_KEY_V1` still absent. This change does not create or
set it, relax generation checks, or admit any live mode. The named key and all
other external supervision/privacy prerequisites must be resolved separately
before a real preparation or recovery dispatch.
