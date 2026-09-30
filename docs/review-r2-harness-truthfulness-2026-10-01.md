# Independent R2 harness truthfulness review

Date: 2026-10-01. Status: GO for source integration and separately authorized hosted synthetic validation. Reviewed exact commit: `7b707bb65cd45e844974fa149cb79fbabdc1086e`.

## Scope and method

Reviewed the source-only worktree `.temp/r2-harness-truthfulness`, initially based on `1a77a50`, against `docs/staging-r2-and-smtp-acceptance-shortest-path-2026-10-01.md`. Inspected the acceptance harness, synthetic fixtures, shared R2 request/delete helper and fixed-marker references. No local project test/build, provider request/mutation, deployment, mail submission or push was performed. Public documentation retrieval is not a live provider probe.

## Findings communicated to implementation owner

1. **HTTP rejection classification was unreachable through the actual transport (high confidence).** `staging_r2_object_capability.call()` discards `HTTPError` bodies and returns `(status, b"")`; `submission_result()` needs the documented numeric code in a parsed envelope. A mocked `call()` returning an error body would not reproduce production execution. Remedy: a bounded send-specific response reader that retains private bytes only in memory, preserving no redirect/retry and shared R2 semantics, with an HTTPError-level synthetic fixture.
2. **Cleanup success must not automatically become definite DELETE acceptance (high confidence).** Existing `delete_owned()` deliberately accepts an ambiguous DELETE followed by exact GET/LIST absence as successful reconciliation. New recovery evidence must distinguish that safe cleanup from an explicitly accepted operation if the stated contract requires no verified evidence after an ambiguous stage. Preserve cleanup, but carry separate definite operation evidence and cover ambiguous DELETE followed by absence.

The worker has been notified; these findings describe an in-progress revision, not a frozen final commit.

## External contract check

The current official [Cloudflare REST send documentation](https://developers.cloudflare.com/email-service/api/send-emails/rest-api/) supports the selected HTTP/numeric-code rejection pairs and distinguishes recipient-grouped delivered/queued/bounce outcomes. Unknown errors, 429 and server/transport errors should remain unverified. Accepted submission is not proof of intended Email Worker execution or R2 delivery.

## Preliminary positive observations

- A source-owned enum separates accepted, rejected and unverified submission.
- Probe sends at most once; route closure precedes object mutation and late-object reconciliation remains active for rejected/uncertain submission.
- Recovery retains the established recovered-absent marker and places new evidence after final route/inventory gates.
- New output is fixed-category only; no address, object key, provider body, token, subject or marker is printed.
- Empty recovery must remain not_observed; pre-existing ownership/MIME and same-token checks must stay intact.

## Release boundary

Any later GO applies only to source integration and eligibility for separately authorized hosted synthetic validation. It cannot authorize another live send, establish existing-object GET/DELETE from historical empty recovery, change B readiness, or release any privacy/production gate.

## Final revision assessment at `7b707bb65cd45e844974fa149cb79fbabdc1086e`

The implementation owner resolved both substantive findings:

- `send_request()` now catches actual urllib HTTPError and reads at most MAX_REPLY + 1 bytes, using the existing no-redirect opener and a single 25-second request, without logging or persisting the response. Oversized or transport-failed responses remain unverified. Shared R2 transport is untouched. The authored fixture constructs HTTPError with BytesIO directly and reaches this real handler rather than mocking an impossible shared-reader result.
- `CleanupState.delete_unverified` records any R2 DELETE exception. Recovery preserves settled cleanup behavior but withholds both success lines if this uncertainty occurred, including ambiguous DELETE followed by confirmed GET/LIST absence. This stricter recovery evidence boundary is explicit in the implementation note; established probe reconciliation semantics are not changed.

The authored synthetic fixtures cover fixed submission categories, unknown/429/5xx fail-closed behavior, one-send branches, route-first late reconciliation, absent recovery, observed recovery, final route/inventory failure, and ambiguous-delete evidence suppression. These are source-inspected contracts, not executed results.

`object_candidate` includes an initial-poll candidate or a successfully returned late reconciliation. As the implementation note explicitly states, failed reconciliation can have inspected a candidate without reporting it. Thus not_observed must not be interpreted as no historical delivery. No success evidence is derived from this diagnostic pair.

**Decision: GO for source integration and separately authorized hosted synthetic validation**, at exact commit `7b707bb65cd45e844974fa149cb79fbabdc1086e` (base `1a77a50`). No substantive issue remains in the inspected revision. `git diff --check` passed during review. Local tests/builds remain prohibited and were not run; no runtime/provider acceptance is asserted.
