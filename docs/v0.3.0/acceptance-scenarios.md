# v0.3.0 acceptance scenarios

These are product invariants for the multi-tenant daemon architecture, not a claim
that a build or deployed environment has passed them. Hosted native journeys use
synthetic homes beneath repository `.temp`; staging journeys own their generated
profiles, addresses and messages. No production mutation is needed.

## Local user journey

1. Start from an empty application home. An ordinary command starts one daemon;
   simultaneous initial CLI processes converge on the same daemon and SQLite state.
2. Multiple CLI processes launched from one terminal observe one active profile.
   Another terminal cannot activate a profile already reserved by the first.
3. `deactivate` removes the terminal's active binding but does not release the
   profile or its mailbox locks. The originating terminal can reactivate it; another
   terminal remains excluded until explicit release or inactivity expiry.
4. The initial profile is `user`. Every operation in that profile requires a fresh
   browser decision unless the configuration explicitly enables yolo. Denial,
   timeout and an unrelated browser request perform no protected operation. A
   successful approval is single-use and applies only to its displayed operation.
5. Profiles created by `user` survive release. Profiles created by other profiles
   are deleted on release and their names become available for a new identity.
   A reused name never revives the old identity or its locks.
6. Thirty minutes of inactivity releases profile ownership and cloud locks, even
   when no further client command arrives.
7. Daemon restart preserves recoverable state without silently extending a cloud
   lease. Configuration defaults resolve to `~/.amail` (Windows
   `%USERPROFILE%\.amail`); explicit configuration overrides defaults. Existing
   send journals, stdout formats and offline discovery remain usable.

## Distributed mailbox ownership

| Existing owners | Request | Expected result |
| --- | --- | --- |
| none | read A | granted |
| read A | read B | granted concurrently |
| read A, read B | write C | conflict, neither reader is displaced |
| write A | read B or write B | conflict, A is not displaced |
| write A | repeated request A | same ownership, not a second authority |
| expired/released A | new owner B | granted with a new fence |
| new owner B | stale operation A | refused; cannot commit or disclose data |

Race acquisition requests from independent clients against the same live mailbox.
Assert the compatible-winner set, not an arbitrary ordering or a particular winner.
Check archive, get, search and continuation pages, feedback/events, mark/delete,
send and address retirement: owner account identity alone must not bypass profile
scope. An enrolled owner cannot bypass a conflicting lease using an older
profile-less client. Non-enrolled legacy owners retain their existing behavior.

## Temporary mailbox generation and expiry

1. Any active profile can register a temporary mailbox; only `user` can register a
   permanent `mail.moesegfault.dev` mailbox. Registration also obeys mailbox locks.
2. Deliver a unique synthetic message into generation A and retain its IDs, archive
   request, search continuation and send receipt. Export while A is live and verify
   the downloaded archive locally.
3. Release A or advance the synthetic clock through its absolute six-hour maximum.
   A vanishes from all ordinary address/message discovery immediately, independently
   of the maintenance cleanup cadence. Reads and writes through previously issued
   IDs or continuations fail closed. No release notification is generated.
4. During the address cooldown, registration is refused. After cooldown, register
   the same textual address as generation B, including from the same account.
   Its immutable generation differs; no message, attachment, search result,
   continuation, receipt/event or stale indexing/projection job from A appears in B.
5. Exercise delayed ingress, indexing and outbound projection across release/reuse.
   Neither a late old-generation job nor a stale holder may publish into B.
6. Cleanup removes retained content and related state without deleting objects
   still referenced by another live mailbox. Deleted history is not downloadable
   or recoverable; an export is a prior user-controlled copy, not a restore API.
7. Temporary-address inclusion is higher than permanent-address inclusion for each
   plan, while storage and outbound usage remain in the same account resource pool.

## Smallest useful hosted split

- Native three-platform CLI lane: local daemon/profile journey and compatibility.
- Existing Worker runtime lane: actual D1 conditional ownership transitions,
  concurrent reader/writer acquisition, expired-generation visibility and cleanup.
- Staging: daemon/native login through the real browser boundary, one owned
  temporary mailbox, existing SMTP/archive/search journey, export and exact owned
  cleanup. Build artifacts are the same immutable bytes admitted for deployment.

A source-only check does not establish runtime acceptance. A passing local mock
cannot establish Cloudflare routing or SMTP delivery. Record the concrete hosted
run and tested source in `docs/validation.md` when these journeys actually finish.
