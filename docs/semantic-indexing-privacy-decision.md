# Opt-in semantic indexing privacy

The v0.3.1 contract replaces automatic account-wide third-party indexing with an
account-level switch that is **off by default**, including for existing accounts.
Both enabling and disabling require the `user` profile and human browser approval
unless the human already explicitly configured YOLO. An agent profile cannot use
YOLO to gain user authority. The setting affects all profiles in the account.
Telemetry settings are independent. Publication and hosted acceptance are recorded
in [validation](validation.md), not established by this contract.

| State or transition | Content processing | Stored document embeddings |
| --- | --- | --- |
| Default / disabled | No new document or query requests to the embedding provider | Existing embeddings remain stored, but cannot enable semantic search |
| Enable, after approval | Background work fills eligible mail without a usable Voyage vector, then subsequent missing mail | Compatible retained Voyage vectors are reused; legacy Qwen migrates once |
| Disable, after approval | Stops admitting new provider requests; in-flight transmitted bytes cannot be recalled | Old vectors are not deleted merely because indexing is disabled |
| Re-enable, after approval | Sends only mail still missing a usable Voyage vector | Reuses existing compatible vectors without retransmitting their mail text |

Use `amail semantic status`, `amail semantic enable` or `amail semantic disable`.
An already-enabled enable is not a new indexing request. A switch approval is
bound to the observed generation: a concurrent change requires fresh review, not
blind replay. An agent profile cannot change this account-wide setting.

The private scheduled maintenance Worker sends the longest valid UTF-8 prefix of
at most 12,000 bytes from subject plus extracted text through OpenRouter to
Voyage 4. It does not send raw MIME, ZIP/attachments, tokens or arbitrary
other-account material. An enabled semantic search also sends its query text.
Ordinary literal search needs no embedding-provider query and remains available
with semantic indexing disabled.

Re-enablement does not retransmit unchanged mail that already has a usable Voyage
embedding. Its original publication consent generation does not make it stale;
current consent still gates search, new provider requests and publication of work.
Mail received while disabled is filled in when consent returns. The forward-only
0019 backend correction preserves stored vectors and outstanding retry state;
switching does not reset backoff or quarantine.

The approved Qwen-to-Voyage migration remains one-time work: incompatible old
vectors cannot be compared with Voyage queries, so their mail text is processed
once after user enablement. The successful Voyage vector is then reused across
later switches. Model identity, dimensions, input version and content projection
prevent mixed spaces without treating every consent switch as a model change.

The route is [`voyageai/voyage-4`](https://openrouter.ai/voyageai/voyage-4),
requesting 256 dimensions supported by
[Voyage's model contract](https://www.mongodb.com/docs/voyageai/models/text-embeddings/).
Matryoshka representation learning ([MRL](https://arxiv.org/abs/2205.13147))
motivates flexible output sizes, not a claim that this workload has measured
256-dimensional quality equivalent to larger vectors. Explicit model/projection
identity follows the practical requirement to
[re-index rather than mix model spaces](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/semantic-text-setup-configuration).
Keeping the same inference model permits
[retaining embeddings without rerunning inference](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/semantic-text-search-retrieval).

## Approved Voyage retention policy

The owner explicitly approved the non-ZDR Voyage route for v0.3.1. The fixed
policy is `voyage4_no_training_retention_v1`: only provider `voyageai`, no provider
fallbacks, `data_collection: deny`, and `X-OpenRouter-Cache: false`. The request
omits `provider.zdr`; it does not send `zdr: false` to weaken stricter account
policy. If account-level ZDR or another provider restriction rejects this route,
fail closed instead of changing that account setting or selecting another model.

No-training and zero retention are different promises. The selected provider is
restricted to its no-training policy, but **may retain transmitted mail text,
queries and outputs under its terms for an unspecified period**. amail does not
promise a provider-side deletion deadline or zero retention. Disabling indexing
or deleting local/service mail does not request, prove or guarantee erasure at
OpenRouter or Voyage. The enable browser must disclose this boundary before
approval; status exposes the policy identity rather than implying a ZDR route.

[OpenRouter's provider policy documentation](https://openrouter.ai/docs/guides/privacy/provider-logging)
separates training controls from upstream retention. Its own prompt/output
logging and product-use options are opt-in, while request metadata is retained;
operators must leave content logging/use disabled rather than assuming the
per-request provider policy controls OpenRouter account logging. See
[OpenRouter data collection](https://openrouter.ai/docs/guides/privacy/data-collection).
Disabling response cache does not change an upstream retention policy.

Never claim content stays only in Cloudflare or that disabling indexing deletes
material already transferred to a provider. A disable
or deletion that wins before provider admission prevents a new request; an
already admitted call may still transmit, but a stale generation cannot publish
its result. No transaction is held open across provider I/O.

The D1 work ledger and bounded fair owner scheduling prevent old poison rows from
starving later mail. Unavailable/missing/mismatched/quarantined vectors make an
enabled semantic search typed incomplete, never silently omit messages from an
apparently exact ranking. [Indexer operations](semantic-indexer-operations.md)
owns retry and recovery semantics.

Search origins retain private request/vector/MAC only for their bounded
continuation lifetime and are scrubbed at expiry/staleness as described in
[search jobs](search-jobs.md). `AMAIL_TELEMETRY=off` changes diagnostic processing,
not the account's semantic consent or server search-task retention.

Related distinction: [OpenRouter ZDR](https://openrouter.ai/docs/guides/privacy/zero-data-retention)
is a stricter routing constraint, **not provided by this approved Voyage policy**;
[response cache](https://openrouter.ai/docs/guides/features/response-caching)
is a separate control.
