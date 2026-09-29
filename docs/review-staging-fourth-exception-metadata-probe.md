# Review: bounded historical exception-metadata probe

Status: independent source review on 2026-09-29, updated after `f927fa4`. **The two required corrections below are resolved. One bounded private owner-side query may proceed after the existing hosted synthetic test job passes**, provided the documented no-logging/no-artifact/one-use controls are followed. This is not a retained-log privacy attestation or causal finding. I reviewed `infra/provider/probe_staging_fourth_exception.py`, `infra/tests/test_staging_fourth_exception.py`, `docs/staging-fourth-exception-metadata-probe.md`, the established retained-event query/parser notes, and Cloudflare's current [telemetry query API](https://developers.cloudflare.com/api/resources/workers/subresources/observability/subresources/telemetry/methods/query/) and [generated TypeScript schema](https://github.com/cloudflare/cloudflare-typescript/blob/main/src/resources/workers/observability/telemetry.ts). I made no live provider call, local test run, or production change.

## Findings

### 1. Credential statement (resolved in `f927fa4`, high confidence)

The original document called the operator credential “read-only”, although Cloudflare requires **Workers Observability Write** for `POST /workers/observability/telemetry/query`. Revision `f927fa4` now distinguishes the dry, non-mutating **operation** from the credential's broader authority. Prefer the narrow existing Observability token over a broad OAuth token if it works. Do not copy either token to logs or repository files.

### 2. `$workers` row identity (resolved in `f927fa4`, high confidence)

The original `classify()` accepted a present `$workers` object without `scriptName` by manufacturing the expected value. Revision `f927fa4` now requires an explicit, exact `scriptName` in every accepted row and adds a missing-script-name regression. This is stricter than Cloudflare's optional `$workers` field; therefore some otherwise relevant rows may become `UNVERIFIED (scope)`. That fail-closed result is preferable to claiming exact Worker identity from an absent field. A wrong-script synthetic case remains a useful optional addition.

### 3. Keep the one-page completeness claim explicitly conditional (coverage, medium confidence)

Cloudflare's schema defines `result.events.count` as the **total** matching events, potentially greater than the returned list length; the API provides cursor pagination through `offset`. The parser's `count == len(rows)` is therefore a valid fail-closed check for a single-page response. At exactly 200 returned rows it remains sound **only if** Cloudflare's total count is authoritative and stable; the previous project canary's complete pagination uses cursor IDs because it handles larger windows. State that the new one-request probe deliberately refuses any total over 200, and add tests for `count=201, len(rows)=200`, exactly 200, missing count, and a response body above 256 KiB. Do not silently page or raise the limit to obtain a diagnosis. This is not a blocker to one dry read if the total-count contract holds.

### 4. Expand synthetic failure-path coverage when practical (test adequacy, medium confidence)

Current tests cover a recognized literal, private error mapped to a fixed label, wrong service, missing Worker identity, count mismatch, and missing opt-in. They do not exercise duplicate JSON keys, redirect rejection, body-cap rejection, `STARTED`/non-dry responses, wrong timeframe/filter echo, out-of-window rows, wrong script name, multiple candidates, or the final `main()` output envelope when a provider error or unexpected exception occurs. These are useful additions for future maintenance, but source inspection finds the listed boundaries implemented fail-closed and **they are not a further blocker for one private historical query after the hosted suite passes**. Mock `fetch`/opener and capture stdout without network to prove one fixed label, no provider/body/token text, and no second request; use the hosted infrastructure test job as required by the project. Tests should assert behavior, not only repeat classifier branches.

## Positives and interpretation limits

- Exact hard-coded Worker/timeframe and confirmation, `dry=true`, no redirect, one request, bounded read, duplicate-key rejection, no raw HTTP response printing, and a closed output vocabulary are appropriate privacy boundaries. The fixed milliseconds correspond to the documented 69-second E2E step window.
- The classifier examines only two exact WebAssembly error literals from `$metadata.error`, not private `source`, `$metadata.message`, URL, stack, or request ID. Unexpected strings map to `other_or_absent`. Even a recognized literal is explicitly `_not_attributed`; one aggregate `scriptThrewException` plus one retained exact error in a busy window does **not** prove it was the address-add invocation or identify a Rust panic site.
- Empty or missing retained events cannot rebut the aggregate metric because invocation logs are disabled and retention/sampling differ. The chosen query may simply return `UNVERIFIED` or an uninformative fixed label; do not replay address creation to force a better answer.
- I did not validate a real Cloudflare response or inspect credential configuration. The conclusion is a source/API-contract review, not an operational privacy attestation.
