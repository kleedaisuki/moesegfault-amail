# Independent review: role Queue privacy remediation `99987c1`

Date: 2026-09-30. Scope: the exact 13-file commit, its immediate shared
capture-off helper, serving-pin helper, and role acceptance callers. Static
source review and official public documentation only; no local build/test,
live provider read, deployment, SMTP submission, or push.

## Disposition

**NO-GO for using this revision as the role deployment/acceptance gate.**
Two concrete integration corrections are required below. Non-deploying hosted
source CI remains useful and safe; this finding is not a prohibition on compilation.
The Rust producer/schema/sink changes have no identified substantive defect in
the examined paths. No production role cutover or privacy acceptance is implied.

### P2 — Bind capability evidence to the pinned serving version

Location: `infra/deploy/verify_role_monitor_staging.py:232-245`, especially the
unversioned `/settings` GET and `inspect_bindings(version, expected_queue)`.

The deployment bracket proves the same expected version has 100% traffic, but
the Queue/D1/send/realm capability check consumes an unversioned settings
response, not that version's resources. No version identity is checked on the
binding evidence. The audit therefore cannot reject a fixture with stable
serving deployment A, apparently safe script settings B, and an A version
whose Queue is missing/wrong or whose D1 is cross-realm. It never reads A's
resources. This is a conditional control-plane state concern, not evidence
that the live account has such a mismatch.

The official [version GET contract](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/get/)
provides the exact version ID and `resources.bindings`; the script
[settings endpoint](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/get/)
is a separate unversioned request. Existing `pin_staging_mail.bindings_match`
already follows the exact-version pattern in this repository. Worker-level
observability is deliberately a different, non-versioned setting and should
remain checked with the strict current-resource policy.

Correction: fetch `/versions/{expected_version}`, require response `id` equality,
validate its complete `resources.bindings` against the exact reviewed Queue/D1
and other capabilities, and retain both deployment reads. Keep the legacy
settings responses for capture-off noncontradiction, not positive capability
evidence. Add orchestration-level synthetic tests for safe unversioned settings
with wrong/missing/version-mismatched serving resources, split traffic, and
deployment drift. Existing helper-only tests do not test this association.

### P2 — Update the existing acceptance caller after required-argument changes

Changed definitions: `infra/deploy/verify_role_monitor_staging.py:80,137`.
Affected caller: `workers/role-monitor/acceptance.py:133-134`.

`inspect_bindings` now requires `queue_id`, and `inspect_observability` now
requires `worker`. The live acceptance driver's `preflight` still calls the
old arities. Even with valid credentials and provider responses it raises
`TypeError` before route creation/SMTP. This safely prevents mutation, but
breaks the documented read-only preflight and controlled SMTP workflow.
The README still directs operators to this driver. Deliberately holding old
deployment jobs without new pins does not repair the incompatible Python call.

Correction: make this preflight reuse the same exact serving-version,
Queue-pin, current-resource capture-off audit, without permissive defaults.
Preserve the driver's distinct ledger baseline and exact-route recovery
semantics; do not simply call an initial-empty-D1 audit after ledger state has
been accepted. Add a mocked preflight regression test that executes the real
calls and rejects absent pins before any mutation. Workflow pin integration
can remain independently owned, but the reusable caller must be coherent.

## Sound examined behavior

- `Record` is an untagged closed union. Both variants reject unknown fields;
  existing Mail serialization has no added wrapper, and existing Mail validity
  checks remain intact. Role field combinations cannot be interpreted as Mail.
- Role diagnostics have fixed service/code/role vocabularies, canonical IDs,
  bounded/coarsened counts, an eight-event producer cap, and a 1,024-byte
  independent producer/sink check. No message, envelope, report UUID, MIME,
  destination, dynamic label, provider error, or binding is passed into the sink.
- Email keeps the original forwarding result and maps failures to static text.
  Only an owned Queue handle and typed vector enter `wait_until`. Missing Queue
  or rejected publication has no console fallback and cannot turn an accepted
  forward into business failure. The official
  [Email handler contract](https://developers.cloudflare.com/email-service/api/route-emails/email-handler/)
  supplies `ctx.waitUntil` for this handler.
- Cron awaits its bounded best-effort Queue handoff, then retains the existing
  static panic on original monitor failure. Phase diagnostics propagate the
  original result; business D1/forward/digest/lease sequencing is unchanged.
  Partial failures do not acquire a new success lease because of telemetry.
- Eight messages at <=1,024 bytes are safely within the official
  [Queue batch limits](https://developers.cloudflare.com/queues/configuration/javascript-apis/)
  of 100 messages and 256 KB. Poison records are individually acked/dropped
  without raw logging; valid serialization preserves producer IDs on retries.
- Both role realms explicitly disable original-context Logs/native traces and
  Issues, with no dual logging. Current-resource readback reuses the existing
  strict policy rather than treating legacy null as disabled.
  [Issues configuration](https://developers.cloudflare.com/workers/observability/issues/)
  supports the explicit TOML switch in the repository's pinned Wrangler version.

## Limits and remaining release obligations

The source tests are unexecuted in this review. Email runtime rejection,
post-error background lifetime, Cron provider failure classification, Queue
partial delivery/duplicate behavior, and complete retained records still need
hosted/deployed evidence. Queue topology must explicitly admit exactly the two
reviewed producers before role deployment; current source documentation rightly
holds this separate integration. The external forwarding/digest Inbox oracle,
fault paths, lease expiry, and exact-route rollback remain independent gates.
No finding here claims an observed Email privacy leak or guarantees reliable
telemetry. D1 outbox and lease remain the operational correctness mechanism.
