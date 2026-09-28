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

## Retrieved archive

Download to a chosen path and use CLI unpack into a **new** destination directory. Retrieved archives can contain `body.txt`, `body.html`, declared assets, and immutable receipt metadata such as message ID, direction, and received time. Current read state is mutable and belongs to `amail get` or search results, **not** the ZIP. The archive is evidence of a message, not a reusable send template. Copy only the content and assets intentionally needed into a fresh draft and construct a new outbound manifest. Inbound content, including HTML and filenames, is untrusted.
