# Outbound policy and incident operations

Amail permits agent-workflow transactional notifications and related replies,
not bulk marketing or unrestricted correspondence. Production sending was
explicitly allowed on 2026-10-02; [validation](validation.md) records evidence.
Global/account/recipient holds remain operative. Initial new storage defaults held;
that is a safe initialization rule, not today's production status.

## Policy and delivery

Every ordinary ZIP send checks ownership, recipient/quota controls, global/account
policy and required release/contact state. Read failure or missing policy denies
send. Errors stay typed: send_held, recipient_blocked, quota_exhausted. Revoking a
required gate re-holds sending. Manual changes leave append-only audit records
with opaque case reference, never report prose.

One-use grants are explicit time-bounded recipient-bound exceptions, not global
unhold or automatic retry. Provider acceptance is not delivered mail. Validate a
controlled send from independently received TEXT/HTML/CID/assets, authenticated
receiver SPF/DKIM/DMARC evidence and the exact delivered lifecycle event. An unknown
submission remains unknown; no blind second send with a new key.

The mail-events Queue consumer validates account/zone/domain/schema/provider ID,
original sender and complete private envelope before attribution. Unique event ID
and D1 transitions deduplicate redelivery. Authenticated complaints hold the owner
and suppress that recipient. Malformed/unknown/expired attribution goes to retry/
DLQ review, not silent acknowledgement or guessed owner.

## Restricted state and retention

send_requests retains restricted sender/envelope/provider attribution separately
from visible mailbox content so deleting an archive cannot sever complaint handling.
No subject/body/raw SMTP prose is stored in abuse tables or telemetry.
Envelope attribution is cleared in bounded maintenance batches after 90 days from
send creation; provider_events after 90 days from Queue receipt; recipient_outcomes
after 90 days from event time. These are scheduled targets, not real-time erasure
promises. Complaint suppression and policy audit require explicit review/removal.
Queue/DLQ provider payloads contain PII under provider retention; restrict access.

## Emergency response

1. Use send-control on main or restricted audited policy control to hold new sends.
   Keep existing accepted/unknown state and inbound/search/archive operations.
2. Inspect safe typed events and exact Queue/DLQ health. If consumer is faulty,
   pause subscription only after hold; retain messages for corrected replay.
3. Resolve complaints using trusted event records. Do not clear suppression to pass
   a canary or treat arbitrary abuse email as policy authority.
4. Preserve additive migrations, idempotency journals and four direct contact
   forwards through repair. No queue purge/table drop/resource deletion as rollback.
5. Restore only compatible source/configuration, verify actual graph and independently
   accepted contact/feedback state, then use the explicit separately gated allow.

Role contact response/privacy is in [operator intake](operator-intake.md).
Cloudflare [event subscriptions](https://developers.cloudflare.com/api/resources/queues/subresources/subscriptions/methods/create/)
and [DLQs](https://developers.cloudflare.com/queues/configuration/dead-letter-queues/)
describe platform behavior; actual deployed configuration remains authoritative.
