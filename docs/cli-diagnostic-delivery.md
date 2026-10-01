# CLI diagnostic delivery and retention

Status: bounded source implementation; hosted acceptance evidence pending. This work
is stacked on PR 54's accepted reader source, not an enriched producer rollout.
No provider access, Mail deployment, user account creation or sending is involved.

Initial source `f38ebe116a0b493935c53cb1a98006343565bde2` in stacked PR 64 passed
hosted CI `36880337510` and syntax `36880337195`. Linux/Windows/macOS each passed
42 unit and 4 actual CLI-process tests, zero failed/ignored/filtered; every CLI
dependency-cache receipt explicitly reported `exact_hit`. Scoped CI correctly
tested changed CLI/infrastructure inputs without rebuilding unchanged Workers.
Observed workflow time was 14:56:32–14:58:09 UTC (1m37s). Linux/macOS/Windows
jobs including setup were 30s/44s/81s; these are samples, not an SLA.

Final source refinements make the initial pending-journal selection boundary
explicit before entering credential auth, test malformed legacy row handling
before credentials, and extend the HTTP fixture with an invalid private response
request-ID header. They do not add probes or alter legacy upload JSON. Final-head
hosted checks supersede this initial source acceptance and remain separately
identified by the PR check URLs; initial success is not a claim about later edits.

## Observed failure boundaries

The original detached uploader discards stderr, acquires credentials before
recording any attempt, treats non-2xx as `Ok`, and marks rows uploaded immediately
after 2xx headers without reading the legacy acknowledgement. Pending rows have
no retention bound while an offline client continues collecting events. Returning
another error from this process alone cannot make that failure visible.

## Ownership and persistence

Keep the existing physical `telemetry.sqlite3`. `events`, `journal_state` and the
new diagnostic-only receipt/counters belong to telemetry. Never prune or rename
`send_attempts`, `refresh_state`, encrypted sessions or command-state keys. Auth
continues to own credential/refresh behavior. The 250ms diagnostic lock budget
remains separate from durable command-state lock waits.

Store one last-upload receipt with generated UUID, UTC schedule/start/end clocks,
monotonic elapsed time, phase/outcome, exact received HTTP status, canonical
response request ID, and selected batch count. A receipt without a completed
result is explicitly unresolved, not successful delivery. Record before credential
work or network I/O. Do not hold a SQLite write transaction over either dependency.
Failed spawn remains visible durably rather than only in discarded stderr.
Its numeric OS error is retained, but no child start/duration is invented.
The existing hidden `_telemetry-flush` invocation still works. The new optional
internal `--attempt-id` carries the parent's generated scheduling identity and
lets a late child decline work after a newer receipt replaced it.

Normal CLI startup reports newly observed failed/unknown/unresolved receipt and
new pending-event eviction counters on **stderr**, preserving machine stdout and
command result. The hidden uploader does not recursively report/init another
upload. Persist the last reported receipt/counters to avoid repeatedly printing
an unchanged warning. Opt-out skips initialization, receipts, reporting,
retention, scheduling and uploading.
Failed/unknown attempt counters also survive a subsequent successful API
acknowledgement. Notices identify the newest started/scheduled attempt, not every
historic error; older concurrent failures still increment the durable counters.

## Delivery semantics

| Boundary | Outcome | Pending rows |
| --- | --- | --- |
| Cannot spawn uploader / acquire credentials / construct request | Failed before delivery | Retain |
| No response headers / deadline / truncated response | Unknown; delivery may have happened | Retain |
| HTTP non-2xx headers | Observed HTTP failure, exact status retained | Retain |
| 2xx but acknowledgement is oversized, invalid or count-mismatched | Unknown, not confirmed acceptance | Retain |
| Complete bounded 2xx legacy `{accepted: N}` equals selected batch count | API accepted, not proof of Queue sink retention | Atomically mark selected IDs uploaded and store acceptance |
| Process dies or receipt persistence fails after network work | Unresolved durable receipt | No invented success |
| No pending events | `empty`, not accepted delivery; no credentials/network | None selected |

Do not retry inside the uploader, probe capabilities, alter the legacy event
JSON or send a diagnostic about its own failure. Future normal scheduling may
retry still-pending diagnostics, whose duplicate-delivery semantics are already
best effort and must not be confused with business send idempotency. A later
upload outcome must not allow an older concurrent attempt to overwrite the newer
receipt. No extra upload lease/crash-retry framework is needed for this boundary.

Read at most 4096 acknowledgement bytes plus an overflow sentinel. Extract only
accepted count and canonical response correlation; never retain response text,
exception messages, URLs, tokens, subjects, paths or body data. Receipt status and
operational UUIDs are useful coordinates, not blanket-hidden private data.
Do not follow upload redirects: a different response location must not quietly
change the endpoint or acceptance boundary. Transport/body deadlines retain
`timeout` distinctly, including reqwest's timeout wrapped inside `io::Error`.

## Bounded retention and honest accounting

Retain the newest **1000 pending** events and **200 accepted-history** events.
The two limits reflect distinct state: eviction before observed acceptance is
diagnostic loss; pruning locally accepted history is routine retention. Count
both separately, with UTC prune time, using saturating durable integers. Insert/
mark/prune/counter changes share short transactions so failed pruning cannot
silently delete an unaccounted record. Re-apply the limit on startup for old
clients' oversized backlog and on insertion/completion for current clients.

Counters mean local pending eviction, not proof that the remote sink lacks that
record: an in-flight batch could be accepted while another process prunes it.
Counters must survive subsequent successful uploads. The bound is live event
rows, **not a hard physical SQLite-file byte cap**; SQLite reuses freed pages.
Do not VACUUM or change global database settings shared with command state.

## Acceptance evidence to collect

Hosted tests only, using synthetic homes below repository `.temp`:

* Actual loopback HTTP uploader: complete acceptance, HTTP rejection, timeout,
  truncated body, malformed/oversized/count-mismatched acknowledgement and poisoned
  private response metadata. Assert row transitions, safe receipt fields, clocks
  and exact legacy request shape.
* Actual CLI process: next normal command surfaces child-process auth failure or
  preseeded unresolved outcome while returning normal JSON/success; unchanged
  warnings are not repeated; opt-out touches no diagnostics.
* Transactional pending/history bounds and exact durable eviction counters,
  including concurrent writers and preservation of send/refresh/session tables.
* A stale completion cannot overwrite a newer attempt receipt. No SQL transaction
  remains open during network/credential work, and no failure creates new event
  rows or a recursive upload.

Production grounding follows OpenTelemetry's separation of enqueue/send failure
from accepted export and SQLite's short transactional updates:
https://opentelemetry.io/docs/collector/internal-telemetry/
https://www.sqlite.org/lang_transaction.html
https://www.sqlite.org/lang_vacuum.html

Implemented test boundaries also include a real failed executable spawn with a
numeric OS error, exact legacy JSON decoded by the loopback peer, no writer lock
during HTTP I/O, counting rollback on injected SQLite failure, saturating integer
counters and stale-child replay refusal. Tests do not call the user's OS credential
store: the actual CLI child uses synthetic configuration whose OAuth registration
guard fails before credentials/network access.

If the shared database is unavailable, no receipt/counter can truthfully be
persisted there. Foreground diagnostics retain the existing safe SQLite/I/O-code
stderr notice; a previously recorded scheduled/running receipt remains unresolved
when final persistence fails. This patch does not add a second store, falsely
count inaccessible records, or claim durable reporting while the medium is lost.

The reader research context in runtime-observability-foundation.md remains
applicable: causal monitoring and analysis-aware sampling require observable
failure/loss boundaries first. No novel sampling or root-cause framework is
introduced by this patch.
