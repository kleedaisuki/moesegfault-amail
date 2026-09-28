# Mail Worker operational design and evidence

The Rust Cloudflare Worker is `crates/mail-worker`; the minimal JavaScript Email-event adapter is `workers/mail-ingress`. This adapter exists because `workers-rs` 0.8.x does not expose an `email` event macro. It transports bounded raw MIME and an envelope recipient over a private service binding; Rust owns mailbox policy, MIME parsing, ZIP compilation, persistence, search and control-plane operations. Ingress observability is off because automatic email spans may contain sender/recipient PII. It forwards an opaque W3C `traceparent` for safe correlation; do not log the envelope or message content.

## Identity and deployment

- Production issuer is fixed at `https://identity.moesegfault.dev`; staging at `https://identity-staging.moesegfault.dev`. Only these trusted deployment-configured issuers are accepted, and each discovered issuer must exactly match. JWKS URI must be HTTPS on that issuer's host.
- The resource API accepts only an RS256 Identity **access** token, pinned issuer, exact audience equal to the registered native CLI OAuth client ID, valid time and `token_use=access`. Product authorization uses `(iss,sub)` plus D1 address ownership. Login and token rotation are solely the native CLI's job.
- Production mailbox domain is `mail.moesegfault.dev`; staging is `mail-staging.moesegfault.dev`. Both use Cloudflare Worker Custom Domains. Never point staging Email Routing rules to production.
- D1 bindings: `MAIL_DB` -> `moesegfault-mail-production` (`ad06f7f3-8897-4150-b9a9-7a46a8e55b30`), staging `moesegfault-mail-staging` (`74f35f95-42ce-482c-86e6-dffbdd35cbbe`). R2 `MAIL_BODIES` -> `moesegfault-mail-raw-production`, staging `moesegfault-mail-raw-staging`.
- Secrets: `CF_EMAIL_ROUTING_TOKEN` (routing rules read/write), `OPENROUTER_API_KEY`, and the same `INGRESS_SECRET` in both the Rust API and its matching Email-event adapter. `CF_ZONE_ID` is a nonsecret deployment var. `OFFICIAL_EMAIL` is a sender-constrained production binding for `mail@moesegfault.dev`; user ZIP sends cannot address it. Staging deliberately omits that binding.

## Durable state and failure semantics

| State | Meaning | Recovery |
| --- | --- | --- |
| Address `pending` | D1 slot reserved, no owner reports active delivery | POST may claim `provisioning`; slot counts toward ten |
| Address `provisioning` | One D1 CAS winner owns external rule creation | Retry sees pending; cron checks provider literal rule and activates or resets stale claim |
| Address `active` | Provider rule ID and D1 ownership confirmed | Inbound accepts exact envelope recipient only |
| Address `deleting` | Inbound blocked before external rule deletion | Cron retries rule discovery/deletion before retirement |
| Address `retired` | Name permanently reserved against transfer | `needs_reconcile` keeps possible orphan rules on cron until verified clean |
| Send `preparing` | Stable idempotency ID; provider has **not** been called | Retry may finish R2 put; quota flag must be reserved before transition |
| Send `reserving` | One CAS winner claims quota | Stale claim resets to preparing after 10 minutes; excess counted conservatively |
| Send `submitting`/`unknown` | Provider call may have happened | **Never blind-resend**; manual provider reconciliation required for ambiguous outcome |
| Send `accepted` | Provider returned an ID, mail index may be incomplete | Cron rebuilds D1 index from immutable R2 ZIP, then marks sent |
| Send `sent` | Provider accepted and D1 index visible | Retry returns same stable message ID |

SQLite partial unique `(owner_iss,owner_sub,slot)` enforces ten active/pending/deleting/provisioning addresses even under simultaneous registrations. An address primary key persists after retirement to prevent later delivery to another account. The provider's literal-rule capacity is 200 per domain; the API checks local capacity and maps provider limit errors to stable `capacity_exhausted`. The D1/Cloudflare boundary is not falsely claimed atomic: a five-minute cron reconciles nonterminal rows and flagged retired rows via provider rule listing.

Inbound raw MIME and normalized ZIP are separate immutable R2 objects. ZIP manifests do **not** store mutable read state; `GET /v1/messages/{id}` and search are authoritative for `read`. D1 stores up to 60 KB of each text body in the message row and additional UTF-8-safe chunks in `message_text_chunks`. Body search reconstructs chunks for exact matching. Semantic vectors are a projection, never a condition for accepting SMTP: cron embeds pending documents with OpenRouter `qwen/qwen3-embedding-8b` at exactly 256 dimensions, validates finite/nonzero coordinates, normalizes, and stores model/dimension. Semantic queries fail explicitly while eligible index rows are missing rather than silently omitting mail; exact cosine is computed across all eligible vectors, capped at 2,000 with explicit 422 on overflow.

There are conservative D1 daily reservations for up to 100 outbound messages per account, 10,000 global outbound sends, and 100 MiB inbound raw bytes per account. Failed attempts may consume quota; retries cannot bypass quota. These are abuse guardrails, not deliverability entitlements. Cloudflare Email Service availability for arbitrary user mailbox send requires an actual external-address smoke test; provider acceptance is not equivalent to delivery.

## CI and live verification

CI must run `cargo test -p amail-worker --locked` for pure ZIP, address, search, vector and SQL invariants, then `cargo check -p amail-worker --locked --target wasm32-unknown-unknown`, followed by `worker-build --release`. It should deploy staging first with D1 migrations, supply secrets to both Workers, and smoke `GET /health`, authenticated registration, provider rule presence, inbound SMTP, ZIP retrieval, read/unread, lexical/semantic search, send idempotency and outbound to an unverified external address. A production release must not claim full readiness solely from a Wasm compile.

## Primary references

- [Identity integration contract](../.agents/skills/moesegfault-identity/references/oidc-integration.md)
- [Cloudflare subdomain routing limitation](https://developers.cloudflare.com/email-service/configuration/subdomains/)
- [Cloudflare Email Routing rule API](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/create/)
- [Cloudflare Email Sending Worker binding](https://developers.cloudflare.com/email-service/api/send-emails/workers-api/)
- [Cloudflare allowed threading headers](https://developers.cloudflare.com/email-service/reference/headers/)
- [OpenRouter embedding API](https://openrouter.ai/docs/api/api-reference/embeddings/create-embeddings)
