# Independent PR 64 diagnostic-delivery review

Date: 2026-10-01 UTC. Reviewer: integration_contract_review.

## Verdict and exact-source boundary

No substantive defect found in PR 64 head
`f38ebe116a0b493935c53cb1a98006343565bde2`, compared with its
`codex/runtime-telemetry-wire` base. Source GO, not runtime deployment/privacy
acceptance. Also inspected the author's uncommitted narrow journal-before-auth
and poisoned-header test refinements in `.temp/runtime-upload-loss`; those do
not have final hosted evidence yet and are not an exact committed-head verdict.

Final source update: the refinements were subsequently committed and the parent
reader branch synchronized with main. Independently inspected the entire CLI
delta from the first head to final PR 64 head
`043f99b062da7711fe4cca56941c55bcbf166ece`: only the reviewed journal/auth phase
refinement and the two corresponding HTTP/SQLite test cases changed. Source GO
now binds this final head, with no substantive findings. `git diff --check`
passed and the author's worktree is clean. At the final metadata snapshot,
run 36881490992 has successful scope/infrastructure and running three CLI jobs;
syntax run 36881490411 already succeeded. Final source CI acceptance remains
pending, not borrowed from the first head's green run.

Existing hosted source run
[36880337510](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36880337510)
is independently confirmed success at the reviewed head, created 14:56:32 and
completed/updated 14:58:09 UTC. Scope selection, infrastructure and all three CLI
platform jobs succeeded. Independent syntax run 36880337195 was reported green;
this review did not execute local project tests. Follow-up source changes require
their own exact-head check metadata.

## Data/state and concurrency

New state is bounded to one `journal_upload` receipt and one `journal_health`
counter/report row, alongside the existing event journal in the same historical
physical database. No new queue/lease/retry framework is introduced. Existing
auth session, refresh marker, durable sending keys and filename are untouched.
The injected credential seam is confined to testing; production still calls
the existing auth owner.

The scheduling receipt and historical 30-second throttle claim share a short
transaction. A scheduled child starts only when both its UUID and `scheduled`
state still match. Older children/replayed completed children decline work.
Manual flush establishes a fresh latest identity. Phase/count/completion writes
use attempt UUID conditions, so an older upload cannot overwrite a newer receipt.
Older real completion still updates the actual selected event IDs and aggregate
failure/unknown counters. This distinction is important: newest receipt identity
is not a reason to erase a real observed earlier outcome.

Overlapping ordinary/manual attempts can still upload the same best-effort batch;
there is deliberately no exactly-once claim. Upload-failure counters count
attempts, not unique events. An in-flight accepted batch may also have been
locally evicted before completion; the documented pending-eviction count is local
loss accounting, not proof that remote delivery failed. These are explicit
contracts, not reasons to add a business-send idempotency mechanism here.

## Retention and transaction boundaries

Newest 1000 pending and newest 200 accepted-history rows are retained separately.
Only owned `events` rows are deleted. Pending evictions and routine history
pruning have different saturating integer counters and a UTC prune coordinate.
Insertion/acceptance/pruning/counters share short IMMEDIATE transactions. An
injected counter failure test checks rollback; concurrent insertion tests check
the row bound and exact loss total. Auth/HTTP occurs after transaction commit;
the real loopback peer obtains a database writer while upload HTTP is in flight.

Startup bounds a legacy oversized backlog; insertion and completion maintain the
current bound. The policy bounds live rows, not physical SQLite bytes, and avoids
VACUUM/global database settings shared with business state. Initial old-backlog
cleanup may be larger than steady-state work; no measured performance regression
was established by this review. The existing 250ms diagnostic lock-wait policy
remains distinct from auth/send state waits.

## Honest upload/result semantics

Receipt creation precedes credential/network dependency work. The reviewed local
refinement starts in `journal`, changes to `auth` only after selecting pending
records, and classifies journal decoding separately. No pending events means
`empty` without credential/network work. Spawn failure preserves a numeric OS
error without inventing child start or elapsed clocks.

HTTP non-2xx is an observed failure; transport/body/deadline/invalid acknowledgement
is unknown acceptance and retains pending rows. Redirects are disabled. A 2xx
alone does not mark uploaded: the complete body is bounded to 4096 bytes plus one
overflow sentinel, parsed and required to contain an integer accepted count equal
to the selected batch. Only then are selected rows marked accepted atomically
with receipt/counters. API acceptance explicitly does not mean Queue/sink delivery.
The legacy wire record shape is retained; local clock/phase enrichment is not
silently uploaded to an older reader.

Stored/reportable errors are finite labels, HTTP status and canonical operational
UUIDs, never response bodies, credentials, paths or exception text. Reused response
correlation parsing fails closed on malformed primary headers. The added poisoned
header fixture checks non-persistence of arbitrary private text. No failure
creates another journal event or upload; the hidden flush bypasses foreground
diagnostic startup reporting. Auth's existing refresh client does not use the
Mail RequestSpan/scheduler, avoiding recursive telemetry through credentials.

## Userspace and reporting

Foreground initialization is best effort and does not turn successful Mail
commands into diagnostic failures. Notices go to stderr; machine stdout remains
unchanged. Reporting durably claims newly changed receipt/loss counters before
printing, so it is intentionally at-most-once best effort terminal reporting,
not evidence that a terminal consumed the warning. A scheduled/running receipt
without completion stays unresolved; it is neither fabricated failure nor success.
Aggregated failed/unknown counters survive later API acceptance.

`AMAIL_TELEMETRY=off` returns before diagnostic initialization, retention,
reporting, event insertion, scheduling and upload, including the hidden command.
Business auth/send operations may still legitimately use their shared physical
store; diagnostic opt-out is not a request to disable business persistence.
The prior hidden command invocation remains accepted with an optional internal
UUID flag. Normal mailing exit behavior is unchanged. The hidden worker now
records observed upload/auth outcomes and may finish successfully after recording
a failure; its discarded stderr/exit was never the durable acceptance signal.

## Scope, complexity and limitations

Reviewed executable paths in main, telemetry, delivery, upload, response-ID
helpers, shared store and auth callers, plus the SQLite/HTTP/subprocess regression
fixtures. The roughly 600 production lines implement bounded state, safe decoding,
SQL transaction and HTTP boundaries; tests account for the remaining additions.
No unsupported framework/redesign concern is elevated to a finding.

No provider operation, user credential access, deployment, sending, local runtime
test or production edit was performed. Tests were inspected and existing hosted
metadata checked; unexamined provider retention and real credential behavior are
not asserted. Reader-base main integration is owned separately and not redone.

Primary grounding checked during review:

* [SQLite transactions](https://www.sqlite.org/lang_transaction.html) — one writer,
  IMMEDIATE acquisition and explicit transaction boundaries explain why
  credentials/network must remain outside the journal write transaction.
* [OpenTelemetry internal telemetry](https://opentelemetry.io/docs/collector/internal-telemetry/)
  — internal loss/flow accounting and separate stderr diagnostics are operational
  boundaries, not proof of end-to-end delivery.

The existing runtime research context is retained; no causal diagnosis/sampling
novelty is claimed. Honest local loss and API-acceptance boundaries are prerequisites
for such analysis, not substitutes for the eventual native retention experiment.
