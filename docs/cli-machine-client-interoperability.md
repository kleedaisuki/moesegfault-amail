# CLI machine-client interoperability

Status: design only; no runtime change or deployed compatibility claim.
Date: 2026-10-01. Source baseline: `6f63e1f559bc2d0a5c9d27c40294349fcf77dde1`.
Owner boundary: this new document only. Implementation belongs to the CLI runtime
owner; provider/security policy and deployment admission remain separate.

## Question and evidence boundary

Can amail identify itself consistently on every machine-originated HTTP request
without changing authentication, request semantics, privacy or failure behavior?
The answer is a small shared application identity, not a browser disguise or a
new WAF framework. Whether that identity passes any particular edge policy is a
separate, presently unverified question.

Read alongside [the native canary's ordinary CLI note](native-cloudflare-tracing-canary.md#ordinary-cli-implication-source-inspection-not-a-live-failure),
[the foundation ledger](infrastructure-foundation.md), and
[the maintainer skill](../.agents/skills/amail-maintainer/SKILL.md).

* Cargo.lock selects reqwest **0.12.28**, with the CLI using its blocking client.
  The version-pinned [async implementation](https://github.com/seanmonstar/reqwest/blob/v0.12.28/src/async_impl/client.rs)
  initializes Accept but no User-Agent. Its application/version example and
  `user_agent()` setter provide the appropriate mechanism. The
  [blocking implementation](https://github.com/seanmonstar/reqwest/blob/v0.12.28/src/blocking/client.rs)
  delegates this setting to the inner builder. A shared compile-time identity
  therefore needs no custom header transport.
* CLI default Mail and Identity URLs are `https://mail.moesegfault.dev` and
  `https://identity.moesegfault.dev` (`config.rs:71,76`), not workers.dev.
  The canary's absent-host 1010 is **not evidence of an ordinary CLI login/API
  failure** on either custom domain. Its later 1042 is not healthy live coverage.
* The user clarified that the earlier prefix-username production/staging login
  problem was an **environment mismatch**, not a production authentication bug.
  Do not reopen account debugging or infer a token/login defect from this work.
* Cloudflare's [Browser Integrity Check documentation](https://developers.cloudflare.com/waf/tools/browser-integrity-check/)
  describes missing/nonstandard User-Agent handling. A truthful `amail/0.1.0`
  can still be treated as nonstandard; syntactic validity is not a promise of
  passage. [1010 documentation](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/)
  identifies client-signature denial, not which configurable rule owns a given
  workers.dev response. No security setting is changed here.
* [RFC 9110 section 10.1.5](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.1.5)
  supplies the product/version grammar and recommends avoiding excessive detail.
  Product identification is not authentication: an attacker can copy this value.

## Proposed contract

Exactly one default `User-Agent` field identifies ordinary amail machine clients:

```text
amail/<CARGO_PKG_VERSION>
```

At this baseline the value is `amail/0.1.0`. It is identical across Mail API,
Identity discovery/JWKS/token/refresh/revocation, and telemetry upload. Version
comes from the compiled package, not an environment variable, remote response,
local config, Git working tree, user name or account identifier. Release and
pre-release package versions must remain valid HTTP product-version tokens; add
a unit assertion for this at version changes. A version identifies a package,
not an exact Git SHA; artifact provenance retains that separate responsibility.

Do not include OS/CPU, installation or device ID, user/account/issuer, mailbox,
credentials, URL/query, source path, network address, runtime mode or telemetry
opt-in state. No browser/platform impersonation (`Mozilla`, Chrome, client hints),
Cookie, Origin, Referer, challenge solver, header sweep or fallback profile is
added. The experimental Python canary profile stays a separate diagnostic.
There is no runtime UA override or server trust/authorization rule based on UA.

The smallest coherent implementation is an internal `http` module in the binary
crate (`main.rs` declares modules; there is no existing `lib.rs`). The following
is an illustrative implementation sketch, **not installed runtime code**:

```rust
//! Public product identification only; callers retain their transport policies.

use reqwest::blocking::{Client, ClientBuilder};

/// Stable package identity; never include user, device, or request data.
const USER_AGENT: &str = concat!("amail/", env!("CARGO_PKG_VERSION"));

/// Start an identified client without changing timeout, redirect, TLS, or auth.
///
/// Callers must retain their existing policy, e.g. `.timeout(duration).build()`.
pub(crate) fn builder() -> ClientBuilder {
    Client::builder().user_agent(USER_AGENT)
}
```

Only the identity is centralized. Do not pool all clients globally, unify their
error handling or add a policy enum/config framework. Do not move bearer tokens
into default headers. Call-site timeouts and redirect settings remain where their
semantics belong. Failure to construct a client propagates through the same
existing path; no panic, UA-less fallback, browser fallback or automatic request
retry is introduced. The constant is static and needs no per-request allocation.

## Complete source migration inventory

Line numbers refer to the baseline and may move as the runtime owner integrates.

| Production call site | Requests using that client | Existing policy to preserve |
| --- | --- | --- |
| `api.rs:269`, `Api::new` | All ordinary Mail API requests, including JSON, ZIP, search and mutation | 30 s; current reqwest redirect behavior; per-request bearer, traceparent and optional idempotency |
| `auth.rs:370`, `login` | Discovery, code exchange, ID-token JWKS fetch | 20 s; existing redirect/TLS/issuer/PKCE/nonce checks |
| `auth.rs:552`, `access_token` refresh | Discovery and rotating refresh-token exchange | 20 s; refresh lock, in-progress marker, uncertain-outcome clearing; no application retry |
| `auth.rs:611`, `logout` | Discovery and optional revocation | 8 s; remote failure does not prevent local credential clearing |
| `telemetry/upload.rs:18`, `run` | One bounded upload of selected legacy events | 5 s; explicitly no redirects; existing delivery receipts, acknowledgement bound and failure isolation |

Discovery/JWKS functions accept the client's reference, so they must not create
another hidden builder. Browser launch and the incoming loopback callback are
not machine-originated reqwest clients and must not acquire spoofed headers.
Telemetry opt-out still prevents diagnostic store/upload work, not ordinary
Mail/Identity HTTP identification or automatic server-side semantic indexing.

Existing telemetry tests inject independent clients via `run_with`. Their success
does not prove `run` uses the shared identity: the owner must additionally test
its actual production construction recipe, rather than only injected clients.
Use a fresh source inventory at integration to catch added clients.

### Explicit diagnostic decision

`src/bin/staging_http_compare.rs:59` is feature-gated, not a sixth ordinary client.
It currently claims to match the ordinary reqwest client but intentionally stops
redirects and restricts its synthetic target. **Leave it unchanged in the first
ordinary-client patch**, preserving historical diagnostic evidence. Until the
separate diagnostic owner updates it, its result must be described as a legacy
UA-less transport profile, not a parity test of the changed ordinary CLI.

A separately reviewed diagnostic update may reuse the same compile-time identity
without changing target restrictions or redirect stopping. It must explicitly
label the new profile in evidence and not reinterpret old runs. The Python
workers.dev canary identity is never copied into business clients automatically.

## Deterministic hosted protocol verification plan

This is an implementation-ready plan, **not executed test evidence**. No provider
request, login, user account, real token, Mail object or deployment is required.
Run on the existing GitHub-hosted CLI matrix (Windows/Linux/macOS), through
`cargo test -p amail --locked --all-targets`; never on this workstation. Keep test
state under checkout-root `.temp`, as existing `journal_resilience.rs` does.
Do not build/install locally or add a special privileged Actions lane.

### Hermetic fixture and construction seams

Use a Rust loopback HTTP/1.1 fixture bound to `127.0.0.1:0`, with bounded header
and body reads, read/write timeouts, explicit Content-Length responses and
`Connection: close`. Parse header names case-insensitively; assert field count
as well as value, not raw capitalization or header order. Assert full synthetic
body/method/path as appropriate. Do not emit captured raw headers in failures:
report the profile and named assertion, with no authorization/body dump.

Disable proxies **only in the test builder** with `.no_proxy()` for isolation;
do not mutate global environment variables across parallel tests or alter the
production proxy default. Every Location points to a second fixture listener;
there are no public hosts, DNS lookups, real secrets or TLS certificate bypasses.
Use connection counts as the retry/redirect oracle, not timing/sleep guesses.

Prefer exposing small private construction functions in the owning modules when
needed to test exactly the recipe used by production: API builder; Identity
builder with the existing duration argument (login and refresh share 20 s,
logout uses 8 s); upload builder with no redirects. Tests may apply `.no_proxy()`
before `.build()`. Keep those functions internal, not new public APIs or runtime
configuration seams. Review that each of the five production call sites calls
that tested construction function. Testing five independently copied builder
chains or just the shared helper is insufficient integration evidence.

For Identity, send synthetic discovery GET and token/revocation form POSTs using
its actual construction function to this fixture, **not** `login`/`access_token`
on a real account. This demonstrates transport headers and form preservation;
it deliberately does not claim successful OIDC login/refresh/revocation. Do not
weaken `discover`'s HTTPS/issuer checks to accommodate the HTTP fixture. Full
successful cryptographic auth workflow coverage remains the existing owner's
separate concern; no test-only insecure endpoint branch is introduced.

### Required assertions

| Test/profile | Wire and compatibility assertion |
| --- | --- |
| Shared helper | Exactly one UA equal to compile-time value on GET and POST; valid product/version; remains static across two unrelated synthetic URLs |
| API / 30 s recipe | Same UA on representative JSON POST and ZIP POST; original Content-Type/body/bearer/traceparent/Idempotency-Key; keep default redirect recipe |
| Login / 20 s recipe | Same UA on discovery GET, JWKS GET and code-exchange form POST; synthetic form fields unchanged |
| Refresh / 20 s recipe | Same UA on discovery GET and refresh form POST; no extra OAuth parameters or client identity substitution |
| Logout / 8 s recipe | Same UA on discovery GET and revocation form POST; synthetic token_type_hint and client_id unchanged |
| Upload / 5 s recipe | Same UA on actual upload fixture path; legacy JSON schema byte/field semantics unchanged; no UA inside event payload; bearer remains request-specific |
| UA-less legacy control | Raw reqwest 0.12.28 builder without `.user_agent()` sends no UA; same fixture verifies the contrast, not a provider verdict |
| Existing error cases | 401/403 JSON, HTML denial, truncated response and transport close retain existing outcome/output/journal behavior; no new fallback request |
| Upload redirect | Fixture 302/307 with second-listener Location: second listener sees zero requests; existing receipt/outcome expectations unchanged |
| Non-upload redirect | A synthetic GET redirect preserves the existing default behavior and identity; no policy change folded into UA work |
| Privacy/failure isolation | Synthetic secret markers absent from stdout/stderr and receipts; telemetry opt-out and failed upload do not change foreground result |

No application-level automatic retry is added. Do not overclaim absence of every
reqwest internal transport retry; preserve pinned transport behavior and test
request counts for completed fixture responses. Refresh replay protection and
logout local deletion are covered by existing/focused state tests, not by UA
header assertions. If those tests need additional fixtures, the runtime owner
must scope them independently rather than weakening contracts.

No wall-clock test should wait 30/20/8/5 seconds merely to infer the unchanged
settings. Preserve/review the production duration arguments; use short explicit
test-only timeouts for fixture failure bounds. All test threads join within a
bounded time; unexpected second requests fail with a named invariant.

## Compatible rollout and unresolved boundary

1. Runtime owner implements the shared identity plus all five source paths in
   one coherent change; keeps diagnostic parity status explicit.
2. Independent review checks the complete builder inventory, unchanged request
   policy, form/ZIP/JSON contracts, privacy and auth-failure behavior.
3. Hosted protocol/native matrix passes on the exact candidate SHA. A docs-only
   commit, source scan or helper-only test is not runtime compatibility evidence.
4. No security policy is made dependent on the header and no old CLI version is
   rejected for missing UA. Previously deployed binaries retain their behavior.
5. Only if separately authorized later, a bounded custom-domain interoperability
   observation can distinguish edge admission from application authorization.
   No provider operation is admitted by this document. Machine UA success would
   not prove authenticated Mail behavior; a denial would not justify a profile
   sweep, credential reset, browser impersonation or broad WAF bypass.

The wire addition is deliberate and may affect caches/policies keyed on UA.
There are no CLI flags/output/schema/storage changes, dependency additions or
server auth changes. Uniform product identification removes per-client special
cases while preserving each client's meaningful transport and failure policy.
If an owned edge still rejects a truthful machine client, identify the actual
rule/hostname and investigate that boundary separately; do not turn app identity
into a security credential. No academic bot-detection/fingerprinting machinery
is adopted: adversarial identification research concerns a different problem
than this bounded, unauthenticated product-description contract.

## Work performed for this design

Inspected the maintainer skill, foundation ledger, native canary ordinary-client
note, CLI config and all builder sites, existing HTTP fixture and upload test
seams, and hosted matrix command. Read exact reqwest 0.12.28 upstream source,
Cloudflare BIC/1010 primary documentation and HTTP standard above. Performed
static document/diff checks only. No runtime test, build, install, account access,
provider API read/write, token creation, deployment or live service request was performed.
