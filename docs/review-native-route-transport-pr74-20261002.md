# Native route transport independent review

## Scope and status

Reviewed orchestration commit `5f795a8de9ee922d1ecd1fc70049d7dab192d39c`
in `.temp/native-tracing-transport`, against its parent, on 2026-10-02.
This review covers the workflow, generated configuration, artifact-admission
allowlist, invocation boundary, collector changes and cleanup adapter. It does
not yet cover the missing `native_route_lifecycle.py` implementation, hosted
validation, Cloudflare mutations or actual retained records. No local runtime
or provider operation was performed.

**Adapter verdict: no demonstrated substantive defect found in the reviewed
changes. Integrated route transport is not yet approved.** The new unconditional
helper import requires the pending helper to land before either historical or
route operations can execute. This is an integration dependency, not a final
finding against an acknowledged in-progress change.

## Checked contracts

- Route mode is an explicit first-attempt main-only dispatch value. The historical
  operation and absent-endpoint diagnosis confirmations retain their old meaning.
- Current infrastructure unit validation and original successful-main artifact
  verification precede provider-capable deployment. The two additional allowlisted
  files are experiment orchestration and its contract tests, not Rust sources,
  module bytes, compiler inputs or general Mail/release admission exceptions.
- The generated route configuration changes `workers_dev` only. Both script
  deployments are private, previews stay disabled and service topology is
  unchanged. Rust inputs and original artifact identity are not fabricated.
- Route preflight precedes receipt creation and the first bounded DNS mutation;
  script deployments and Route creation cannot proceed if that mutation fails.
  The helper must independently enforce the substantive preflight and ownership
  conditions; mocked adapter tests cannot establish them.
- `trigger-route` requires the explicit receipt transport and exact fixed ingress
  URL, then calls the helper revalidation before the one empty anonymous POST.
  Provider credentials are used for revalidation but are not placed in the POST
  headers, URL or body. Redirects remain refused and ambiguous invocation is not
  automatically retried.
- Cleanup calls ingress cleanup first. An unresolved Route/DNS ownership failure
  prevents deleting scripts underneath a possibly live ingress.
- The collector now persists each partial typed summary and waits for per-case
  native parentage rather than a potentially misleading global span count.
  Unassigned marker locations invalidate its redaction-elimination assertion.
  Async context, exception and replacement-attribute retention are explicitly
  `unverified`: this source change cannot claim full native acceptance.

## Required next evidence

Review the concrete helper with fixtures for pagination, overlapping routes,
foreign existing records, inactive TLS/account mismatches, ambiguous first
writes, replacement ownership, cleanup ordering and stale serving versions.
Run hosted tests on the integrated head. Actual invocation and cleanup remain
separate provider evidence and cannot be inferred from unit fixtures.

## External grounding

Cloudflare Routes require a proxied DNS record and route patterns determine
which Worker handles an incoming request. This supports the proposed explicit
DNS-plus-Route preconditions, not any assumption that a readable API proves
write permission or that a Worker deployment proves usable TLS:
https://developers.cloudflare.com/workers/configuration/routing/routes/

The platform guidance prefers service bindings for Worker-to-Worker calls and
structured observability with deliberate capture settings. The private probe
service binding and fixed synthetic caller preserve that separation:
https://developers.cloudflare.com/workers/best-practices/workers-best-practices/

## Integrated helper review: blocking finding

Reviewed integrated head `b1cab04165dae4bf0413c7931b17b5fec82a72f4`
(helper d5d7058, certificate page-size correction fa734aa, tests b1cab04).

### P1: Scope-filtered absence can erase ownership evidence for a moved resource

Location: `infra/deploy/native_route_lifecycle.py::cleanup_ingress`, initial
`rows` construction and `if not rows` branch.

Trigger: after a positively acknowledged owned Route creation, the same Route ID
is modified to `https://elsewhere.invalid/*` while still targeting the canary
caller. `routes()` contains the object, but the host-overlap filter removes it.
The helper marks the receipt Route `deleted`, deletes the original DNS, returns,
and the adapter deletes the caller/probe. A live Route can now reference the
removed caller, and the cleanup receipt falsely attests absence. A DNS object
renamed away from the exact reserved hostname has the analogous false-absence
path. This violates the advertised refusal of changed ownership/shape and the
Route-before-script cleanup contract.

This is a direct static executable trace, not a concurrency probability claim.
Existing `test_route_foreign_target_pattern_or_pair_version_refuses_delete`
(changed-pattern variant) and `test_dns_exact_nonce_proxy_and_content_required`
(changed-name variant) expect an exception but the traced branch cannot provide
one. Hosted execution is pending, not claimed here.

Correction: for a positively known receipt resource ID, perform exact GET by ID
before accepting scope absence. A found object must match its original intended
shape and ownership or cleanup must stop, without mutating it. Only exact-ID 404,
combined with a complete scoped inventory proving no conflicting replacement,
can establish absent. Unknown-create receipts without returned IDs can retain the
existing finite unique scope/nonce lookup. Preserve single-attempt DELETE and
unknown-delete read-only recovery.

Confidence: high. Source transport approval remains withheld pending correction
and exact-head hosted validation. No provider operation was performed.

### Primary schema checks

Official Certificate Packs list documents count/page/total_count/total_pages and
active certificate hosts/expiry/upload timestamp fields. Worker Domains list
similarly documents bounded opaque IDs and paginated results. The reviewed code
uses those fields; no demonstrated API-shape mismatch was found in this scope.

- https://developers.cloudflare.com/api/resources/ssl/subresources/certificate_packs/methods/list/
- https://developers.cloudflare.com/api/resources/workers/subresources/domains/methods/list/

## Correction verification

Correction `1e0f3f6744ce307d59e1db02ff462fb4522a604c` performs the
exact known-ID GET before scope-filtered inventory classification. A found moved
Route/renamed DNS record fails its original shape comparison and stops cleanup.
Exact-ID absence with a scoped replacement also refuses; inconsistent live-ID
and inventory evidence refuses. The demonstrated P1 finding is **resolved in
source**. The correction preserves single-attempt writes and does not adopt or
mutate the changed object.

The parent reports hosted infrastructure execution on the old head corroborated
the moved-resource failures; this review does not independently claim that run
as final validation. The pending test-fixture correction must distinguish a lost
Route DELETE acknowledgement from a subsequent independent DNS DELETE fault.
The intended recovery is to read the deleted Route absent, never replay its
DELETE, and then continue downstream owned DNS cleanup. Catching all errors would
hide failures and is not an acceptable test correction.

**Corrected source verdict:** no remaining demonstrated blocker in this reviewed
scope; eligible for exact integrated-head hosted validation. Provider dispatch,
actual TLS/invocation, complete retained-record observation and cleanup remain
unexecuted and are not certified by this source review.
