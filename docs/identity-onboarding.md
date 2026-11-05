# Native Identity integration

amail is a pre-registered native public OIDC client, not a confidential client.
Production issuer is https://identity.moesegfault.dev with client amail-cli;
staging issuer is https://identity-staging.moesegfault.dev with amail-cli-staging.
login.moesegfault.dev is the login SPA, not discovery. Never copy production
credentials into staging or diagnose a realm mismatch as a password defect.

Default login uses discovery with exact pinned issuer, Authorization Code + S256 PKCE, ephemeral
127.0.0.1 loopback redirect and registered native-loopback-any-port policy.
The Identity owner provisions the exact client/redirect registration; no dynamic
self-registration or invented mail scopes. The native client has no client secret.
Current scopes are openid/profile/offline_access.

## Remote-terminal device login

`amail login --device-code` (also `amail auth login --device-code`) selects
[RFC 8628](https://www.rfc-editor.org/rfc/rfc8628.html) for a terminal whose browser
cannot reach its loopback callback. Add `--no-browser` to display the verification
address and human code without launching a browser. Plain `amail login` and its
existing `--no-browser` option retain PKCE semantics; the latter does not change
the grant. Use the installed CLI's help to check support before requesting this
new option from an older release.

Discovery must advertise both `device_authorization_endpoint` and the device grant.
Production and staging discovery advertised both on 2026-11-05. This does not enable
an individual client: Identity migration `0012_device_authorization.sql` defaults
existing registrations to `device_authorization_enabled=0`. The Identity operator
must explicitly enable `amail-cli` and `amail-cli-staging` in their respective
environment migration streams, preserving their client IDs, sector identifiers,
subject-salt revisions, scopes and existing loopback redirects. A new client ID
would change pairwise subjects and Mail ownership; do not create one as a shortcut.
The upstream registration migrations currently establish the original clients,
not this opt-in. The reviewed desired manifests are
[`client-production.json`](../infra/identity/client-production.json) and
[`client-staging.json`](../infra/identity/client-staging.json). For these existing
clients, import the exact environment's
[`enable-device-code-production.sql`](../infra/identity/enable-device-code-production.sql)
or [`enable-device-code-staging.sql`](../infra/identity/enable-device-code-staging.sql)
as a new migration in Identity's corresponding environment stream, after shared
schema 0012, and apply through its normal deployment lane. Do not rerun the
create-only client generator against an existing registration. These files express
desired configuration, not proof that the live client was updated. See the
[Identity device integration contract](https://github.com/kleedaisuki/moesegfault-indentity/blob/main/skills/moesegfault-identity/references/device-login.md).

The pending device secret lives only in the initiating process. The human opens
the verification address on their own device, compares the code and registered
application name with this terminal, and explicitly approves or denies. A complete
verification link pre-fills the code; opening it is not approval. Never approve a
code from someone else's unsolicited message. As
[RFC 10027](https://www.rfc-editor.org/rfc/rfc10027.html) explains, authentic sign-in
and even a Passkey do not prove that the requester controls the intended terminal.

Polling uses the issuer's interval and absolute expiry, waits before the first
poll, permanently increases the interval on `slow_down`, and backs off connection
timeouts. Denial and expiry end the attempt rather than starting another login.
Closing the initiating CLI cancels its pending daemon login; a later browser
approval cannot create a hidden local session for that disconnected request.
This grant has no callback, PKCE verifier or OIDC nonce. The ID token still needs
RS256/JWKS, exact issuer/client audience, time, subject and `token_use=id`
validation. Successful login means the validated token set reached the same
protected local storage as PKCE, not merely that the browser approved. Refresh
rotation and logout use the existing lifecycle below. Never put device secrets,
human codes, complete verification links or tokens in telemetry.

Device login establishes identity, not a billing authorization. Subscription
changes use `amail billing subscribe/manage --device-code` for a similar short-code
handoff: Mail resolves the human code to the original hosted Subscribe session,
where the human reviews and explicitly confirms the operation. It issues no OAuth
tokens and preserves existing billing idempotency/session recovery. Neither code
entry, a new login nor an existing session authorizes spending by itself. See the
[billing workflow](../skills/amail/references/billing.md).

Billing navigation requires Mail migration `0020_billing_device_navigation.sql`
before deploying the compatible Worker. It only adds an optional short code to
existing owner-scoped sessions; old clients and sessions keep their direct hosted
links. The code expires with that session and resolves only while it is pending.
Neither its public lookup page nor redirect changes entitlements; the existing
service-authenticated Subscribe receipt remains authoritative. Apply this through
the next normal deployment lane, not historical version-pinned recovery writers.

## Shared token lifecycle

Validate callback state, response iss, nonce, signature/audience/time claims and
one-use code; reject duplicate parameters and wrong origin/path. Mail Worker accepts
only valid RS256 Identity access tokens with fixed issuer, exact native-client aud
and token_use=access. Ownership is immutable (issuer,sub), not email/profile claims.
No shortcuts through unverified registration, direct JWTs or D1 account edits.

[Auth storage](auth-storage.md) describes bounded OS-keyring keys, encrypted SQLite,
refresh serialization/crash marker and callback acknowledgment after persistence.
Logout removes local state even when best-effort remote revocation fails; it does
not claim browser SSO logout. Keep credentials/codes/callback queries out of telemetry.

Normal owned-account production and staging PKCE journeys passed within the scope
in [validation](validation.md). Synthetic accounts do not prove the owner's account
journey or every rotation/concurrency/revocation edge. The owner's original account
belongs to production Identity. Register dedicated test principals through normal
browser verification only when a new owned-account journey is actually needed;
use the protected exact-route verification inbox and isolated hosted CLI home.
Private destination/OTP/OAuth URL never appears in logs or repository.
