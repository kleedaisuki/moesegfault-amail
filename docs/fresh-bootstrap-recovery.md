# Protected fresh-bootstrap recovery admission

`infra/deploy/fresh_bootstrap_recovery.py` admits a prior immutable creator artifact
before the existing controller performs read-only recovery. It never creates,
updates, deletes, migrates, deploys, consumes Queue messages, or grants activation.

## Contract

`load(run_id, folder) -> (Epoch, controller_path)` requires a completed main
`ci.yml` workflow-dispatch attempt 1 and exactly one completed **Fresh held
production bootstrap** job. Success, failure and timeout are admissible: a failed
writer can already have performed real writes. Skipped, cancelled, arbitrary PR,
wrong-workflow and rerun origins are refused. Every original full source gate
must nevertheless have succeeded.

The recovery artifact name is fixed by the original run. Only flat known journal
and Queue-receipt names are accepted. ZIP duplicates, traversal, symlinks,
encryption, expansion overflow and oversized metadata are refused. JSON schemas
are closed; duplicate keys, free-form provider output and private payload fields
are never copied to disk.

The controller's admission intent **and observed** records must precede recovery.
Its epoch binds the original source SHA, run, immutable worker artifact ID,
manifest digest and exact Rust / worker-build versions. The original downloaded
seven-tree artifact manifest and every module hash are verified; caller JSON
cannot substitute for those coordinates. Early failures with no controller or
without positive admission remain typed unavailable, not provider absence.

Only after all checks pass is an absent folder under this repository's `.temp`
created, with exclusive private files. Existing destinations are never replaced.
The caller constructs the existing `Bootstrap` with the returned epoch and path
and an unused receipt target. Recovery observes coordinates; it does not grant
write replay, successful receipt, adoption, activation or old-work drain.

## Verification scope

The focused synthetic tests are intended for GitHub Actions, not the developer's
machine. They cover failed / timed-out origins, provenance substitution,
incomplete source gates, hostile ZIP / JSON, byte corruption, closed optional
receipts and once-only owned extraction. No local runtime test was performed.
Actual recovery workflow execution remains a separate hosted integration step.
