# Ten-address cleanup: retain serial settlement

Date: 2026-10-01. Decision: **do not ship batch cleanup in this acceptance**.
This is a source-derived analysis, not measured live performance. No local
tests, builds, CLI invocation, network call or deployed cleanup was performed.

## Bound and opportunity

`infra/tests/staging_ten_address_hosted.py::recover` sends one supported owner
DELETE, then waits for that alias's exact D1 tombstone and route absence before
the next DELETE. `RETIREMENT_TIMEOUT_SECONDS = 360` allows one five-minute
staging Cron interval plus headroom. Ten aliases can therefore require roughly
50 minutes of Cron waiting under unfavorable phase alignment, with a
conservative sum of ten per-alias polling allowances of 3,600 seconds
(60 minutes), **plus** serial DELETE and complete readback latency. These are
derived waiting allowances, not a hard end-to-end wall-clock bound: snapshots
and subprocess/network calls require their own finite adapter timeouts. Eleven
unexpected allocations can consume eleven such allowances (66 minutes).

A proposed alternative would send exact owned DELETEs serially without
per-alias settlement, re-audit immediately before each send, and share one
360-second read-only settlement period. It would not parallelize mutation.
The anticipated happy-path saving is from ten Cron waits to one, not an
experimentally established speedup. The ten-route Cron deletion budget in
`docs/routing-reconcile-subrequest-budget.md` is only a capacity assumption:
unrelated due rows, provider errors, claims and backlog can consume that
budget. A ten-alias batch is not guaranteed to settle in one tick; regression
cleanup of eleven aliases can require another tick. Timeout must remain
cleanup-required/NO-GO, never a successful acceptance.

## Why the optimization is deferred

The authenticated immutable v2 manifest persists the complete resource intent,
owner, baseline and service provenance. It does **not** persist a durable
per-DELETE attempt/outcome journal. If the process dies after submitting a
DELETE but before a response or D1 transition becomes observable, an active
row on restart does not distinguish an unattempted DELETE from an ambiguous
previous attempt. No-replay across that boundary cannot be proved from this
manifest alone. This limitation also warrants operational caution with the
existing recovery path; retaining serial settlement does not magically fix
the cross-run ambiguity. It limits outstanding uncertain work and avoids
introducing broader pending-state permission into a one-time acceptance.

There is a second policy boundary: DELETE can leave
`retired + needs_reconcile=1 + cf_rule_id=NULL` while an exact provider route
awaits Cron. The current strict `recovery_actions` intentionally rejects this
as unsettled. Accepting it between batch sends would need an explicit
observation-only rule audit; restoring a saved ID synthetically must never
authorize another DELETE. Existing pending/deleting state transitions must
also not be confused with new deletion eligibility.

The trial implementation was removed before commit. The default strict
manifest reconciliation, serial hosted retirement polling and their existing
tests remain unchanged. The containing acceptance workflow should retain a
finite **80-minute** job bound; expiration remains NO-GO and calls for exact
same-artifact recovery, not a fresh campaign or blind replay. No live dispatch
is authorized by this note.

## Future option and acceptance bar

If cleanup latency becomes a recurring requirement, design a durable attempt
journal or server-side idempotency contract first. A journal must bind each
entry to authenticated manifest identity, owner, exact alias and attempt;
persist an attempt marker **before** submitting DELETE; and distinguish
confirmed settlement from ambiguous transport. On restart an attempted alias
is read-only until exact settlement or deliberate operator escalation. A
crash between the marker and send conservatively leaves a possibly-unsent
operation; it must not silently authorize replay. An idempotency key is only
useful if the service durably enforces it and defines concurrent retries,
retention and result recovery, not merely if the CLI emits a key.

Only then reconsider batch settlement, with synthetic hosted fixtures for:

- ten pending exact routes under one deadline and a partial batch failure;
- process restart before send, after send, after D1 retirement, and after
  provider deletion, including an ambiguous response with an active row;
- pending/deleting/retired ownership and route changes, duplicate/foreign
  saved IDs, and unrelated baseline drift before any mutation;
- Cron contention, eleven-alias regression cleanup and safe shared timeout;
- no request replay and preservation of the complete final invariant: exact
  owner emptiness, retired clean tombstones, full baseline rules and unrelated
  rows/count, unchanged R2 inventory, message absence and serving pin.

The parent integrator selected the simpler serial policy because this is a
one-time acceptance, not a production bulk-retirement throughput requirement.
