# Independent validation ledger

Status: **in progress**. This ledger records observed behavior, not implementation claims. Observations below were made on 2026-09-28 from the repository workspace on Windows PowerShell. No local Rust, Wasm, or cross-platform build was run, per the project's GitHub-hosted testing requirement. Recheck only affected rows after a fix; an unexercised workflow is not a pass.

## Acceptance basis

The user request and `docs/architecture.md` establish these externally visible claims: browser-authorized native OIDC login; CLI-owned registration of at most ten non-reserved `@mail.moesegfault.dev` addresses; real routed inbound mail; safe ZIP exchange and HTML/MIME delivery; combined metadata, text, regex, case-sensitive, date, read-state and exact-cosine 256-dimensional Qwen semantic search; explicit read/delete state; redacted end-to-end diagnostics; deployed API and Astro site with manual/changelog tables of contents; cross-platform CI and a v0.1.0 Release including the agent skill. DNS and delivery authentication must be verified separately from HTTP reachability. `docs/operations.md` supplies the representative live workflow.

| Claim | Independent check | Expected | Observed / verdict |
| --- | --- | --- | --- |
| Native login and authorization | Execute `amail auth login`, then authenticated `/v1/addresses` | Human browser authorization followed by token-backed CLI operation | **Not exercised**: no deployed API or published CLI release yet. Static client and issuer configuration do not prove an end-to-end login. |
| Address registration and quota | Two-account live registration, reserved name, eleventh address, retry and delete; inspect corresponding Cloudflare literal rules | Exact active route only after provisioning; no ownership/quota race; retired name not reassigned | **Not exercised**. Route-control code exists, but live rules and ingress must be checked. |
| SMTP inbound and ZIP retrieval | Send external MIME with text, HTML, inline CID image and attachment; search/read/unpack; compare bytes | One authenticated delivery; valid ZIP with manifest and content; GET/archive does not set read | **Not exercised**. SMTP path must include the Email Routing ingress Worker, not just API `/health`. |
| Outbound ZIP and MIME | Pack a directory natively, send to non-verified external recipient, inspect received MIME, DKIM/SPF/DMARC, attachment and HTML | Provider accepts and external recipient actually receives correct content; duplicate idempotency key does not resend | **Not exercised**. Provider acceptance is not delivery proof. |
| Search and mutation | Live AND filters, date boundaries, regex/case, metadata, read/unread, semantic ranking, delete, cursor replay | Exact filtered results, exact cosine over matching vectors; deleted copies disappear; unrelated mailbox remains | **Not exercised**. A preliminary full-account cap defect was corrected in the evolving source; the new paginated/filtered scan still needs deployed evidence. |
| Privacy and tracing | Inspect local SQLite and Worker trace after live operation | Correlatable request/span IDs without tokens, addresses, subject, body, query or ZIP paths | **Not exercised**. Code review alone cannot establish generated logs or Cloudflare auto-span privacy. |
| API and site DNS/HTTPS | `Resolve-DnsName` and `Invoke-WebRequest` against production hosts | Publicly resolvable HTTPS API/site | **Pending deployment**. Authoritative DNS has mail MX/SPF/DMARC, but local recursive resolver reported NXDOMAIN for both `mail` and `amail` HTTP names; all four HTTPS probes failed TLS connection. This may include negative-cache delay and is not a final deployment verdict. |
| CI and release | `gh api repos/kleedaisuki/moesegfault-amail/actions/runs --jq '.total_count'`; `gh run list` | Passing Linux/macOS/Windows, Wasm, site, deployment and actual smoke, then v0.1.0 assets/checksums/skill | **Not exercised**: zero Actions runs at time of check. Files under `.github/workflows` are intentions, not run evidence. |

## Reproducible probes and observations

```powershell
# Ran from D:\Code\moesegfault-amail on 2026-09-28.
gh api repos/kleedaisuki/moesegfault-amail/actions/runs --jq '.total_count'
# 0
gh api repos/kleedaisuki/moesegfault-amail/releases --jq 'length'
# 0

Resolve-DnsName mail.moesegfault.dev -Type MX -Server jermaine.ns.cloudflare.com
# route1.mx.cloudflare.net (39), route2.mx.cloudflare.net (49), route3.mx.cloudflare.net (94)
Resolve-DnsName mail.moesegfault.dev -Type TXT -Server jermaine.ns.cloudflare.com
# v=spf1 include:_spf.mx.cloudflare.net ~all
Resolve-DnsName _dmarc.mail.moesegfault.dev -Type TXT -Server jermaine.ns.cloudflare.com
# v=DMARC1; p=reject;

Resolve-DnsName mail.moesegfault.dev -Type MX
Resolve-DnsName amail.moesegfault.dev -Type A
# Local recursive resolver: DNS name does not exist for both.

Invoke-WebRequest https://mail.moesegfault.dev/health
Invoke-WebRequest https://amail.moesegfault.dev/
Invoke-WebRequest https://amail.moesegfault.dev/manual/
Invoke-WebRequest https://amail.moesegfault.dev/changelog/
# All: The SSL connection could not be established.
```

The authoritative MX/SPF/DMARC result confirms only those DNS records. It does not verify a routing rule, inbound Worker execution, outbound sender approval, delivery authentication, or HTTP custom domains.

## Static risk findings to turn into discriminating checks

1. **Search cap placement.** The initial implementation capped all account messages before lexical filtering. The owner revised it to page through messages, apply filters, then cap matching candidates, with an explicit 10,000-row scan limit. A selective query on an account with over 2,000 messages should now find a unique older match; the change remains unverified on a deployed Worker.
2. **Semantic indexing failure state.** The initial implementation stored an empty string on embedding failure. The owner revised send/inbound to store SQL `NULL` and added a scheduled reindex routine. Induce one OpenRouter failure, restore it, and verify an explicit incomplete-index state followed by recovery without re-ingesting mail.
3. **HTML fidelity.** The initial parser used the default `ammonia::Builder` plus a `cid` scheme. The owner added local CSS inlining and explicit safe image/style policy. Compare the actual MIME received by Gmail/Outlook-compatible fixtures containing `<img src="cid:chart">`, inline styles and `<style>` rules; source changes alone do not prove client fidelity.
4. **Ingress integration.** The live rule target is `amail-inbound`; acceptance must prove the `workers/mail-ingress` Email Routing Worker forwards raw MIME through its private service binding to the Rust API, securely and without exposing its ingress secret. Check both a registered and an unregistered recipient. The shim and deployment job appeared during this validation, but have no run evidence yet.

## Next validation gate

Once the owners report a deployed commit and CI run, record the exact commit SHA and run URLs here, inspect failed jobs before retrying, then execute the `docs/operations.md` live checklist using disposable resources. Keep only sanitized status codes, trace IDs and timestamps in this ledger; never commit mail bodies, tokens or test-address ownership details.
