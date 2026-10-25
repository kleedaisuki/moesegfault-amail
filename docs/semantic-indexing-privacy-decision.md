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
| Enable, after approval | Background work indexes all eligible retained mail, then subsequent eligible mail | A fresh indexing generation replaces old vectors only after successful publication |
| Disable, after approval | Stops admitting new provider requests; in-flight transmitted bytes cannot be recalled | Old vectors are not deleted merely because indexing is disabled |
| Re-enable, after approval | Re-indexes the complete eligible retained corpus, including already indexed mail | Never treats a retained old vector as proof that the new generation is complete |

Use `amail semantic status`, `amail semantic enable` or `amail semantic disable`.
An already-enabled enable is not a new full-index request. A switch approval is
bound to the observed generation: a concurrent change requires fresh review, not
blind replay. An agent profile cannot change this account-wide setting.

The private scheduled maintenance Worker sends the longest valid UTF-8 prefix of
at most 12,000 bytes from subject plus extracted text through OpenRouter to
Voyage 4. It does not send raw MIME, ZIP/attachments, tokens or arbitrary
other-account material. An enabled semantic search also sends its query text.
Ordinary literal search needs no embedding-provider query and remains available
with semantic indexing disabled.

Retaining an embedding is not a remote retransmission: on re-enable the service
re-sends the **mail text** to compute a fresh embedding, rather than uploading an
old vector as if it could be converted into another model's embedding space.
The dedicated forward migration preserves existing vectors while disabling
processing. Model identity, dimensions, input version and consent/indexing
generation prevent old Qwen and new Voyage projections from being mixed.

The route is [`voyageai/voyage-4`](https://openrouter.ai/voyageai/voyage-4),
requesting 256 dimensions supported by
[Voyage's model contract](https://www.mongodb.com/docs/voyageai/models/text-embeddings/).
Matryoshka representation learning ([MRL](https://arxiv.org/abs/2205.13147))
motivates flexible output sizes, not a claim that this workload has measured
256-dimensional quality equivalent to larger vectors. Explicit model/generation
identity follows the practical requirement to
[re-index rather than mix model spaces](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/semantic-text-setup-configuration).

Provider zero-data-retention/no-training routing and disabled response cache reduce
retention, not transfer. Never claim content stays only in Cloudflare or that
disabling indexing deletes material already transferred to a provider. A disable
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

References: [OpenRouter ZDR](https://openrouter.ai/blog/insights/zero-data-retention/),
[response cache](https://openrouter.ai/docs/guides/features/response-caching).
