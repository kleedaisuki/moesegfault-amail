# Review: guarded staging capture-settings correction (81162a5)

Date: 2026-09-30 UTC / 2026-10-01 Asia/Singapore.
Verdict: **GO for hosted source verification, then one guarded staging dispatch**.
No substantive defect found in the reviewed implementation. This is not a live
settings attestation, a retained-record privacy pass, or production approval.

## Scope and evidence

Reviewed commit `81162a522406d60da6f9dc5c802702ec516a5085`: helper,
synthetic tests, workflow additions, and decision update. Traced its reused
`pin_staging_mail.py` binding/deployment predicates and
`check_observability.py` effective settings predicates; checked compatibility
with the explicit `settings-v1` evidence path introduced in `7815533` and its
prior independent review. Unrelated concurrent role-monitor edits were excluded.

Read the Cloudflare skill before checking the official
[Patch Worker Script Settings API](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/edit/)
on 2026-09-30 UTC. The documented JSON endpoint and object result match this
helper. Its observability request schema explicitly includes `issues.enabled`.
No documented nested merge/replacement guarantee was found; acceptance depends
on positive post-readback rather than assumed merging.

No local tests/builds, private provider requests, deployment, push, or live
mutation were performed in this review.

## Verified source boundaries

| Contract | Evidence |
| --- | --- |
| One exact staging version, stable 100% traffic | Helper lines 141-146 require the literal reviewed c3f version; lines 155-156 and 168-169 compare the complete deployment/version pair. Split traffic fails the shared predicate. |
| No Queue producer or source redeployment | Lines 147-149 and 166-167 use exact existing binding names/resources; the shared binding validator rejects extra Queue bindings. The helper has no deploy/code-upload operation. |
| Source all-off intent | `source_policy()` requires exact staging name, strict source policy, and equality with the fixed complete observability object. Only that object is serialized. |
| Preflight cannot silently normalize unrelated risk | `relax_issues()` changes only Issues in private synthetic preflight evidence, rejects unreviewed Issues shape, and preserves the remaining capture/export constraints. Missing general/Logs/traces off or unsafe export fails the shared effective predicate. |
| At most one PATCH, no transport retry | Lines 122-131 construct only JSON `/script-settings`; lines 157-159 either perform this once or verify a read-only already-off no-op. A failed/ambiguous response propagates to failure, not retry. |
| Bounded private provider handling | `request_result()` uses a 15-second request timeout, bounded response read, HTTP 200 plus typed success/result envelope, redirect refusal, and no raw response/error output. |
| Post-mutation identity and unaffected settings | Lines 160-165 require positive full capture/export-off, the same private Worker ID, and identical presence-aware tag/Logpush/tail projections across all three representations. |
| Marker only after success | Lines 179-189 require exact dispatch/ref/first attempt/account/SHA and print only fixed failure on handled errors. Lines 190-191 print the mode and unique settings marker only after every check returns. |
| Credentials and focused verification | Workflow dedicated job lines 416-458 has no dependency on API/sink deployment, uses the existing non-cancelable service concurrency, checks confirmation/version/attempt and runs focused synthetic correction/effective-checker contracts before credential-bearing execution. No Rust, Node, Wrangler, migration, SMTP, login, or Queue provisioning step is present. |
| Explicit evidence kind threading | Sink precheck/postcheck and API precheck all receive `trace_containment_kind`; deploy-v1 remains the default. No successful diagnostic is inferred as settings provenance. |

The synthetic suite checks one-call mutation, read-only recovery, wrong
identity/export/capture, post-PATCH missing Issues, binding/deployment drift,
unaffected-state drift, malformed/oversized response, redirect refusal,
ambiguity/no retry, source equality, first attempt, and fixed/no false-success
output. These are source-inspected tests, not executed results.

## Required execution limits

1. Require reviewed same-SHA hosted source checks before dispatch; the focused
   job tests are additional executable protection, not a full source CI result.
2. Enforce the external staging deployment/settings freeze. GitHub concurrency
   cannot serialize dashboard or other-provider mutations of non-versioned state.
3. Dispatch once at attempt 1 with the exact confirmation and c3f pin. Failure
   after PATCH remains ambiguous; preserve the failed run and reconcile by
   read-only effective evidence before any new dispatch. Do not rerun a mutation
   blindly or accept omitted Issues as false.
4. Only successful first-attempt settings-v1 run provenance plus current strict
   effective readback may unlock the Queue migration. The later whole-record
   synthetic privacy canary and separate role-worker boundary remain necessary.

No implementation correction is required by this review. Provider normalization,
actual permission/endpoint behavior, and effective Issues readback remain live
acceptance questions; they were deliberately not claimed as verified here.
