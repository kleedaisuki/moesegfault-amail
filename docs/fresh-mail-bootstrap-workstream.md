# First protected fresh-production bootstrap: implementation contract

Date: 2026-10-01. Source-only work; no provider creation/deploy/account/mail or
secret changes are authorized. Root approved a controlled fresh storage epoch
and two-step receipt -> reviewed source adoption; v1 lifecycle stays unchanged.

Cheap source/history search found production D1
`ad06f7f3-8897-4150-b9a9-7a46a8e55b30` and R2
`moesegfault-mail-raw-production` first in source `d5a98a8` (2026-09-28).
Operations/backend docs retain coordinates but no successful provider creation
response/owned immutable run receipt was found. Held inspection explicitly
states current-only facts and no historical/old-work admission. That is not a
positive fresh-resource witness. Preserve both original stores and reject any
retained user data, migration or abandonment from this first-bootstrap lane.

## Settled interfaces and ownership

* Shared `fresh_bootstrap_contract.py`: `Epoch(source_sha, run_id, artifact_id,
  manifest_sha256, rust, worker_build="0.8.5")`; source/run derive a 24-hex suffix
  and bounded D1/R2 names. `Scope(epoch, database, database_created_at,
  bucket_created_at)` binds successful response/readback identities; original
  production and staging D1 are refused. Objects validate syntax, not authority.
* Resource worker owns `fresh_bootstrap_scope.py`: bounded no-redirect provider
  transport, complete positive name absence, each create attempted once, durable
  pre-submit recovery intent, validated create plus exact GET readback, and
  `create_scope(provider, epoch, recovery_path) -> Scope`.
  `render_configs(scope, folder) -> dict[str, Path]` maps keys `api`, `maintenance`
  to source-derived TOML; only production resource IDs/names and source-owned
  absolute main/migration paths may differ. No guessed adoption on 409/timeout,
  no token, no deletion, no rebuild, no user-controlled path/name/epoch.
* Readback/receipt worker owns `fresh_bootstrap_readback.py` and
  `fresh_bootstrap_receipt.py`. `verify(scope, pins, queue, dlq, provider) -> dict`
  pins all three fixed scripts (API/maintenance/sink) by version+deployment;
  enforces fresh bindings, held NEW DB, independent capture/surface checks,
  strict two-producer Queue/DLQ, unchanged external forwarding snapshot and both
  explicit empty schedules. `pins` starts as `{script: version_uuid}`, and the
  result is the complete v1 graph-shaped `{pins:{script:{version,deployment}},
  api_crons:[],maintenance_crons:[],topology:"api-scheduled"}`.
  `persist(scope, graph, queue, dlq, path) -> dict` emits a closed v2 paused
  first receipt only after that successful exact readback. `load(run_id)` must
  admit only successful first-attempt main ci.yml protected job
  `Fresh held production bootstrap` and immutable bounded unique artifact
  `mail-fresh-bootstrap-<run>-1` containing `receipt.json`; v1 untouched.
* Leader owns `fresh_mail_bootstrap.py`, CI target/job/source-gate/lock wiring,
  shared model and integrated docs. Controller independently verifies full same-
  run hosted source checks + original artifact identity before any provider step,
  calls existing OLD scope complete held-empty/absence/routing/send preconditions,
  provisions new scope, runs source migrations/NEW DB held-empty checks, packages
  the same generated modules once per fixed sink/paused maintenance/fetch-only API,
  exact readback, then persists first receipt. Failure persists owned recovery
  metadata, never a successful receipt or automatic retry/rollback/delete.
* Validator owns controller/workflow synthetic tests in its separate worktree;
  no local execution. Provider models/readback tests belong to their implementers.

## V2 meaning and unfinished acceptance

V2 records fresh positive creation, original same-run artifact source/run/ID/hash/
compiler, exact scope/Queue/pins and paused schedules, original stores retained,
global sending held, source adoption required, activation NOT_GRANTED.
Fresh storage proves only its isolated storage scope. Independent shared
routing/sending current writer/freeze/history preconditions must not be waived;
unknown old external work stays explicit. No active/legacy rollback command.

The initial generated deployment config is not automatically established normal
source truth. After a genuine successful protected receipt, root separately
reviews adoption of internal resource coordinates in checked-in configs/operator
targets. Public CLI/domain/Identity/ZIP contracts remain unchanged; no migration
or hash-Secret ceremony. Ordinary deployment/release remain fail-closed until
source truth matches the actual receipt-owned graph.

### First actual bootstrap refusal (2026-10-02)

Protected run [36906562887](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36906562887)
passed its source gates but stopped in old-scope inspection. The first D1 query
was `SELECT name FROM d1_migrations ORDER BY id`; it returned HTTP400, CF-Ray
`a43d8a26bf6c6bfb-DFW`, at October1 18:30:38 UTC. The provider body was not
retained, so a missing migration table is **not yet an observed fact**.
Immutable recovery artifact `11185461013` contains only admission intent/observed
and old_scope intent/failed: no fresh creation intent, scope journal or receipt.
No D1/R2/Queue/Worker creation phase was reached.

The existing inspector now lets this first-bootstrap caller read successful
complete `sqlite_master` metadata before querying the migration table. A database
with no non-platform schema objects, zero whole-bucket R2 objects, absent current
store callers and unattached product route may be retained as uninitialized old
storage. Missing policy/grant tables are not reported as held rows. Both metadata
snapshots and forwarding brackets must still agree. Nonempty unrecorded schema
and failed reads stop with safe structural reasons; recorded prefixes retain
their exact migration/held-state checks. Old stores are never migrated/deleted.
This correction permits a new changed-source initial deployment, not an unchanged
retry or an activation. Cloudflare documents [SQLite metadata inspection](https://developers.cloudflare.com/d1/sql-api/sql-statements/)
and the separate [Wrangler migration ledger](https://developers.cloudflare.com/d1/reference/migrations/).

The old-scope opaque-domain reader repair is integrated from main PR 73. It
preserves incomplete-read refusal; this source integration does not imply actual
inspection or first receipt acceptance.

## Executable source integration

`infra/deploy/fresh_mail_bootstrap.py` now implements the protected controller and
the CI `production-fresh-bootstrap` target. It verifies all original same-run
source jobs and the immutable module artifact before provider construction,
preserves old stores and owner state, creates the new epoch once, migrates only
that epoch, verifies default-held state, installs and attests the sink before the
two paused producers, then persists the closed v2 observation.

An initial bounded `preflight.jsonl` survives admission refusal before controller
creation. Append-only controller/scope intent plus the bounded Queue provisioning
receipt survive partial failure; secrets and arbitrary provider outputs do not.
All intended Worker submissions are observed during recovery, including those
whose timed-out Wrangler invocation never yielded a version. Failed recovery
reads remain UNVERIFIED, not absence. The durable read-only recovery workflow
admits the original protected run and immutable recovery archive before any
provider observation; it never replays writes, creates a success receipt, adopts
stores, activates schedules or lifts the send hold.

PR 75 source checks and independent review are ongoing. No actual production
bootstrap, new-store adoption, activation or rollback has been executed.

Runtime validation is GitHub Actions only; local AST/diff work only. Root alone
may authorize/perform provider operations. The successful future first receipt
does not establish complete product release or deployed end-to-end acceptance.
