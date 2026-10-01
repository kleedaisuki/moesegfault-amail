# Actual owned production users

## Purpose and ownership

The user authorized normal online production execution, including creating
dedicated synthetic Identity principals and delegated real-user operation.
This lane executes the existing public CLI; it does not introduce Mail API
shortcuts, JWT bypasses, D1 edits, local toolchain builds, or an audit framework.
The root remains the sole deployment/control-plane writer and must dispatch
registration only after the bootstrap writer has terminated.

Two independently generated accounts are protected by repository Secrets
`PRODUCTION_ACTOR_A_USERNAME`, `PRODUCTION_ACTOR_A_PASSWORD`,
`PRODUCTION_ACTOR_B_USERNAME`, and `PRODUCTION_ACTOR_B_PASSWORD`.
They are not a copy of a human or staging account. Registration uses normal
production Login pages and the existing controlled private verification inbox.
The two owned apex test contacts have temporary exact routes; each route is
closed before submitting its vetted OTP. Credentials, OTPs, OAuth URLs and MIME
are never written to logs. Existing human profiles and the local global amail
keyring are never used; actual authenticated CLI actions run on isolated hosted
Windows. A disposable runner's encrypted token store is not a durable credential
backup; the dedicated Identity credentials remain protected in GitHub Secrets.

`NativeProduction` contains only public native-login coordinates. It deliberately
does not fabricate unused D1 UUIDs or Email Sending tags merely to satisfy a
larger dormant acceptance-realm model.

## Execution and failure semantics

Workflow `actual-production-users.yml` has two explicit phases:

- `register`: create and verify both dedicated production accounts using the
  first-party browser UI. A partial account registration must be recovered as
  the same account; never dispatch fresh credentials to hide a partial result.
- `journey`: native PKCE login, own-address registration/reuse, TEXT+HTML+asset
  pack, A-to-B notification, B-to-A research reply, real received archives,
  owner-positive/foreign-negative object access, composed filters, regex/case,
  explicit read/unread, archive export, automatic semantic indexing, and deletion
  of only the two intended owned inbound deliveries.

Both require `confirm=RUN_OWNED_PRODUCTION_USERS`. The root coordinates temporary
verification-route mutation. Sending policy is not changed by this lane. A
`send_held` outcome is an actual normal-user blocker and must be resolved by the
authorized operator, not bypassed. Sends are single submissions; an ambiguous
provider outcome is not permission to dispatch the journey again. A successful
CLI send alone never proves delivery: recipient search plus safe archive
download, TEXT/HTML checks and exact attachment bytes are required.

Automatic OpenRouter indexing of eligible synthetic subjects and extracted text
is explicitly authorized; raw ZIPs and attachments are not indexing inputs.
Ordinary diagnostic telemetry is disabled, which does not disable indexing.

User B is a delegated independent actor. Its authored research reply is retained
under `infra/user-drafts/reply/`. The reply deliberately distinguishes content
integrity, delivery, authorization and read state as separate observations.

## Observed evidence

Candidate artifact from release build run **36909041053**, source **9037997**,
Windows target `x86_64-pc-windows-msvc`, reports `amail 0.1.0`.
On 2026-10-02 local normal-use execution (no build/test/tool install) successfully
ran native `pack` and `unpack` on the synthetic B TEXT, HTML and attachment.
SHA-256 comparisons matched all three authored/extracted files. Task artifacts
remain under root `.temp/actual-production-offline` and
`.temp/actual-production-artifact`, not outside the repository. This establishes
offline native ZIP usability only; it does not establish online registration,
authentication, sending or receipt.

Online observations will be appended with run IDs, public phase labels and
conclusions only, not usernames, addresses, mail subjects, bodies or credentials.
