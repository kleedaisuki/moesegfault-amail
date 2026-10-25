# Daemon, terminal profiles and temporary mail

Read this for v0.3.1 profile isolation and testing mailboxes. Candidate documentation
does not establish publication, remote deployment or permission to send.

## Local ownership

The CLI automatically connects to the local daemon and starts it when absent.
The daemon owns authenticated network work, expensive mail processing and shared
concurrency. Configuration and SQLite state live under `~/.amail`, or
`%USERPROFILE%\.amail` on Windows; installed binaries belong in its `bin`
subdirectory. `AMAIL_HOME` explicitly selects another application home. Do not
place task mail in an unprotected shared directory.

Defaults apply when `config.toml` omits a setting. This optional example shows
the safe defaults, not settings the agent should rewrite:

```toml
yolo = false

[daemon]
max_concurrency = 4
start_timeout_seconds = 15
```

The initial profile is `user`. A terminal has one active profile; repeated CLI
processes in that terminal reuse it. A profile can be activated in only one
terminal at a time. Do not spoof terminal IDs to evade this rule. Deactivation
leaves the profile reserved and recoverable; release relinquishes its mailbox
ownership. Thirty minutes without use releases it automatically. Profiles created
by `user` persist after release; profiles created by another profile are deleted
and their names can be reassigned.

```sh
amail profile status
amail profile create build-test
amail profile activate build-test
amail profile list
amail profile deactivate
amail profile activate build-test
amail profile release
amail daemon status
```

Create durable task profiles while `user` is active. Deactivation does not select
`user` automatically: explicitly activate the intended profile before continuing.
`profile release NAME` releases a named reservation when permitted. `daemon stop`
stops the local service; it is not a way to steal cloud occupancy.

The user profile requires human browser approval for each protected operation.
Do not click approval, manufacture callback requests, or set `yolo = true` on the
human's behalf. YOLO is the human's explicit removal of that protection, not
permission to spend money, send unrelated mail or bypass server policy. Profiles
are not a security sandbox against arbitrary code running as the same OS user.

## Mailbox ownership

An account mailbox permits either several reading profiles or one writing
profile. Ownership is nonpreemptible: a conflict means wait, choose another
authorized mailbox, or ask its holder to release it. Never repeatedly create
profiles or change names to steal an occupied mailbox. Read occupancy does not
authorize marking, deletion or sending; fetching still does not mark mail read.
Cloud sessions and leases enforce this across daemons and machines, not merely
across CLI processes on one terminal.

Headless launchers without a console must provide `AMAIL_TERMINAL_ID` as one
stable logical-terminal identifier. Keep it in the launcher's process environment
or pass the same value on every invocation; a newly generated value per command
would represent a different terminal. Existing terminal/session context is
preferable to another configuration file. Do not change it to evade an occupied
profile. These identifiers are mapped to private local capabilities and are not
passwords or cloud session tokens.

```sh
amail mailbox acquire test@tmpaddr.moesegfault.dev --mode read
amail mailbox release test@tmpaddr.moesegfault.dev
amail mailbox acquire test@tmpaddr.moesegfault.dev --mode write
```

Use the actual task-owned address, and the staging domain in a staging task.
Default acquisition mode is `read`; release before asking to change modes.

Owners not enrolled in profiles keep their previous protocol behavior. After
enrollment, requests without a valid profile session cannot bypass occupancy;
upgrade the client rather than falling back to legacy requests.

## Temporary test addresses

Only `user` may register `@mail.moesegfault.dev` addresses. Any active profile
may register `@tmpaddr.moesegfault.dev` test addresses; they still obey mailbox
occupancy. Staging uses `tmpaddr-staging.moesegfault.dev`, not the production
domain. A temporary mailbox has an absolute maximum lifetime of six hours.
Activity, another profile and a paid plan do not extend it.

```sh
amail address add build-test --tmp
amail address list
```

Expiry or release immediately removes query access. Release sends no notification
and cannot be undone. Download retained mail history **while the mailbox is live**
if the task needs a durable record; this is an export, not an undelete or a promise
to archive expired data:

```sh
amail mailbox export build-test@tmpaddr.moesegfault.dev --output history.zip
```

Keep the bundle private. Export requires a live mailbox and read occupancy, follows
all result pages and includes message ZIPs and a mailbox manifest. It does not
extend the mailbox lifetime; expiry during export is a failure, not a partial
successful backup. A later holder of the same address never receives access
to the earlier mailbox generation. Physical object cleanup proceeds through
scheduled maintenance; the name is not reusable until cleanup, route retirement
and cooldown complete. The default cooldown is one hour. Delayed delivery to a
reused address is the task owner's risk; do not use temporary addresses for
password recovery or durable identity.

| Included concurrent addresses | Free | Lite | Plus |
| --- | ---: | ---: | ---: |
| Permanent mail domain | 1 | 3 | 5 |
| Temporary domain | 3 | 6 | 10 |

These are independent address allowances, not new resource pools. All profiles,
temporary mailboxes and permanent mailboxes share the account's existing send
and storage resources; creating a profile never multiplies the subscription.
Provider capacity, spending approval and sending policy remain independent.
Temporary and permanent mail share the account's default-off semantic setting.
If the human enables it, eligible temporary mail is also indexed through
OpenRouter/Voyage 4; read [privacy](privacy.md) before requesting enablement.
