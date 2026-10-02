# Native Identity integration

amail is a pre-registered native public OIDC client, not a confidential client.
Production issuer is https://identity.moesegfault.dev with client amail-cli;
staging issuer is https://identity-staging.moesegfault.dev with amail-cli-staging.
login.moesegfault.dev is the login SPA, not discovery. Never copy production
credentials into staging or diagnose a realm mismatch as a password defect.

Use discovery with exact pinned issuer, Authorization Code + S256 PKCE, ephemeral
127.0.0.1 loopback redirect and registered native-loopback-any-port policy.
The Identity owner provisions the exact client/redirect registration; no dynamic
self-registration or invented mail scopes. The native client has no client secret.
Current scopes are openid/profile/offline_access.

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
