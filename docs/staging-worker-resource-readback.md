# Staging Worker-level observability resource discriminator

Status: source prepared for independent review and GitHub-hosted tests. No live
read, mutation, deployment, Mail request, or local test/build has been performed.

## Purpose and bounded scope

This implements the five-GET discriminator selected in
[the effective-readback decision](observability-effective-readback-decision.md).
The old four-GET discriminator and all containment/privacy gates remain unchanged.
It does not infer missing/null as capture disabled and cannot authorize rollout.

Only the named staging Mail Worker is read, in this exact order:

1. Latest script deployment, requiring the supplied expected version at 100%.
2. Script settings.
3. Non-versioned script-settings.
4. Worker-level resource, using the official Beta GET path
   /accounts/{account}/workers/workers/amail-mail-staging.
5. Latest deployment again, requiring the identical deployment/version pair.

The Worker resource requires the exact name and a nonempty string immutable ID.
Only match/mismatch and valid/invalid identity categories can appear in output;
the ID, name values, timestamps, and other resource properties are not emitted.
The response is limited to 262,144 bytes, a 15-second transport timeout, HTTP 200,
a literal successful provider envelope, and an object result. Redirects are
rejected (no extra traversal or credential forwarding); no listing, retry,
fallback endpoint, version detail, Mail traffic, or write is performed.

Settings read failures do not skip the final deployment check. A changed or
unreadable final deployment discards all representation categories. A failed
Worker GET or invalid Worker identity is unavailable, not absent or disabled.

## Output contract

All output keys and values are selected from a fixed reviewed vocabulary.
No raw JSON, URL, arbitrary provider key/value, account/version/deployment ID,
secret, exception, or provider error body is printed or persisted.

- observability/logs/traces/issues containers distinguish missing, null, object,
  boolean, number, string, array, and other.
- Reviewed Boolean fields distinguish missing, null, false, true, and other.
- Sampling distinguishes missing/null/zero/one/other, never coercing Boolean to
  numeric or equating zero sampling with capture off.
- Tails and destination shapes distinguish missing/null/list and other JSON
  types. Tail values distinguish empty/populated/malformed, validating all service
  names and optional environment strings first.
- Destinations distinguish empty/cloudflare_only/external/malformed, validating
  every nonempty string before categorizing the list. Unknown exports stay
  external; their names are never emitted.
- Real-time issues.enabled has its own fixed category; absent is not default off.

Top-level staging_worker_resource_readback=stable100 means only all three
representations were read under an unchanged expected serving deployment.
UNVERIFIED with a fixed reason means the input, serving bracket, endpoint, or
identity could not be verified. Even stable100 is **not containment success**;
an explicit false field is evidence for a later reviewed endpoint-specific
policy, not an automatic replacement for the existing gate.

An operator settings/deployment freeze is required: identical deployment IDs do
not exclude a concurrent non-versioned settings edit, and these observations are
not an atomic transaction or future guarantee.

## Hosted invocation

The manual CI target is staging-worker-resource-readback, exclusively on
codex/amail-v0.1.0 with the distinct exact confirmation
READ_STAGING_WORKER_RESOURCE_OBSERVABILITY and expected_worker_version set to
the privately reviewed 100%-serving version. The staging job runs synthetic
contracts before its final credential-bearing step, using existing repository
CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN only. It does not require a new
credential or CF_OBSERVABILITY_TOKEN.

Example (replace the placeholder privately; do not print the live response):

    gh workflow run ci.yml --ref codex/amail-v0.1.0       -f target=staging-worker-resource-readback       -f confirm=READ_STAGING_WORKER_RESOURCE_OBSERVABILITY       -f expected_worker_version=<reviewed-serving-version>

Run only after independent source review and hosted synthetic CI pass. Retain the
run ID and fixed bins as evidence, not raw provider artifacts. Interpret the
result using the explicit-safe / explicit-unsafe / still-ambiguous branches of
the decision document; do not loosen production gates from this diagnostic.

## Verification and provenance

Added synthetic contracts cover the exact five reads; same-version changed
deployment IDs; early wrong-version rejection; unavailable Beta GET and invalid
name/ID; all JSON kinds; strict Boolean/numeric distinction; malformed collection
members; fixed private output; input denial; transport bounds/envelope/GET/no
redirects; and branch/confirmation/test-before-secret workflow policy.

Only Python AST parsing and git diff whitespace inspection were performed
locally. Tests, live resource availability, and effective containment remain
unverified until hosted execution. The official
[Get Worker API](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/get/)
was consulted on 2026-09-30; its current resource schema and evidentiary limits
are recorded in the linked decision rather than rediscovered or assumed.
