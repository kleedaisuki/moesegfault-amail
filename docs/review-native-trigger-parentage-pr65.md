# Independent review: fixed native trigger profile and per-case parentage (PR 65)

Reviewed exact source `d22312e315d6879ad30bf88a9e7bae770b592907` in `.temp/native-tracing-client-trigger` on 2026-10-01. Scope: three-file diff, surrounding trigger/admission/collection/summary code and hosted test contracts. No production edits, local runtime tests/builds, provider operations, secrets reads, deployment or merge.

## Verdict

**No demonstrated blocking correctness defect found.** This bounded orchestration change strengthens cohort and native-causality checks without changing Rust/build/config/workflow or the existing deployment admission policy.

* Normal trigger now sends the previously reviewed fixed self-identifying compatibility User-Agent and records the profile before submission. It remains one empty anonymous POST, with redirects refused and no credential/cookie/body forwarding or automatic retry.
* Trigger still requires four rows, native availability/sampling/completion, exact run identity and correct source-defined success/failure status. Membership and uniqueness in the four baseline/redacted × success/failure combinations now prevent four duplicate reports from passing.
* Collection verifies exactly the four case keys, one named custom child per mapped invocation, non-self parent, nonempty trace identity, and an observed parent with matching span ID **and trace ID in that same invocation**. Global counts or a parent in a foreign invocation no longer suffice.
* New tests cover exact POST/header/profile, duplicate/unknown cohorts and missing/duplicate child, foreign parent, wrong/missing trace and self-parent rejection. Surrounding summarize preserves strict source nonce/case mapping and duplicate-invocation refusal; caller records still reject the disabled capture verdict.

## Evidence and remaining limits

Coordinator reports scoped CI36880597980 and syntax36880596241 successful. No receipt was independently fetched by this reviewer. Prior absent-host variant404/code1042 and baseline403/1010 are endpoint observations; they do not prove a live POST will succeed or justify policy/token/compatibility changes.

The source correctly documents that successful API calls and four safe completion reports do not establish retained after-await attributes or fixed exception events. First actual native records must determine the provider representation, followed by bounded typed extraction and checks. Current per-case causal summary alone is not full async/error retention acceptance. Privacy conclusions are likewise restricted to marker surfaces whose baseline was actually retained; path-only baseline cannot prove header/body removal.

Conditional operational observation, not a demonstrated finding: collection currently exits its ingestion wait when global spans>=8/four case logs/path marker appear, then applies stricter per-case checks immediately. If actual provider records contain extra spans or uneven late ingestion, global readiness can precede per-case causal readiness and cause an early failure within the remaining180-second budget. Inspect the first actual provider representation; if this occurs, use the same per-case completeness predicate to control the bounded read-only wait, while still refusing contradictory/duplicate evidence and never retrying invocation. Do not add guessed waits or provider-field models before observing this condition.

Accepted integrated Rust/reader changes require a new complete original-main compiled artifact for normal canary. This orchestration-only patch and prior diagnostic do not grant an exemption, release admission or permission to resume Mail. Owned cleanup and actual serving/capture/readback remain necessary.
