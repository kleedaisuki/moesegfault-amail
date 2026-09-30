# Staging Identity verification inbox — source review

Reviewed 2026-09-28, with a targeted follow-up after the test-channel changes; still before hosted build/deployment or live SMTP. Scope: `workers/identity-test-inbox/{src/lib.rs,wrangler.toml,ensure_route.py,test_ensure_route.py}` and `docs/staging-test-account.md`; adjacent Identity sender config and existing Email/R2 Worker implementations were checked. This is **not** evidence that Cloudflare accepted the Worker, rule, or an Identity verification message.

## Findings

### Resolved P1 — A public, spoofable sender could overwrite the only verification message

The original `src/lib.rs:38-61,92-95` accepted a spoofable SMTP envelope sender and unconditionally PUT `verification/latest.eml`. A third party could replace the genuine message; this was availability/integrity, **not demonstrated account takeover**. The follow-up source now assigns each accepted delivery a UUIDv4 key under `verification/`, eliminating overwrite of the genuine MIME by a later delivery. The operator procedure opens the exact route only for a short registration window, privately lists fresh candidates, checks trusted authentication evidence, rejects ambiguous selection rather than guessing an eight-digit code, and removes the route in a `finally` path. No standing public code-capture route is intended. These changes resolve the reported overwrite failure path; live provenance inspection and flood response still require operational validation.

Removing the SMTP envelope-sender allowlist is justified: Cloudflare Sending may use a provider bounce address as `MAIL FROM`, while any third party could forge an apparent `identity@moesegfault.dev` envelope. The new procedure explicitly distinguishes trusted receiver-added `Authentication-Results` or independently validated DKIM/DMARC from attacker-supplied headers. The Identity challenge-completion endpoint remains the code's authority.

### Resolved P2 — Expiry had a read/delete race with a fresh PUT

The previous cron read the fixed key, checked the **old** R2 object's upload time, then deleted that key without a version precondition; a fresh PUT in between could be deleted. The follow-up removes this cron and the shared key entirely. UUIDv4 objects are removed by exact operator key after use, with the already configured one-day R2 lifecycle rule as a backstop. This resolves the specific race. Retention is not an exact one-day SLA, which the procedure correctly states.

### Resolved P2 — Route creation readback proved count, not the promised enabled/owned route

The earlier `ensure_route.py:123-134` returned `created` whenever one alias matcher existed after POST, even if it was disabled or pointed elsewhere. The follow-up now requires exactly one `owned()` rule in the readback, verifying enabled state, API ownership, exact alias matcher and sole staging Worker action. `test_ensure_route.py` includes a foreign-target regression test. A separate live SMTP probe is still required.

## Boundaries checked, not findings

- The Worker hardcodes one apex test alias, not `@mail.moesegfault.dev`, and has no fetch event, HTTP route, workers.dev URL or preview URL in `wrangler.toml`. The R2 bucket binding is separate from user/ops mail data. Identity staging config (`../moesegfault-indentity/wrangler.identity.jsonc`) does send from `identity@moesegfault.dev`; staging and production use distinct Identity databases, client IDs, issuers, and test credentials. The sender address is shared, so an email's From alone cannot prove *staging* origin.
- Streaming input is capped at 64 KiB in addition to checking `raw_size`; no message bytes are logged by the Worker, and automatic Worker observability is disabled. Per-message UUIDv4 keys are not aggregate rate/byte caps: a hostile flood during the short open route window can still accrue objects/cost. The runbook says to close the route immediately and stop when that occurs; if this channel becomes standing automation, add explicit aggregate quotas and monitoring before that use. R2's one-day lifecycle is a backstop only, not a precise deletion SLA. The exact rule helper refuses foreign/disabled/duplicate alias matches before mutation, and never enumerates or edits other aliases intentionally. A control-plane inventory race remains possible in principle; final readback and SMTP evidence matter.
- Rust Email event, `raw_size`, `raw_byte_stream`, `set_reject`, R2 `put`, `uploaded`, and cron shapes match adjacent deployed project Workers, but the new crate has **not** yet passed its own hosted native/Wasm build. Public-domain absence and lifecycle configuration are recorded in `docs/staging-test-account.md`, not independently verified by this source review. No claim of runtime compatibility or absence of provider logs follows from static inspection.

## References

- [Cloudflare Email Worker handler and rejection](https://developers.cloudflare.com/email-service/api/route-emails/email-handler/)
- [Cloudflare Email Routing rules and addresses](https://developers.cloudflare.com/email-service/configuration/email-routing-addresses/)
- [Cloudflare R2 Workers API consistency](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/)
