# Independent review: resumable exact search jobs (2026-09-28)

Scope: reviewed committed `crates/mail-worker/migrations/0005_search_jobs.sql`, `src/search_jobs.rs`, and the relevant search projection/budget/trigger integration in `src/lib.rs`, plus `docs/search-jobs.md` and the prior search/privacy design note. This was a static code review; no local heavy build or deployed search test was run by the reviewer. GitHub Actions [run 36424923690](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36424923690) passed 16 Worker unit tests, five search contracts, eight search-job contracts, Wasm checking, and bundling. The owner-scoped D1 lookups, versioned lease CAS, full-row marker discipline, and bounded semantic top-K are sensible. The findings below document source-level corrections; deployed concurrency and large-corpus behavior remain unverified.

## Resolved in tree — Semantic embedding admission and concurrency

The initial `search()` called OpenRouter before job admission; a cheap precheck fixed serial but not concurrent cost amplification. The revised flow now atomically inserts a `preparing` job under the five-active/256-total guards **before** calling OpenRouter (`search_jobs.rs:164-183`), reserves per-account and global daily semantic budgets, then embeds and transitions to `running` (`search_jobs.rs:187-218`). A failed preparation deletes its slot; cron removes abandoned `preparing` rows after ten minutes (`search_jobs.rs:605-612`). This closes the identified provider-cost race at source level. Hosted concurrency and provider-call-count tests remain pending.

## Resolved in tree — Aggregate admission for broad lexical search

The first fast path scanned before any aggregate admission. The revised `expensive` classifier selects text/regex/metadata/semantic predicates, and broad nonsemantic searches atomically reserve 300/account and 20,000/global daily work units **before** `scan_batch` (`search_jobs.rs:14-44,165-172`). Indexed newest/mailbox/date/read lists stay write-free; they normally require only a small keyset page. Semantic search reserves a job slot and work/model quotas before the provider call (`search_jobs.rs:202-245`). This closes the identified unlimited broad-scan path in source. Quota tuning and D1 throughput require hosted workload evidence.

## Resolved in tree — Completed-job replay and generation race

The initial code checked generation separately from the final D1 state update, and replayed cached `result_json` without rechecking it. The revised completion and checkpoint UPDATE statements contain an owner-generation subquery predicate (`search_jobs.rs:330-343`), and done replay validates current generation before rehydration and again before return (`search_jobs.rs:277-290`). A changed generation moves the job to `stale` with query/vector fields cleared. This closes the identified source-level race; hosted interleaving tests remain pending.

## Resolved in tree — Completed-job retention and total quota

The initial quota excluded done jobs, and `result_json` stored full summaries for about 48 hours. The revised schema removes `result_json`; done jobs retain bounded hit IDs/scores and rehydrate owner-scoped summaries on replay. Creation now caps active jobs at five and active+done+stale at 256 (`search_jobs.rs:143-149`), including the stale-state bypass found in an intermediate revision. At 24 hours, cron clears `request_json` and `state_json` and marks an opaque `expired` tombstone, which is deleted a day later (`search_jobs.rs:528-543`). A native SQLite contract test covers stale-state quota and the exact expiry/scrub boundaries (`tests/search_job_contract.rs`). Source-level storage/PII retention concerns are resolved; deployed quota behavior remains unverified.

## Resolved in tree — Oversized completed-result D1 row

The first implementation persisted the entire `result_json` page in one D1 row. The revised completion persists only the bounded `SearchState` hit IDs/time/score bits and clears the query vector; `result_page` rehydrates owner-scoped summaries on every replay (`search_jobs.rs:323-337,464-525`). The summary projection now clips subjects to 2,048 characters and exposes `subject_truncated` (`lib.rs:1107`), bounding a major HTTP response dimension without altering full-message storage/search. This avoids the single >2 MiB result-row failure.

## Resolved in tree — No-progress budget boundary

The revised `advance_claimed` compares markers before/after a partial batch and returns typed `search_resource_limit` when no row progressed (`search_jobs.rs:312-318`). That closes an infinite 202 poll loop for a single unprocessable row. Hosted large-body fixtures remain useful.

## Positive controls and review limits

- `load_job` scopes by `(id, owner_iss, owner_sub)`, returning 404 for other owners; completion hit rehydration also scopes by owner and excludes tombstones. No cross-owner read path was identified.
- `claim` uses state/version CAS; a late holder cannot overwrite a newer checkpoint. A fetched page's unprocessed suffix is revisited because marker advances only after a fully processed row. The semantic accumulator retains `limit+1` best hits under a deterministic score/time/ID comparator, and a semantic page resumes from the rank cursor by rescanning all eligible messages.
- Message insert/update/delete triggers cover `messages` mutations including read and embedding updates. Text chunks are written before message insert in normal ingestion and removed after tombstoning, so no ordinary uncovered text mutation was found. The formerly separate check/commit race is closed by an atomic generation predicate at checkpoint commit; deployed interleaving tests are still needed.
- A search job intentionally persists query text and a vector as account data, not telemetry; the implementation does not log these values in the inspected path. Done jobs clear the query vector, and 24-hour expiry scrubs query text/state; only an opaque tombstone lasts another day.
- Passing native/Wasm CI did not prove deployed D1 lease timing, Worker CPU behavior, or CLI polling; those need hosted concurrency and large-corpus tests.
