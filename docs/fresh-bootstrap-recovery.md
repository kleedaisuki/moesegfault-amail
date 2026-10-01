# Protected fresh-bootstrap recovery admission

`infra/deploy/fresh_bootstrap_recovery.py` admits a prior immutable creator artifact
before the existing controller performs read-only recovery. It never creates,
updates, deletes, migrates, deploys, consumes Queue messages, or grants activation.

## Contract

`load(run_id, folder) -> (Epoch, controller_path)` requires a completed main
`ci.yml` workflow-dispatch attempt 1 and exactly one completed **Fresh held
production bootstrap** job. Success, failure, timeout and cancellation are
admissible: a stopped writer can already have performed real writes. A terminal
cancelled conclusion grants no evidence exemption. Skipped, unfinished, arbitrary PR,
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
An absent immutable recovery artifact is `fresh_recovery_artifact_unavailable`;
a scope-creation intent without its original scope journal is
`fresh_recovery_scope_unavailable`. Truncated JSON and malformed sequence/identity
prefixes are rejected without extraction or provider reads. A complete sequence
prefix ending at a submit intent is valid interruption evidence, not proof of
the corresponding resource's existence or ownership. Only identities captured
from original positive creation responses may be observed; the rest stay UNKNOWN.

Cancellation can interrupt upload itself; `if: always()` does not promise durable
artifacts after a force-stop or runner loss. Missing evidence remains unresolved,
not a retry/recreate/adopt invitation. Expired artifacts remain outside this
bounded admission. Any later source-coordinate adoption requires its own reviewed
protected operation; current inventory cannot replace the creator's evidence.

Only after all checks pass is an absent folder under this repository's `.temp`
created, with exclusive private files. Existing destinations are never replaced.
The caller constructs the existing `Bootstrap` with the returned epoch and path
and an unused receipt target. Recovery observes coordinates; it does not grant
write replay, successful receipt, adoption, activation or old-work drain.

## Verification scope

The focused synthetic tests are intended for GitHub Actions, not the developer's
machine. They cover failed / timed-out / cancelled origins, provenance substitution,
incomplete source gates, hostile ZIP / JSON, byte corruption, closed optional
receipts and once-only owned extraction. No local runtime test was performed.
Actual recovery workflow execution remains a separate hosted integration step.

The cancellation fixture crosses the actual loader/controller boundary: a
cancelled creator with original passing source gates and immutable controller +
scope evidence produces exactly one known-D1 GET, keeps an ambiguous R2 submit
UNKNOWN, and grants no receipt, replay, adoption or activation. Missing recovery
artifacts, incomplete admission, missing scope, truncated/malformed scope bytes
and cancelled/incomplete prerequisites are negative hosted fixtures. This is
synthetic acceptance, not actual Cloudflare recovery or bootstrap readiness.

## Platform references

* [GitHub workflow cancellation](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-cancellation):
  cancellation interrupts running entry processes and can terminate remaining work;
  a terminal cancellation cannot establish whether a prior remote write committed.
* [Immutable upload-artifact v4](https://github.com/actions/upload-artifact):
  uploaded immutable artifact IDs are retained evidence, but retention expiry and
  interrupted uploads do not supply indefinite crash recovery.
