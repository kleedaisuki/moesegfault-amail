# Independent incremental integration review

Date: 2026-10-01. Frozen candidate:
`fb046c5a005ffe6e718cbb161b685edc6dad9a84`, based on
`1a77a5034de6d7bcd7946a2e8927e984b2b91e26`. Review workspace:
`.temp/feature-batch-integration`.

## Decision

**GO for this exact incremental source integration and separately authorized
hosted source validation. No outstanding substantive integration defect was
found.** This is not authorization to merge PR #1, push, register a workflow on
main, dispatch provider operations, deploy, publish, or release sending/privacy
holds. Hosted validation of this integrated source remains required; syntax
parsing is not executed-test or provider acceptance evidence.

## Scope and reproducible checks

The review reused the independent R2, historical containment, native D1 proof
and pre-merge privacy records. It examined only their integration delta, the
YAML correction, registration documentation, shared helper callers and preserved
external boundaries, not the entire Mail PR again.

A static Git-object inventory constructed each input's changed path set and
expected blob, with later approved integration fixes taking precedence:
`91af371`, `ae46ec4`, `c2f9d70`, `90836e1`, `0002e52`, `7b707bb`,
`5d99147`, `2b57e7d`, `89dd227`, `56f636a`, and the integration-record-only
`fb046c5`. At the frozen candidate the result was:

| Check | Independently observed result |
| --- | --- |
| Expected changed paths | 28 |
| Actual base-relative changed paths | 28 |
| Missing/unexpected paths | 0 / 0 |
| Final blob mismatches to ordered input inventory | 0 |
| Site, site/candidate workflows, existing CI/Release workflows, release helpers, runtime/configuration, both Skill trees | Zero base-relative diff |
| New native D1 workflow | Static PyYAML parse succeeds; six steps; dependency command preserved exactly with trailing newline |
| Base-relative whitespace check | `git diff --check` succeeds |
| Isolated candidate status before review artifact | Clean |

The workflow parse used only `git show` bytes and the YAML parser; no project
module or test was imported or executed. No local project tests/builds,
dependency installs, private provider requests, provider mutations, dispatches,
private logs/artifacts, deployment, tags, Releases, or pushes occurred. Only
this review document is added after the frozen candidate.

## Integration contract assessment

| Boundary | Assessment |
| --- | --- |
| R2 versus quota imports | R2 changes are local submission/cleanup categorization and fixed output evidence. Shared `github_json` behavior used by quota provenance is unchanged; shared R2 transport remains unchanged. No new automatic send call is introduced. |
| Historical versus current bindings | The exact c3f historical factory/matcher is explicitly selected by old correction/containment callers. Ordinary current/queue-api matching has no fallback. The native D1 proof still requires exactly one D1 `MAIL_DB`, so accepting old `ROLE_MONITOR` for historical provenance does not admit it for new proof. |
| Escrow parser sharing | Extracted `query_result()` preserves actual nonnegative integer changes acknowledgement and tightens outer-success/row-shape rejection. It does not broaden SQL capability, permit a replay, or manufacture an Arm authority. |
| D1 proof scope | Schema mode explicitly applies additive real escrow and synthetic mirror DDL. Other modes write/read only synthetic mirror state; no purge, real-mailbox callback, address creation or mail send exists. Final held-state/schema/deployment brackets remain in place. |
| Dispatch and source provenance | New workflow is only manual, trusted feature-ref, first-attempt and staging-environment gated. Confirmation guard and secret-free tests precede its sole secrets-bearing execution step. Program checks actual checkout SHA, its own dispatch identity and exact six-job source CI before provider capability extraction. |
| Default-branch registration | `56f636a` documentation explicitly requires separately reviewed main registration before feature-ref dispatch; `--ref` is not represented as registration. Registering this path on main does not satisfy the feature-only job guard or authorize DDL. |
| Default push side effects | Existing push behavior is unchanged. No added push/schedule trigger, deploy or public-send activation appears in this delta. The baseline hourly contact-health production reads/conditional writes still exist and remain subject to the explicit warning in the pre-merge review; this batch does not authorize them anew. |
| Privacy and immutable evidence | Strict current Issues acceptance, immutable evidence markers, historical version identity and existing one-shot guards are not weakened. Historical binding success remains insufficient for capture-off acceptance or replay authority. |
| Candidate/main continuity | Site, source-state/candidate copy and generated-header publication helpers are unchanged. The delta introduces no new deployed-site SHA or publication claim and performs no main synchronization. |
| Secrets and synthetic evidence | Public fixture key and invented owner/object IDs stay in synthetic proof only; output explicitly sets `synthetic_only=true` and `real_cleanup_attested=false`. Inspected output and failure paths emit bounded synthetic metadata or fixed labels, not provider payloads, tokens, user addresses or mail bodies. Bounded credential-pattern inspection found no new credential-shaped match; it is not a history/entropy audit. |

## Integration finding resolved before this pin

The original native proof dependency command placed `--only-binary=:all:`
followed by a space inside an unquoted YAML scalar. The integration owner found
the parser-level failure before submission. `89dd227` changes only that `run`
field to a literal block scalar; the shell command remains unchanged. Its
regression-source assertion requires the block form without adding a new job
dependency. Independent parsing of the final Git object confirms registration
syntax is no longer blocked by this issue. No hosted actionlint/test result is
claimed by this review.

## Remaining operational gates

1. Obtain fresh hosted source checks for the exact source selected for remote
   submission, including the integrated shared-helper and workflow tests.
2. Separately authorize and verify main workflow registration before proposing
   any feature-ref proof dispatch. Do not confuse this source GO with registration.
3. Treat schema application as real, separately confirmed DDL. Provider ACK loss
   or schema/provenance drift can leave state and must stop for manual review;
   no blind redispatch, repair or deletion is approved.
4. Preserve the current direct-only promotion requirement, live Issues unknown
   state, missing privacy/containment evidence, SMTP/R2 acceptance and all sending
   holds. Native synthetic terminal retention does not attest real cleanup.

The exact source under assessment is the parent of this review artifact, not
an unpinned subsequent branch tip. Public-platform contract references remain
in the reused individual reviews and registration runbook; no new external
guarantee or academic result is inferred by this integration pass.
