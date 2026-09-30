# Independent review: hosted quota phase composition

Date: 2026-10-01
Reviewed commit: `c0ae04be6b6f6c8d8d6b2a630d9f7f78b5c816d6`.

## Decision and scope

**GO for hosted source-only checks. Live quota and recovery dispatch remain
NO-GO. No substantive defect found in the reviewed composition increment.**

Compared the commit with `staging-ten-address-hosted-acceptance-design.md`, the
prior native, readback, service-admission and binary-artifact reviews, and the
actual controller/manifest/native/artifact implementations. Inspected the new
synthetic composition tests and serving-check fixtures. No local tests, build,
executable harness invocation, provider requests, artifact downloads, account
or alias operations, SMTP, or deployment were performed. Public documentation
was consulted only to confirm the version/binding model. Unrelated concurrent
worktree changes are outside this review and were not staged.

This decision permits obtaining hosted synthetic evidence; it is not evidence
that those tests passed, that a deployed provider accepts the observed API
shapes, or that the ten-address quota/cleanup campaign ran.

## Boundary assessment

| Boundary | Static evidence and assessment |
| --- | --- |
| Execution authorization | `environment` rejects non-hosted/non-Windows, wrong repository/ref/event/environment/confirmation, and attempts other than 1 before consuming private capabilities. `checkout` compares actual full Git HEAD with `GITHUB_SHA`; `dispatch_record` independently binds the current in-progress manual run to the exact intended standalone workflow path, repository, branch, SHA and attempt. The workflow is not registered by this increment. |
| Source authorization | `successful_source` executes before binary download/native authentication. It independently requires completed successful attempt-1 push CI at the exact current SHA, all six actual named jobs, and the executed real encryption step. A green unrelated run or operator-provided pass flag cannot replace those observations. |
| Native binary | The fresh owned `.temp/ten-address-hosted-*` directory receives only `Artifacts.binary` output. The reused reader selects the single exact SHA-named Windows artifact, binds its run/SHA metadata, checks the actual downloaded ZIP SHA-256, rereads metadata, and exclusively writes the one `amail.exe` entry. No caller path, checkout executable, cache fallback or shell extraction enters native login. |
| Hold and service relation | `Services` is constructed with the bound `reader.sending_state` method, not a literal-held lambda. Initial reads validate version-scoped staging resource bindings and two equal Mail/Identity/Login serving relations. Each adapter pin recheck reads actual held D1 policy before/after and all three single-100% serving versions. Observed relation/hold drift fails rather than supplying a new accepted pin. |
| Effective capture-off | `mail_pin.run == match` is independently required before fresh login/campaign/recovery, in addition to service bindings. Successful campaign and recovery then require a second complete effective privacy check before returning outcome labels. Matching immutable binding IDs alone is not treated as capture-off evidence. |
| Prepare and durable readback | Prepare receives neither add nor delete capability; it seals the real complete baseline and creates one new exact ciphertext path with exclusive creation. Campaign downloads the supplied exact immutable artifact ID from the original run/SHA, authenticates the envelope, and compares it with the original local ciphertext through `hosted.campaign` before the first add. No artifact lookup by ambiguous name or substitute local manifest is used. Upload remains outside this module and must precede campaign. |
| Recovery identity | Recovery independently reads original manual attempt-1 run metadata, downloads the exact supplied artifact ID, authenticates the original run/key-generation envelope, and compares manifest checkout with original run SHA. Original Mail/Identity/Login pins must still match. Fresh native verified A binding must equal the sealed owner and username. No operator alias or owner selector is accepted. |
| Recovery capabilities | Recovery can proceed without a surviving local prepare file. Its adapter add callback is an explicit always-failing function; only manifest-eligible supported CLI deletes reach the controller. The current reviewed source/binary can differ from the original source while original manifest/artifact coordinates remain unchanged; this preserves the supported DELETE contract rather than depending on expired original binary artifacts. |
| Polling and ambiguity | Activation polls candidate D1 allocations without add replay, requires allocations to exist, and uses a bounded deadline. Exact prefix, owner API, unrelated rows/rules/R2 and serving/hold observations remain enforced by the controller before a campaign claim. Ambiguous add results enter full-manifest reconciliation. Drift or unresolved cleanup prevents success, not broader deletion authority. |
| Privacy and local ownership | Secrets are removed from inherited environment before subprocess use; the reviewed native adapter supplies its restricted CLI environment. Raw provider/CLI outputs remain private. The executable emits fixed outcome labels or a fixed failure label, not exception strings. Fresh native session and binary scratch directories are cleaned through their owned-path guards. The encrypted prepared manifest deliberately survives for upload/recovery. |

## Why the lighter pin recheck is coherent

The new `Services.check` retains initial binding admission but does not refetch
the same version bodies around every CLI observation. Cloudflare documents a
version as capturing Worker code, assets, bindings and compatibility settings,
and a deployment as selecting serving version(s):
[Versions and deployments](https://developers.cloudflare.com/workers/versions-and-deployments/).
Consequently, comparing all originally admitted immutable serving IDs is the
appropriate repeated relation check, while mutable effective observability
settings retain their separate full before/after check. This is not a distributed
transaction, deployment lock, or proof of no transient changes between reads.

## Synthetic evidence adequacy and limits

The new composition fixtures run the real prepare/campaign/recover controller
with synthetic authenticated envelopes while replacing all provider, browser,
GitHub and subprocess capabilities. They cover prepare without mutation, same
ciphertext campaign with ten creations and cleanup, independent-run recovery
without local ciphertext or add capability, capture-off admission failure,
local/download ciphertext mismatch, missing activation allocation, and current
manual-run path/event/status/SHA/attempt rejection. The callback-identity
assertion directly verifies that service hold admission receives D1 readback.
The added service fixture verifies three deployment-only pin reads and rejects
an expected-pin mismatch. Earlier primitive fixtures remain responsible for
real cipher integration, archive/digest transport, native authentication,
complete inventory semantics and controller cancellation/drift behavior.

These are sufficient to justify the next hosted source-only check, not actual
native/provider integration. In particular, the test named for activation
"missing rows and timeout" only exercises missing rows in this increment;
timeout is visibly bounded in source but its new wrapper path is not directly
exercised by that fixture. This is a coverage limit, not evidence of an unbounded
loop or a replay defect.

The post-operation effective privacy checks occur after successful
`hosted.campaign`/`hosted.recover` returns. A controller failure or cooperative
interrupt can execute controller cleanup and native teardown without reaching
that second wrapper readback. Such paths report no quota/recovery success, so
they cannot falsely satisfy the accepted-result gate. Do not describe every
failed/cancelled run as having a completed post-run privacy attestation. The
future workflow's failure/finally controls should obtain a bounded independent
post-run check where execution survives; hard runner termination still needs
external original-artifact recovery. No in-process `finally` can prove cleanup
after process kill.

## Remaining live blockers

1. Hosted source checks must pass on a containing exact SHA, including this
   composition, all primitive contracts and pinned real AES-GCM integration;
   earlier source results do not cover this increment.
2. Independently review the standalone workflow, protected staging Environment,
   literal confirmations, exact source-run selection, least-privilege token
   placement, pinned immutable upload action and returned exact artifact ID.
   Upload must finish successfully before any campaign add capability is used.
3. Retain encrypted original-run artifacts and the protected recovery key
   generation according to the design. Configure the key rather than allowing
   a new secret/generation to replace an unresolved campaign's recovery context.
4. Review concurrency exclusion with deployment jobs, no retry/replay on
   failure, failure/cancellation controls, and independent original-artifact
   recovery dispatch. A job lock does not stop manual deploys or Cron.
5. Establish current live native A authentication, complete staging D1/provider/
   mail-R2 LIST observations, effective privacy, actual held policy, version pins
   and capacity gates. This source review grants no override for a missing or
   drifting observation and no SMTP/account/verification transport capability.

The quota path still cannot establish cross-owner mailbox isolation, which
remains an independent acceptance path.
