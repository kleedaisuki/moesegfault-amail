# amail architecture and wire contract (v0.1)

Status: implementation contract for CLI, mail Worker, and deployment. This is an internal design record; the public launch site should present workflows, not copy this document.

## Representative workflow and boundaries

1. `amail auth login` opens the system browser for moeSegFault Identity Authorization Code + S256 PKCE. The issuer is `https://identity.moesegfault.dev` (staging: `https://identity-staging.moesegfault.dev`), whose discovery JSON supplies authorization endpoints; `login.moesegfault.dev` is a human-facing SPA, **not the OIDC issuer**. The CLI is a pre-registered **native public** client. It stores tokens in OS-protected storage where available. The mail Worker accepts only Identity access tokens whose `aud` is exactly that native client ID, fixed `iss`, `token_use=access`, valid RS256 signature and time bounds. The current Identity issuer advertises `openid`, `profile`, `offline_access`, not invented mail scopes. Mail authorization is local mailbox ownership keyed by `(iss, sub)`. Registration of the client ID and exact loopback redirect is a deployment dependency, not a runtime self-service action.
2. `amail address add alice` sends authenticated POST `/v1/addresses`. The server canonicalizes the lowercase ASCII local part, atomically reserves it and the account's <=10 active address quota, then provisions a *literal* Cloudflare Email Routing rule for `alice@mail.moesegfault.dev`. An address has `pending -> active -> deleting` states. It must not be reported active until the route is confirmed. A retry/reconciler finishes interrupted provisioning; deletion disables the route before releasing ownership. Do not immediately recycle retired names, to prevent delivery to a future owner.

The route-control token needs only `Email Routing Rules Write` for the zone and must remain a Worker secret. Create with the Cloudflare Rules API (`POST /zones/{zone_id}/email/routing/rules`), action `worker` targeting the ingress Worker and a `literal` matcher on the exact recipient; record the returned rule ID for reconciliation/deletion. User-created routes are API-managed (`source=api`), not static Wrangler `addresses` entries, because Wrangler reconciles its own desired set on deploy and should not own mutable user data.
3. Cloudflare Email Routing invokes a small Rust `#[event(email)]` Worker, which transports bounded raw MIME bytes and the exact envelope recipient to the Rust mail API over a private service binding. The mail API owns validation, parsing, storage, indexing, and policy. Only registered active exact recipients deliver. Raw message and attachments are stored in R2, indexed metadata in D1. D1 stores immutable message identities and mutable per-mailbox read/deleted state. A multi-recipient inbound email has one content object and separate mailbox delivery rows.
4. `amail search ...` POSTs filters to `/v1/messages/search`; results are compact metadata by default, not bodies. `amail read <id> -o file.zip` retrieves an archive without marking the message read. `amail mark <id> --read` changes state explicitly. Agent extracts body/assets to a selected path; it never operates on an implicit rendered view.
5. Agent creates a ZIP and `amail send draft.zip` POSTs it. CLI validates archive shape and packages it with a native Rust ZIP library; server revalidates all untrusted bytes and ensures `from` belongs to caller. The server compiles UTF-8 `body.txt` and/or `body.html` plus assets into MIME multipart/alternative/related/mixed with safe content IDs. Email provider acceptance and delivery are distinct states. Send must use idempotency key; retries must not duplicate sends.

### Hard platform constraints

Cloudflare Email Routing subdomains require literal routing rules; **catch-all is unavailable on a subdomain**. Address registration is thus a control-plane operation, not merely a D1 insert. The published limit is **200 rules per domain**, giving at most 200 concurrently routed addresses (and 20 fully provisioned ten-address accounts) without a limit increase. **Launch decision:** use Cloudflare's current literal-route capacity as a bounded public service. Count all routes still present at Cloudflare, including those provisioning or deleting, against the domain-wide capacity; document the cap and return stable `capacity_exhausted` when it is reached. Never imply unlimited registration. Revisit a higher limit or different inbound transport only when demand justifies it. Delegating the mail subdomain as a separate Cloudflare zone to gain apex catch-all would require Enterprise and is not part of the launch. Cloudflare Email Sending currently advertises transactional email, a 5 MiB total outbound size, <=50 recipients and <=32 attachments. Whether arbitrary user-to-user agent mail is permitted must be explicitly validated with the provider before promising unrestricted outbound. A production-grade alternative is a separate outbound SMTP/API provider with the same `MailTransport` boundary; never silently degrade to forwarding-only. If beta sending is used, onboard both `mail.moesegfault.dev` (user addresses) and `moesegfault.dev` (site-originated `mail@moesegfault.dev`) independently and validate sender-domain approval. Never allow user registration under the apex domain.

| Inbound option | Correctness and operations | Decision |
| --- | --- | --- |
| Cloudflare literal routes | Native event delivery and one trust domain; hard 200-address cap, control-plane API per registration, route reconciliation. | **Chosen launch topology**; explicitly bounded capacity and exhaustion behavior. |
| Cloudflare child zone + apex catch-all | Native delivery without per-address rules; requires Enterprise, DNS delegation and verified Email Service support on child zone. | Deferred until real demand and entitlement. |
| External inbound MX with catch-all webhook (e.g. Mailgun) | One domain-level route, raw MIME webhook, signed requests and retries; new vendor, cost, privacy boundary and replay/dedup logic. | Deferred alternative if capacity becomes material; cannot activate without provider account/credentials and a data-processing decision. |

Mailgun's documented recipient regex/catch-all and raw-MIME HTTP forward would preserve the Rust ingestion/storage/search design; only the `InboundTransport` shim and MX change. Verify webhook HMAC over timestamp/token (or body for JSON variant), reject replay, idempotently key provider event plus MIME hash, and return successful HTTP only after R2+D1 durability. Do not combine both MX providers simultaneously as a failover experiment without a clear delivery-duplication and priority policy.

## Data/state ownership and invariants

| Object | Owner/storage | Invariant |
| --- | --- | --- |
| Account | D1 `(issuer, sub)` | No joining by mutable username/email. |
| Address | D1 + Cloudflare literal routing rule | Unique canonical local part, at most 10 non-retired (`pending`, `active`, or `deleting`) per account; reserved names (`admin`, `moesegfault`, `mail`, `login`, `api`, `account`, `auth`, `support`, `security`, `postmaster`, `abuse`, `noreply`, plus configured service names) never user-owned. |
| Message content | R2 object keyed by opaque message ID | MIME/raw ZIP content immutable; cap bytes and verify hash. |
| Delivery | D1 per mailbox/message | `read` belongs to delivery, not shared content; soft-delete/tombstone first so searches cannot rediscover it. |
| Search document | D1 text/metadata + vector | Indexed only after content durable; vector row records model slug, dimension=256 and source hash; semantic unavailability does not corrupt lexical search. |
| Outbound attempt | D1 idempotency key `(owner, key)` | Immutable payload hash, one provider submission; mismatched replay = 409; indeterminate provider outcome remains `unknown`, never blind-resend. |

Use unique constraints and transaction/conditional mutation for quota and address collisions. A simple robust representation is an address `slot` in `[0,9]` with a unique `(issuer,sub,slot)` index for all non-retired rows and unique normalized full address across all rows; a single conditional insert claims a free slot, so concurrent requests cannot race past the quota. Keep retired names reserved unless an explicit reclamation policy is designed. Reconciliation handles D1/Cloudflare rule partial failures; avoid claiming cross-service atomicity. The R2-first/D1-index-last ordering prevents visible dangling content. Server-side deletion removes delivery first, then asynchronously GCs content once no delivery references remain. Preserve IDs and wire field semantics throughout v0.x; additive fields only.

## HTTP v1 contract

All URLs are under `https://mail.moesegfault.dev`; requests except health use `Authorization: Bearer <Identity access token>`. JSON responses include `request_id`; errors use `application/problem+json` with stable `code`, `detail`, `request_id` and `x-moesegfault-correlation-id` where available. Timestamps are UTC RFC 3339; IDs are opaque and never infer ownership. Content and email addresses must not appear in telemetry. Unknown JSON response fields must be ignored by CLI; unknown request fields are rejected for mutation but can be added in new protocol versions.

| Method path | Request | Success |
| --- | --- | --- |
| `GET /v1/addresses` | — | `{"addresses":[{"address":"alice@mail.moesegfault.dev","state":"active","created_at":"..."}],"limit":10}` |
| `POST /v1/addresses` | `{"local_part":"alice"}` | 201/202 same address object; 409 collision/reserved/account quota/domain-wide `capacity_exhausted` |
| `DELETE /v1/addresses` | `{"address":"alice@mail.moesegfault.dev"}` | 202 `{ "state":"deleting" }`; idempotent for caller-owned address. Address stays out of URL-based automatic traces. |
| `GET /v1/messages?limit=20&cursor=...` | list newest | `{ "messages":[<summary>],"next_cursor":null }` |
| `POST /v1/messages/search` | SearchRequest below | `{ "messages":[<summary>],"next_cursor":null }` |
| `GET /v1/messages/{id}` | — | one summary incl. size, text/html presence, attachment metadata |
| `GET /v1/messages/{id}/archive` | — | `application/zip` in the ZIP contract below |
| `PATCH /v1/messages/{id}` | `{"read":true}` or false | updated summary; no implicit read from GET/archive |
| `DELETE /v1/messages/{id}` | — | 204; only this caller's delivery is deleted |
| `POST /v1/messages/send` | `application/zip`, `Idempotency-Key: <UUID>` | 202 `{ "id":"...","state":"accepted" }`; never claim delivered before provider confirmation |
| `POST /v1/telemetry` | redacted event batch; opt-out respected | 202; never block mail operations on failure |

Summary fields: `id`, `mailbox`, `direction` (`inbound` or `outbound`), `from`, `to`, `subject`, `received_at`, `read`, `size_bytes`, `has_attachments`; optional `score` only for semantic search. Default CLI line format should emit concise parseable JSON lines, not human decoration. `--human` may add layout/color but must not change server state.

SearchRequest (all supplied predicates AND together):

```json
{
  "mailbox": "alice@mail.moesegfault.dev",
  "after": "2026-01-01T00:00:00Z",
  "before": "2026-10-01T00:00:00Z",
  "title": "release",
  "from": "sender@example.org",
  "to": "alice@mail.moesegfault.dev",
  "body": "incident",
  "metadata": {"message_id": "abc"},
  "semantic": "discussion about rollout risk",
  "regex": false,
  "case_sensitive": false,
  "read": false,
  "limit": 20,
  "cursor": null
}
```

All optional string filters use substring matching by default; `regex` applies to the textual filters supplied, with bounded pattern length and CPU budget. `metadata` is an allowlisted key/value map (e.g. `message_id`, `in_reply_to`, `content_type`, `attachment_name`), not arbitrary SQL. `after` inclusive, `before` exclusive. Semantic query is embedded server-side via OpenRouter `qwen/qwen3-embedding-8b`, `dimensions:256`; validate exactly 256 finite coordinates, normalize and compute **exact cosine** over all lexically filtered candidate vectors (no approximate nearest-neighbor index). Order semantic matches by score descending, tie by time and ID; other searches by time descending and ID. Cursor binds canonical filters and owner; changes invalidate it. Because exact scan can be expensive, enforce per-account candidate caps and return an explicit partial/limit error rather than silently approximate. Model or embedding errors return typed failure for semantic search; lexical search remains available.

## ZIP archive v1

ZIP is the only agent-facing content exchange format. No external `zip` executable is required. Paths use `/` separators, UTF-8, relative names only; reject duplicate normalized names, symlinks, absolute paths, `..`, encrypted entries, zip bombs and unsupported compression. Require root `manifest.toml`; at least one of root `body.txt` and `body.html`, both UTF-8. Entries under `assets/` are binary and listed explicitly. Define limits both pre- and post-decompression; outbound must respect actual provider MIME size, not merely ZIP size. No generated archive may include secrets or local traces.

Send example:

```toml
version = 1
from = "alice@mail.moesegfault.dev"
to = ["bob@example.org"]
cc = []
bcc = []
subject = "Hello"
reply_to = "alice@mail.moesegfault.dev" # optional
in_reply_to = "<prior-id@example.org>" # optional
references = ["<prior-id@example.org>"] # optional

[[assets]]
path = "assets/chart.png"
content_type = "image/png"
disposition = "inline" # `inline` or `attachment`
cid = "chart" # required for inline; HTML refers to cid:chart
filename = "chart.png" # optional attachment display name
```

`body.html` is already authored HTML, not a template or raw MIME. Compiler builds MIME: `text/plain; charset=UTF-8` + `text/html; charset=UTF-8` alternatives, related inline assets by `cid`, ordinary attachments as mixed parts. If only HTML exists, generate readable text by stripping tags/decoding entities with sensible block breaks; if only text exists, HTML may be omitted. HTML compilation should resolve only archive-local CSS, inline ordinary style rules for broad email-client compatibility, preserve safe `cid:` references and basic image/layout properties, then sanitize active content, dangerous URL schemes and event handlers. Never fetch remote stylesheets or images while compiling; a sanitizer whose default policy silently strips all style or `<img>` tags is not sufficient. Compare generated MIME in representative Gmail/Outlook fixtures rather than assuming browser HTML rendering equals email rendering. No arbitrary mail headers, envelope sender or custom SMTP commands in manifest; server creates Date/Message-ID, validates all recipients, MIME types and encoded lengths. `reply_to` must be caller-owned or omitted. For inbound archives, the server emits the same body and assets layout and adds immutable read-only fields `id`, `direction`, `received_at`, `message_id`, and attachment descriptors. **Do not put mutable `read` in an immutable R2 archive**: current read state is returned by GET/search and never changed by archive download. CLI must reject using an inbound archive as an outbound draft unless agent explicitly edits/removes read-only fields; this prevents accidental echo or forged metadata.

Cloudflare's structured sending API explicitly allowlists `In-Reply-To` and `References` as custom headers; compile those two manifest fields into the provider builder after CR/LF and length validation. Do not silently discard them, as reply threading would then fail. `Date`, `Message-ID`, MIME framing and DKIM are provider-controlled and must not be agent-specified.

## Privacy and diagnostics

CLI SQLite is a local operation journal, not a mail cache: span IDs, command type, timings, error code, size/count buckets, retry attempts, Worker ray/request ID. Do **not** store subject, body, raw address, token, ZIP path, query text, or vector. Use a local rotating salt for pseudonymous account/address IDs; do not upload salt. Telemetry upload is batched, bounded, non-blocking and user-configurable. Worker logs/traces contain the same redacted dimensions; Cloudflare automatic email spans may include `cloudflare.email.from/to`, so review retention/access and sampling before production. A CLI `traceparent` can correlate CLI->Worker; a separate opaque request ID survives across Worker->OpenRouter/Cloudflare API logs. Cloudflare native traces instrument fetch and bindings, but do not currently propagate trace IDs to non-Cloudflare services, so use request IDs for those joins.

Semantic search is a separate privacy boundary: the Worker sends extracted message text and user semantic queries to OpenRouter and potentially its selected upstream embedding provider. This is not telemetry and must be disclosed plainly in the manual; never imply that mail content remains only in Cloudflare. Do not send entire MIME, attachments, tokens, or other users' messages unnecessarily. Constrain provider routing to approved zero-data-retention/no-training endpoints (`provider.zdr` and `provider.data_collection`) and explicitly disable OpenRouter response caching (`X-OpenRouter-Cache: false`), then verify these options on the actual Qwen route; per-request ZDR alone does not disable cache. If indexing is delayed or an embedding call fails, expose `index_state` and retry through a bounded queue rather than silently treating those messages as semantically searchable. See [the search/privacy research note](search-privacy-research.md) for evidence and test design.

## DNS and release gates

`mail.moesegfault.dev`: Email Routing subdomain onboarding creates MX/SPF records; independently onboard for outbound DKIM/SPF/DMARC and `cf-bounce` as directed by Cloudflare. `moesegfault.dev`: separate outbound onboarding for site `mail@moesegfault.dev`; no user mailbox at apex. `mail.moesegfault.dev` is public Worker API hostname; `amail.moesegfault.dev` is Astro launch site hostname. Do not invent static DNS values when the provider provides per-domain records: provision, inspect and verify live authoritative DNS in deployment workflow. **Preserve the existing apex DMARC `p=reject`** and verify alignment for both sender domains; any new subdomain DMARC policy must be a deliberate deliverability/security choice, not an implicit weakening of apex protection. GitHub Actions must test CLI on Windows/macOS/Linux and Worker Wasm in CI, deploy after tests, then smoke real Identity login, address registration, SMTP inbound, ZIP retrieval, send, search, read update and delete against production/staging as appropriate. Publish v0.1.0 Release only after smoke and artifacts succeed.

## Sources and assumptions

- Identity native/resource contract: local `.agents/skills/moesegfault-identity/references/{application-onboarding,oidc-integration}.md`; live discovery still must be checked at deployment.
- [Cloudflare Email Routing subdomain limitation](https://developers.cloudflare.com/email-service/configuration/subdomains/) and [Wrangler routing addresses](https://developers.cloudflare.com/email-service/configuration/email-routing-addresses/).
- [Email Routing Rules API and permission](https://developers.cloudflare.com/api/resources/email_routing/subresources/rules/methods/create/).
- [Cloudflare Email Routing 200-rule limit](https://developers.cloudflare.com/email-service/platform/limits/) and [Enterprise-only child-zone delegation](https://developers.cloudflare.com/dns/zone-setups/subdomain-setup/).
- [Mailgun recipient-route catch-all](https://documentation.mailgun.com/docs/mailgun/user-manual/receive-forward-store/route-filters), [raw MIME HTTP receive/retry behavior](https://documentation.mailgun.com/docs/mailgun/user-manual/receive-forward-store/receive-http), and [webhook signing](https://documentation.mailgun.com/docs/mailgun/user-manual/webhooks/securing-webhooks) as a researched alternative, not an installed dependency.
- [workers-rs event macro capabilities](https://docs.rs/worker/latest/worker/attr.event.html).
- [Cloudflare Email Sending API/limits](https://developers.cloudflare.com/email-service/api/send-emails/workers-api/) and [service scope](https://developers.cloudflare.com/email-service/).
- [OpenRouter embeddings request including `dimensions`](https://openrouter.ai/docs/api/api-reference/embeddings/create-embeddings), [model slug](https://openrouter.ai/qwen/qwen3-embedding-8b/providers), [Qwen model card/MRL](https://huggingface.co/Qwen/Qwen3-Embedding-8B).
- [Gmail HTML email CSS support](https://developers.google.com/workspace/gmail/design/css) and [Rust `css-inline` library](https://github.com/stranger6667/css-inline) (candidate, not yet verified in Worker Wasm).
- [Cloudflare send header allowlist and provider-controlled headers](https://developers.cloudflare.com/email-service/reference/headers/).
- [Workers traces](https://developers.cloudflare.com/workers/observability/traces/) and [cross-provider propagation limitation](https://developers.cloudflare.com/workers/observability/traces/known-limitations/).

The hard unresolved assumption is entitlement to arbitrary user outbound through Cloudflare Email Sending. Verify provider terms and an actual send to an unverified external address. If unsupported, keep the exact HTTP/ZIP contract and swap only `MailTransport` to a provider explicitly permitting mailbox traffic. The live `https://identity.moesegfault.dev/.well-known/openid-configuration` has been verified to return OIDC JSON; `login.moesegfault.dev` is only the SPA and its similarly named path returns HTML. The deployment has no known pre-registered native client ID. Until reviewed native registration exists, authenticated CLI smoke tests are blocked. Do not substitute an insecure login bypass or guessed client ID.
