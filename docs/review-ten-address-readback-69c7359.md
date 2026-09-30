# Review: complete staging ten-address readback adapter

Reviewed commit: `69c7359574960b80e41ce781ca348c5df37c3340`.

## Decision

**GO for hosted source CI; NO-GO for live quota dispatch.** No substantive defect was found in this dormant read-only increment. This is not a live provider acceptance or permission attestation.

## Scope and evidence

Static review covered `staging_ten_address_readback.py`, its synthetic tests, the changed manifest/storage contracts, the campaign controller callers, the shared `cf_rules` pagination and redirect-resistant HTTP helper, all address migration column declarations, and fixed staging D1/R2 configuration in `crates/mail-worker/wrangler.toml`. No local test, build, Cloudflare request, SMTP submission, deployment, account mutation, or route mutation was performed.

* D1 reads use the fixed staging database and parameterized candidates. Allocation reads retain every current address column, include all global non-retired states plus candidate tombstones, use stable ordering and a bounded limit, and require independent matching counts before/after. The existing schema fixture compares against all address migrations. Owner issuer/subject remain unprojected and are independently checked by manifest prefix/recovery contracts.
* Zone routing inventory reuses the bounded, count-consistent, duplicate-ID-rejecting `cf_rules` adapter. Normalization does not filter disabled, unrelated forward, or drop rules out of capacity. Unknown/nonliteral/multiple matcher/action forms fail closed. Complete raw rule digests preserve priority, forward recipients, and additional fields for unrelated-state equality. Only the exact enabled API-owned staging inbound action remains recovery-eligible.
* R2 reads use whole-bucket LIST only, without prefix/delimiter selection or object GET/DELETE. Keyset progression rejects reordered/duplicate keys, enforces inventory/page bounds, and demands an explicit empty follow-up even after a short page. Empty pages declaring truncation are rejected. Missing required replacement metadata fails closed. Canonical digests cover all returned object fields; additions, removals, and observable same-key metadata replacement reject campaign prefix or final cleanup success.
* Two consecutive complete cross-service observations must agree canonically. This detects observed drift without claiming an atomic distributed snapshot or capacity reservation. External allocation/Cron concurrency can still invalidate a future campaign, as the design explicitly states.
* The HTTP capability accepts only GET of the fixed staging bucket LIST path and SELECT-only POSTs to the fixed database; provider redirects are rejected. Tokens, raw records, provider response bodies, and object keys are not emitted by this module. Read failures reaching the public snapshot capability use fixed source-owned codes. There is no executable entry point or workflow target in this increment.

## External contract verification

The [Cloudflare R2 List Objects API](https://developers.cloudflare.com/api/resources/r2/subresources/buckets/subresources/objects/methods/list/) documents `start_after` as selecting keys after a supplied key in lexicographic order, and exposes optional ETag, size, last-modified, and pagination fields. This supports the keyset approach; optional metadata omission is intentionally a rejection, not evidence of unchanged storage. Metadata equality is an observation, not cryptographic proof of object-byte identity or a history of transient changes between reads.

## Limits and next gate

Synthetic fixtures were inspected, not executed. Hosted CI must discover and pass the new tests along with existing manifest/controller tests before this source increment is accepted. The new tests exercise short-page continuation, malformed truncation/order/metadata, aggregate drift, count-preserving raw-rule drift, storage drift, fixed config binding, and suppressed private exceptions. No inference is made about actual Cloudflare LIST capability or live response shapes.

Live dispatch still requires the separately reviewed native PKCE/subject wrapper, exact CI-built binary and serving/binding/hold provenance, immutable encrypted upload/download and same-artifact recovery orchestration, and pinned real AES-GCM hosted integration. This review grants none of those missing mutation capabilities. The one-principal quota campaign remains distinct from two-principal mailbox isolation.
