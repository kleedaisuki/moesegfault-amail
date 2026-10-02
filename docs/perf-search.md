# Exact search and performance

## Dominant contract

All authorized filter-matching vectors participate in exact 256-dimensional cosine
ranking; semantic search cannot present an arbitrary candidate prefix as a complete
answer. Stable score/time/ID ordering and mutation-bound cursors are user contracts.
Lexical search remains available when semantic indexing/provider work is incomplete.
[D1 limits](https://developers.cloudflare.com/d1/platform/limits/) motivate bounded
continuations, not weaker answers; [search jobs](search-jobs.md) defines those states.

A batch persists only its last fully examined row plus bounded top-limit+1 hits.
If a budget ends inside a row/page, revisit its uncommitted suffix. One oversized
unit that cannot progress returns a typed resource error. No complete 200 until EOF
and the mailbox generation still match. Indexed mailbox/time/read listings avoid
broad text scanning/admission writes.

## Measurement before complexity

Use a representative synthetic corpus, real authorized filters and fixed stored
query vectors. Compare identical answers before optimizing. Measure D1 statements/
rows/bytes, reconstructed text, CPU/memory, continuation count and end-to-end latency
across small mailboxes, broad filters and larger bodies. Include equal timestamps,
near ties, mutation, lease contention and interrupted continuations.

[Validation](validation.md) records two-document exact-score and real production
journey evidence; it is not a throughput benchmark. No large-corpus measurements
justify ANN, a vector database, a scheduler service or a per-patch oracle campaign.
Prefer bounded top-K memory and existing D1 keyset indexes first. Change representation
only after a measured dominant bottleneck, preserving exactness and old wire behavior.
