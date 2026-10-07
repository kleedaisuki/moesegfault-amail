# Privacy and protected task files

Read when explaining mail processing, choosing suitable content, or changing
diagnostics. These are v0.2.0 processing contracts, not a promise that a particular
service is currently available or sending is enabled.

## Content indexing is separate from diagnostics

The service automatically sends each eligible received or sent mail's subject
plus extracted body text, bounded to the combined first **12,000 UTF-8 bytes**, to
OpenRouter and its upstream embedding provider for background semantic indexing.
Raw ZIPs and attachments are not embedding inputs. This happens even if the agent
never runs `--semantic`. There is no per-account indexing opt-out.

A semantic search also sends its query text. When page 1 has further pages, the
service retains the query text and exact query vector in owner-scoped state for
up to **24 hours**; later pages reuse that vector without another provider call.
Ordinary searches do not send a query to the model, but do not stop automatic
mail indexing. Do not say that avoiding `--semantic` prevents content transfer.

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
