# Independent PR 68 local/auth command journal review

Date: 2026-10-01 UTC. Reviewer: integration_contract_review.

## Verdict and evidence

No substantive issue found. Source GO for exact PR head
`b4fddada8adbb5e104ab6a9fba41c0a297f5ce61`, independently checked through PR
metadata before source inspection. This is local synthetic/source acceptance,
not real login, provider/runtime retention, deployment or sending authorization.

Hosted PR CI [36886377574](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36886377574)
has this exact head and completed successfully, 15:42:33–15:44:28 UTC. Scope,
infrastructure and three CLI platform jobs succeeded; independent syntax
36886377144 succeeded. Inspected all three CLI logs: each passed 50 unit tests,
five new command-process tests and four existing journal-resilience tests, with
zero failures/ignored cases. Linux logs individually confirm the real loopback
HTTP auth helper test and the retention/rollback/contention/thread-isolation
tests. `git diff --check` passed. Author worktree was clean.

## Representation, scope and wire compatibility

The new `command_spans` and singleton discard-counter table remain local-only in
the existing physical database. No exporter/capability probe is added. The
existing uploadable API `events` table, selected wire fields and uploader are not
modified. This separation removes the special-case risk of local operations
poisoning a batch rejected by an old/current API reader.

Public command kinds are matched exhaustively to closed canonical labels; login
and logout aliases share identities. Command UUIDs correlate retained local
dependency/completion records only: they are not W3C trace/span IDs, user or mail
identifiers, or complete distributed traces. The hidden uploader gets no ordinary
scope, including auth dependency calls made during its flush. Thread-local state
is restored on normal return and unwind; unrelated threads do not inherit it.

The whole-command boundary covers dispatch/output/filesystem work after parser,
configuration and existing diagnostic startup. It records returned completion,
not panic/kill/config-parser failure. New journal persistence starts after source
end clocks are frozen, so its lock waits are not misreported as command/auth
latency. Existing API-journal overhead remains inside dispatch as documented.

## Auth correctness and privacy

`identity_json` preserves the original send/error-for-status/JSON sequence for
discovery, JWKS, authorization-code exchange and refresh. Token/claims validation,
refresh serialization/crash marker, session persistence and ambiguous-outcome
clearing are unchanged. `access_token` wraps the same owner implementation and
returns its result untouched. Logout remains best-effort revocation followed by
local clear; recording an HTTP failure does not newly block logout.

Dependency completion means precisely the selected source boundary: successful
discovery decoding does not assert issuer policy validation; successful token
decoding does not assert claims/session persistence; revocation records headers,
not body completion. Exact received HTTP status survives malformed/truncated
JSON (including 200 followed by failure). Source predicates supply fixed error
codes; unknown local causes stay null rather than guessed provider rejection.

Persisted fields are closed operational enums, random UUIDs and measurements.
No argv, path, endpoint, provider header/body, user identifier, subject, search
text, credential or exception display enters the new records. Existing user-facing
errors remain unchanged rather than being reused as diagnostic payloads. Tests
exercise private markers and check their absence from stored diagnostics.
No new write transaction runs while auth locks or dependency HTTP are active:
dependency results are buffered and persisted after ordinary command return.

## Retention, opt-out and userspace

Both per-command buffer and persisted local-span history are capped at 200.
Old buffered records count as discarded; command completion is appended last
and retained. One short IMMEDIATE transaction inserts, prunes and saturates the
discard counter. Counter failure rolls back both inserts and pruning. The counter
means local span history loss, not failed commands, remote delivery loss or
API acceptance. Store failure emits only fixed safe stderr and preserves the
actual command result; inaccessible storage is not falsely counted durably.

No send keys, refresh/session tables, event/receipt counters, SQLite journal mode
or physical-file-size policy changes. Existing 250ms diagnostic lock budget is
used. New synthetic contention tests confirm command results survive locked
storage; cross-thread tests exercise real shared-file writes and identity isolation.

Opt-out disables the ordinary scope and record collection before store access.
The public config stdout remains structurally compatible; enabled/off differ
only in its documented telemetry flag. Local ZIP success/failure, alias guard
failures, hidden flush and poisoned-store cases use real child processes and
verify JSON/exit behavior. The five new subprocess tests are meaningful behavioral
checks rather than only assertions repeating enum/SQL implementation assumptions.

## Limits and external grounding

Read the maintainer/foundation and Identity skill contracts, focused diffs and
surrounding auth/main/store callers, tests and local-journal runbook. No local
project/runtime test, dependency install, real credential access, provider
operation or production edit occurred. Real browser login, OS keyring persistence,
refresh-token rotation and remote revocation acceptance are not newly validated.
The original account's production realm is distinct from synthetic/staging guards;
source tests do not establish a production-account login failure or success.

Primary documentation checked during this review:

* [OpenTelemetry tracing API](https://opentelemetry.io/docs/specs/otel/trace/api/)
  distinguishes span lifetime/context and timestamp/duration; this implementation
  intentionally uses bounded local command correlation, not an SDK or distributed
  propagation claim.
* [SQLite transaction semantics](https://www.sqlite.org/lang_transaction.html)
  explain the short single-writer transaction and atomic retention accounting.

No new tracing/sampling research result is asserted. The useful advance is
observable local/auth failure boundaries without legacy-wire or private-data
contamination; future export would need its own schema/reader acceptance.
