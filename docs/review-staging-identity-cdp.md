# Independent review: staging Identity CDP probe (2026-09-28)

Scope: reviewed the frozen `infra/tests/staging_identity_cdp.py` and `docs/staging-identity-flow.md`, with the helper's referenced first-party registration/PKCE contract. This is a static test-harness review: no browser, route, account, OTP or CLI execution was performed. Findings below concern whether the probe can safely generate trustworthy staging evidence, not the Identity service itself.

## Resolved in source — Browser teardown and exact-route cleanup

The first `registration()` revision called `browser.close()` before route cleanup in one `finally`, so a Chrome/WebSocket teardown exception could skip `--remove`. The revised code independently catches teardown failure, then always attempts route audit/removal and reports sanitized combined stage errors (`staging_identity_cdp.py:494-513`). `Browser.__init__` now kills a launched Chrome process if CDP connect/enable fails before returning an instance (`staging_identity_cdp.py:218-239`). This closes the identified source-level leak path. A provider outage can still prevent route removal; the runbook correctly requires manual inventory and closure in that case.

## Resolved in source — Chrome environment data minimization

The first helper copied almost the entire environment through a short denylist, which could pass a confidential variable with an unexpected name into Chrome. `browser_environment()` now uses a short platform-basic allowlist (`staging_identity_cdp.py:150-165`) and the CLI's staging coordinates are explicitly added later. A mock test plants an unknown confidential variable and verifies exclusion. No arbitrary project secret is inherited by the current helper.

## Resolved in source — PKCE request shape assertion

The initial URL validation checked `code_challenge_method=S256` but not the proof material. The revised `valid_authorization_url` checks one base64url-shaped `state`, `nonce`, and `code_challenge`, exact staging issuer/client/response type/scopes, and an uncredentialed IPv4 loopback callback without query/fragment (`staging_identity_cdp.py:559-589`). It does so in memory without logging field values. Mock tests cover missing/malformed fields. This makes the harness's named PKCE-request assertion materially stronger; successful CLI/token flow remains the final proof of integration.

## Positive controls and acceptance limits

- Registration uses a first-party staging Login page in a fresh isolated Chrome profile, not a raw privileged Identity API call. A random staging username/password is stored as a same-user DPAPI blob before form submission; no plaintext credential file or command-line password is created. A separate login invocation/profile prevents accidental reuse of registration's Identity session.
- The helper validates the staging issuer/client/mail API coordinates and a loopback redirect, captures the CLI authorization URL in memory, suppresses raw Chrome/CLI output, and confirms login via CLI exit, a separate-process status check, and authenticated staging `address list`. `Network.responseReceived` observations are restricted to staging Identity origin and reviewed paths; completion checks HTTP 200 and `verification_state=verified` rather than trusting UI text.
- The mandatory 60-second route settle and second route audit precede registration. The normal path removes/readbacks the route **before** entering the vetted OTP; the operator—not the script—must independently establish MIME provenance and delete the private object. No test-harness success can establish that external SMTP delivery, Chrome/DPAPI behavior, or a provider route is live until the controlled probe actually runs.
