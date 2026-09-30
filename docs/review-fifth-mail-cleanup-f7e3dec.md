# Review: historical fifth-run exact-fixture cleanup (`f7e3dec`)

**Decision: conditional GO for one guarded hosted dispatch, not a claim of historical E2E acceptance.** The revised script has no demonstrated wrong-message deletion path under its stated staging-only, exact-run assumptions. This is a source review only; hosted CI and live fixture values are separate gates.

## Scope and evidence

Reviewed `infra/tests/staging_fifth_mail_cleanup.py`, its synthetic tests, the prior cleanup design and review, the old run's MIME constructor, Worker inbound archive construction, CLI `read`/`unpack` implementation, and the D1 aggregate. `git diff f7e3dec^ f7e3dec --check` passed. No local heavy tests, live dispatch, provider reads, or secret inspection were performed.

## Guard trace

1. The fixed confirmation/run/attempt, staging account, HMAC-derived mailbox, Windows-only native binary, 100%-serving Worker/bindings pin, exact retired-address/no-route/expected-issuer D1 aggregate, two-fixture cardinalities, and initial embedding gate remain before authentication and before any deletion.
2. Native PKCE authentication is followed by complete owner-scoped mailbox pagination and exact-title reconciliation. For **each active fixture**, `get` checks ID, mailbox, direction, subject, sender, recipient, text/HTML/attachment shape, bounded delivered Message-ID syntax, and received time. `read` downloads the exact ID's ZIP; native `unpack` rejects traversal, symlinks, duplicate entries, excessive expansion and pre-existing extraction destination. The script checks exact file set and path containment, full immutable manifest equality (including delivered Message-ID versus `get.metadata.message_id`), exact nonce-bearing body phrase, sanitized HTML's phrase/CID/no `onerror`, exact PNG bytes, and 73-byte attachment length. Both fixture loops finish before the second D1/route control read, repeated full inventory, second serving pin, and the first delete.
3. Each exact ID is deleted at most once, followed by exact-ID 404 `not_found`, full owner-scoped inventory-minus-one, fresh route/D1 aggregate, and finally empty inventory plus zero active aggregate and a serving pin. After mutation only, zero-or-one soft-deleted fixture counts allow legitimate Cron physical purge; unrelated/outbound/foreign-shape owner-visible mail still fails closed.
4. The CLI captures stdout/stderr privately; failure output is fixed labels only. ZIPs and auth material remain under repository `.temp` and are removed in `finally`; no raw message, address, token, ZIP, or Message-ID is intentionally printed.

## Material residual risk (explicit acceptance)

The delivered Message-ID is checked for syntax and consistency between `get` and the ZIP manifest, **not** against the original SMTP submission. That is the correct change after hosted `fixture_get_message_id_mismatch`: Cloudflare may own/rewrite this header, and the old SMTP DATA receipt was not retained. The ZIP and metadata originate from the same Worker parse, so their equality is not independent provider-origin proof. Exact secret-derived mailbox, two unique titles, sender/recipient, MIME structure, body phrases, PNG, attachment length, complete inventory and D1 corroboration materially narrow the risk of deleting an unrelated owner-visible message, but cannot cryptographically prove historical submission provenance. The random 73-byte attachment digest is irrecoverable and is therefore checked only for length. The D1 aggregate joins only the address owner and attests issuer, not exact authenticated `owner_sub`; it cannot certify absence of foreign-owner rows. This dispatch is a conscious, narrow cleanup-risk decision, not a global mailbox-erasure attestation.

## Conditions before dispatch

- Hosted CI must run the new tests and build the exact script version; review any failure before a mutation attempt.
- Pin the current serving Worker version and allow no concurrent deploy. Require the script's fresh exact aggregate, route, native login, both ZIP validations and second pre-delete reads to pass. Do not bypass a failed fixed label.
- On any ambiguous or partial delete result, do **not** blindly rerun. Read the exact aggregate and inventory and reassess remaining fixture state before another separately reviewed action.
- Preserve the fifth E2E as failed regardless of cleanup outcome; separately test fresh SMTP receipt-to-ZIP/search acceptance after repairing the E2E oracle.

**No blocking code defect identified in this revision.** A separate exact-principal/foreign-row attestation and provider-event/raw-MIME provenance would strengthen the proof but are not represented as already accomplished, and lack of them is part of the bounded risk acceptance above.
