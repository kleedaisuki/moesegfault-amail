# Automatic indexing privacy

Eligible active messages are automatically indexed even when the user never runs
--semantic. This is an explicit disclosed product choice, **not telemetry**;
AMAIL_TELEMETRY=off cannot disable indexing. Current bounded production indexing
acceptance is in [validation](validation.md).

The private scheduled maintenance Worker sends the longest valid UTF-8 prefix
of at most 12,000 bytes from subject plus extracted text to OpenRouter's configured
qwen/qwen3-embedding-8b route, requesting 256 dimensions. It does not send raw MIME,
ZIP/attachments, tokens or arbitrary other-account material. Semantic queries also
cross that provider boundary. Literal search continues to examine stored full text;
exact cosine refers to the stored projection, not omitted message sections.

Provider zero-data-retention/no-training routing and disabled response cache reduce
retention, not transfer. Never claim content stays only in Cloudflare or that not
using --semantic prevents processing. Manual/help/skill must disclose automatic
processing and the bounded projection consistently. A provider/model/input change
requires reviewed policy plus forward migration, not merely changing a model name.

The D1 work ledger and bounded fair owner scheduling prevent old poison rows from
starving later mail. Unavailable/missing/mismatched/quarantined vectors make semantic
search typed incomplete, never silently omit messages from supposedly exact ranking.
[Indexer operations](semantic-indexer-operations.md) owns retry/recovery semantics.

A delete before claim/active-row read prevents transfer; deletion during an in-flight
provider call cannot recall transmitted bytes, but blocks vector publication.
The local invariant is useful, not distributed erasure. Search origins retain private
request/vector/MAC only for their bounded continuation lifetime and are scrubbed at
expiry/staleness as described in [search jobs](search-jobs.md).

References: [OpenRouter ZDR](https://openrouter.ai/blog/insights/zero-data-retention/),
[response cache](https://openrouter.ai/docs/guides/features/response-caching).
