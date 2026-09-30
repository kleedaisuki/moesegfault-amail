# Independent review: direct-only production graph, f62a1d9

Date: 2026-10-01. Reviewed commit:
`f62a1d99e055334f2be25bfb17097715398a4d4e`, together with the
`09f7921` Mail configuration and prior topology review F1.

## Decision

**GO for hosted source-only checks on the coherent direct-only candidate.**
This is a static review decision permitting evidence collection, not a claim
that tests passed. **Prior topology F1 is closed at the source level** by the
committed pin correction and meaningful resource-identity tests.

No substantive defect was found in the five-file source delta within this
review's scope. **NO-GO to treat f62a1d9 alone as an integrated deployment or
release candidate:** its committed workflow callers still select the old
maintenance and role-bootstrap graph contracts. Workflow reconciliation and
runtime/SQL/operator acceptance remain separate prerequisites. Uncommitted
companion edits observed in the shared worktree are not certified here.

This review grants no deployment, provider mutation, contact adoption, human
attestation, public-send authorization, or mailbox access. No local tests or
builds, provider API calls, Wrangler commands, migrations, or sends were run.
Only source inspection, public documentation retrieval and this review artifact
were performed.

## F1 resolution and exact resource contract

`pin_staging_mail.py::expected_bindings` no longer indexes a nonexistent second
D1 entry. `mail_resources` requires exactly one dictionary entry named `MAIL_DB`
and one named `MAIL_BODIES`, validates database UUID shape and a nonempty bucket
name, and rejects missing, extra, duplicate or renamed resource entries.

The actual immutable binding set must equal the full reviewed allowlist:
binding count, unique names, binding kinds, Mail database UUID, bucket name,
plain-text variables, official sender restriction, and Queue ID are checked.
`ROLE_MONITOR` is not an optional extra. The `queue-api` phase independently
requires the exact realm producer declaration and reviewed Queue ID. Existing
pre-Queue callers retain a strict no-Queue set, not an optional-bindings policy.

`ResourceConfigTests.test_single_mail_d1_preserves_each_established_database_identity`
now explicitly asserts production `ad06f7f3-8897-4150-b9a9-7a46a8e55b30` and
staging `74f35f95-42ce-482c-86e6-dffbdd35cbbe`. This also resolves the prior
review's optional observation that separation alone would accept two wrong IDs.
The old `test_pin_staging_mail.py::bindings` fixture uses the corrected function;
its concrete `IndexError` failure path is removed by inspection. Hosted execution
is still needed to establish actual suite success.

## Active graph and hold assessment

| Contract | Source evidence and assessment |
| --- | --- |
| Explicit lifecycle | `prepare` accepts only bootstrap or api-only-maintenance, checks main branch, writer-freeze statement and exact confirmation before graph preparation. No provider-state auto-selection occurs. |
| Bootstrap dependencies | Reviewed Mail resource config, held Mail policy, complete successful API/role absence inventory and unchanged verified direct forwards; removed isolated role schema/storage call. Existing sink recovery remains subject to the separate exact Queue checker. |
| Maintenance/post-bootstrap graph | `verify("api-only", "replacement")` routes to one direct checker, rejects role migration flags and rejects nonempty role version/nonzero role-routed input. |
| Serving identity | API and sink UUID pins are required; `serving` requires one 100-percent version and preserves deployment IDs around the observations. Immutable API bindings are checked against the exact production contract. |
| Queue ownership | Both passes use readback/api-only. Existing `ensure_trace_queues.reconcile` pins name-to-ID inventory and details, rejects missing queues, requires distinct IDs, sole API producer, one exact private sink consumer and no DLQ producer/consumer. No arbitrary or role producer is accepted. |
| Privacy | API and sink capture checks are independent. Existing sink isolation verification remains delegated to the privacy checker; this change does not replace it with a generic success flag. |
| Role independence | Active checker does not call `storage` or `role_capabilities`, read isolated D1, install a role Worker, require its serving pin or import a lease. A complete successful inventory must prove the production role Worker absent, twice. |
| Public-send preservation | `held_send` checks global held and unset contact gate before and after the active graph checks. Neither changed script writes an allow, attestation, lease or health record. All user/account/recipient protections remain outside this observational graph probe and are not modified. |
| Four forwards | Full private snapshots require a verified destination, exact four role shapes and rule identity; the final snapshot must match. No routing mutation, replay, destination disclosure or contact adoption occurs. |

The observation brackets detect drift that persists to the final read, not a
transaction across Cloudflare and D1. They cannot prove that nothing changed
and changed back between observations. Writer freeze, separately scoped
rollout authority, final serving evidence and the retained privacy/release
requirements remain important. This limitation is documented and is not a new
defect introduced by this delta.

Historical `before`, `after` and `maintenance` checker branches still retain
role storage logic. Their existence is compatible with the architecture's
permission to preserve separately scoped research; an active v0.1 workflow
must never select them implicitly. Removal of the API binding is not deletion
or retirement of isolated role data or staging resources.

## Workflow integration boundary

At the exact reviewed commit, `.github/workflows/ci.yml` still calls
`prepare_production_graph.py --phase api-role-maintenance`, which the new CLI
rejects, and uses `check_production_role_graph.py --phase maintenance` or
`--phase before --lifecycle first-bootstrap`, which retain the old dependencies.
Thus the source gate changes must ship with reviewed workflow caller and
workflow-test changes. This is an established integration prerequisite, not
evidence that the new api-only checker opens sends or should accept legacy
inputs. Preserve fail-closed rejection; do not add an alias that revives the
old topology merely to satisfy a stale caller.

## Test assessment and review limits

The added suite keeps the real immutable binding comparison while mocking
transports and independent guards. It checks wrong Mail IDs, extra role binding,
bad pins/topology, role inputs, independent privacy failures, Queue/role-absence/
held guard failures, serving/forward drift, forbidden migration lifecycle,
maintenance dispatch and bootstrap's absence of role storage dependencies.
Named-resource tests cover malformed UUID and missing/duplicate/renamed entries.

Those are useful composition tests, not independent proofs of mocked guards.
Queue detail/inventory, forwarding audit, deployment parser, privacy surfaces
and Mail held-state semantics require their existing independent suites and
hosted real readback. New bootstrap tests mock successful absence/forward
proofs; they do not establish live inventory completeness or receipt outcomes.
This review does not certify SQL migration, runtime admission race behavior,
operator writes, direct health scheduling, release attestation or concurrent
workflow edits. No test result was fabricated from inspection.

## External grounding

[Cloudflare Wrangler configuration](https://developers.cloudflare.com/workers/wrangler/configuration/)
documents environment-specific non-inheritable bindings. The explicit realm
allowlists are consistent with that capability boundary; no role storage
retirement follows merely from removing API access.
[Queue configuration](https://developers.cloudflare.com/queues/configuration/configure-queues/)
distinguishes producer bindings from consumer configuration, supporting the
decision to check both rather than accepting API configuration alone as graph
proof.

[Huang et al., Gray Failure, HotOS 2017](https://www.microsoft.com/en-us/research/publication/gray-failure-achilles-heel-cloud-scale-systems/)
provides a relevant systems-research distinction between component health and
application-observed outcomes. Here successful configuration checks cannot
establish human Inbox/Junk review or effective response. This is an explanatory
connection, not a new contact-monitoring requirement or speculative redesign.

Internal basis: [direct-only architecture decision](direct-forward-role-release-gate-architecture.md#complexity-decision-v01-is-direct-forward-only),
[held deployment contract](direct-forward-api-deployment.md),
and [prior topology review](review-direct-forward-api-topology-09f7921.md).
