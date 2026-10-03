# Search filters, pagination and resumable exact work

Read when finding mail, continuing pages or handling a search job. Use
`amail discover search` and installed help for the targeted contract; the examples
below describe v0.1.2 rather than service availability or sending authorization.

## Narrow before retrieving content

```sh
amail sync --limit 20
amail search --from sender@example.org --unread
amail search --title release --after 2026-01-01T00:00:00Z --before 2026-10-01T00:00:00Z
amail search --meta attachment_name=chart.png
```

Predicates combine with AND. `--after` is inclusive, `--before` exclusive, in UTC.
Other filters include mailbox, to, body, read state, regex and case sensitivity;
use `--semantic` only when meaning-based search helps and its query transfer is
appropriate. Ordinary search does not stop [background indexing](privacy.md).
Search results are compact metadata, not bodies, and do not mark mail read.

Allowlisted metadata keys are `message_id`, `rfc_message_id`, `provider_id`,
`in_reply_to`, `reply_to`, `references`, `content_type`, `attachment_name`.
Distinct `--meta KEY=VALUE` flags combine; a repeated same key is rejected rather
than silently overwritten. `references` matches individual IDs, not concatenated
chains. Metadata patterns are bounded at 512 UTF-8 bytes; ordinary text at 256.
For identity distinctions read [replies](replies.md) only if relationships matter.

## Continue complete pages, not stale result sets

A JSONL `{"next_cursor":"..."}` record is pagination metadata, not a message.
Pass it unchanged with the same filters and `--cursor`; do not decode/edit it.
Current v5 semantic pages reuse the exact first-page server-held query vector,
whose origin expires after at most 24 hours. Do not concatenate restarted pages
with a previous result set.

Collect the bounded intended ID set before `mark` or `delete`; a
paginate -> mutate -> next-page loop can invalidate its own cursor. If enumeration
becomes stale, restart it without mixing pages, retain completed per-ID work and
never repeat an irreversible action just because listing restarted.

## Resume unfinished work

```sh
amail --machine search --title release --wait-seconds 1
amail --machine search --resume SEARCH_JOB_UUID --wait-seconds 30
```

Replace `SEARCH_JOB_UUID` with the returned job ID. The service may accept durable
work for a large exact search; stdout contains only a **complete** result page.
In `--machine` mode read the versioned stderr job/next-action record rather than
English prose. Default mode prints a prose resume hint. `--resume` accepts no
filters; do not resubmit private filters while that accepted job exists.

`--wait-seconds` bounds only this invocation (default 900, valid 1..86400).
Jobs are owner-scoped and normally retained for 24 hours. Completion can return a
normal `next_cursor`; use it for the next filtered page, not with `--resume`.

| Typed state | Action |
| --- | --- |
| Running / `resume_search` | Resume that job; unfinished is not empty. |
| `search_job_stale`, `search_job_expired` | Start a fresh search if still needed. |
| `search_cursor_stale`, `search_cursor_expired` | Restart page 1; never mix old/new pages. |
| Legacy `search_cursor_vector_changed` | Discard the compatibility cursor and restart. |
| `search_job_quota`, `search_work_quota`, `semantic_quota` | Respect limits; finish work or wait rather than retry aggressively. |
| `semantic_index_incomplete` | Eligible mail awaits indexing, not an empty or partial answer; use bounded waiting/retries of the same query, or resume its accepted job. |

Only an initial cursorless `sync` automatically retries `search_job_stale` once;
other stale pages/jobs require fresh enumeration. None of these failures means
there were no matching messages.
