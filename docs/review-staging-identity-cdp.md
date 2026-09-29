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

## Hosted CDP startup follow-up (2026-09-29)

Reviewed the failure in [hosted run 36550428480](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36550428480), the prior successful native-login stage in [run 36533465672](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36533465672), and source change `475aad4`. The failed run reached `identity_chrome_cdp_unavailable` about 13 seconds after entering the Python harness; the former 12-second `_connect` deadline explains **when** it stopped, but does not distinguish slow startup from an early Chrome exit or local CDP failure. The earlier hosted login passed with the same source and runner image. No address was created in this latest run; its exact alias was separately reconciled as clean (see `validation.md`).

**Assessment: no substantive source-level blocker in the narrow mitigation.** The revised 45-second wait is finite, applies only while attaching to a fresh localhost Chrome page before typing credentials or mutating mail, and remains inside the CLI's 300-second loopback lifetime under normal continuation. It preserves the exact WebSocket host/port and proxy-bypass checks. A browser that exits early and a still-running browser that times out now receive distinct fixed labels; browser stdout/stderr stay suppressed. Constructor failure kills and reaps the process, and the hosted wrapper still cleans the private run directory. There is no automatic retry of login or address registration, no OIDC bypass, and no token injection.

The new mock tests cover attachment after the old deadline, early exit, timeout, wrong-port target, and process cleanup. Their real Chrome/runner behavior is **not** verified by static review; GitHub-hosted tests and one explicitly guarded deployed login are required. If the next run reports `chrome_exited_before_cdp` or repeats a startup timeout, investigate that distinct boundary rather than extending timeouts indefinitely or exposing raw browser logs. This review did not execute a browser, tests, Identity calls, address creation, SMTP, or Cloudflare mutation.

### Hosted mock-adapter correction

The first hosted infrastructure run after `475aad4` ([36551356686](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36551356686)) exposed a test-only fixture error: its synthetic `websocket` module lacked `create_connection` and `WebSocketException`, which the new CDP tests reference. Change `c5529ae` adds those two attributes only when the optional package has not already been loaded. Static re-review finds no production-harness or login-contract change; the real staging browser job installs `websocket-client` and runs in a separate process. The tests must pass in hosted CI before interpreting any subsequent deployed CDP result. This correction did not run a browser or mutate staging services.

## Direct Chrome clarification and next hosted gate

The current harness **already controls an installed Chrome process directly** through its localhost DevTools connection; it does not call a browser-use plugin or reuse the operator's interactive Chrome profile. Thus a broken external Chrome-use plugin is not, by itself, a reason to replace this driver with Playwright or another browser layer. The next useful discriminator is one hosted run after the corrected mock-adapter CI gate, observing whether the bounded startup succeeds or reports one of the fixed early-exit/timeout labels. Do not infer an Identity or PKCE defect from Chrome startup alone.

If a future browser-layer replacement is justified by repeated hosted startup evidence, review it against these preservation requirements before a live attempt:

1. Use the runner's installed Chrome with a fresh isolated profile and bounded startup, navigation, and teardown times. Keep browser dependency changes scoped to the explicitly confirmed Windows staging job and synthetic infrastructure tests; do not silently download a browser or broaden production workflow permissions.
2. Keep the authorization URL entirely in process memory. Validate exact staging issuer/client, authorization-code response, S256 challenge, single state/nonce, expected scopes, and IPv4 loopback callback **before** navigating. The native CLI must still independently validate callback state/issuer, ID token issuer/audience/nonce, and PKCE token exchange; browser automation must not inject tokens or bypass the first-party Login page.
3. Observe only actual Identity `POST` responses for registration, verification start, and completion. Correlate request method with response, so a CORS `OPTIONS 204` cannot stand in for a successful `POST 201/200`. Treat a missing response after submission as ambiguous account state, not proof that registration did not happen.
4. Type the synthetic credential only after verifying the exact Login origin. Suppress raw browser/CLI/provider output and disable screenshots, HAR, tracing, console capture, and response-body logging. Preserve only fixed phase/status labels; use the existing allowlisted child environment rather than inheriting GitHub secrets into Chrome.
5. Close the exact temporary OTP route in a `finally` path independent of browser teardown, then read back absence before entering the vetted code. Reap the browser and CLI listener even on attach or navigation failure. A failed cleanup must remain a stop condition, never an automatic rerun trigger.

This is a risk checklist, **not** evidence that a replacement has been implemented or that the current hosted browser path now succeeds. No local or hosted browser execution was performed for this note.
