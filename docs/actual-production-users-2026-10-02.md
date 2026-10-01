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
verification-route mutation. The global sending hold is never changed by this
lane. The root explicitly authorized an optional existing 15-minute one-use
operator grant immediately before each of the two synthetic normal sends. It
requires the separate exact `grant_confirm=GRANT_OWNED_PRODUCTION_TWO_USER_SENDS`,
production issuer, two distinct owner subjects read from only the two addresses
already positively owned by their normal CLI sessions, and SHA-256 of the other
exact owned recipient. It dynamically uses the adopted `send_control.DATABASES`
mapping and invokes the existing `grant_canary.py` once; it is not a generic grant
API. An independent narrow readback requires the unconsumed matching grant. No
grant is needed when the global policy is allowed. Other `send_held` outcomes
remain ordinary user blockers, not permission to evade policy. Sends are single
submissions; an ambiguous
provider outcome is not permission to dispatch the journey again. A successful
CLI send alone never proves delivery: recipient search plus safe archive
download, TEXT/HTML checks and exact attachment bytes are required.

Automatic OpenRouter indexing of eligible synthetic subjects and extracted text
is explicitly authorized; raw ZIPs and attachments are not indexing inputs.
Actual mail commands use the ordinary default diagnostic telemetry so safe
request and trace receipts remain useful on failures. The existing native-login
adapter temporarily disables telemetry during its isolated login ceremony; this
does not disable indexing.

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

### First actual registration execution

Run **36912275906** at merged source **87acaaa** downloaded the existing current
candidate binary and entered actual registration. It stopped with exactly
`chrome_cdp_startup_timeout`, about 111 seconds after the action began: 60 seconds
of route propagation plus 45 seconds of blank-browser CDP startup and cleanup.
The Browser constructor failed before first-party navigation or any registration
request, so neither A nor B was created. The exact original error propagated
only after registration `finally` successfully removed/read back the temporary
A route and required no new private R2 object relative to its baseline. B was
never entered. This is a browser-runtime failure, not an Identity auth rejection.

The original installed-Chrome driver compressed local HTTP readiness, page-target
readiness and WebSocket handshake failures into a timeout. The exact lower-level
cause cannot be reconstructed from that historical log. The narrow next source
change uses Google's official Chrome for Testing binary under repository `.temp`
and records its numeric version, adds only a fixed failing-startup-boundary label,
and starts the same owned blank browser before opening a verification route.
No credential/browser trace, probe workflow or alternative auth path is added.
The next actual registration remains root-dispatched only after its bootstrap
writer has terminated.

Google recommends [Chrome for Testing for browser automation](https://developer.chrome.com/blog/remote-debugging-port)
and a non-default `--user-data-dir`; the owned profile already satisfied the
latter condition. [Chrome Headless documentation](https://developer.chrome.com/docs/automation-and-testing/headless)
confirms the unified headless mode. The runtime substitution is a practical
mitigation, not evidence that the installed Chrome version/security change was
the historical root cause.
