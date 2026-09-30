# Agent-first CLI product-contract review

Status: source and documentation review, 2026-09-29. This is **not** a new build, test, or deployed acceptance result. Scope: the original agent-first workflow, `crates/amail/src/{main,config,archive,auth}.rs`, the Mail API's summary/search contract in `crates/mail-worker/src/{lib,search_jobs}.rs`, `site/src/pages/manual.md`, and both checked-in amail skill copies. Existing release and hosted-E2E gates remain owned by `docs/release-gap-audit.md` and `docs/validation.md`.

## Product judgment

The source has the right core shape: the person authorizes a browser login; the agent can use short commands for address management, metadata-first retrieval, explicit read-state changes, deletion, and ZIP-only content handoff. `amail login`, `sync`, `search`, `get`, `read`, `mark`, `delete`, `pack`, and `send` exist. There is no `view` command or terminal body rendering. Default result rows are compact JSON Lines, while global `--human` is opt-in. `get` gives metadata without marking read; `read -o` creates a ZIP or safely unpacks it; `mark` alone changes read state. Search composes date, title, sender, recipient, body, selected metadata, regex/case, read state, and server-side semantic matching. Configuration uses defaults, then `config.toml`, then environment overrides. Native ZIP packaging and the archive skill cover HTML/plain-text and declared assets. These are **source observations**, not proof that a deployed user can complete SMTP-to-ZIP or sending.

The v0.1 product should not add a web inbox, a `view` command, arbitrary message editing, or a broad configuration language. The following two gaps are worth fixing because they affect the dominant agent journey, not because a feature checklist is incomplete.

## Findings, prioritized

### P1 — repeated metadata filters silently discard a predicate

`crates/amail/src/main.rs::metadata` inserts each `--meta KEY=VALUE` into a `BTreeMap<String,String>`. A repeated key overwrites the prior value before the request reaches the server. Yet `search` is presented as AND-composing supplied predicates, and the CLI accepts the repeatable flag without a warning. For example:

```sh
amail search --meta attachment_name=report.pdf --meta attachment_name=chart.png
```

The source sends only `attachment_name=chart.png`. An agent could then mistake a result lacking `report.pdf` for one satisfying **both** conditions. This is a source-level correctness risk; it does not require deployed evidence to establish the overwrite. The server currently models metadata as a map and allows four selected keys (`message_id`, `in_reply_to`, `content_type`, `attachment_name`), so implementing same-key conjunction would change the wire contract. The smallest compatible fix is to **reject duplicate keys in the CLI with a clear error before making the request**. Document that different metadata keys combine by AND; do not silently promise same-key conjunction. If real tasks later need two attachment names, deliberately extend the API and index model rather than treating last-write-wins as search semantics.

Acceptance: the example above exits nonzero without an HTTP request and reports that `attachment_name` was repeated; `--meta message_id=x --meta content_type=text/plain` still sends both; an ordinary single-key filter is unchanged. Run focused source tests in GitHub Actions, not on the development machine.

### P1 — first-login manual asks the person to operate the CLI, not just authorize

`site/src/pages/manual.md` says the person should personally run `amail auth login`. The actual supported agent flow is simpler: the agent invokes `amail login`, then the person completes only the browser consent/sign-in. The skill already describes that division correctly, and `amail login` is the short alias implemented in source. This wording matters because the original promise is not merely “no web inbox”; it is that the agent owns routine CLI work while the person controls the Identity authorization boundary.

Recommendation: make the primary manual journey “ask the agent to run `amail login`; authorize in the browser; the agent continues with `amail address list`/`add` and mail commands.” Keep `amail auth login` as an optional explicit human/manual equivalent, not the required step. Avoid implying that successful Identity login proves mail provisioning or delivery.

Acceptance: a first-time reader can identify exactly one required human action (browser authorization), and the command example uses the short alias. No auth or API behavior needs changing.

## Guardrails and evidence limits

- **Do not rework the default summary merely to shave fields.** The current row includes ID, mailbox, direction, sender/recipient, subject/time, read state, size, and content/attachment flags. It is somewhat verbose, but it supports agent triage without a follow-up request and is an established response shape. Changing fields now risks consumers. If token cost becomes a measured problem, consider an opt-in projection or versioned compact format, not silent removal.
- **Make metadata search discoverable without making it arbitrary.** The server accepts only four keys. The installed `search --help` describes `KEY=VALUE` but not that allowlist; the manual and skill show examples but not the full set. Alongside the duplicate-key fix, list these keys in help/skill/manual or link a concise reference. This is a small documentation/UX improvement, not a call for arbitrary JSON-path search.
- **Keep release claims calibrated.** Passing source/CI checks and a native authenticated address-list call do not prove registration, inbound SMTP, ZIP retrieval, search, outbound MIME, or delivery. The first hosted address-add attempt failed before SMTP; `docs/release-gap-audit.md` retains the live gates. No broad public-send promise is justified by this review.
- The two amail skill copies under `.agents/skills/amail` and `skills/amail` were byte-identical when inspected. Preserve that mirror when changing examples or metadata-key guidance.
