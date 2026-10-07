# Logical sending, recovery and constraints

Read for sending or recovering a submission. Use `amail discover send`, its
`send.schema` child and installed help for current fields. Prepare the draft with
the [archive contract](archive.md); do not infer sending permission from a CLI
version or release announcement.

## Persist intent before submission

Save one fresh UUID in the protected task record **before** invoking send. Pack
once, keep the resulting bytes, and replace `TASK_UUID` below with that saved key:

```sh
amail pack report-draft -o report.zip
amail --machine send report.zip --idempotency-key TASK_UUID
amail send-status TASK_UUID
```

`--intent` is an alias for `--idempotency-key`. Same intent and identical ZIP bytes
reuse one submission; different bytes under that key are invalid. A genuinely new,
authorized send can use a new UUID with identical content. Legacy automatic keys
protect unresolved payload retries, not permanent content deduplication.

Capture stdout and stderr separately. `--machine` leaves stdout unchanged and
emits `amail.machine.v1` control records on stderr; its pre-submission intent record
does not replace saving the UUID beforehand. `--human` is mutually exclusive.

## Lost output or uncertain submission

Query `send-status` for the original UUID first. `send-receipts --limit 20` and
`send-status TASK_UUID --local` can discover past acceptance on this device.
Local history retains at most **100 intents**, is not account-specific current
server state, and does not prove delivery. Missing local/remote evidence after
transport uncertainty does not authorize a new key or prove no send occurred.

| State/action | Required interpretation |
| --- | --- |
| Preparing, reserving, submitting, unknown; `query_send_status` | Preserve UUID/ZIP and query or reconcile that same intent; never blind resend or replace its key. |
| Accepted, pending/archived projection | Provider accepted; archive progress is separate. Follow outcome/event links only if delivery matters. |
| `send_index_pending` or unclassified send 5xx | A submission may already be accepted; query the same intent, not a fresh send. |
| Rejected, `send_held`, blocked/suppressed/not-allowed recipient | Respect the typed refusal; no policy/recipient workaround. |
| Quota/provider limit, `retry_later` | Not permission to rotate an unresolved intent. Avoid aggressive retries or splitting recipients/identities to evade limits. |

Acceptance is not remote delivery or reading. The CLI saves a bounded local
acceptance receipt before releasing only its matching unresolved key; a local
receipt write failure still requires same-intent server lookup. Unknown provider
outcomes may require authorized operational reconciliation, not more sending.

## Quotas and recipient privacy

Query `amail sending-status` for the owner's current policy/usage and
`amail billing status` for effective included resources and approved budget. Both
are advisory,
not quota reservation or recipient authorization; the send still validates and
reserves. A narrow operator canary does not open ordinary global sending.

Source limits: 50 recipient entries/account/UTC day, 20 sends/account/UTC day,
5 sends/account/UTC hour, 10 entries/account/normalized recipient/UTC day; one
message permits 50 recipient entries and 32 attachments. A global 10,000-entry
daily guard also applies. To/Cc/Bcc and duplicate entries all count. Earlier
reservations can remain consumed if a later check or submission fails.

The separate v0.2.0 monthly billable unit is one distinct normalized envelope
recipient across To/Cc/Bcc: identical recipients are charged once per message.
An accepted send consumes its reservation even if it later bounces; retries of the
same intent do not charge twice. A known pre-acceptance rejection releases the
billing reservation; unresolved sends keep it. Abuse guards above remain separate
from pricing and cannot be bypassed by paying. `outbound_quota_exhausted` or
`resource_budget_exceeded` means inspect [billing status](billing.md), not an
automatic upgrade, fresh financial key or recipient/identity splitting.

Bcc is hidden from recipient-visible headers, not from the owner's draft,
envelope or authorized feedback. Do not share the raw owner archive/receipt
context with recipients. For known feedback read [feedback](feedback.md) only
when the task needs it.
