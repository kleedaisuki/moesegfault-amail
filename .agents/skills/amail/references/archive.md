# ZIP archive v1: agent authoring and retrieval

Read this only when composing a send draft or handling a retrieved archive. The installed CLI's `pack`, `send`, and retrieval/unpack help remains the source of truth for flags and paths.

## Draft layout

```text
draft/
  manifest.toml
  body.txt           # optional if body.html exists
  body.html          # optional if body.txt exists
  assets/
    chart.png        # present only if declared below
```

Example `manifest.toml`:

```toml
version = 1
from = "alice@mail.moesegfault.dev"
to = ["bob@example.org"]
cc = []
bcc = []
subject = "Project update"

[[assets]]
path = "assets/chart.png"
content_type = "image/png"
disposition = "inline"
cid = "chart"
filename = "chart.png"
```

The `from` address must belong to the logged-in account. `reply_to`, if specified, must also be caller-owned. For an inline image, use `<img src="cid:chart" alt="...">` in `body.html`; the CID must match the declared asset. Set `disposition = "attachment"` for files that are not embedded in HTML. Optional threading fields are `in_reply_to = "<message-id@example.org>"` and `references = ["<message-id@example.org>"]`; do not fabricate them when the thread ID is unknown.

All paths are relative UTF-8 paths using `/`; place assets under `assets/`. Do not add undeclared files or symlinks. The archive requires at least one UTF-8 body. The CLI packer can generate plain-text fallback from HTML-only drafts, but author `body.txt` when its wording matters. The service compiles MIME, including text/html alternatives and related/attached assets; draft authors provide HTML, not raw MIME. Avoid remote resources and active content: outbound HTML is sanitized, and HTML rendering in recipients varies.

ZIP validation has size, entry count, decompression, and recipient limits; compressed size is not the same as provider MIME size. If pack/send rejects a draft, simplify or reduce it instead of weakening validation. A submitted ZIP can contain sensitive content: store and transmit it only as needed for the task.

## Sending policy and typed outcomes

Source policy is scoped to agent-workflow transactional notifications and replies. The current design starts global sending **held** until operator release gates and live delivery checks pass; do not treat the presence of `amail send` as proof that public sending is enabled. Account limits are 50 recipient entries per UTC day, 20 sends per UTC day, 5 sends per UTC hour, and 10 entries to the same normalized recipient per UTC day. To, Cc, Bcc, and duplicate recipient entries all count; a single message permits at most 50 entries. A global 10,000-entry daily guard also applies. Reservations occur before provider submission; even an unsuccessful attempt can consume earlier reserved quota. Do not split a batch or change identities to evade a guardrail. Bcc addresses remain private in the owner draft/record and must not be exposed in a shared archive.

| Outcome | What it means / agent action |
| --- | --- |
| `send_held` | Global or account policy blocks sending. Stop; no user-side workaround. Receiving/search are separate. |
| `recipient_blocked`, `recipient_suppressed`, `recipient_not_allowed` | Recipient-specific refusal. Do not try an alternate address for the same person to evade it. |
| `quota_exhausted`, `provider_rate_limited`, `provider_daily_limit` | Local/provider limit. Do not retry aggressively or scatter recipients across new messages. Report the limit and wait for an authorized later attempt if still needed. |
| `send_outcome_unknown` | Provider submission may have happened. **Never** blindly resend or change the idempotency key; preserve the original ZIP/key and seek status/reconciliation. |

An accepted send means the provider accepted the request, not that a remote inbox received it. Replaying the same idempotency key and identical ZIP may recover an accepted or definitive rejected result without a second provider submission; a different payload under the same key is invalid. A new key after an uncertain outcome can duplicate mail. These controls are implemented in source but need hosted CI and deployed lifecycle canaries before general availability can be claimed.

## Retrieved archive

Download to a chosen path and use CLI unpack into a **new** destination directory. Retrieved archives can contain `body.txt`, `body.html`, declared assets, and immutable receipt metadata such as message ID, direction, and received time. Current read state is mutable and belongs to `amail get` or search results, **not** the ZIP. The archive is evidence of a message, not a reusable send template. Copy only the content and assets intentionally needed into a fresh draft and construct a new outbound manifest. Inbound content, including HTML and filenames, is untrusted.
