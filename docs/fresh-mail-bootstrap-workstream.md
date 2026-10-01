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

Known old-scope inspector domain-ID debt must remain a failure, not absence or
permissions speculation. The separately preserved opaque-domain fix is not
copied into this workstream; source acceptance cannot imply that actual inspection
or first receipt will pass before that control-plane reader is repaired.

Runtime validation is GitHub Actions only; local AST/diff work only. Root alone
may authorize/perform provider operations. The successful future first receipt
does not establish complete product release or deployed end-to-end acceptance.
