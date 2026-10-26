# Semantic indexer: consent generations, D1 ledger and recovery

The v0.3.1 indexer is **off by default per account**, including after upgrading an
existing account. The private scheduled maintenance Worker runs indexing; the API
has empty Cron. `amail semantic status|enable|disable` exposes the account-wide
setting. Only an active `user` profile can change it, normally after browser
approval; an existing human-configured YOLO setting retains its usual behavior.
All other profiles share the resulting setting, not permission to change it.
See [privacy](semantic-indexing-privacy-decision.md) and [validation](validation.md).

## State ownership and transitions

`messages` owns the mail and its retained document vector. Vector validity follows
the unchanged content projection, model, dimensions and input version, not the
current consent generation. Consent gates use and new processing; it does not
expire an otherwise compatible stored vector. `embedding_work` is a durable queue, not a second copy of
mail. It holds opaque message/owner identities, arrival time, generation,
retry/lease state and fixed error codes, never subjects, bodies, addresses or
provider responses. `embedding_owner_schedule` tracks bounded fair service;
`embedding_dependency` holds the global provider cooldown.

| Transition | Durable effect | Provider effect |
| --- | --- | --- |
| Forward migration 0018 | Preserve legacy embeddings; absent preferences mean consent off; revoke old work/lease eligibility | No mail re-send |
| Backend correction 0019 | Preserve preferences and vectors; reconcile work with usable Voyage projections | No retransmission or implicit enablement |
| Disabled to enabled | Advance consent generation and admit only eligible mail without a usable Voyage vector | Background work fills missing vectors; legacy Qwen is migrated once |
| Enabled to disabled | Revoke new work and stale publication eligibility; keep document vectors | No newly admitted document/query requests |
| Same desired state | No state transition or work restart | No extra provider work |
| Re-enable | Reuse compatible retained vectors; resume outstanding work under the new consent generation | No document call for already indexed, unchanged Voyage mail |

Switches use the caller's observed generation as a compare-and-swap condition.
A conflicting concurrent opposite-state switch requires a fresh status/approval decision rather
than silently replaying consent. Index state and consent are separate: enabled
with a pending corpus is not ready, and disabled with stored vectors is not enabled.
Toggling is not a retry-reset API: existing backoff, attempt counts and quarantine
remain in force. Mail received while disabled is filled in after enablement.

Each provider admission requires current enabled consent and generation as well
as a live eligible message. Publication requires that same consent generation and
lease, preventing disable/re-enable or deletion from accepting an old result.
There is no transaction across provider I/O: already admitted bytes cannot be
recalled by a concurrent disable. Never describe this as distributed erasure.

`semantic_preferences` stores the account switch and monotone `generation`.
`embedding_work.consent_generation` and its mirrored consent lease token fence
claims, including claims attempted by an overlapping old Worker;
`messages.embedding_consent_generation` records the consent under which a vector
was published; equality with the latest consent generation is not a freshness
requirement. Migration 0018 introduced consent and preserved legacy vectors.
The forward-only `0019_incremental_embeddings.sql` correction separates stored-vector reuse from lease/query
revocation. Never edit the already deployed 0018 migration to change that contract.
`semantic_compatible_embeddings` centralizes usable-vector membership. Status
`indexed_messages` counts compatible active vectors even while disabled;
`pending_messages` describes outstanding work, not a request to regenerate
already compatible vectors.

## Bounded processing and model migration

Every five-minute Cron sweep selects at most 20 due IDs with at most four rows per
owner, favoring least-recently-served owners and first pending work over second.
This rotates across more than 20 owners without letting poison rows monopolize
the batch. It is a throughput bound, not a five-minute full-index SLA. The
20-minute per-item lease exceeds the current 15-minute scheduled-handler wall
limit; revisit it if Cloudflare raises that limit.

The input is the longest valid UTF-8 prefix of at most 12,000 bytes from
`subject + "\n" + body_text`. Requests go through OpenRouter to Voyage 4, with
separate document/query task types. Raw MIME, ZIPs and attachments are not inputs.
Policy `voyage4_no_training_retention_v1` pins provider `voyageai`, disables fallback,
sets `data_collection: deny` and disables response caching. It omits the request
`zdr` field: this user-approved route is **non-ZDR**. Upstream may retain inputs
and outputs for an unspecified period under its terms; disabling indexing or
mail deletion does not guarantee upstream erasure. An account-level ZDR rejection
is a closed failure, not permission to turn off that account protection. Keep
OpenRouter's own content-logging/product-use opt-ins disabled; provider policy
fields and response-cache flags do not configure those settings.
The exact route is `voyageai/voyage-4`, requesting 256 dimensions; see
[the route](https://openrouter.ai/voyageai/voyage-4) and
[Voyage's dimension/task contract](https://www.mongodb.com/docs/voyageai/models/text-embeddings/).
The dedicated forward migration does not transform Qwen coordinates into Voyage
coordinates: the spaces are incompatible even when dimensions match. A successful
fresh result replaces an incompatible legacy vector and records model,
dimensions, input version and the publication's consent generation. Once a Qwen
projection has become a valid Voyage projection, later disable/enable cycles do
not resend that mail. Semantic queries score compatible vectors regardless of
the consent generation that produced them; incomplete or
quarantined rows produce typed incomplete, never a silent partial ranking.
Ordinary literal search remains independent.

Transient errors retain the existing per-message backoff: approximately five
minutes, 15 minutes, one hour, six hours, then at most 24 hours with deterministic
jitter. Provider authentication, throttling and transport/5xx errors open a global
cooldown rather than spending a call per message on a broken route. Ambiguous
400/413/422 responses are not proof of corrupt mail; repeated ambiguous responses
open cooldown. Locally impossible inputs and repeated invalid vectors quarantine
the row. Fixed codes, not provider bodies or mail, belong in diagnostics.

## Readout and recovery

Use aggregate SELECT-only diagnostics in the intended realm. Do not retrieve
subjects, bodies, vectors or raw provider errors for health checks. Separate
**disabled retained vectors**, **enabled compatible vectors**, **pending work** and
**quarantined work**: counting only NULL vectors is no longer a correct backlog
measure because an incompatible retained Qwen vector may await its one-time
Voyage migration. Compatible Voyage vectors are not backlog after re-enablement.

```sql
SELECT state,
       CASE WHEN lease_until > CAST(unixepoch()*1000 AS INTEGER) THEN 'leased'
            WHEN next_attempt_at > CAST(unixepoch()*1000 AS INTEGER) THEN 'backoff'
            ELSE 'due' END AS bucket,
       COUNT(*) AS messages, MIN(received_at) AS oldest_received_at
FROM embedding_work GROUP BY state,bucket;

SELECT blocked_until,last_error_code FROM embedding_dependency WHERE id=1;
```

A growing due backlog is a capacity signal, not proof of a failed Cron invocation;
a growing quarantine needs diagnosis. After correcting a provider dependency,
let cooldown expire or explicitly review a targeted reset. Never delete work to
make incomplete search appear healthy, clear retained vectors as a disabling
mechanism, or enable accounts as an operator migration shortcut. Quarantine reset
must preserve the active message and its current consent generation.

Deploy from reviewed same-run artifacts with the old background sender fenced
before migration; changing a model name alone is not a migration. Historical
migrations 0007/0010 remain immutable. Search jobs/cursors are invalidated across
a consent/model generation change instead of reusing incompatible query vectors.
The affected hosted checks exercise retained Voyage reuse, missing-only admission,
one-time Qwen migration, retry-state preservation and disable/re-enable fences.
Reuse established default-off/user-authority evidence rather than repeating
unrelated suites; use no customer mail as a canary.

References: [D1 SQL](https://developers.cloudflare.com/d1/sql-api/sql-statements/),
[D1 migrations](https://developers.cloudflare.com/d1/reference/migrations/),
[Workers scheduled handler](https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/),
[Workers limits](https://developers.cloudflare.com/workers/platform/limits/).
