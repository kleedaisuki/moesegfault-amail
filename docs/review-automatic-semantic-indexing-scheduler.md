# Automatic semantic-index scheduler: independent review (2026-09-29)

Scope: commit `34a0ba0` and follow-up fix `8dfae5d`, migration 0007, the Cron ledger/lease path, provider classification, and semantic-search compatibility checks. This was a static source review, not a hosted D1/provider test or deployment verification. The product decision is automatic indexing with advance disclosure; see `semantic-indexing-privacy-decision.md`.

## Finding and disposition

**P1, resolved by `8dfae5d`: the provider call could outlive the original 120-second lease, causing duplicate mail-content transfers.** Original `crates/mail-worker/src/lib.rs:473-480` claimed a 120-second lease; `:488` awaited `platform::embed_classified`, whose Fetch has no application timeout or lease renewal. Cloudflare permits a scheduled invocation to run for up to 15 minutes, including network wait ([Workers limits](https://developers.cloudflare.com/workers/platform/limits/)); the Cron cadence is five minutes. A stalled first invocation could therefore overlap a second claim of the same mail. The token-fenced final write protected vector ownership, but not duplicate provider transfer or billing. This was a conditional production path, not an observed incident.

The follow-up sets `EMBEDDING_LEASE_MS` to 20 minutes, longer than the documented 15-minute scheduled-invocation wall limit, and uses it in the claim. Under that platform limit, another Cron cannot reclaim a row while the original invocation is still active; a killed invocation is recovered on a later sweep. The operations document records the limit dependency. This resolves the identified overlap path without an application-level timeout. A crash after provider processing but before D1 commit can still produce a later repeat; a D1 lease cannot guarantee exactly-once external side effects, and neither code nor operations text makes that promise.

## Checks that did not produce another finding

- Migration 0007's insert trigger and backfill cover active NULL-vector messages, and delete/embedding-completion triggers remove work. The claim and final write both check active, missing-vector rows and a matching lease token. Deletion after the last active-row read but before the network send remains inherently possible without a cross-system transaction; the operations document states this boundary accurately.
- The due query limits an owner to four rows per sweep and prioritizes owner rank before last-served time. A quarantined row leaves the due set, so the original oldest-20 poison-row starvation is removed. Hosted D1 rows-read and latency at a large backlog remain unverified.
- Status classification distinguishes dependency, rate-limit, transient, ambiguous 400/413/422, and malformed vectors without persisting raw provider responses. Ambiguous 4xx remains retryable by design rather than assuming a bad message.
- The semantic scan requires query/document model, 256 dimensions, and input version 1 before scoring. The model is read from the same invocation's `Env` after the query embedding call, so I found no concrete configuration-change race there. Existing jobs lacking a model checkpoint fail typed incomplete rather than being compared in an unknown vector space.

Hosted CI, synthetic-message staging, real provider-route eligibility, and deployed public disclosure are separate release gates, not established by this review.
