# Reviewed feature batch integration

Date: 2026-10-01. Base: `1a77a5034de6d7bcd7946a2e8927e984b2b91e26`,
the inspected remote `codex/amail-v0.1.0` pin. Workspace:
`.temp/feature-batch-integration`; local branch `codex/feature-batch-integration`.
This record is source integration evidence, not deployment, provider acceptance,
publication, sending authorization or permission to push.

## Immutable source inputs and reconciliation

All requested commits were cherry-picked in full without conflicts or omitted
source, tests or documentation:

| Input | Integrated commit | Scope |
| --- | --- | --- |
| `91af371` | `4c27b8e` | R2/SMTP shortest-path handoff |
| `ae46ec4` | `403aef9` | Held promotion and predecessor handoff |
| `c2f9d70` | `7a2ea18` | Pre-merge privacy review |
| `90836e1` | `e369efd` | Independent R2 source review |
| `0002e523f520253c746400c7408d138d1bdf16cd` | `f729e10` | Independent historical binding review |
| `7b707bb65cd45e844974fa149cb79fbabdc1086e` | `3d3ac75` | R2 submission/recovery truthfulness |
| `5d99147a80607b58127c0bad48adcde30c4b5c9d` | `6d126fa` | Frozen historical binding policy |
| `2b57e7d4189c30327b635b4c4ddd3458e1290910` | `f27c727` | Native D1 synthetic proof and independent review |

The quota parent `b373c35` is already an ancestor of the base. Neither its old
source chain nor any site/main reconciliation commit was re-imported.

## Integration-discovered syntax failure

Static PyYAML parsing of the new proof workflow failed at line 57, column 54:
`mapping values are not allowed here`. Its dependency-install command contained
`--only-binary=:all:` followed by a space inside an unquoted plain `run` scalar.
The YAML colon-space delimiter prevents workflow registration before any job
can start; provider preflight tests cannot repair this bootstrap failure.

The only workflow correction is a literal block scalar (`run: |`) containing
the unchanged command. A same-source regression contract now requires that
block form and rejects the exact broken plain form without adding a runtime
parser dependency. The regression source was authored, not executed locally.
Whole-document static parsing is checked separately; hosted workflow lint and
exact integrated source CI are still required before interpreting runtime
behavior. This matches the prior failure lesson recorded in
`workflow-parser-stage-guard.md` rather than weakening any proof guard.

## Preserved integration boundaries

- The historical c3f matcher is explicitly selected by historical containment
  helpers only. Current direct-only/queue-api matching has no fallback or union.
- The native D1 proof still requires the current sole `MAIL_DB` D1 identity;
  accepting the historical `ROLE_MONITOR` binding for containment does not
  authorize it for proof admission or current deployment.
- R2 submission categories and object observation remain separate. Recovery
  success still requires settled route/inventory cleanup and definite DELETE
  evidence; old empty recovery does not prove existing-object capability.
- Only the new manual D1 workflow is added. Existing CI, candidate/site lanes,
  release helpers, Worker runtime/configuration and packaged Skills are unchanged.
- No main/candidate-site synchronization is attempted here. The existing hourly
  contact-health workflow implication remains in the base review and is not
  removed or newly authorized by this batch.

## Local evidence and authorization limits

Checks are source-only: Git object/diff/status inspection, AST parsing, YAML
parsing and `git diff --check`. No local project test/build, dependency install,
workflow dispatch, provider operation, migration, mail submission, private
artifact/log/body read, deployment, tag/Release, main change or push occurred.

A bounded committed-tree pattern scan found no PEM private-key block, GitHub
token, OpenRouter token or long JWT-shaped match; only match paths would be
reported. Tracked filenames contained no ZIP/EML/private-key or
`.idea`/`.temp`/`.cache` artifacts. This is not an entropy scanner, repository
history audit, or proof that arbitrary confidential content is absent.

The primary worktree's unrelated modified test and untracked `.idea` were not
changed, staged or copied. Final integrated exact SHA, final reviewer decision,
and hosted success evidence must be recorded by the operator/root separately;
no source-only check grants live proof dispatch or releases any existing hold.
