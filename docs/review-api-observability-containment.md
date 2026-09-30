# Review: public API retained-context containment

Reviewed commit `f3d389c81e442577d86715c104c94f73a5c6c4fe` on 2026-09-30.
Decision: **GO for hosted CI and a staged containment deployment**, subject to
the readback and serving-pin gates below. No substantive source defect was
found in this narrow change. This is not a full privacy attestation, a Queue
sink review, or approval to enable production public sending.

## Scope and evidence

The commit changes exactly three files: `crates/mail-worker/wrangler.toml`,
`check_observability.py`, and `test_check_observability.py`. Both production and
staging explicitly disable top-level observability and retained Logs; native
traces and invocation logs remain explicitly disabled. No Rust business logic,
route, binding, Cron, secret, storage schema, CLI response, or request contract
is changed. Other agents' uncommitted Queue/workflow/Cargo changes were excluded.
No local test, build, live API call, deployment, or push was performed.

Current [Cloudflare Wrangler documentation](https://developers.cloudflare.com/workers/wrangler/configuration/#observability)
describes the top-level enabled setting as the persistence switch. The actual
Cloudflare-published [Wrangler 4.142.0 configuration schema](https://unpkg.com/wrangler@4.142.0/config-schema.json)
was fetched separately: its `Observability` definition accepts Boolean
`enabled`, `logs.enabled`, `logs.invocation_logs`, `traces.enabled`, and
top-level `redact_query_string`; the TOML sections use the corresponding nesting.
The [Workers Logs documentation](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)
confirms explicit per-environment configuration and redeployment. The unchanged
100% sampling setting is inert while capture is disabled, not a claim that
sampling redacts data.

The strict checker requires literal false for both capture switches and native
traces, literal false for invocation logs, and rejects Logpush or Tail consumers
and non-Cloudflare destinations. Both settings endpoints must pass. Its
existing `persist`-not-false predicate is unnecessarily restrictive for disabled
capture but does not permit capture: a provider that normalizes disabled fields
away or to `persist=false` would fail the gate rather than silently pass. Such
a hosted readback failure must be examined as a provider-shape issue before
claiming the deployed containment is unsafe or weakening the checker.

At the reviewed commit, CI runs the checker unit tests on hosted runners;
staging deployment uses pinned Wrangler 4.142.0 and `--env staging`, production
deployment remains manual/main-gated, and each API deployment is followed by
the matching realm's read-only checker and a health GET. These are deployment
and config gates, not an automatically completed serving-version/privacy proof.

## Rollout conditions and limits

1. Deploy the exact containment-only committed source, not the unfinished Queue
   worktree. Require hosted CI and post-deploy checker success. No assertion of
   a currently deployed change is made by this review.
2. Preserve the deployment Version ID, freeze competing staging deployments,
   and run the existing `staging-serving-pin` against that exact ID. The pin
   rejects split traffic, requires a single 100% version, validates its resource
   bindings, reads both settings endpoints and compares deployment/version IDs
   again. This pins an observed interval; settings are script-level observations
   rather than immutable version-specific settings. Do not treat a health GET
   or uploaded version alone as proof that all traffic uses containment.
3. Disabling future capture does not erase historical retained events or cover
   unrelated platform Security Events. It also deliberately creates a temporary
   retained application-trace gap. Keep the public-send/privacy gate closed;
   the independently reviewed and deployed replacement sink plus retained-data
   and failure canaries remain necessary to satisfy the full observability goal.
4. Do not blindly roll back to a pre-containment version on a business failure.
   Redeploy any necessary old business code with the disabled retention boundary,
   then read settings and pin serving traffic again. Never restore the known
   request-facing retained logger as a diagnostic fallback. Cloudflare's
   [rollback documentation](https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/)
   describes serving an older version; it is not a privacy exemption.

The change preserves external Mail API userspace behavior by inspection of the
exact diff. That statement excludes hosted build/runtime equivalence testing,
other Workers' independent retention boundaries, and the unfinished Queue path.
