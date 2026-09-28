# amail native Identity onboarding

Status (2026-09-28): **both Identity clients are registered; a CI-built Windows amail completed production browser login and a later cross-process token refresh after access-token expiry**. Authenticated mail API operations remain untested because the mail API host is not yet deployed; refresh-rotation edge cases, logout/revocation, and staging-account login remain separate acceptance gates.

## Decision and trust boundary

`amail` is an installed **public/native** OpenID Connect client. The human authorizes only the browser login; the CLI holds the resulting token set in platform credential storage and performs mail operations. The mail Worker is a resource service for this *same* OAuth `client_id`: Identity currently issues access-token `aud` equal to the OAuth client ID, not an independently configurable API audience. Never point OIDC discovery at the Login SPA or accept a different audience to make an integration appear to work.

| Environment | Fixed issuer | Registered client ID | Mail API | Sector |
| --- | --- | --- | --- | --- |
| Production | `https://identity.moesegfault.dev` | `amail-cli` | `https://mail.moesegfault.dev` | `amail.moesegfault.dev` |
| Staging | `https://identity-staging.moesegfault.dev` | `amail-cli-staging` | staging mail origin, once deployed | `amail-staging.moesegfault.dev` |

Both environment-specific client migrations have now been applied; the manifests under `infra/identity/` document their intended public metadata. Pairwise `sub` is scoped to the sector. Changing the sector later changes user identity from the application's perspective; persist account mapping by `(issuer, sub)`, never email or username. No `mail` OAuth scope exists. The granted scopes are `openid`, `profile`, and `offline_access`; the latter is needed for unattended agent operations after the one human login. Mailbox-level authorization belongs to the mail Worker.

## Registration metadata and callback contract

The two non-secret manifests are `infra/identity/client-production.json` and `infra/identity/client-staging.json`. Both request:

- `client_type=native`, `token_endpoint_auth_method=none`, **no** public JWK or bundled secret;
- `subject_salt_revision=1`, the environment-specific sector above;
- `http://127.0.0.1/callback` with `match_mode=native_loopback_any_port`;
- no post-logout redirect: the CLI clears its local token set and attempts refresh-token revocation, but does not initiate browser SSO logout;
- scopes in the exact order `openid`, `profile`, `offline_access`.

Identity's generator only permits variable-port loopback registration for native clients on `http://127.0.0.1` or `http://[::1]`, where the **registered URI has no port**. Requested redirect URIs must still have the same host, path, and query. `localhost` is not interchangeable. The CLI now defaults to the portless `http://127.0.0.1/callback` template, binds `127.0.0.1:0` before opening the system browser, then uses the selected ephemeral port in both the authorization and token-exchange requests. `AMAIL_REDIRECT_URI` can override this only with a registered loopback URI; a fixed port is supported but no longer required. The selected port is not an authorization secret.

The CLI uses the reviewed and remotely verified production client ID `amail-cli` and portless loopback template as convention defaults. Staging must explicitly pair `AMAIL_ISSUER=https://identity-staging.moesegfault.dev`, a staging mail API origin, and `AMAIL_CLIENT_ID=amail-cli-staging` (or equivalent `config.toml` fields). Production mail Worker must pin `IDENTITY_ISSUER=https://identity.moesegfault.dev` and accepted audience `amail-cli`; staging must pair its own issuer and audience. No cross-environment fallback.

## Provisioning handoff — Identity repository owner only

Identity repository: `D:/Code/moesegfault-indentity` at the time of investigation. Its `docs/integrating-app.md` defines the workflow. Migrations create scope rows but **do not create application clients**. There is no dynamic client registration endpoint or account-level provisioning API. Do not mutate production D1 ad hoc.

1. Copy each manifest into the Identity repository's `.temp/` directory. Run `node scripts/generate-oauth-client-migration.mjs .temp/<manifest>.json` **from that repository**. The generator validates metadata and emits create-only SQL in `.temp/` without database access.
2. Review generated SQL, particularly client ID, redirect match mode, sector, scopes, security audit event, and archive outbox entry. Put each under the Identity repository's `migrations/environments/<target>/` overlay as a reviewed forward-only change. `scripts/prepare-migrations.mjs <target>` composes shared migrations with only the selected environment overlay without changing already-applied common filenames. Do not reuse a migration number.
3. Staging was applied and read back as recorded below. Identity PR #17 was then merged; its main pipeline applied the production migration after staging succeeded. A CI-built Windows amail subsequently completed **production browser login and a cross-process token refresh**. The next gate is an authenticated **mail API smoke** once its host is deployed, followed by refresh-rotation edge cases, logout/revocation, and recovery-path verification. A staging login requires an actual staging account; production and staging account stores are isolated, so a production account cannot be used as a staging credential. A failed Worker rollback does not remove D1 client rows; disable with a new audited migration if necessary.
4. Configure mail Worker audience and CLI release defaults only after the row is confirmed. Do not put a client secret in a native app. The access-token `aud` must be the exact registered client ID.

Read-only staging verification example (Identity repository root):

```sh
npx --no-install wrangler d1 execute moesegfault-identity-staging --remote --config wrangler.identity.jsonc --command="SELECT client_id,client_type,token_endpoint_auth_method,sector_identifier,state FROM oauth_clients WHERE client_id='amail-cli-staging'"
npx --no-install wrangler d1 execute moesegfault-identity-staging --remote --config wrangler.identity.jsonc --command="SELECT redirect_uri,match_mode FROM oauth_redirect_uris WHERE client_id='amail-cli-staging'"
npx --no-install wrangler d1 execute moesegfault-identity-staging --remote --config wrangler.identity.jsonc --command="SELECT scope FROM oauth_client_scopes WHERE client_id='amail-cli-staging' ORDER BY scope"
```

Production commands must use `moesegfault-identity-production --env production`, and `client_id='amail-cli'`. These commands do not register the client.

## Live capability and verification gates

### Staging deployment evidence (2026-09-28)

Identity [PR #17](https://github.com/kleedaisuki/moesegfault-indentity/pull/17) head `736cbc495708c3e78ae54614c0f6735da934e952` passed its full [GitHub Actions quality run](https://github.com/kleedaisuki/moesegfault-indentity/actions/runs/36413992288). Its controlled [staging-only dispatch](https://github.com/kleedaisuki/moesegfault-indentity/actions/runs/36414550396) applied **only** `0007_oauth_client_amail-cli-staging.sql` to remote `moesegfault-identity-staging` D1. The production job was skipped. Remote read-only queries returned `amail-cli-staging`, `client_type=native`, `token_endpoint_auth_method=none`, `sector_identifier=amail-staging.moesegfault.dev`, `state=enabled`; redirect `http://127.0.0.1/callback` with `native_loopback_any_port`; scopes `offline_access`, `openid`, `profile`. Identity/Login/Account staging smoke passed. An independent HTTPS discovery request returned HTTP 200 JSON with exact issuer `https://identity-staging.moesegfault.dev`, authorization-code and refresh-token grants, and those three scopes. This is **not** evidence of a completed amail login or mail API round trip. The remote readback did not separately query absence of the production ID; environment-stream tests and the remote migration list support isolation without overstating that check.

### Production Identity rollout evidence (2026-09-28)

Identity [PR #17](https://github.com/kleedaisuki/moesegfault-indentity/pull/17) merged as `a50482b27541e37c909557d0f3b994544115d2b4`. Its [main release workflow](https://github.com/kleedaisuki/moesegfault-indentity/actions/runs/36419434738) completed successfully through staging and production promotion. The production release log shows `0007_oauth_client_amail-cli.sql` applied and Identity/Login/Account smoke passed. The new, general SELECT-only [registration inspector](https://github.com/kleedaisuki/moesegfault-indentity/actions/runs/36420788130) then read back remote production D1: `amail-cli`, `client_type=native`, `token_endpoint_auth_method=none`, sector `amail.moesegfault.dev`, `state=enabled`; redirect `http://127.0.0.1/callback` with `native_loopback_any_port`; scopes `offline_access`, `openid`, `profile`; and the same migration in D1 history. A safe live production authorization request for `amail-cli` with requested `http://127.0.0.1:37847/callback`, those scopes, and S256 PKCE returned HTTP 302 to `https://login.moesegfault.dev/login` with a server transaction; no user credentials or tokens were used. Correlation ID: `01a0e7ee-7b95-7230-8101-fdff0fe61975`.

The next acceptance slice used a CI-built Windows amail at revision `5152f7b`. A human completed the normal production Identity browser sign-in; `amail auth login` exited **0** with `authenticated: true`. A separate process then reported `amail auth status` as authenticated, and encrypted `auth.sqlite3` persisted the local authentication state. After the original access token expired, a later CLI process successfully obtained a fresh production token through the refresh path. Its subsequent mail API request failed because the mail API host was not deployed, so that failure does **not** establish a mail-service authentication defect. This establishes one live cross-process refresh, not full refresh-token rotation correctness (for example, predecessor replay or concurrent refresh). Mail API authorization, token revocation, and logout are still unverified. No token, subject, password, or callback query is recorded here.

On 2026-09-28, direct HTTPS GET returned HTTP 200 `application/json` for both issuers' `/.well-known/openid-configuration`; their `issuer` fields matched the respective origins. Production `https://login.moesegfault.dev/.well-known/openid-configuration` returned HTTP 200 **HTML** (the Login SPA), not discovery. The live production discovery advertises Authorization Code, refresh tokens, S256 PKCE, RS256 ID tokens, `openid profile offline_access`, and authorization-response issuer support. Recheck at deployment, because discovery describes deployed availability. The Identity repo's `docs/integrating-app.md`, `scripts/generate-oauth-client-migration.mjs`, and `crates/identity-worker/src/oauth.rs` corroborate the registration and loopback matching rules.

Production browser login, separate-process status, and one refresh after access expiry have passed. Remaining acceptance must cover negative `state`/response `iss`/ID-token `nonce` cases, one-use authorization code, RS256 JWKS verification failure paths, `iss`/`aud`/`token_use=access` checks at the deployed mail Worker, mailbox ownership binding to `(issuer, sub)`, refresh-token rotation under concurrent use and predecessor replay, staging/production rejection, and logout/revocation behavior. Keep tokens, codes, raw identity claims, and callback query strings out of telemetry. `profile` claims are not authoritative for mailbox ownership. The current CLI requires callback `iss` to equal the pinned issuer, rejects duplicate callback parameters, uses an ephemeral loopback port, and serializes refresh under an OS file lock with a durable crash marker. Logout attempts revocation through the discovered endpoint, but its success response does not prove remote revocation because the attempt is deliberately best-effort; local credential deletion proceeds even if discovery or revocation fails. It does **not** clear the browser's Identity SSO session or perform RP-initiated logout. These are code-level observations, not substitutes for deployed rotation-edge-case and logout smoke tests.

### Sources

- Identity repository `docs/integrating-app.md` and `docs/configuration.md` (local sibling repository; deployment-owned provisioning contract).
- Identity repository `scripts/generate-oauth-client-migration.mjs` and `crates/identity-worker/src/oauth.rs` (validation and URI matching implementation).
- [Production OIDC discovery](https://identity.moesegfault.dev/.well-known/openid-configuration), [staging OIDC discovery](https://identity-staging.moesegfault.dev/.well-known/openid-configuration).
- [RFC 8252, OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252.html); [RFC 9700, OAuth 2.0 Security BCP](https://www.rfc-editor.org/rfc/rfc9700.html); [RFC 9207, Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207.html).
