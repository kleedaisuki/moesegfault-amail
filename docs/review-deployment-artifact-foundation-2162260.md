# Independent review: same-run ordinary deployment artifacts (2162260)

Reviewed commit `216226028293c70365c7ea573ccf5cffeac04d59` in `.temp/deployment-lifecycle-foundation` on 2026-10-01. This review is source-only: no local runtime tests/builds, provider operations, secrets inspection, deployment or merge. Read the deployment-artifact ledger, 14-file diff, surrounding producer/consumer workflows, ordinary Wrangler configurations, Mail entry adapter, helpers and new/updated hosted test contracts.

## Verdict

**No substantive blocking defect found in the reviewed change.** It materially repairs the previously identified ordinary-deployment rebuild gap while preserving the existing external workflow identities and deployment realm/confirmation contracts. Hosted source acceptance and any protected lifecycle exercise remain separate required evidence. This is not complete lifecycle acceptance or authorization to deploy Mail.

## Evidence and boundaries

| Concern | Source evidence and conclusion |
| --- | --- |
| Artifact admission | All nine ordinary Worker consumer jobs directly depend on `worker` and `worker-build`; default dependency success semantics remain. Download uses only the same-run fixed producer artifact ID. Restore compares actual SHA/run/attempt/compiler policy/bundler policy and complete hashes/file set before provider mutations. Canary ancestry reuse is not imported. |
| Post-restore verification | Mail and sink helpers additionally verify original retained manifest and installed trees before submission; Mail verifies before creating temporary secret material. Wrong source/run/attempt/compiler/bundler and changed/missing/extra installed modules have explicit hosted unit contracts. |
| Hidden build | Checked ordinary Mail/sink/ingress/events/inbox Wrangler TOMLs have no custom `[build]` command. Removed `worker-build` installation and Rust compile steps are not silently reintroduced by those configurations. The Mail entry adapter still composes the generated shim and fetch-only contract. |
| Final packaging | Wrangler remains pinned to 4.142.0 and JavaScript bundling remains enabled. The change does not prove identical uploaded module bytes or complete final module discovery. Its ledger explicitly marks that limit rather than silently claiming equivalence; this is necessary remaining foundation evidence, not a newly introduced regression. |
| Secrets | Existing job-level provider credentials remain available before restore, unchanged by this slice. Therefore the stronger claim is verification before provider mutation and before Mail secret-file creation, not capability-free consumer setup. Existing protected environment ownership is preserved. No new secret store or manual hash-secret ceremony was introduced. |
| Writer/readback | Existing workflow production graph lock, staging serialized dependency chain, resource/privacy/held-send checks and post-submit version readbacks remain. No schedule enablement, time-based drain assumption, automatic rollback or retry is added. |
| Ambiguous failure | `worker_deploy_result.submit` submits once with timeout, captures only typed exit/version/reason facts and refuses duplicate/missing UUIDs or oversized output. A unique version on failing exit is recovery metadata only; failed steps and dependent jobs remain failed/skipped. Timeout is ambiguous and does not mine incomplete output for a presumed serving pin. |
| User-facing contracts | Default Mail target remains production/main-only; staging requires explicit target, branch, confirmation and bindings. Command flags, secret file cleanup and success/failure exit conventions are preserved. Sink now retains a failure UUID, explicitly marked recovery, without making the deployment successful. |
| Release compiler | Release still tests/builds each existing platform and assembles fixed archives without rebuilding in publish. It no longer mutates unrelated floating stable; checked-in exact toolchain remains the selected compiler. No existing archive/platform/publication verification contract was removed. |

## Required next evidence, not speculative findings

1. Hosted full source CI must validate the helper tests, workflow parser and native-tested producer. PR checks cannot exercise protected deployment consumers, and source-string workflow assertions cannot prove those job executions.
2. Complete final packaging proof on a credential-free hosted runner: run pinned Wrangler dry-run packaging against each relevant configuration/realm, retain the actual emitted module inventory and hashes, verify Wasm identity and exact module resolution, and run the final packaged entry/module tree through suitable native fixtures. Include composed Mail API entry, sink, ingress/events and private inbox. Account for compatibility/config-dependent wrappers rather than assuming one generated shim hash proves all uploads.
3. Any later actual lifecycle exercise needs separately admitted writer ownership, exact serving/readback evidence and bounded recovery. A printed UUID and green source/native tests are not paused/active, drain, rollback or deployed privacy acceptance.

Do not add `--no-bundle` blindly: it changes dependency/module discovery requirements. Either verify existing deterministic packaging as an explicit tested stage or adopt prepackaging/no-bundle only with exact composed-entry/module tests. The current documentation appropriately leaves this work open.

## Primary references

* [Cloudflare Wrangler bundling](https://developers.cloudflare.com/workers/wrangler/bundling/) — Wrangler bundles JavaScript by default; dry-run output and no-bundle are distinct packaging choices.
* [Cloudflare Worker rollbacks](https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/) — old code deployment is not resource/data/schema rollback.
* [GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax) — dependency success ordering and explicit failure/skip handling.

No research novelty is needed for this slice: immutable same-run artifacts and the platform dependency graph are the appropriate production foundations. More advanced lifecycle inference should wait for correct explicit serving and recovery records.
