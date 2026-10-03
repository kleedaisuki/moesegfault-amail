# Owner-visible outcomes, events and policy

Read when delivery matters, a changed message ID is unknown, or current sending
constraints are needed. Explore `amail discover events` and `events.schema` for
the targeted field contract; do not add lifecycle histories to ordinary listings.

```sh
amail sending-status
amail outcomes MESSAGE_ID
amail events --message MESSAGE_ID --limit 20
amail events --kind bounced --since 2026-10-03T00:00:00Z --limit 20
```

Replace `MESSAGE_ID` with the local owned outbound message ID, not a provider or
RFC ID. Outcomes are known per-recipient feedback, not a complete envelope list.
They use risk precedence, not simply the last arrival: delayed deferrals cannot
erase delivery; permanent failure or complaint takes precedence. No event proves
human reading. Missing feedback means **not observed**, not delivered, failed,
historically absent or safe to resend.

Account events discover changes without a known message ID. The six kinds are
`deferred`, `delivered`, `bounced`, `failed`, `rejected`, `complained`. The inclusive
RFC3339 `--since` filters service receipt time (`received_at`), not provider
occurrence time (`occurred_at`), so delayed older events remain discoverable.

Pages default to 20 and allow 1..100 entries. A `next_cursor` JSONL record is
pagination metadata, not an event. Pass it opaquely with the same filters:

```sh
amail events --kind bounced --since 2026-10-03T00:00:00Z --limit 20 --cursor CURSOR
```

A continuation retains its initial boundary; start a fresh query for later
receipts. Event cursors expire after **one hour**; `events_cursor_expired` /
`restart_events` means start without that cursor, preserving desired filters.
Retained history may disappear during pagination, not become an infinite snapshot.
Events/outcomes normally expire after **90 days**; empty retained history cannot
prove no event ever happened. This differs from an unfinished search job.

Feedback requires the owner's visible undeleted outbound delivery. Deletion/GC
does not revive recipient data through event queries. Owner-visible recipients
can include Bcc; do not disclose them outside the authorized task. Raw provider
prose, private operator notes and other owners' activity are not query fields.

`sending-status` exposes applicable policy and own quota facts, not reservation,
recipient approval or permission to bypass a hold. For submission uncertainty
return to the original intent's [send recovery](send-recovery.md), not a new send.
