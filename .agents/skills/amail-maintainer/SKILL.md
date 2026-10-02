---
name: amail-maintainer
description: Maintain amail builds, deployments and mail operations. Use for repository/service maintenance, not ordinary user mail.
---

# amail maintenance

Read docs/operations.md for the active topology/lane and docs/validation.md for
delivered evidence and limits. Filenames identify the relevant contract; Git
history is the archive, not another executable runbook. This skill grants no
additional provider, mail, account, secret, deployment or send authority.

* Build once in hosted CI, run its small product-contract checks and restore the
  checked same-run artifact before mutation. See docs/deployment-artifact-foundation.md.
  Cache hits/native-only passes are not release admission.
* Preserve fetch-only API empty Cron, scheduled-only maintenance, exact Queue
  ownership, realm isolation, direct contacts and backward-compatible clients.
* Use the existing writer lock and explicit workflow confirmation. A lost watch,
  timeout or failed read never authorizes replay or establishes resource absence.
  Fresh bootstrap/recovery is exceptional: docs/fresh-mail-bootstrap-workstream.md.
* Hold new sending first for an applicable incident; preserve accepted/unknown
  journals, additive migrations and queued evidence. Do not purge stores/queues or
  resend unknown provider submissions. docs/outbound-abuse-operations.md and
  docs/operator-intake.md define policy/contact operations.
* Read bounded typed journals before building new diagnostics. Credentials/mail/
  private destinations/provider prose never enter public logs or artifacts.
  docs/runtime-observability-foundation.md separates correlation from native traces.

Runtime/cross-platform checks belong in GitHub Actions, not heavy local toolchain
setup. Static syntax/link/diff checks are fine; scratch files stay under root
.temp/.cache. Use one existing run watch or bounded snapshots, not repeated dispatch.

Maintain a small static test set tied to product invariants and concrete failures.
No per-task audit ledger, test-of-test framework or incident workflow by default.
Update existing canonical knowledge when semantics change; delete unused experiments
instead of defending their machinery. For user mailbox actions use the amail skill,
not direct D1/R2 edits, infrastructure credentials or a web inbox.
