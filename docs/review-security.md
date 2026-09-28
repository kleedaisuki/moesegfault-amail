# Independent security and compatibility review (2026-09-28)

Scope: inspected architecture, feasibility, identity onboarding, DNS/operations notes, Rust Worker auth/archive/platform/API and schema, Rust CLI auth/archive/API/telemetry, Wrangler configuration and GitHub workflows. This is a static review of an in-progress, uncommitted tree; I did not run a local build or deployment. Findings below distinguish demonstrated code paths from deployment gates. Reassess a finding only after the corresponding implementation changes.

## Resolved in tree, pending deployed verification — Inbound event consumer

The initial tree lacked the `amail-inbound` event consumer and shared `INGRESS_SECRET`. An in-progress correction now exists at `workers/mail-ingress/src/index.js` and `wrangler.toml`, with a CI deploy job and service binding to `amail-mail` (`ci.yml:164-196`). This removes the source-level absence, but no deployed SMTP smoke has yet demonstrated the Cloudflare Email Routing target, secret, binding, and Rust ingestion path together. The release gate remains open until that test passes.

## Resolved in tree, pending failure-injection test — Address provisioning orphan rules

The first implementation could retire an address while an in-flight Cloudflare rule was created, leaving an orphan. The revised code CAS-claims `pending -> provisioning`, discovers existing rules by address before creation, records or compensates a rule on failed transition, and leaves an in-flight delete in `deleting` (`lib.rs:527-635`). A scheduled `reconcile_addresses` discovers orphan rules and finishes provisioning/deletion (`lib.rs:108-156`). This addresses the observed race/failure path at source level. Fail-injection coverage for Cloudflare response loss, D1 update failure, concurrent add/delete, and reconciliation remains a deployment gate.

## Resolved in tree, pending contract test — Telemetry payload schema

CLI `telemetry.rs:17-24` serializes `status: u16` and `bytes_bucket: u64` as JSON numbers. The initial Worker code expected strings, rejecting every non-empty batch. The Worker has since been changed to `status:u16` and `bytes_bucket:u64` (`lib.rs:491`), aligning the wire shape. A realistic serialized CLI batch should still be exercised in CI/deployment to verify the endpoint and observability sink.

## Mostly resolved in tree — Send acceptance recovery

The initial implementation left every post-provider indexing failure in a permanently pending state. The revised code persists a stable message ID before submission and provider ID at `accepted` (`lib.rs:1042-1115`), and a scheduled `reconcile_outbound` reconstructs a missing sent record from R2 (`lib.rs:104-145`). This repairs the common provider-success/index-write-failure path. A D1 failure at the **accepted-state write** after provider success is still genuinely indeterminate locally and correctly must not auto-resend; document operator recovery from provider logs and test that failpoint. No further source-level correction is claimed here without evidence.

## Resolved in tree — Unfiltered 2,000-message search cutoff

The initial `search` loaded 2,001 unfiltered owner rows and failed all queries above that total. The revised implementation pushes owner/mailbox/read/time predicates into D1, scans 200-row keyset pages, applies the 2,000 bound only to final semantic candidates, and has a separate explicit 100,000-row scan bound (`lib.rs:719-761`). This removes the pathological refusal to search a narrow mailbox/date range after an account grows. Stable pagination and exact semantic ranking still need deployment-level tests.

## Resolved in tree — Search metadata population

The initial inbound record stored only a generic content type, and the outbound record omitted attachment names. The revised `archive::inbound_archive` returns structured message/attachment metadata; `outbound_metadata` includes provider message ID, threading value, content type, and joined attachment filenames (`lib.rs:1118-1125`). The matcher now has data for its allowlisted fields. Test both directions with real MIME fixtures before declaring complete.

## Resolved in source, pending live GC acceptance — Retained sensitive storage

The initial `delete_message` only set a D1 tombstone, while the first cumulative cap used a non-atomic `SUM` check and could not track an R2 object written before a failed D1 insert. The current implementation addresses these paths: migration `0004_storage_ledger.sql` creates per-object reservations and a trigger-enforced 1 GiB account ledger, with the quota check and increment in one SQLite write transaction. `reserve_storage` records the object and charges bytes **before** inbound/outbound R2 writes (`lib.rs:549-592,1458-1463,1575-1590`); retry with the same ID cannot double-charge. Scheduled `reconcile_storage` marks reservations indexed after uncertain D1 responses, `garbage_collect` removes tombstoned ZIP/raw R2 objects and D1 content before releasing ledger bytes, and `clean_orphans` removes old reserved objects without a message row (`lib.rs:99-206`), while preserving outbound states with uncertain/accepted provider outcomes. Migration backfills existing nondeleted message reservations. The prior orphan and read-before-write over-cap findings are **resolved in source**. GitHub native/Wasm validation passed per project CI evidence, but a live deletion/GC/orphan-recovery exercise remains an acceptance gate; this review does not claim deployed R2 cleanup was observed.

## Resolved in tree, with residual recovery risk — Same-key quota reservation

The first quota implementation allowed retry after 429 to skip reservation; the next version could over-reserve on concurrent same-key attempts. The current code CAS-claims `state='reserving'` before incrementing usage and requires `quota_reserved=1` for provider transition. A new `reservation_started_at` migration and cron reset use claim age rather than original request age (`lib.rs:180-195,1190-1211`), closing the identified old-row/cron race; a regression test covers the timestamp criterion (`lib.rs:1547-1549`). **Residual conditional accounting issue:** if account reservation succeeds but global reservation fails, account credit remains consumed and can be spent again on retry without a send. That is conservative (overcount), not a send-cap bypass or duplicate-send path. Transactional reservation would make the quota precise; this is an availability/fairness improvement rather than a release blocker absent evidence of frequent failures.

## Resolved in tree, pending mail-client fixtures — HTML/CSS compilation and threading

The initial Worker only used default Ammonia sanitization and omitted reply threading headers. The revised `archive.rs:171-204` uses `css-inline` with remote stylesheets disabled, an allowlisted CSS property set, and `cid:` preservation; `platform.rs:170-186` sends `In-Reply-To` and `References` through the provider builder. A source-level test covers safe CSS and `cid` (`archive.rs:403-404`). Real Gmail/Outlook delivery/rendering fixtures remain an acceptance gate, but the original source-level feature gaps are closed.

## Resolved in tree — Bodyless inbound ZIP contract

The initial `inbound_archive` could emit an attachment-only ZIP with neither body file, which CLI `unpack` rejected. The revised parser inserts `Some(String::new())` for `body.txt` when both text and HTML are absent (`archive.rs:253-259`), so any accepted inbound archive has a body entry. Test an attachment-only external message end to end before marking the deployed path verified.

## Resolved in tree — CLI ZIP sync partial-download handling

The initial CLI wrote the final file directly and skipped any existing `{id}.zip`. The revised `write_new` writes and syncs a same-directory temp file before rename (`main.rs:308-338`), while `sync --out-dir` re-fetches the archive and byte-compares any existing file (`main.rs:374-386`). An incomplete file now causes an explicit conflict instead of being silently accepted. Deployment behavior remains unverified; no further production correction is indicated by this finding.

## Resolved in tree — CLI/server custom idempotency-key format

The initial CLI accepted arbitrary `[A-Za-z0-9_.-]` keys while the Worker required UUID. The revised CLI now calls `uuid::Uuid::parse_str` for custom keys and generates a v4 UUID by default (`main.rs:492-500`), matching the Worker parser. A cross-component request test remains useful but the static incompatibility is resolved.

## Release/operations gates, not claims of observed runtime failure

- CI tests/builds, then deploys and probes only HTTP health and public pages (`ci.yml:136-166`); the release workflow publishes on a version tag without dependency on a live login/inbound/outbound/search smoke (`release.yml`). The task explicitly requires deployment-level validation. Add an authenticated staging/prod acceptance job using dedicated fixtures and a safe secret strategy before v0.1.0; avoid putting tokens, addresses, and message content in logs.
- `wrangler.toml` uses a route pattern for `mail.moesegfault.dev/*`, while `docs/deployment-dns.md` specifies a Worker Custom Domain. Verify the HTTP DNS record and routing actually exist; SMTP MX/TXT presence does not establish HTTPS routing. Review this after deploy config changes.
- The known 200 literal-routing-rule cap is documented, but capacity exhaustion is surfaced by a generic `service_unavailable` from `create_rule`; confirm a useful stable capacity error in production. The workflow falls back from a narrow `CF_EMAIL_ROUTING_TOKEN` to `CLOUDFLARE_API_TOKEN`, giving the runtime potentially excessive privileges; remove fallback once the scoped token exists.
- Server ZIP parsing bounds compressed size, expanded declared size, and count, and rejects traversal/symlinks, but it does not enforce a compression-ratio ceiling despite the architecture contract. This is not by itself a demonstrated unbounded decompression (the expanded cap is 12 MiB); consider a ratio check and stream-time byte cap as defense in depth.

## Positive controls observed

The Worker pins Identity issuer and exact configured audience, RS256 signature, `token_use=access`, and `(iss,sub)` ownership (`auth.rs`); CLI performs browser-based PKCE with state/issuer/nonce checks and a serialized refresh lock (`amail/src/auth.rs`). ZIP paths reject absolute/traversal/symlink entries on both sides. `from` and `reply_to` require active caller-owned addresses. Query regex uses Rust's linear-time `regex` crate and a pattern size limit, so classic backtracking regex DoS is not an evident issue. Semantic vectors are checked for 256 finite values, normalized, and scored by exhaustive dot product over the selected set; exactness is impaired by the prefilter/candidate-cap issue above, not by approximate ANN indexing. Local journal fields exclude mail content and tokens. These are static observations, not deployed-service verification.
