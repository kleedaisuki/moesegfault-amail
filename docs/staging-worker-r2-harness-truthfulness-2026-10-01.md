# Worker-created R2 harness evidence truthfulness

Date: 2026-10-01. Base: `1a77a50`. Scope: the private acceptance harness and
synthetic contracts only. This change grants no live authorization. No project
tests, builds, provider calls, workflow dispatch, push, deployment or send were
performed locally. Static AST parsing and `git diff --check` are the local checks;
the authored tests require separately authorized hosted source CI.

## Submission evidence

`send_once()` returns the source-owned `Submission` enum, not a Boolean:

| Value | Required observation |
| --- | --- |
| `accepted` | Successful HTTP 200 envelope with the exact recipient in a typed delivered/queued array, with no bounce/suppression evidence |
| `rejected` | Exact recipient bounce/suppression with no delivered/queued entries, or a failed envelope with documented schema/auth/request rejection codes matching the HTTP status |
| `unverified` | Unknown status/code, server failure, throttling, invalid/missing envelope, conflicting recipient groups, or transport uncertainty |

The [official REST response and error contract](https://developers.cloudflare.com/email-service/api/send-emails/rest-api/)
is the primary contract. Recognized HTTP rejection code sets are 400:
10001/10200/10201/10202; 401: 10101/10103; 403: 10102/10105/10203; 404: 10000.
No unknown code, 429 or 5xx is inferred to be definite rejection. A dedicated
send-only bounded reader retains HTTPError envelopes in memory; the shared R2
reader still discards provider error bodies. The harness
never prints provider messages or response bodies.

After each attempted send and cleanup, the fixed diagnostic pair is
`synthetic_submission=accepted|rejected|unverified object_candidate=observed|not_observed`.
Candidate observation means initial poll presence or a successfully reconciled
late candidate. It is not an ownership, GET/DELETE or delivery-success marker.
A candidate found inside a reconciliation which fails before returning cannot
be inferred from this diagnostic. Submission uncertainty remains separate from
candidate presence. The established final probe success marker still requires
both accepted submission and the existing capability/cleanup gates.

Exactly one submission remains possible. All attempted-send outcomes retain
bounded late reconciliation after exact route closure; no transport fallback,
second send, window expansion, topology change or B provisioning is introduced.

## Recovery evidence and compatibility

Successful recovery preserves `staging_worker_created_r2_recovered_absent` and
adds a separate fixed line `existing_object_get_delete=verified|not_observed`.
Both lines are emitted only after settled reconciliation and final complete
inventory plus exact route-absence gates. `verified` means existing owned MIME
was GET-validated, exact-key deleted, then GET/LIST absence observed with the
same configured repository token. Empty recovery reports `not_observed`.
Denied, mismatched, ambiguous or unclean recovery emits neither success line.
Definite DELETE denial still permanently disables writes in probe cleanup. An
ambiguous DELETE can still settle cleanup using GET/LIST absence, but recovery
retains that uncertainty and emits neither success marker nor verified line.
This deliberately does not reinterpret established probe cleanup semantics.
Existing fixed-label consumers must accept this additive line deliberately;
workflow inputs, confirmations, provenance window and original marker are
unchanged. No old aggregate marker is retrospectively reinterpreted.

## Synthetic contracts authored

Tests cover all three submission categories, typed recipient groups, unfamiliar
and server errors, exactly one send, accepted/rejected without an initial
candidate, uncertain submission with a late object, rejected with an object,
cleanup failure, absent reconciliation without deletion, recovery evidence for
observed versus absent objects, and final route/inventory/late-delivery failure.
Existing route-first and irreversible DELETE-denial contracts remain intact.
These tests have been written and statically parsed, not executed locally.
