# Staging Identity registration and native amail authorization

Status: **procedure only; no synthetic account or authorization was created by this document** (2026-09-28). This is the narrow Identity gate for the broader [staging mail E2E plan](staging-e2e-plan.md). Reuse the already reviewed [private verification inbox](staging-test-account.md) and its [source review](review-staging-test-inbox.md); do not build another OTP channel or treat this plan as live evidence.

## Decision and important sequencing fact

Use the first-party `https://login-staging.moesegfault.dev/register` page to create and **email-verify** one staging-only synthetic account. Only after verification completes, start the CI-built `amail auth login` against `identity-staging.moesegfault.dev` and `amail-cli-staging`. The initial controlled-local-browser run uses the existing Windows release artifact, not a local Rust/Node build. A future GitHub-hosted browser harness may reuse the same verified account and a staging-only credential secret.

**Do not start `amail auth login` before registration.** The CLI loopback attempt has a 300-second deadline, while mail delivery and the Identity code can take up to ten minutes. More subtly, Identity's password-registration response does not carry an OAuth `authorization_resume_uri`; the Login page's registration completion calls `finishAuthentication` with that original response. Registering through a pending OAuth Login transaction would therefore not reliably resume the CLI. Separate registration and authorization into two browser phases. This is a source-level flow finding, not a claim about a deployed failure.

The Identity first-party handler creates the principal, **verified username**, **unverified email**, and Identity browser session atomically. Its Login UI immediately starts email verification after password registration, and the current public registration policy is `open`. Although the backend can authenticate a verified username while its email remains unverified, using that behavior to bypass the UI verification ceremony is **not** an acceptable staging acceptance result. Do not insert verified D1 rows, borrow a production account/password/token, or call the token endpoint with a synthetic bearer credential.

| Phase | Authority | Completion evidence | Stop if |
| --- | --- | --- | --- |
| Controlled inbox | Exact temporary apex alias route → private staging Email Worker/R2 | One owned enabled literal rule, bounded private object, then route removed | Conflicting/duplicate rule, untrusted/ambiguous message, missing cleanup |
| Account registration | First-party Login → staging Identity | Registration HTTP 201 followed by verification HTTP 200 and `verification_state=verified` | 201 succeeded but mail delayed: recover same account; never blindly register again |
| Native authorization | `amail-cli-staging` → staging Identity → loopback | CLI exit 0 and `authenticated:true`; separate-process `auth status` true | Wrong origin/client, missing callback, issuer/state/nonce/token error |
| Resource authorization | Staging mail API | Authenticated `address list` succeeds with the staging token | 401 after CLI success: investigate Worker issuer/audience/JWKS; never disable checks |

## Preconditions: evidence, not assumptions

1. Identity's staging discovery must return JSON with exact issuer `https://identity-staging.moesegfault.dev`, S256 PKCE, authorization-code/refresh grants, and a staging JWKS. The `amail-cli-staging` client, `http://127.0.0.1/callback` variable-port registration, and three scopes were previously read back from staging D1; see [Identity onboarding](identity-onboarding.md). Recheck only if a later deployment or failure points at them.
2. The [test-inbox runbook](staging-test-account.md) must have passed a hosted native/Wasm Worker build, staging deploy, R2 private-access/lifecycle readback, exact route readback, and one controlled SMTP delivery. The route must be **closed** after that preflight. Open it again only immediately before the real registration. A CI-green source build or R2 bucket alone is not an OTP delivery proof.
3. Use the fixed system alias `amail-e2e@moesegfault.dev` **only as the Identity contact**, not as a user mailbox under `mail-staging.moesegfault.dev` and never as the official `mail@moesegfault.dev` sender. Confirm no other account already owns the verified alias and no conflicting Cloudflare rule exists. The route helper refuses foreign/disabled/duplicate rules; do not override it.
4. Record the CI artifact commit, deployed staging Identity/mail versions, UTC window, and operator in a private run record. Put temporary files only in this repository's ignored `.temp/staging-identity-flow/<run-id>/`. Do not copy an auth database between runners or commit it. The test username should be unique, lowercase ASCII, 3–32 characters; the password should be high-entropy and 15–128 Unicode scalar values, never a production credential. Keep it in a private credential channel or process memory, not a shell command line, transcript, Actions input, or artifact.

## One-time registration in a controlled browser

1. Set an explicit stop time and **open the exact verification route** with `workers/identity-test-inbox/ensure_route.py --apply` only after the Worker and bucket are ready. Verify that the returned rule is enabled, API-owned, literal `to=amail-e2e@moesegfault.dev`, and targets only `amail-identity-test-inbox-staging`. Arrange `--remove` in an operator `finally` path; an interrupted/cancelled runner requires manual rule inventory and removal before further work.
2. In a fresh browser profile/context, navigate directly to `https://login-staging.moesegfault.dev/register`—**not** from a pending amail authorization URL. Enter the synthetic values in fields named `display_name`, `username`, `email`, `password`, and `password_confirm`; select the password submitter `button[name="method"][value="password"]`. Do not attach an avatar, phone, profile text, or unrelated data. Normal browser requests establish `/v1/browser-context` and use the first-party Origin, cookies, CSRF token, and idempotency key; a raw server-side POST without these is not equivalent.
3. Observe registration success and the page's `form.verification-card`. The first-party page automatically calls `POST /v1/me/contacts/{contact_id}/verification-transactions`; its HTTP 201 means the challenge/outbox write was accepted, **not** that mail arrived. The email contact ID comes from the registration response's `identifier_id` (or a fresh contact list's `contact_id`), never the principal ID. Do not print IDs or response bodies into public CI logs. If registration HTTP 201 occurred but the page/mail failed, recover **this account** and challenge; do not create a second account with the same alias. Respect the 60-second resend cooldown and ten-minute challenge expiry.
4. Privately list fresh `verification/` R2 objects for the bounded time window. Fetch only the candidate MIME into ignored `.temp`, verify exact recipient, plausible staging Identity time and visible sender, and use **trusted receiver-added** authentication evidence or independent DKIM/DMARC verification where available. The SMTP envelope sender and headers supplied by the message alone are spoofable. If multiple fresh candidates or provenance ambiguity remain, close the route and investigate—never guess codes against Identity's ten-attempt lockout. Preserve leading zeroes in the eight-digit code.
5. **Remove and read back absence of the exact route before entering the code**, even if later browser actions fail. Enter the vetted code into `form.verification-card input[name="code"]` and submit once; the successful completion endpoint returns HTTP 200 with the contact's `verification_state=verified`. Do not treat a generic success page or R2 receipt alone as verification. Delete the local MIME and exact R2 object(s) immediately afterward; the one-day lifecycle rule is only a backstop. The account remains staging-only and non-privileged.

The operator may perform this first bootstrap in a controlled local browser using a CI-built binary; it is a **deployed workflow probe**, not a local compilation/test-suite run. The only unavoidable human step if the private inbox or browser cannot be safely automated is to enter the short-lived code in that controlled browser. Never place the OTP in `workflow_dispatch` inputs, GitHub issues, chat, or a command-line argument.

## Native CLI authorization after verification

Use a distinct temporary `AMAIL_HOME` and pin all three environment coordinates **before** login. The following is a non-secret configuration template, not an instruction to run now:

```powershell
# Run from the repository root with the CI-built amail.exe on PATH.
$runId = [guid]::NewGuid().ToString('N')
$homePath = Join-Path (Get-Location).Path ".temp\staging-identity-flow\$runId\amail"
New-Item -ItemType Directory -Path $homePath -Force | Out-Null
$env:AMAIL_HOME = $homePath
$env:AMAIL_ISSUER = 'https://identity-staging.moesegfault.dev'
$env:AMAIL_CLIENT_ID = 'amail-cli-staging'
$env:AMAIL_API_BASE = 'https://mail-staging.moesegfault.dev'
$env:AMAIL_REDIRECT_URI = 'http://127.0.0.1/callback'
$env:AMAIL_TELEMETRY = 'off'
amail config   # Check only these public coordinates; do not print auth state or secrets.
amail auth login
amail auth status
amail address list
```

`amail auth login` binds `127.0.0.1:0` before opening the system browser, sends the chosen port in **both** authorization and token requests, and requires the returned callback's exact state and `iss` plus an RS256 ID token with expected issuer/audience/nonce. The browser must be on the **same host** as the CLI's loopback listener. An already-authenticated staging Identity browser session may skip the password form; this still exercises real Authorization Code + S256 PKCE, but it does not independently prove a fresh password sign-in. To prove the latter, use a fresh browser context/profile for this phase, not a production browser profile. Confirm CLI exit 0 and only its final non-secret `authenticated:true`; run `auth status` and one `address list` from separate processes with the same temporary home. A production issuer, `amail-cli`, or `mail.moesegfault.dev` in this run is a **stop**, not a fallback.

### Prepared local CDP helper (not yet executed)

`infra/tests/staging_identity_cdp.py` is a bounded Python 3.14 + installed `websocket-client` helper for this **deployed** browser workflow. It performs first-party DOM interactions in an isolated installed-Chrome profile under `.temp`, not raw Identity registration POSTs. It runs registration and native authorization as **separate invocations/profiles**, captures the CLI's `--no-browser` authorization URL only in process memory, and does not enable HAR, screenshots, console or network-body logging. It **generates its own** unique synthetic username and 256-bit random password, encrypts both with current-user Windows DPAPI into `$runDir/credential.dpapi` **before registration submission**, then decrypts them for the later login phase. No plaintext credential file, password/username command argument or credential log is created. Only the vetted OTP is entered via a hidden prompt. It passes Chrome and CLI a short allowlist of basic OS environment variables plus explicit staging coordinates, suppresses raw output, and prints only fixed stage labels or sanitized stage errors. Its registration phase audits the already-open exact route, **waits at least 60 seconds and audits it again before the first-party registration request**, requires registration HTTP 201 and verification-start HTTP 201, waits for operator-provided trusted OTP, **removes and readbacks the route before code submission**, then requires completion HTTP 200 and `verification_state=verified`; route cleanup still runs if browser teardown fails. The authorization phase validates issuer/client/PKCE challenge/state/nonce/loopback coordinates in memory, tolerates transient CDP execution-context loss during navigation, uses a fresh first-party login page, and requires CLI login success, a separate-process authenticated status, and an authenticated staging `address list` command. These are designed assertions, **not results**.

The 60-second settle is based on a real two-attempt route probe, not folklore: an Email Sending REST canary sent immediately after exact-route API readback was provider-accepted but Cloudflare later classified it as `deliveryFailed` / `routing_unknown_address`; no routing event or private R2 object appeared within 120 seconds, and the route was closed. A second controlled attempt waited **60 seconds after route creation** before sending; the accepted message arrived as a private nonce-tagged MIME object within seconds, after which the exact route was closed/read back and the object deleted. The first failure remains evidence of control-plane/data-plane propagation lag; the second pass does not prove zero future delay. The helper therefore always waits 60 seconds after an enabled-route audit and checks the rule again before causing Identity to send a real verification code. Never burn an Identity code attempt based only on route API readback.

Before invoking it, require: hosted CI native/Wasm/bundle pass for the private inbox Worker, staging deploy and private R2/lifecycle readback, one controlled SMTP inbox probe, and exact-rule absence. Python must be 3.14 on Windows with the already installed `win32crypt` (pywin32) and `websocket-client`; the **same Windows user** must perform registration and later login because the DPAPI blob is user-bound and cannot be copied to a GitHub runner. This current local deployed probe is not the future hosted regression harness. Open the exact route only for the registration window using `ensure_route.py --apply` after the preflight; never run the helper if `--apply`/readback is ambiguous. The helper assumes the CLI artifact is a GitHub-built `amail.exe` already placed under `.temp`, not a local build. From a non-transcribed terminal at the repository root, the future invocation is:

```powershell
# Template only; do not execute until the Worker, route and private inbox are verified.
$runId = [guid]::NewGuid().ToString('N')
$runDir = ".temp/staging-identity-flow/$runId"
python infra/tests/staging_identity_cdp.py register --confirm-staging --run-dir $runDir
# At the hidden OTP prompt: inspect one fresh private MIME, confirm provenance,
# enter its code once; the helper closes the route before submitting it.
# Delete that exact R2 object and any downloaded .temp MIME immediately afterward.
python infra/tests/staging_identity_cdp.py login --confirm-staging --run-dir $runDir --amail .temp/staging-cli/amail.exe
```

Do not paste the code, decrypted credential or URL into chat, PowerShell arguments/transcripts, CI logs or saved browser traces. If the script reports `registration_created_verification_started` but later fails, **do not rerun `register` blindly**: the account exists and the DPAPI blob is the recovery credential. Close/readback the route, recover the same account/transaction through the documented Identity flow, and only then retry the failed phase. If route cleanup is uncertain, stop immediately and reconcile the exact rule before another attempt. Browser profiles, the DPAPI blob and encrypted CLI auth state remain inside `$runDir` until the operator completes evidence capture and cleanup; the script does not delete private R2 objects or retire the account. A local controlled-browser deployed probe uses a CI-built binary and does not replace GitHub Actions cross-platform tests.

For a later GitHub-hosted regression harness, launch `amail auth login --no-browser` with stdout captured **in memory** by the harness; it prints the sensitive authorization URL before waiting at the loopback listener. Validate its origin/client/redirect in memory, pass it to an external headless browser in the **same runner**, and never echo it or enable browser HAR, screenshots, console, network-body tracing, or shell `set -x`. Use an isolated staging-only secret for the already verified synthetic password, and enter it only on `login-staging.moesegfault.dev`. On Linux, first prove a functioning D-Bus/Secret Service keyring for amail's encrypted SQLite session key; on Windows, prove runner Credential Manager works. Do not weaken keyring requirements for CI. Only implement this harness after the one-time registration/inbox path is proven. The CLI's 300-second listener timeout starts at `auth login`, **not** at registration.

## Failure classification and confidential evidence

| Observation | Likely boundary | Next action |
| --- | --- | --- |
| Registration 201; no verification mail | Identity encrypted outbox/provider or exact Email Routing/R2 intake | Keep same account/challenge; inspect bounded correlation and route/object status privately; do not re-register |
| `Contact was not found` on verification start | Wrong/stale contact ID or session ownership | Use returned registration email `identifier_id` or a fresh contact `contact_id`; never substitute principal ID |
| `Authentication failed` on Login password POST (401) | Wrong/suspended staging account, unverified email alias, bad password, or rare credential race | Use the synthetic **username** after email verification; do not blame OAuth registration or retry indefinitely |
| Browser reaches Login but CLI times out | Browser/CLI on different hosts, stale transaction, no callback, or registration mixed into OAuth flow | Separate phases; same-host loopback; inspect only redacted hostname/path and correlation ID |
| CLI login succeeds; mail API returns 401 | Mail Worker JWT issuer/audience/key/token-kind boundary | Stop; compare staging Worker config/discovery and trace IDs; never accept a production token |
| Mail API DNS/5xx after CLI login | Service deployment/availability, not proof of Identity failure | Keep login evidence separate; verify staging `/health` and deploy state |

Store only commit SHA, UTC times, named phase, HTTP status/error code, non-secret correlation IDs, and boolean assertions in [validation evidence](validation.md). Keep the OTP route closed except for the bounded verification window. Do not upload auth SQLite, OS keyring material, MIME, captured URLs, OTPs, cookies, passwords, codes, token claims, or recipient inventory as Actions artifacts. If cleanup is uncertain, stop and reconcile the one exact rule/object before another attempt. Preserve one persistent verified synthetic account only if its ownership, credential rotation, and recovery channel are explicitly assigned; otherwise revoke its sessions and follow the supported account-retirement process rather than deleting D1 rows ad hoc.

## Sources

- Identity first-party [`apps/login/src/pages.ts`](https://github.com/kleedaisuki/moesegfault-indentity/blob/main/apps/login/src/pages.ts), [`apps/login/src/transaction.ts`](https://github.com/kleedaisuki/moesegfault-indentity/blob/main/apps/login/src/transaction.ts), [`crates/identity-worker/src/password.rs`](https://github.com/kleedaisuki/moesegfault-indentity/blob/main/crates/identity-worker/src/password.rs), and [`crates/identity-worker/src/oauth.rs`](https://github.com/kleedaisuki/moesegfault-indentity/blob/main/crates/identity-worker/src/oauth.rs).
- Identity [`openapi/identity.yaml`](https://github.com/kleedaisuki/moesegfault-indentity/blob/main/openapi/identity.yaml) operations `registerWithPassword`, `createContactVerification`, `completeContactVerification`, `authenticateWithPassword`; Identity skill [`references/contact-verification.md`](https://github.com/kleedaisuki/moesegfault-indentity/blob/main/skills/moesegfault-identity/references/contact-verification.md).
- amail [`crates/amail/src/auth.rs`](../crates/amail/src/auth.rs), [private inbox runbook](staging-test-account.md), [mail E2E plan](staging-e2e-plan.md).
