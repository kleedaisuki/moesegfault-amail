# Resumable exact searches

Read this only when `amail search` reports a job ID, an interruption, or a typed search-job failure. The installed CLI help is authoritative for flags.

The service may return an accepted background job for a large exact search. The CLI polls automatically and writes only the **complete** result page to stdout. The job ID and resume hint appear on stderr; they are not search results. If the command times out or is interrupted, run `amail search --resume JOB_ID` with no filters. `--wait-seconds N` bounds this invocation's wait (CLI default 900 seconds, valid 1–86400); it does not change the underlying query or turn partial results into a complete page. Jobs are scoped to the authenticated account and retained for a limited time. Do not repeat the original private query while a resumable job exists.

| Failure | Meaning | Agent action |
| --- | --- | --- |
| `search_job_stale` (409) | Mailbox state changed, invalidating ranking. | Start a fresh search if still needed. |
| `search_job_expired` (410) | Resumable job retention elapsed. | Start a fresh search if still needed. |
| `search_cursor_expired` (410) | The v5 semantic vector origin reached its 24-hour expiry. | Restart at page 1; do not concatenate with previous pages. |
| `search_cursor_stale` (409) | Corpus generation or cursor compatibility changed. | Restart at page 1; do not concatenate with previous pages. |
| `search_job_quota` (429) | Too many jobs retained for the account. | Finish existing jobs or wait for expiry; do not retry aggressively. |

None of these errors means an empty result set. A job's successful completion returns a normal result page, including any continuation cursor. Use that cursor with a new filtered search page rather than with `--resume`.
