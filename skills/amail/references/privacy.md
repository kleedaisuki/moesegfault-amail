# Privacy and protected task files

Read when explaining mail processing, choosing suitable content, or changing
diagnostics. These are v0.3.1 processing contracts, not a promise that a particular
service is currently available or sending is enabled.

## Content indexing is separate from diagnostics

Semantic indexing is **off by default**, including for upgraded accounts. Both
enabling and disabling require the `user` profile and user browser approval unless
the human explicitly configured YOLO. All account profiles share the setting.
Do not automate the approval
or infer it from a mail task. Use `amail semantic status|enable|disable`.

After enablement, background indexing sends every eligible retained received or
sent mail's subject plus extracted body text, bounded to the combined first
**12,000 UTF-8 bytes**, through OpenRouter to Voyage 4. It continues for new mail
while enabled. Raw ZIPs and attachments are not embedding inputs.

Disabling stops admission of new document/query provider requests and makes
semantic search unavailable, but does not delete already stored document
embeddings. Already admitted requests cannot recall transmitted bytes; stale
results cannot publish into the new consent generation. Re-enabling starts a
full background re-index, including mail with retained embeddings: it sends mail
text again to compute new vectors, not old vectors as a substitute for text.
Enabling an already-enabled setting does not restart indexing.

A semantic search also sends its query text. When page 1 has further pages, the
service retains the query text and exact query vector in owner-scoped state for
up to **24 hours**; later pages reuse that vector without another provider call.
Ordinary searches do not send a query to the model and work while indexing is
disabled. Avoiding `--semantic` alone does not stop document transfer if the user
has enabled account indexing. An embedding migration never mixes old Qwen and
new Voyage vector spaces or silently grants consent.

`AMAIL_TELEMETRY=off` stops subsequent diagnostic collection/upload, not semantic
indexing or server query retention, and does not delete previous local diagnostics.
`amail config` exposes non-secret resolved settings. Configuration precedence is
defaults < `AMAIL_HOME/config.toml` < environment; OAuth tokens do not belong in
that TOML file. Do not change privacy settings merely to make a task work.

## Retention and visibility are not the same

Deleted deliveries are not accessible through message/feedback queries. Limited
sender/envelope information and provider feedback may remain for approximately
**90 days** to attribute late events; maintenance delays may extend cleanup.
Complaint blocks/audits can persist until operational review. Ordinary event
queries show only retained feedback for the owner's visible outbound messages,
not private operator notes. Deleting mail does not immediately erase every
operational record.

Accepted local send receipts retain at most **100 intents** in the device's
configured home. They contain intent/local ID and past acceptance, not addresses
or body, and are device-home history rather than current account/server state.
Their absence is not proof of non-submission.

Treat task ZIPs, drafts and Bcc/envelope feedback as private. Keep them in a
protected task-appropriate workspace and clean only files created for the task.
Never include credentials, raw mail, subjects, complete addresses, ZIP paths or
query text in public diagnostics. Operational contact mail can be forwarded to an
external mailbox provider and is not covered by ordinary mail-event cleanup; do
not attach passwords or tokens to a report.
