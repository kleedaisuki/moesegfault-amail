# Fresh Mail storage scope: source-owned provider boundary

Date: 2026-10-01. This is source implementation/design evidence only. No local
runtime tests, Cloudflare requests, resource creation, mail/account operations,
deployment, toolchain installation, push or PR was performed for this work.
Hosted synthetic/runtime acceptance belongs to the integrating controller owner.

## Contract and preservation

`infra/deploy/fresh_bootstrap_scope.py` implements `FreshProvider(account, token)`,
`create_scope(provider, epoch, recovery_path)`, `reconcile_scope(provider, epoch,
path)` and `render_configs(scope, folder)`. Shared immutable `Epoch`/`Scope` remain
owned by `fresh_bootstrap_contract.py`. The protected controller must establish
same-run artifact/main/full-gate authority, freeze writers and pass the original
scope preconditions before invoking creation. Constructing an Epoch is not that
authority. Existing production/staging databases and the original R2 bucket are
not mutated, adopted, migrated, deleted or abandoned by this helper.

Names derive solely from the approved Epoch's source/run key. Both complete,
successful inventories must establish name absence before the first create.
D1 uses unfiltered account pagination, consistent total_count, exact page/count/
per_page and duplicate-free UUIDs. R2 uses default-jurisdiction cursor pagination,
duplicate-free names and a terminal missing/empty continuation cursor in validated
result_info. Missing result_info, unreadable lists, cycles, drift or over-bound
inventory fail closed, never become absence. Limits are 1 MiB per HTTP response,
1000 rows per page and 10000 inventory entries; exhaustion refuses provisioning.

The creator exclusively creates a recovery-only JSONL journal before any provider
operation. Ownership and each one-attempt pre-submit intent are flushed/fsynced.
Acknowledged creates retain only validated name/UUID/provider creation timestamps;
each must agree with an exact GET. A D1 partial success remains recoverable even
if the later R2 create fails. 409 is existing-resource refusal, not adoption.
Transport timeout/error on POST is ambiguous, never retried. Existing journal
paths and repeated transport create families refuse replay. No cleanup exists.

Read-only reconciliation observes only identity coordinates from acknowledged
successful creates. Missing responses, failed reads, drift and 404 remain UNKNOWN.
It does not search for/adopt an ambiguously created store, emit a receipt, grant
adoption or grant write replay. The controller owns a separate journal and must
retain both journals as recovery artifacts on failure.

## Concrete Cloudflare schema references

The official English API schemas were checked on 2026-10-01:

* [D1 list](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/list/)
  documents GET `/accounts/{account_id}/d1/database`, UUID/name/created_at entries
  and count/page/per_page/total_count metadata. No name filter is used because
  total_count describes unfiltered inventory, not a safe filtered completeness
  witness.
* [D1 create](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/create/)
  documents POST to that collection with name, yielding the D1 object.
* [D1 get](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/get/)
  provides exact UUID readback rather than adopting a list candidate.
* [R2 list](https://developers.cloudflare.com/api/resources/r2/subresources/buckets/methods/list/)
  documents result.buckets, creation_date, default jurisdiction, cursor pagination
  and result_info.cursor/per_page. The created bucket uses the implicit default
  jurisdiction; this is not an assertion about buckets in other jurisdictions.
* [R2 create](https://developers.cloudflare.com/api/resources/r2/subresources/buckets/methods/create/)
  and [R2 get](https://developers.cloudflare.com/api/resources/r2/subresources/buckets/methods/get/)
  supply name/creation_date identity readback. Explicit non-default jurisdiction
  in a create/readback response is refused.

Provider timestamps must be actual validated UTC ISO8601 values. Fractional
seconds are retained in recovery and compared exactly between create/readback;
only the validated shared Scope representation drops fractional precision to
match the settled contract. No wall-clock timestamp substitutes for provider
creation time. Optional API metadata is deliberately required where its absence
would prevent a positive bounded completeness verdict; actual incompatible
provider response shapes must fail rather than silently weaken admission.

## Transport and generated configuration

The sole authority is `https://api.cloudflare.com/client/v4`. One optional leading
slash is normalized, redirects are denied, bodies are bounded and duplicate JSON
keys are refused. Successful envelopes require actual 2xx HTTP, success=true,
errors=[] and a result. Diagnostics use control_plane_trace's numeric HTTP status,
safe CF-Ray, bounded numeric provider codes, closed reasons and monotonic timing.
Tokens, raw URLs/query/body/provider prose and exception strings are never logged.

GET families are bounded source-owned D1/R2, fixed API/maintenance/sink Worker
readback, bounded GET-only settings for every current script inventoried by the old-scope inspector, Queue readback and validated zone inventory/routes. POST families are
Epoch-bound exact-name creation and successfully Scope-bound SELECT or three
read-only source schema PRAGMAs. Migration writes use the controller's captured
single Wrangler invocation; this module provides no generic SQL writer. External
forwarding reads keep their separately managed routing token/reader.

Rendering starts with the two original source TOMLs. Only production D1 name/ID,
R2 bucket, absolute original source main/migration paths and source-owned explicit API preview_urls=false differ. Staging,
custom domain/routes, both empty Cron schedules, privacy settings, Queue and
send bindings retain source semantics. No rebuild, new secret values, routing
override or activation is added. Source adoption after a real receipt remains a
separately reviewed operation, not automatic rewriting of checked-in configs.

## Verification handoff

`infra/tests/test_fresh_bootstrap_scope.py` contains hosted synthetic scenarios for
positive creation, journal-before-submit ordering, complete pagination, count/
cursor drift, duplicate identities, failed reads, existing names, conflict,
timeout, partial D1 ownership, exact readback, original/staging UUID refusal,
provider timestamp validation, read-only recovery, transport privacy/bounds and
semantic TOML equivalence outside the explicitly permitted fields. Local checks
are limited to AST syntax and Git diff inspection; no runtime success is claimed.
