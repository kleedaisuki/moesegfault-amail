# Explicit realms for native Mail acceptance

## Scope and reason

The deployed staging harness already owns actual CLI PKCE, first-party browser
login, SMTP DATA receipts, immutable ZIP comparisons, composable searches and
bounded fixture cleanup. Reuse these operations for a future held production
acceptance run instead of cloning a second harness or monkeypatching module globals.
This change supplies coordinates only. It does not dispatch any production probe,
register an account, grant sending, deploy a Worker or create a release.

## Contract

`infra/tests/acceptance_realm.py` defines an immutable `AcceptanceRealm` with
explicit Mail, Identity, Login and Account origins, OIDC client, ingress Worker,
D1 database, sending-domain registration and synthetic SMTP sender. The default
singleton preserves every existing staging coordinate and public helper entrypoint.
Production public origins and names are exact first-party constants, not merely
syntactically valid HTTPS URLs. Production D1 and sending registration must be
explicit and distinct from staging. Selecting production never imports credentials.

Native production login requires an explicit credential tuple and expected contact.
Missing/malformed material fails before directory creation, CLI or Chrome startup;
production cannot read staging's local DPAPI credential blob. Browser navigation,
origin-before-typing and PKCE request validation share the same selected realm.
CLI and Chrome still inherit only the existing OS-variable allowlist; provider
secrets cannot enter child environments and CLI telemetry remains off for fixtures.

SMTP sender, provider route ownership, D1 owner issuer, ZIP manifest sender,
search sender and **all cleanup layers** receive the same explicit realm. A partial
adapter draft omitted realm propagation through cleanup_run -> cleanup_messages ->
cleanup_verify, causing production receipt/ZIP checks to silently select staging.
That defect was corrected before hosted submission and has dedicated mock tests.

Existing helper names and staging top-level command behavior remain compatible.
Only explicit callers can choose production. Constructor-bypassing browser mocks
now initialize realm state, and the existing failed-message mock accepts added
keyword context so it still exercises its intended failure rather than TypeError.

## Verification

Eleven new synthetic contracts cover immutability, exact origin/name pinning,
resource separation, malformed coordinates, default CLI compatibility/environment
filtering, PKCE realm discrimination, credential loading isolation, login-origin
protection and the three cleanup propagation edges. No provider, browser or CLI
is invoked by these tests. The existing infrastructure job discovers them without
workflow changes. Local work is limited to Python AST/whitespace/source review;
all project test execution remains on GitHub Actions. Hosted acceptance is pending
until exact source CI completes; these contracts alone do not establish production
OIDC client readiness, SMTP delivery, privacy containment or CPU suitability.

## Platform grounding

- [RFC 8252](https://www.rfc-editor.org/rfc/rfc8252.html): production native users
  continue to authorize through the external browser with loopback PKCE, not by
  giving passwords to amail. Automated browser typing is restricted to synthetic
  acceptance accounts and is not a new user authentication mechanism.
- [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html): issuer-bound authorization
  and explicit client/redirect validation motivate preserving the existing PKCE
  checks while switching the configured first-party issuer.

Neither reference proves a test harness is secure by itself. Exact origin pinning,
credential non-inheritance and discriminating negative tests are concrete safeguards
at the harness boundary; serving provenance/containment remain separate deployment
obligations. No speculative authentication abstraction is introduced.

### First hosted result and mock correction

Run 36823925172 executed 1,004 infrastructure tests; one existing failed-add
ordering fixture did not reach its snapshot side effect because that mock omitted
the newly propagated realm keyword. All eleven new realm tests passed. The mock
signature now accepts keyword context, restoring the real snapshot-before-cleanup
failure path; production snapshot behavior is unchanged. This failed run is not
accepted evidence. Automatic corrected-source CI must pass before merge.
