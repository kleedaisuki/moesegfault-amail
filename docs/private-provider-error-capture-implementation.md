# Private provider error capture implementation boundary

Status: source implementation awaiting independent security review and hosted
Linux/Windows synthetic checks. **Not authorized for a live capture.** No keys,
local cryptographic tests, provider reads, or private artifacts were produced.

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

## Remaining blockers before any live use

This source slice deliberately does **not** generate operator keys, download
artifacts, or expose decrypted provider prose. A reviewed local operator helper
is still required for current-user-only private-key ACLs, authenticated artifact
run/SHA/digest validation, bounded exact ZIP-member reads, envelope/provenance
validation before interpretation, predeclared offline classification, remote
artifact deletion and exact local 24-hour cleanup. The synthetic decryption
routine is a test, not that operator helper.

Do not dispatch merely because the encryption job is source-complete. Without
that operator lifecycle and independent security GO, the complete design's
acceptance criteria are not met. Do not substitute plaintext output, assistant
tool ingestion, broad ZIP extraction, or permanent private-key storage. Unknown
provider errors remain confidential and unresolved until a safe interpretation
path exists. An upload failure is not authorization for a second provider read.

Implementation constraints and threat model remain those in
`private-provider-error-capture-design.md`; this capture cannot prove historical
delivery, B readiness, or platform settings/production privacy acceptance.
