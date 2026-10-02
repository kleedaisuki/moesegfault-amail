# Fresh storage bootstrap and recovery

This is an exceptional owned-storage lifecycle, not the normal deployment path.
The delivered graph and current coordinates are in [operations](operations.md).
Original stores are retained; current inventory is not historical ownership proof.
No document itself grants a new bootstrap, activation, drain or deletion.

## Protected creation

production-fresh-bootstrap admits original exact-main full hosted checks and its
immutable six-tree artifact identity before a provider call. Historical seven-tree
receipts remain readable without rebuilding the retired native tracing canary.
The source/run epoch
binds source SHA, run/attempt, artifact ID, manifest digest and compiler versions;
derived names cannot be caller-selected. Establish complete positive name absence,
persist submit intent, attempt each creation once, then capture positive response
identity and exact readback. A timeout/409/failed read is UNKNOWN, not adoption or
retry authority.

Create fresh D1/R2, apply source migrations and verify held/empty state without
inventing grants or unconditional writes that alter migration audit rows. Submit
private sink first, paused maintenance and fetch-only API from the checked artifact.
Read back pinned versions/deployments, response-owned bindings, two exact Queue
producers/one private consumer/DLQ, independent capture/public-surface checks,
empty schedules and unchanged external forwards. Only complete successful readback
emits the immutable paused receipt. It grants neither activation nor old-work drain.

Reviewed source adoption and separately protected production-fresh-online activation
are distinct transitions. Normal API replacement/rollback never restores Cron.

## Read-only interruption recovery

fresh-mail-bootstrap-recovery.yml and infra/deploy/fresh_bootstrap_recovery.py admit
the original completed main ci.yml dispatch attempt 1 and exact creator job.
Success/failure/timeout/cancellation may be observed only if all original source
gates succeeded and immutable controller/scope evidence is available. Cancellation
can interrupt artifact upload; always() is not a durability guarantee.

Verify original manifest/module hashes and closed bounded JSON/ZIP journal before
provider reads. Refuse duplicate/traversal/symlink/encrypted/oversized entries,
changed source/compiler coordinates or substituted caller receipts. Extract only
known safe records to a new repository .temp folder, never replace existing files.

Only positive original creation identities may be observed. A prefix ending at a
submit intent is valid interruption evidence, not resource existence/ownership.
Missing artifact or scope remains typed unavailable; truncated/malformed journals
are rejected. Expired artifacts are not admission. Current inventory/name equality
cannot replace creator evidence.

Recovery never creates, updates, deletes, migrates, deploys, consumes messages,
replays writes, adopts coordinates, activates, drains or emits a success receipt.
Review unknown outcomes explicitly rather than launch a replacement epoch.

References: [GitHub cancellation](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-cancellation),
[immutable artifacts](https://github.com/actions/upload-artifact),
[D1 migrations](https://developers.cloudflare.com/d1/reference/migrations/).
