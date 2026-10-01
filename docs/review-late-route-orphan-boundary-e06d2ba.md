# Independent late-orphan workerd boundary fixture review

Date: 2026-10-01. Candidate: `e06d2bab`. Reviewer scope: source inspection only; no local project tests/build, no provider request, no deployment, no push. Candidate worktree: `.temp/late-route-orphan-implementation`.

## Verdict

**Suitable for hosted execution, with the bounded test-harness improvements below recommended before calling the adversarial matrix complete.** The requested safety timelines have executable checks against the actual compiled Rust Worker boundary. No P0 implementation counterexample was established by this inspection. This is not an execution pass, a killed-isolate proof, a provider-concurrency proof, or authorization to enable destructive maintenance. The exclusive managed-namespace precondition and documented GET/DELETE TOCTOU limit remain material rollout gates.

## Evidence and reproducibility

Inspected `git show --stat e06d2bab`, `git diff e06d2bab^ e06d2bab -- crates/mail-worker/src/{lib.rs,platform.rs}`, `infra/tests/worker-boundary/address-add.test.mjs`, its `package.json` and `worker-module-rules.mjs`, `.github/workflows/ci.yml`, and `docs/address-late-provider-orphan-implementation-2026-10-01.md`. PowerShell `Get-Content` / `Select-String` and Git inspection only. No dependency install or executable project checks were performed.

Hosted reproduction is the exact-head CI Rust Worker job: the pipeline bundles `crates/mail-worker` using `worker-build --release`, then runs `pnpm test` in `infra/tests/worker-boundary`. Its package test command explicitly discovers `address-add.test.mjs` and `sql-comments.test.mjs`. The Miniflare workers load `build/worker/shim.mjs`, interpret generated JavaScript as ESM and Wasm as CompiledWasm, and use migrated actual D1 SQL. HTTP fixtures substitute only external OIDC/provider services; they do not reimplement the Rust address state machine. The scheduled boundary calls `mf.getWorker().scheduled()`, and request boundaries call `mf.dispatchFetch()` with locally signed access JWTs.

## Contract-derived adversarial expectations

| Timeline | Expected independent observable | Fixture strength / limit |
| --- | --- | --- |
| POST side effect becomes visible after permanent retirement and marker clear; original invocation cannot resume | A later zero-due scheduled tick discovers and removes strict owned rule, without another POST; retired state never resurrects | Two zero-due fixtures plus explicit submitted/commit/respond barriers inspect provider store, D1 state, call counts. Creator remains blocked through acceptance tick. This meaningfully detects old due-only reconciliation, but is not a killed isolate. |
| Provider list is partial or uncertain | No destructive request; repair intent retained, bounded list pages | Malformed/false envelopes, short intermediate page, page-count overflow, duplicate/malformed/403 second page and ten full pages without terminal metadata exercise production decode and pagination. |
| Saved rule ID repurposed or current scoped GET drifts | Foreign object preserved, no DELETE; permanent row retains retryable intent | Request saved-ID foreign drift and scheduled current-GET repurposing use provider-rule structures, not error-string checks. |
| DELETE HTTP 200 says success=false or omits required success | Must not settle repair as complete | Two scheduled fixtures assert one attempted DELETE, retained needs_reconcile and preserved provider store. |
| Response exceeds body bound without Content-Length | No destructive request or completion based on oversized body | A real ReadableStream produces >256 KiB through workerd egress. See streaming allocation coverage limit below. |
| Forty due retired lifetimes exceed one invocation budget | Every invocation <=20 routing exchanges; unfinished rules/markers persist; all eligible rules eventually receive a turn | Real D1 and persistent provider Map; bounded nine-tick sequence forces due times without making claimed rows precede never-claimed rows. Covers successful-provider rotation, not failure fairness. |
| Rule becomes committed active during current GET | No DELETE of newly committed ID | Provider hook updates actual D1 before GET response. Both D1 active ID and provider object must survive. Existing active-prune/disabled-active tests cover stable committed IDs. |
| Large historical tombstone set but empty provider inventory | One external inventory, no per-tombstone egress | 1,000 SQL tombstones, one GET assertion. This does not prove no internal all-tombstone SQL scan; that is established only by source inspection. |
| Old provisioning shared snapshot says absent but later snapshot has disabled route | Do not transition to retryable pending | Fresh inventory fixture asserts two list calls, no DELETE, and unchanged provisioning. |

The mock's `lastGet` assertion independently prohibits blind DELETEs, while D1/state and provider-store assertions prevent a swallowed mock exception from falsely establishing cleanup. The old implementation should fail the zero-due cases because it never inventories after marker clear, and fail scoped cleanup because it does not issue current-ID GETs; this is source-based mutation sensitivity, not an executed before/after regression result.

## Actionable findings

### P1 test-harness resilience: unbounded barrier waits

`address-add.test.mjs:588-624` waits for `submitted.promise` and `committed.promise` and later awaits `creator`, with no `node:test` timeout, AbortSignal or bounded barrier deadline. If an address-add regression fails authentication, crashes, or incorrectly declines POST, the test waits at `submitted.promise` rather than producing a useful failed assertion. The eventual GitHub job timeout is not a useful narrow failure diagnosis.

Recommended isolated harness change: bounded barrier waits with descriptive phase failures and cleanup which always releases commit/respond and disposes Miniflare. Explicitly settle or observe creator rejection so a regression cannot wait forever or become an unhandled rejection. A test-level timeout alone may not cancel awaited cleanup; bound the cleanup as well. Validate this on hosted CI with an isolated intentionally non-submitting fixture, without changing production to make it pass.

### P1 evidence gap: failure fairness and per-row error continuation are not exercised

`address-add.test.mjs:560-579` demonstrates rotation only when every inventory/current-GET/DELETE succeeds. Candidate `claim_address_repairs` intentionally rotates claims *before* inventory, and `reconcile_addresses` intentionally continues after a failed row. Those are consequential liveness claims not demonstrated by the present forty-row case.

Recommended fixtures: (1) forty due lifetimes, first one or two inventories fail, advance clock/due admission in a controlled way, inspect different claimed cohorts and eventual cleanup after provider recovery; (2) first selected row has current-GET scope conflict or a false DELETE acknowledgment, while later eligible rows get a turn and a later state-only deleting/retired transition proceeds within the same twenty-call bound. Ensure poison intent remains. These would detect moving claim rotation back after provider I/O, or returning on the first row error.

### P2 evidence precision: oversized stream tests semantic limit, not incremental allocation

`address-add.test.mjs:722-742` correctly checks rejection of an oversized stream. An implementation which first eagerly reads the entire stream and only then checks length can also pass this case. The claim that reads stop incrementally at the bound rests on inspected Rust `rule_body`, not on this assertion alone.

Recommended stronger synthetic stream: track pulls/cancellation, feed a substantially longer bounded fixture stream, and assert the consumer does not drain all payload before failing. This is an incremental-read behavioral check; avoid claiming a measured peak-memory bound from a JavaScript stream pull count, since runtime buffering affects it. Add GET/create/DELETE body-path coverage if claiming identical runtime behavior across all four envelope types; present oversized fixture directly covers list only.

## Remaining limits, not new product defects

- No actual killed invocation, resumed-after-isolate-loss test, redirect response test, or deployed Cloudflare provenance test was executed here.
- Provider pagination is not an atomic snapshot; strict current GET cannot prevent foreign provider edit between GET and DELETE. Fixtures cannot grant stronger capabilities than provider API contracts.
- The list-field coherence examples do not exhaust every optional page/per_page/count/total_count mismatch or unsafe-ID variant. Source inspection shows checks, but runtime completeness must not be inferred from static checks.
- Forty-row case bounds routing HTTP exchanges only, not total scheduled D1 subrequests, embedding traffic, CPU, or account plan limits.
- Pending-clean late-route race is explicitly outside this retired-lifetime repair contract; do not advertise universal orphan convergence.
