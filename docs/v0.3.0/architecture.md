# v0.3.0 multi-tenant architecture

Status: implementation contract for the client, daemon, Mail API and hosted
acceptance. Delivery evidence belongs in [validation](../validation.md); this
document does not establish deployment or a successful user journey.

## Boundaries and representative journey

```text
terminal A: amail processes --+                 +-- Identity / Billing
                            | local IPC       |
terminal B: amail processes --+--> one daemon --+-- Mail API --> primary D1
                                  |           |               + R2 / Routing
                                  +-- SQLite  +-- pooled HTTPS
                                      ~/.amail
```

The CLI parses arguments and renders the established JSONL/machine contracts.
The daemon owns profiles, OAuth use, cloud I/O, archive work, command journals,
and a bounded shared concurrency budget. Multiple invocations from the same
terminal share one activation, not one activation per process. Help, version and
offline discovery remain available without a daemon, credentials or network.

1. Resolve `AMAIL_HOME`, otherwise the current user's `~/.amail` (including
   `%USERPROFILE%\.amail` on Windows). Defaults precede `config.toml`; existing
   environment overrides retain precedence for automation compatibility.
2. Discover the local daemon. If absent, acquire a startup OS file lock, recheck,
   then launch one hidden detached daemon. Publish its endpoint atomically only
   after listening. A live competing instance is reused, never killed by name.
3. Identify the terminal independently of the short-lived CLI PID. Activate the
   built-in `user` profile, or create and activate a named profile. Cloud activation
   enforces exclusive terminal possession; a repeated activation from that same
   terminal is recovery, not theft.
4. In `user`, show a browser approval for each requested operation. Approval binds
   the exact request and is one-use. Explicit `yolo` configuration suppresses these
   profile approvals, not Identity login, Billing consent or sending-policy checks.
5. Claim an address with a cloud read or write lease. Read leases can coexist;
   write possession excludes every other profile. Existing possession is not
   preempted. Normal mail commands use the active profile and its possession.
6. `deactivate` removes the terminal's current selection but preserves the profile
   session and claims for same-terminal recovery until release or inactivity.
   An explicit release, or 30 minutes without actual use, releases possession.

## State ownership and identities

| State | Authority | Lifetime / invariant |
| --- | --- | --- |
| Account | Existing OIDC `(issuer, subject)` | Billing, resource pools and permanent-mail ownership are unchanged. |
| Profile | Cloud registry with local SQLite cache | Immutable random ID; reusable display name is never an identity. |
| Profile class | Recorded creator authority | `user` and profiles created by `user` persist after release; profiles created by other profiles are deleted on release. |
| Terminal activation | Daemon + cloud session | At most one selected profile per terminal; one terminal session per profile. |
| Profile session | Cloud opaque random token | Scoped to owner/profile/terminal; server expiry is authoritative. |
| Address possession | Primary D1 | Address lifetime, profile/session, mode and opaque token; stale release cannot remove a successor. |
| Temporary mailbox | Address kind + generation | Absolute expiry no later than creation + six hours, never extended by use. |
| Message | Immutable ID + mailbox generation | Same textual address does not grant predecessor-generation data. |
| Local journals | Daemon-owned SQLite | Existing accepted/unknown send history survives migration and daemon restart. |
| OAuth material | Existing protected auth store | Never copied to `config.toml`, IPC responses, profile records or logs. |

The same OS account is trusted. Profiles prevent accidental agent interference,
not malicious arbitrary code running as that OS account from reading its files or
invoking its credentials. This release does not claim an OS sandbox. Passwordless
profiles do not create new OIDC accounts or independent subscriptions.

Cloud authorization uses the registered profile/session, never a caller-supplied
name such as `user`. Existing authenticated no-profile clients remain a legacy
account-owner path only until that owner enrolls in v0.3.0 profiles. Enrollment
makes a profile session mandatory for that owner's mail operations; otherwise an
old client could ignore a new writer's lock. Existing unenrolled accounts are
unchanged. The enrolled owner must upgrade old clients, a deliberate per-account
security transition rather than a global version cutoff. The daemon must not
drop its session header to escape profile restrictions. This remains no isolation
boundary against a hostile owner of the OAuth credential.

### Profile state machine

```text
persistent:  available --activate--> held --release/idle--> available
ephemeral:   created   --activate--> held --release/idle--> deleted
                                      |
                                      +--deactivate--> held, unselected
```

Idle time is measured from actual profile commands, not maintenance or lease
renewals. A background daemon must not keep an abandoned profile alive forever.
Release is idempotent for its exact session. Reactivation after expiry creates a
new session, and ephemeral name reuse creates a new profile ID. A cloud outage
does not authorize local-only takeover; stale sessions fail closed at the API.

## Shared cloud wire contract

Existing endpoints and successful stdout remain compatible. New authenticated
profile requests carry `X-Amail-Profile-Session`; the daemon supplies the existing
OIDC bearer credential separately. Session and lease tokens are secret and must
not enter diagnostics or public Actions artifacts.

| Method / path | Body / meaning |
| --- | --- |
| `GET /v1/profiles` | List this account's profile metadata, not session secrets. |
| `POST /v1/profiles` | `{ "name": "worker-a" }`; durability derives from the creator session. |
| `POST /v1/profiles/activate` | `{ "name": "worker-a", "terminal_id": "opaque", "session_token": "optional recovery token" }`; returns profile identity, session token and expiry. |
| `POST /v1/profiles/release` | Release the current exact session and its address possession. |
| `POST /v1/leases/acquire` | `{ "address": "...", "mode": "read" or "write" }`; returns opaque lease token and generation. |
| `POST /v1/leases/renew` | Exact current lease token; renewal cannot resurrect a released session. |
| `POST /v1/leases/release` | Exact current lease token; no force/preempt operation. |
| `POST /v1/addresses` | Existing `local_part`, optional `kind: "tmpaddr"`; absent kind remains permanent `mail`. |

Stable errors distinguish occupied profile, conflicting address mode, expired
session, stale lease, absent/expired mailbox and exhausted quota. They do not
silently replace a holder, convert a read claim to write, or expose another
profile's session. Retryable transport failure is not proof that a claim was not
committed: recover by the same session/token and read the resulting state.

## Distributed possession: correctness before round trips

The cloud, not the daemon cache, is authoritative. Use D1 conditional statements
and atomic batches for admission: there must never be a read-check/unconditional-
insert race. Ownership checks must use primary-consistent state. The existing
non-session D1 binding routes queries to the primary; introducing read replicas
later requires an explicit first-primary/session policy for authorization.

For each live address lifetime, either all holders are readers or exactly one
profile is the writer. A writer may read too. Same-session repeated acquisition
recovers the same possession. An upgrade must fail while any other reader holds
the address; there is no implicit eviction, priority queue or lock stealing.

A lease is not merely a promise by the client. Resource access must validate its
current profile session, address generation and possession. Mutation predicates
must preserve that fence at the data transition, especially after awaited I/O;
checking once before a long network operation is not enough. Read filtering must
apply to account-wide search, archives, events, feedback and resumable jobs, not
just direct mailbox commands. A remembered message UUID is not authority.
Each request snapshots its opaque lease tokens and rechecks those exact tokens
in resource predicates; release/reacquire in the same profile cannot bless an
already running predecessor request. Send recovery is scoped by immutable profile
identity, not a rotating session token, so legitimate session recovery preserves
the same logical send while a recycled ephemeral profile name gains no access.

Hold possession across short CLI calls to amortize acquisition. Reuse the HTTP
pool, coalesce renewals, cache only until conservative local deadlines, and attach
session authority to every operation. An expiry or rejected renewal invalidates
the local cached claim. Do not introduce etcd or a second consensus cluster: D1
already serializes the authoritative state for this bounded mailbox workload.
The daemon shares one cloneable `reqwest::blocking::Client` pool. HTTP redirects
are disabled so custom profile-session headers cannot escape to another origin.
Outbound validated vectors move into request bodies; inbound `copy_to` fills the
final buffer directly, avoiding an intermediate full-archive `Bytes`-to-`Vec`
copy. These mechanisms avoid specific copies, not all TLS/network/kernel copies.

## Temporary addresses and generation isolation

`xxx@tmpaddr.moesegfault.dev` is a separate kind, not an alternate spelling of a
permanent mailbox. Any active profile may register it, and registration acquires
the normal write possession. Only `user` may register `@mail.moesegfault.dev`.

Temporary included counts are larger than permanent counts. The selected baseline
is Free/Lite/Plus `3/6/10` temporary versus `1/3/5` permanent addresses. Send and
storage remain the same owner resource pools; this must not multiply included
outbound volume, storage or approved overage budgets. Address kind affects its
counting/slot limits without creating a new Billing customer or tariff history.
Per-kind slot uniqueness permits the temporary and permanent allocations to
coexist; the original `slot BETWEEN 0 AND 9` constraint still applies within
each kind. Provider-wide routing capacity remains a separate total limit.

```text
reserve --> provision --> active --release / absolute expiry--> deleting
                                                       --> retired / purged
                                                       --> cooldown elapsed
                                                       --> new random generation
```

Expiry makes the mailbox and its messages unqueryable immediately, even if the
maintenance Cron has not run. Release is silent, irreversible and does not create
a recovery window. A CLI export must download the active generation before
release/expiry; an already exported local file is independent of cloud retention.
The server must not retain a hidden downloadable archive after claiming deletion.

Physical D1/R2 cleanup is bounded scheduled work and may lag the visibility cutoff
during provider failure. Do not promise exact-time physical erasure across an
unavailable object store. Name reuse waits for successful owned route retirement,
complete predecessor data purge, and configured cooldown. Cleanup must preserve
the exact old generation and opaque object keys until deletion is confirmed; it
cannot delete by textual address after that name has a successor.

Purge includes message bodies/metadata, text chunks/vectors, cached search pages,
temporary-profile views, raw/ZIP objects, and address-generation-specific exported
server work. Existing provider submission/idempotency invariants must not be
destroyed into a possible duplicate send; expired temporary-generation receipts
must not disclose old mail to a successor. In-flight background projection also
checks generation/expiry and cannot resurrect expired content.

Only active, unexpired recipients enter ingress. Reused names never attach
predecessor stored messages. SMTP delivery delayed beyond cooldown cannot reveal
the sender's original intended generation; that external address-reuse edge is
the user's responsibility, rather than a fabricated server guarantee.

## Local implementation and compatibility

Prefer existing `rusqlite`, `fs2`, `reqwest`, `toml`, `webbrowser`, and a mature
cross-platform IPC/HTTP library over custom transports, parsers or crypto. The
daemon has one SQLite writer with short transactions, bounded busy timeout and
WAL where appropriate; never hold a write transaction through a browser wait or
network request. WAL does not create parallel SQLite writers.

`profiles.sqlite3` is separate from diagnostics because it holds cloud session
capabilities. Local state is partitioned by `(API origin, issuer, client ID)`;
staging profiles cannot become production activations. The store uses foreign
keys, WAL, `synchronous=NORMAL`, a five-second busy timeout and Unix mode `0600`
under the `0700` application home. Cloud profile identities and session expiry are
mapped to local profile records rather than replacing them by reusable names.

Keep bulk archives out of JSON/base64 IPC. Stream bytes or pass a protected local
file/path through the trusted local boundary; let the daemon validate and perform
archive work. Avoid copying a full payload merely for logging, IPC framing or an
intermediate result. Bound queue depth, request sizes and CPU workers globally so
many agent processes cannot spawn unbounded independent work.

Retain `AMAIL_HOME`, existing config keys, protected credential format, output
contracts and idempotency journals. Default-path migration discovers and preserves
the old platform application-data home rather than silently appearing logged out
or losing accepted/unknown send state. It uses SQLite `VACUUM INTO` snapshots under
the legacy refresh lock rather than copying only main database files and losing
WAL data. Source files are retained, an interrupted migration is recoverable,
and conflicting initialized destination state stops instead of merging histories.
Close old binaries before upgrading: two independently mutable homes cannot
safely share rotating credentials. Explicit `AMAIL_HOME` does not trigger migration.
Binary installation belongs under
`~/.amail/bin`; it is not a temporary/cache directory. Do not replace a live
daemon with a different wire version silently: negotiate version or return a
clear restart/upgrade action. Candidate tests use an isolated repository-root
`.temp` home, never the real user's session.

The default configuration needs no file. Optional settings are:

```toml
yolo = false

[daemon]
max_concurrency = 4          # Accepted range: 1..32.
start_timeout_seconds = 15   # Accepted range: 1..120.
```

## Integration and focused acceptance

1. Add backward-compatible cloud tables and generation columns; keep old mailbox
   identities, paid grants, historical currency records and provider journals.
2. Implement cloud profile/claim admission and fenced mailbox access, then
   temporary lifetime visibility and generation-safe purge/reuse.
3. Route existing CLI operations through the daemon and add profile/claim/export
   commands without changing existing successful stdout.
4. Build once in hosted Actions, test the same artifact, and use the established
   serialized staging writer. Do not rebuild deployment bytes after admission.
5. Validate real multi-process/terminal journeys plus native Windows/macOS/Linux
   daemon startup and recovery. Local execution is for real user experience,
   not duplicating the hosted heavy toolchain.

The high-value properties are: two readers coexist; a writer never overlaps
another holder; stale release cannot affect a successor; deactivation preserves
recovery; idle cleanup deletes only ephemeral profiles; each `user` operation
requires its own approval unless explicit yolo; stale message IDs and search jobs
cannot reveal expired/reused temporary data; concurrent first CLI invocations
produce exactly one daemon. Use deterministic clock/interleaving fixtures and
property-based sequences where they simplify these state-space checks. Preserve
the existing real SMTP/archive/search/delete/send-recovery journey instead of
replacing it with schema-only tests.

## References and design rationale

* [SQLite transactions](https://www.sqlite.org/lang_transaction.html) and
  [WAL](https://www.sqlite.org/wal.html): one writer and short transactions; WAL
  improves reader/writer coexistence, not write parallelism.
* [SQLite VACUUM INTO](https://www.sqlite.org/lang_vacuum.html): a consistent
  database snapshot preserves committed WAL content during home migration.
* [D1 read replication](https://developers.cloudflare.com/d1/best-practices/read-replication/):
  existing non-session queries use the primary; replicated sessions supply
  sequential consistency rather than arbitrary fresh authorization reads.
* [etcd's expired-lock example](https://github.com/etcd-io/etcd/blob/main/contrib/lock/README.md):
  lease expiration alone cannot stop a paused old owner; the resource validates
  fencing authority.
* [Burrows, Chubby, OSDI 2006](https://research.google/pubs/the-chubby-lock-service-for-loosely-coupled-distributed-systems/):
  coarse-grained possession amortizes coordination and ephemeral objects belong
  to sessions. This informs the model, not a proposal to implement consensus.
* [Docker CLI transports](https://docs.docker.com/reference/cli/docker): a thin
  CLI and reusable daemon are mature practice; Unix sockets and Windows named
  pipes demonstrate platform-local alternatives to unauthenticated public TCP.
* [reqwest blocking Client](https://docs.rs/reqwest/latest/reqwest/blocking/struct.Client.html)
  and [Response::copy_to](https://docs.rs/reqwest/latest/reqwest/blocking/struct.Response.html#method.copy_to):
  reuse the connection pool and avoid unnecessary intermediate archive buffers.

These sources inform mechanism choices. Performance improvements still require
measurements of this project's real hosted command journeys, not borrowed scale
claims or CPU-only microbenchmarks.
