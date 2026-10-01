# Native canary Route and DNS lifecycle

Status: executable source lifecycle implemented; provider operations and deployed acceptance remain unexecuted. Hosted contract tests are maintained separately.
Implementation baseline: `bfb0276`; 2026-10-02.
This document scopes an alternative external ingress for the isolated native
tracing experiment. The parent owns helper implementation and dispatch. No Mail,
Identity, storage, sending, WAF or user-account capability is added.

## Fixed contract and topology

| Coordinate | Exact value / invariant |
| --- | --- |
| Zone | `6edff81c6ed02f412e70868076411a5e`, expected name `moesegfault.dev` |
| Hostname | `amail-native-trace-canary.moesegfault.dev`, reserved infrastructure hostname |
| DNS | Exactly one new `AAAA`, content `100::`, `proxied: true`, automatic TTL; exact owner comment bound to run nonce |
| Route | Exactly `https://amail-native-trace-canary.moesegfault.dev/*`, targeting only the source-owned caller script |
| Worker pair | Existing two fixed source-owned canary names; initial absence required for both |
| Ownership | Durable run receipt plus DNS comment nonce; route identity/pattern/script plus caller/probe nonce, role and serving version |
| TLS | Existing Universal SSL covering this first-level hostname; no certificate order or settings write |
| External trigger | One empty anonymous HTTPS POST; no provider credential, redirect follow or application retry |

```text
Hosted external client --HTTPS--> proxied AAAA + exact Route --> caller
                                                           |
                                                   service binding
                                                           |
                                                private native probe

Cleanup: owned Route --> owned DNS --> owned caller --> owned probe
```

A Route does not provision DNS or a certificate automatically. Cloudflare's
[Worker best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/)
explicitly permit a proxied `AAAA` to `100::` when no origin exists.
[Routes documentation](https://developers.cloudflare.com/workers/configuration/routing/routes/)
requires proxied DNS and explains pattern matching. The placeholder is not a
working origin: do not use pass-through/fail-open origin behavior as success.
The hostname is not a Custom Domain; no domain attachment or Advanced Certificate
operation is part of this alternative.

## Prerequisites: reads are not write permission proof

Source inspection found the existing native helper's provider wrapper only
supports its account/script paths; zone-path additions belong to the parent.
`infra/provider/probe_routing_write.py` examines **Email Routing Rules** grants,
not DNS or Worker Routes. Its result must not be reused as authorization for this
lifecycle. Its deny-first and unknown-shape handling are useful design precedent.

| Capability | Required evidence / restriction |
| --- | --- |
| Zone identity | Exact ID/name/account, active unpaused full setup |
| DNS writes | One smallest absent-only nonce-owned DNS creation is the effective permission probe; GET success is never promoted to write success |
| Route writes | One absent-only exact Route creation after serving pair ownership/version verification |
| Worker deployment/removal | Existing source-owned artifact, version and ownership gates remain required |
| Universal SSL | Enabled and already active covering certificate with valid time; no certificate/settings mutation |

The [DNS create API](https://developers.cloudflare.com/api/resources/dns/subresources/records/methods/create/)
requires DNS Write; the [Route create API](https://developers.cloudflare.com/api/resources/workers/subresources/routes/methods/create/)
requires Workers Routes Write. No token-policy introspection or new credential
is required. Preflight proves scope, TLS and absence only. The source-authorized,
smallest owned write is the finite effective-permission test. Failed or ambiguous
writes are journaled and never repeated automatically. This avoids requiring a
second permission ceremony that cannot establish actual write success anyway.

[Universal SSL limitations](https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/limitations/)
cover apex and first-level subdomains on a full setup zone. This hostname has
exactly one label beneath `moesegfault.dev`; `*.moesegfault.dev` covers it, but
coverage cannot be assumed merely from the hostname shape. Inspect existing
[Universal SSL settings](https://developers.cloudflare.com/api/resources/ssl/subresources/universal/subresources/settings/methods/get/)
and [certificate packs](https://developers.cloudflare.com/api/resources/ssl/subresources/certificate_packs/methods/list/)
only through an authorized parent operation. Enabled alone is not active issuance.
Reject pending/expired/uncovered packs, unsupported zone setup or ambiguous
certificate metadata. No enable/order/renew action or TLS-validation bypass is
admitted. A verified HTTPS handshake later proves served TLS at that instant,
not the native API or privacy result.

## Absent-only creation and ownership

Before any mutation, positively prove both fixed scripts absent, no DNS record
of any type at the exact hostname, and no exact/conflicting Worker route.
A complete paginated inventory is required where the API paginates; malformed,
truncated or failed lists never mean absence. Detect patterns that overlap this
host's paths (including wildcard-host and more-specific-path routes); refuse
unknown pattern syntax rather than attempting a generic routing framework.
Do not replace, patch, adopt or delete existing records/routes/scripts even if
apparently compatible. Preflight can report a conflict without exposing foreign
content. Existing ordinary service hosts/routes are never modified.

Persist a receipt before each side effect, including the fixed source-defined intended shape
and `attempted` phase, then persist the returned ID and verified readback before
advancing. The parent must bind receipt source/run/attempt, nonce, zone, hostname,
script roles and actual serving versions, not accept arbitrary user-supplied
coordinates. IDs alone do not establish ownership.

Creation order is: full GET-only preflight; owned DNS create and exact readback;
checked-artifact private probe and caller; ownership/version readback; owned Route
create and exact readback. DNS creation does not require scripts to exist; Route
creation always does. Verify
script/version ownership again before the public trigger. A Route exposes only
the caller; the probe remains private via the existing service binding.

The future exact DNS body is `{type: AAAA, name: HOST, content: 100::, proxied: true, ttl: 1, comment: amail-native-tracing/<nonce>}`. No input selects other names or types.

DNS readback must match ID, hostname, type, normalized IPv6 value, proxy flag and
exact comment nonce. Route has no nonce/comment field in the API contract; bind
its returned ID, exact pattern and caller script to the receipt and the owned
caller's nonce/role/serving version. Reject omitted script, changed destination,
changed pattern or missing ownership. Do not invent a Route nonce API property.
Fresh inventory/readback reduces replacement risk but cannot make independent
provider API calls transactional; writer serialization is still required.

## Unknown outcomes and destructive safety

Each POST/DELETE is single-attempt. Timeout, connection loss, non-success
response or missing/malformed acknowledgement creates an **unknown outcome**,
not permission to resubmit. Persist that boundary, then perform bounded exact
readback/inventory in a separately admitted recovery path. No automatic retry,
name sweep, replacement nonce or speculative delete is allowed.

* Unknown DNS create: inspect the exact hostname; only one exact nonce-owned
  match may be recorded as recovered. No match means no presently observed
  resource, not proof that another POST is safe or authorized.
* Unknown Route create: inspect the exact pattern, expected caller and script
  ownership/version. A unique match may be recovered only with durable pre-write
  receipt plus absent-before-create evidence. Ambiguity/foreign replacement
  remains unowned; no delete-by-pattern and no create retry.
* Unknown deletion: confirm exact absence before recording cleanup success.
  If the owned object remains, stop with unresolved outcome, not another DELETE.

Before cleanup, read back all relevant ownership facts. Delete only the exact
owned Route, positively confirm it absent, then exact owned DNS, confirm absent,
then owned caller/probe. A route conflict or unconfirmed route removal stops DNS
and script deletion: do not leave a live route pointing at a removed script.
A DNS ownership conflict stops subsequent script deletion. Already-absent owned
resources may count as removed only from successful exact readback/inventory.
A failed read cannot count as absence. Foreign IDs/comment/nonces/versions cause
fail-closed refusal; unrelated records and scripts are untouched. Interrupted
runs retain recovery coordinates rather than declaring the fixed hostname free.

## 1042: transport layers must not be conflated

[Cloudflare's error table](https://developers.cloudflare.com/workers/observability/errors/)
associates 1042 with Worker-to-Worker fetch on the same zone.
[Route documentation](https://developers.cloudflare.com/workers/configuration/routing/routes/)
states Routes cannot be targets of same-zone `fetch()`. This is not a reason to
set `global_fetch_strictly_public` in our experiment.

The existing Rust caller uses `env.service("PROBE").fetch_request(...)` to invoke
the private probe, not a public same-zone URL fetch. The external hosted Python
POST is also not a Worker-originated same-zone fetch. Keep this topology and
all compatibility flags unchanged. Do not route the caller through another
Worker or change the probe's service binding to URL fetch.

The historical absent-workers.dev 404/1042 did not identify its internal provider
proxy/routing path. It does not prove a defect in this different ingress, a
specific edge policy, or a health result. If the reviewed Route experiment still
returns 1042, retain status, tightly parsed code, CF-Ray, source/run/serving
versions and exact routing readback; clean up owned resources. The next safe
step is a separately admitted **no-write exact routing/topology discriminator**,
not a flag/WAF change, new credential or repeated POST. A 403/1010 likewise
requires owned-host policy evidence, not browser impersonation or disabling BIC.

## Hosted lifecycle contract test plan

Tests must use the parent's shared helper interface, fake provider inventories
and scripted outcomes. Do not add another production helper to satisfy tests.
Test file ownership: `infra/tests/test_native_route_lifecycle_contract.py`.
The implementation is `infra/deploy/native_route_lifecycle.py`. Provider transport
must expose `request(method, suffix, data=None, *, envelope=False)`, `account`,
and `script(name, suffix="settings")`; envelope mode preserves pagination metadata.
The Routes endpoint is a documented non-paginated array. DNS, certificates and
Worker Domains require count-consistent complete paginated inventories, bounded
at 100 pages / 10,000 objects, with duplicate IDs refused. Requests use 50
objects per page, respecting the certificate-packs documented maximum of 50. Worker deployment GET
returns `{deployments: [...]}`.

`preflight(provider)` returns only fixed coordinates and successful booleans,
never foreign inventory or certificate contents. Parent persists this result in
`receipt.ingress = {schema: "native-route-ingress/v1", zone_id, hostname, preflight}`.
The shared receipt retains `source_sha`, `run_id`, 32-hex `probe_id` and `versions`.
DNS and Route children contain only `phase` and a positively known opaque `id`.
Phases are `attempted`, `verified`, `unknown`, `delete_attempted`, `delete_unknown`,
`deleted`. Parent-supplied `persist(receipt)` must durably save before each write.

`create_dns`, `create_route`, `cleanup_ingress` accept `(provider, receipt, persist)`.
`assert_pair` and `assert_ingress` accept `(provider, receipt)` and return no value
on success. Unknown create recovery is cleanup-only: one exact owned inventory
match may be recorded and removed, but never retried or used to continue exposure.
Unknown delete recovery performs reads only; a still-present object prevents a
second DELETE. A cleanup refusal prevents parent script deletion.

Runtime test execution belongs on
GitHub-hosted infrastructure; local static syntax/diff checks are allowed.

Required cases:

1. Fixed coordinates and exact DNS/Route request bodies; no Custom Domain,
   certificate write, WAF edit, global-fetch flag, arbitrary target or new token.
2. All initial absence checks precede first mutation; any DNS type/script/route
   conflict, overlap, unknown schema, failed read or incomplete inventory refuses.
3. DNS ownership requires all exact fields and nonce; IPv6 equivalent canonical
   forms are handled deliberately; no broad object adoption.
4. Route ownership requires ID/pattern/script plus caller nonce/role/version;
   missing or changed fields refuse even when the route ID matches.
5. Success persists receipt phases before/after each create and verifies exact
   readbacks; triggers only after every prerequisite is accepted.
6. POST timeout, bad acknowledgement and malformed body never create a second
   POST; recovery requires unique exact ownership; foreign/duplicate matches
   stop without destructive action.
7. Cleanup order Route -> DNS -> caller -> probe; route unknown/error/replacement
   prevents lower-level deletion; DNS mismatch/unknown likewise prevents scripts.
8. Already-absent owned resources are distinguished from 401/403/5xx/transport
   failures. DELETE timeout performs at most one mutation and no blind retry.
9. Successful GET cannot become write-success proof; pending SSL, uncovered or
   expired certificates and unsupported zone setup block admission.
10. Public receipts expose operational IDs/status/timing only; arbitrary provider
    prose, token policy, credentials and response bodies do not enter output.

## Evidence produced here

Read maintainer/Cloudflare skills, foundation/canary notes, native helper, Rust
caller topology, existing token-policy classification source and official API/
routing/SSL documentation. No provider API request, DNS resolution/HTTPS service
probe, write, deployment, account or runtime test was performed for this design.

## Implementation verification boundary (2026-10-02)

The executable module implements preflight, smallest DNS create, route create,
pre-trigger ownership readback and ordered cleanup. Opaque IDs are bounded and
URL-encoded rather than assumed to be 32-hex. DNS compares canonical IPv6, proxy,
TTL and exact nonce comment. Route checks its ID, fixed pattern and caller plus
both serving roles/nonces/versions. No provider request or local runtime test was
performed while implementing this source. Static Python syntax and whitespace
checks do not constitute hosted contract or provider acceptance.
