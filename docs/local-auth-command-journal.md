# Local/auth command journal

Status: source-only bounded implementation; hosted acceptance pending. Based on
accepted main `d5e7947`. No provider operation, deployment, account, sending,
password debugging, real keyring access or local runtime/build/install is authorized.

## Boundary and compatibility

The original account belongs to **PRODUCTION**. Staging has a different issuer
and data realm; a staging login failure for that production account is an
environment mismatch, not an unresolved production login defect. All new tests
use dedicated synthetic state under repository `.temp`, invalid registration
guards before credentials, and/or hosted loopback HTTP fixtures. They never use
user account credentials or production endpoints.

The existing uploadable `events` table accepts API operations only. Putting local
commands there would poison batches for old/current uploaders. A separate
`command_spans` table in the compatible physical `telemetry.sqlite3` has no
exporter. No capability probe or provider access is introduced. Existing uploader,
OAuth, keyring, encrypted session, refresh crash markers, send keys, stdout and
exit status contracts remain unchanged. Alias spellings map to canonical commands.
The hidden `_telemetry-flush` has no ordinary command scope and cannot recursively
collect local/auth records. `AMAIL_TELEMETRY=off` skips store access and recording.

## Small model and source clocks

Each retained completion stores a generated command UUID, fixed command/phase,
UTC epoch start/end milliseconds, nonnegative monotonic elapsed milliseconds,
`success`/`failure`, actual received HTTP status when known, and optional typed
reqwest dependency code. The UUID correlates local command/dependency boundaries;
it is **not** a W3C trace ID, an existing user/mail identifier, native platform
span or complete distributed trace. No argv, filename/path, mail/search text,
identity subject, endpoint URL, token, HTTP body/header or exception string enters
the journal. Missing status/cause remains null; no guessed provider code is added.

| Boundary | Exact scope | Outcome limitation |
| --- | --- | --- |
| `command` | Ordinary dispatch, including local pack/unpack, config, filesystem writes and output | Completed return only; parsing/config-loading failure, abrupt kill and panic do not create invented completion |
| `access_token` | Existing credential acquisition and serialized refresh | Failure means no token returned, not proof provider rejected refresh |
| `discovery` | Actual discovery send/status/JSON body | Does not claim later issuer/endpoint policy validation succeeded |
| `token_exchange` | Actual authorization-code send/status/JSON body | Does not claim token validation/session persistence succeeded |
| `token_refresh` | Actual refresh send/status/JSON body | Existing ambiguous outcome clearing/replay prevention is preserved |
| `jwks` | Actual signing-key send/status/JSON body | Does not claim signature/claims validation succeeded |
| `revocation` | Existing revocation send through response headers | Success does not mean body was read; failed revocation still permits local logout |

HTTP 200 followed by malformed/truncated JSON is `failure` with exact status 200.
Successful dependency decoding can precede later command failure. Token values
are returned untouched and never inspected for diagnostic content. Error codes
come only from reqwest predicates: timeout/connect/http_status/decode/body/request/
transport. Clock reversal may put UTC end before UTC start; duration uses the
monotonic clock, not wall-clock subtraction.

Dependency completion only queues in memory. Command completion freezes its own
clocks before one diagnostic store open/transaction. Thus **new** journal SQLite
initialization/writer waits are excluded from whole-command/dependency elapsed;
no new journal transaction runs while auth credential locks or HTTP work are
active. Existing API journal overhead remains inside ordinary dispatch and is not
silently redefined by this change. Thread-local context/buffer restoration is RAII,
including unwind, and scopes do not propagate across threads implicitly.

## Bounded ownership and loss

Keep at most 200 completed local spans in memory per command and 200 recent local
spans on disk. A long command evicts oldest buffered dependency completions;
whole-command completion is appended last and retained. A single short immediate
transaction inserts retained completions, prunes older history and updates
`command_journal_state.discarded_count`, saturating at signed 64-bit maximum.
The count means **local spans discarded by memory/history retention**, not failed
commands, remote pending-event loss or successful/failed delivery. Memory-evicted
records cannot be individually recovered; only their count survives a successful
commit. If persistence itself fails, emit fixed safe stderr loss text, preserve
the command result, and do not pretend to have durably counted that loss.

Use `local_store::open` with the existing 250ms diagnostic busy budget. No
transaction covers command/network work. Counter failure rolls back insertion
and pruning. No `events`, receipts, send attempts, refresh state, encrypted session
or other owner's table is modified. No VACUUM, physical-file-size promise,
command-state cleanup, automatic retry or delivery claim is introduced.

## Engineering evidence and follow-up

Tests target local success/failure stdout/exit, canonical auth aliases with safe
precondition failures, hidden suppression, opt-out with absent/existing/poisoned
store, exact HTTP 200/503 and body/decode failure, privacy, 200-row retention,
saturating discard counter, transaction rollback, contention and per-thread UUID
isolation. Real browser login, OS credential persistence, rotating refresh and
remote revocation acceptance remain existing behavior, not newly claimed hosted
end-to-end coverage. Source-only CI is the authorized acceptance lane.

This design follows established [OpenTelemetry span boundary semantics](https://opentelemetry.io/docs/specs/otel/trace/api/)
without importing a new SDK or logging exception messages. Atomic insertion,
retention and accounting use [SQLite transactions](https://www.sqlite.org/lang_transaction.html)
and its [busy handling contract](https://www.sqlite.org/rescode.html).
The research-facing question remains whether bounded local operational spans
materially improve failure localization without leaking semantic content; this
slice supplies controlled observables rather than claiming a new tracing result.
Future export needs an explicitly reviewed schema/capability contract and reader
acceptance. It must not silently inject these local operations into API batches.

## Explicit command-to-request linkage (source follow-up)

Ordinary dispatch passes its generated optional command UUID explicitly into
the API client. Each request attempt retains that value in the additive nullable
local `events.command_id` column. A local analyst can join:

```sql
SELECT c.command, e.operation, e.trace_id, e.span_id, e.phase
FROM events e
JOIN command_spans c ON c.command_id = e.command_id AND c.phase = 'command';
```

The UUID joins a command to zero or more independent HTTP attempts. It is **not**
a native span parent, W3C trace ID, user/account/mail identifier, credential
fingerprint or argument-derived value. Request trace/span generation and HTTP
`traceparent` stay unchanged. Neither legacy nor enriched telemetry wire
payloads include this local relationship. Unscoped callers retain the existing
constructors and record null; historical rows remain null after a transactional,
idempotent column migration. No fabricated historical relationship is backfilled.

The existing bounded histories can independently prune either side of the join;
a missing counterpart is not proof of a missing command/request. Abrupt command
termination can retain request events without completed command spans. Opt-out
and hidden uploader dispatch pass no ordinary command context. API diagnostics
do not read implicit thread-local state: explicit context travels from the
command closure through dispatch and the API instance to each request span.

Hosted checks must cover migration, shared UUID with distinct attempt traces,
null unscoped context, unchanged wire, and an actual subprocess pre-HTTP auth
failure joining its request event to command and access-token records. This
follow-up does not claim real browser/account authentication or platform-native
parentage acceptance.
