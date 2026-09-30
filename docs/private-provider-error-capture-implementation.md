# Private provider error capture implementation boundary

Status: source implementation awaiting independent security review and hosted
Linux/Windows synthetic checks. **Not authorized for a live capture.** No keys,
local cryptographic tests, provider reads, or private artifacts were produced.

Bounded existing hosted evidence (owner reported): exact reviewed source
`a36d11c` passed source CI
[36767492647](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36767492647)
(six jobs), workflow lint
[36767492242](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36767492242),
and real Python-to-PowerShell synthetic encryption/decryption on Ubuntu and
Windows in
[36767492318](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36767492318).
That evidence predates the operator lifecycle slice: it does **not** establish
the newly added key ACL, native classification, authenticated artifact download
or remote/local cleanup behavior. No real operator key was generated.

## Source contract

`infra/tests/private_provider_capture.py` imports the unchanged reviewed
`staging_worker_r2_history_error.QUERY` and original run/window validator. It
performs one nonredirecting POST, projects only `http_status` and the full
nonempty `errors` subtree, and sends that bounded JSON through anonymous stdin
to `private_provider_crypto.ps1`. The child receives no provider/GitHub tokens.
Only a validated encrypted envelope is written to the exact ignored path
`.temp/private-provider-diag/capture.enc.json`.

The helper uses RSA-3072 OAEP-SHA256, AES-256-GCM, a random 96-bit nonce, 128-bit
tag, and a fixed 256-KiB framed plaintext. Exact stored header bytes are GCM
associated data. The public header carries only algorithms, key fingerprint,
nonce, wrapped AES key and source/run/workflow/repository/query provenance.

The existing registered `ci.yml` gains the target
`staging-private-provider-error-capture`, **no dispatch inputs**. It remains
within the 25-input cap. Confirmation is exactly
`CAPTURE_PRIVATE_WORKER_R2_ERROR_36751791789_ONCE`; first attempt and exact
reviewed SHA are mandatory. Repository variables are
`PRIVATE_PROVIDER_CAPTURE_PUBLIC_KEY` (canonical base64 SPKI DER) and
`PRIVATE_PROVIDER_CAPTURE_REVIEWED_SHA` (40 lowercase hex characters). Neither
variable is a credential. Do not set them until independent review and hosted
checks pass. Public-key fingerprint must also be independently bound to the
operator's ephemeral local session before dispatch.

The capture job has only contents/actions read and the existing Analytics
secret in the capture step. All referenced actions in this job are SHA pinned.
Upload receives no provider secret, uses one exact ciphertext file, one-day
retention, no compression/overwrite, and runs only after successful encryption.
The final step attempts exact-path ciphertext deletion on every outcome.

`private-provider-crypto-tests.yml` is an independent push/PR synthetic lane
covering Ubuntu and Windows without secrets or builds. It does not require
default-branch dispatch registration. Other offline tests are also collected
by the existing Infra suite; native cryptography is skipped unless the hosted
lane explicitly enables it.

## Local operator lifecycle source (not exercised)

`infra/tests/private_provider_operator.py` now implements that lifecycle in a
separate source slice. All commands below are documentation, **not executed**:

```powershell
python infra/tests/private_provider_operator.py keygen <lowercase-session>
python infra/tests/private_provider_operator.py inspect <session> <capture-run-id> <reviewed-full-sha>
python infra/tests/private_provider_operator.py classify <session>
python infra/tests/private_provider_operator.py cleanup <session>
```

Key generation refuses Actions runners, linked session paths and existing
sessions. The private PKCS#8 key is created only inside the new session folder:
Windows gets a protected current-user SID-only inheritable DACL before key
creation; Unix uses directory mode 0700 and atomic file creation mode 0600.
Windows checks the raw descriptor, rejecting NULL/missing/empty DACLs, unknown
or callback ACEs, non-user SIDs, denies and an unprotected session directory.
Hosted Windows synthetic descriptor fixtures cover the allowed policy and
NULL/empty/everyone/deny/inherited-broad alternatives without real keys.
Public SPKI and creation timestamp share that protected folder. No private key
is passed through command arguments/environment or stored in GitHub. Operator
must bind the public fingerprint before setting the two repository variables;
this slice intentionally does not automatically set variables or dispatch.

Inspection requires the authenticated operator `gh` session, the exact reviewed
SHA and first-attempt successful manual run/job. It validates the immutable
artifact's API metadata, SHA-256 digest and age, follows exactly one approved
HTTPS download redirect without bearer credentials, bounds the archive and
reads exactly `capture.enc.json` in memory without extraction. An unfamiliar
download host fails closed; do not widen the suffix list from private error
prose. Full envelope/provenance validation precedes native decryption.

Native decryption checks fingerprint, OAEP/GCM and framing in memory and emits
only seven predeclared categories based on narrow public error grammars. Unknown
fields/messages remain `unclassified`. It never emits decrypted JSON/prose.
The raw interpreter cannot print, execute provider commands or contact network
APIs; the orchestrator's network calls are only authenticated GitHub lifecycle
operations, never Cloudflare or an LLM provider.

Before any inspection API request, the helper records public run/SHA recovery
intent, then stores the authenticated numeric artifact ID **before download**.
Receipts are flushed to an exclusive exact pending file and atomically replaced;
the existing receipt is never truncated in place. POSIX syncs the containing
directory; Windows replacement is atomic but is not a promise against every
power-loss/filesystem failure. A malformed/partial/pending-only receipt fails
closed and retains the key rather than reporting cleanup. Interruption fixtures
also check replacement failure preserves the previous usable coordinates.
Interruption fixtures cover token/provenance/download/ZIP/envelope/decrypt/delete
boundaries, preserving key and recovery receipt. A session
without a receipt may have been dispatched but never inspected: automatic
cleanup refuses to destroy that key because remote state is uncertain. Supply
the actual capture run/SHA through inspection to establish recovery coordinates;
do not erase the key just to make the cleanup status green.

After successful private classification, the exact numeric remote artifact is
deleted and its absence checked. Local ciphertext/key stay in the protected
session for inexpensive offline `classify` iterations without another provider
read. Output explicitly says `LOCAL_RETAINED`, never `CLEANED`, until explicit
`cleanup` retires that evidence. In particular an `unclassified` result does not
destroy the only diagnostic and force a new live capture. No recursive delete
is used. On interruption, `cleanup` uses the public-only receipt to
authenticate the original run and recover remote deletion before removing local
files. Artifact absence is accepted only after that exact authenticated run
attempt has terminal `completed` status; queued/running/waiting runs preserve
the key because a later upload may still occur. Completed failed/cancelled runs
remain recoverable. Synthetic fixtures cover both late-upload rejection and
terminal cancellation/failure absence. A provider cleanup failure retains only encrypted evidence and private
key until retry/24-hour deadline; the next operator session must finish cleanup
before opening another session. There is no background expiry task: the operator
must enforce the documented deadline. Deletion is not a physical secure-wipe
claim. The one-day artifact retention is a fallback, not proof of deletion.

## Remaining blockers before any live use

Do not dispatch merely because the encryption job is source-complete. Without
independent security GO for the operator slice and hosted synthetic evidence,
the complete design's acceptance criteria are not met. Windows ACL handling
and operator download/classification remain source-reviewed only until checked.
Do not substitute plaintext output, assistant
tool ingestion, broad ZIP extraction, or permanent private-key storage. Unknown
provider errors remain confidential and unresolved until a safe interpretation
path exists. An upload failure is not authorization for a second provider read.

Implementation constraints and threat model remain those in
`private-provider-error-capture-design.md`; this capture cannot prove historical
delivery, B readiness, or platform settings/production privacy acceptance.

References: [GitHub artifact API metadata/deletion](https://docs.github.com/en/rest/actions/artifacts),
[Windows directory ACL contract](https://learn.microsoft.com/en-us/dotnet/api/system.security.accesscontrol.directorysecurity),
[native ACL extensions](https://learn.microsoft.com/en-us/dotnet/api/system.io.filesystemaclextensions).
