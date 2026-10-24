# v0.3.0 production promotion

The owner authorized production deployment on 2026-10-25 (Asia/Singapore), after
the accepted staging delivery and real native/profile/SMTP journey documented in
[validation](../validation.md). This authorizes the matching public CLI/Skill
release, not a change to sending policy, spending consent or existing customer
data. Actual serving versions and completion receipts must be recorded after
successful provider readback.

## Accepted predecessor, not an interrupted writer

The production predecessor is completed run
[37660780530](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37660780530),
source `1c1c891ef2c20d31dfd1aa3fe7b373617aba86bd`, receipt artifact
`11501340995`. Earlier v0.2.0 API/sink interruptions are historical recovery
boundaries, not the current maintenance version.

| Role | Accepted deployment | Accepted version |
| --- | --- | --- |
| API | `45e72a6e-aca8-4c79-aaa9-5d3cee3cc884` | `8dc1268f-6947-404b-bb89-95c4f1e5cde9` |
| Maintenance | `48992383-31d6-4e35-8cdd-0d6eb0268c81` | `271e6d3f-9355-4804-b0c4-0d2426ad6c5a` |
| Trace sink | `a3e92449-7853-4d82-81af-f7014f24f44a` | `f401659a-d076-4c6a-bfe5-28d0e71698b1` |

Fresh read-only inspection must still match these exact pins, existing stores,
queues, contacts, original lifecycle subscription and current sending-policy
snapshot. Names or an old successful receipt do not replace live readback.

## Existing hosted lane

Use trusted `main`, the protected `production` environment and the existing
workflow-level production graph writer lock:

| Existing target | Confirmation | Required freeze |
| --- | --- | --- |
| `production-inspect` | `INSPECT_PRODUCTION_V030` | `FREEZE_PRODUCTION_GRAPH_WRITERS` |
| `production` | `RUN_PRODUCTION_V030` | `FREEZE_PRODUCTION_GRAPH_WRITERS` |

The freeze is the `production_graph_freeze` workflow input. Inspection is read
only. The writer requires first attempt, complete source gates and the restored,
reverified same-run Worker artifact before mutation. The historical v0.2.0 writer
remains frozen and is not used as a shortcut for this release.

## Ordered compatible replacement

1. Verify the exact accepted production graph and preserve original ownership and
   policy fingerprints. Onboard only `tmpaddr.moesegfault.dev`, using deployment
   authority and provider-generated records. Preserve unfamiliar DNS; decode TXT
   presentation without replacing a matching DKIM key or merging SPF policies.
2. Apply only compatible pending migrations 0016/0017. Preserve existing owners,
   addresses, messages, accepted/unknown send journals, paid grants, currencies,
   resource history and approved budgets. There is no initial-Free reset.
3. Replace the lifecycle consumer with its dual-domain-compatible implementation,
   then add only the exact temporary-domain subscription to the existing owned
   queue. Preserve the permanent-domain subscription and direct operator forwards.
4. Replace scheduled maintenance at its existing cadence, then replace the API
   last. This prevents newly registered temporary mail from reaching an old
   consumer or old maintenance implementation. Retain unchanged ingress and trace
   sink only with accepted pins and source-closure checks.
5. Verify actual immutable versions, private surfaces, queues/subscriptions,
   capture settings, empty API Cron and unchanged policy/ownership. Failed or
   ambiguous submissions stop with their exact captured coordinates; they are
   never automatically replayed.

Normal v0.2.0 clients remain supported for unenrolled accounts. The compatibility
repair adopts mailbox fields only for identical, validated, never-submitted
legacy `preparing` intents; original identity/holds/evidence remain intact.
Accepted, unknown and submitting records are not reset or resubmitted.

This is normal rolling compatibility, not retroactive revocation: already-admitted
v0.2 owner-authorized requests may finish under their original contract. New
profile fences apply to newly admitted v0.3 requests. No HTTP drain is inferred
from elapsed time, Cron limits or platform runtime-update grace periods.

After profile enrollment is possible, the v0.2 API is not a compatible rollback
target: it does not enforce the persisted enrollment fences. Preserve profile-
aware API semantics when deploying a corrective version. Allowing an already
admitted old request to finish is different from routing new traffic back to an
old API. This controller provides neither automatic rollback nor write replay.

## Public assets after backend readiness

Publish the five-platform v0.3.0 CLI archives, matching Skill, checksums and
attestations only after the production API reports the matching version and the
existing outbound release attestations pass. The minimum supported old client
remains v0.2/protocol 2 for unenrolled owners; there is no need to publish the new
client ahead of the backend. Public-site replacement follows verified published
asset bytes, not a candidate build or a tag alone.

## Completion

Production inspection [40116394849](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/40116394849)
and normal upgrade [40116604490](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/40116604490)
completed successfully at source `d3d913d4bf59f48790a2753bc066033b4d8cf7a6`.
Receipt artifact `12570076705` (`production-v030/v1`) preserves all 11 original
address-ownership records. The original allowed policy and its complete
fingerprint remain unchanged; retained contacts, stores, queues, ingress and sink
anchors also match their inspected fingerprint. The temporary-domain DNS and
dual-domain lifecycle subscription passed actual readback.

| Role | Production version |
| --- | --- |
| API | `0592192f-5937-445c-8c26-73ab18799bba` |
| Maintenance | `ec73a333-0fba-497f-8f38-1fceffebc122` |
| Lifecycle consumer | `c17d92ad-cbc4-4ff3-a250-724f17d5bc60` |
| Retained ingress | `5c296407-5048-43b3-aad6-ac106676e7f2` |
| Retained trace sink | `f401659a-d076-4c6a-bfe5-28d0e71698b1` |

Independent production health readback returned `status=ok`, `version=0.3.0`,
`api_version=2`. Existing sending policy was not enabled, disabled or reset by
this release. The successful receipt is the next upgrade's reviewed epoch;
advance source-owned preconditions before another writer, rather than replaying
this historical predecessor controller.

Formal CLI/Skill publication has its own backend-version, five-platform build,
checksum, attestation and public-asset/site gates. The actual public state is
available at [GitHub Releases](https://github.com/kleedaisuki/moesegfault-amail/releases)
and the latest [validation ledger](../validation.md); it is not inferred merely
from a successful backend deployment.

## Formal publication and local installation

[Release workflow 40118186853](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/40118186853)
completed successfully for immutable tag `v0.3.0`, source
`df757dd422c1e1c0845a44ae5d1d8e378ca611d1`. That source differs from the admitted
production runtime only in delivery documentation. All five native builds and
daemon/profile journeys, attestations, assembled/published asset checks and public
site smoke passed. The formal nondraft, non-prerelease
[v0.3.0 release](https://github.com/kleedaisuki/moesegfault-amail/releases/tag/v0.3.0)
was published on 2026-10-25 Asia/Singapore.

The owner explicitly requested upgrading every local amail entrypoint and the
global amail Skill. Downloaded Windows and Skill archives matched the public
manifest and their GitHub attestations; installed Skill files additionally matched
the immutable-tag source. The canonical CLI is in `~/.amail/bin`, existing PATH
entrypoints are synchronized for compatibility, and all eleven global Skill files
match the official package. Previous binaries/instructions are retained in private
versioned `.amail/backups` storage; no credentials or YOLO preference were reset.

| Verified artifact | SHA-256 |
| --- | --- |
| Windows ZIP | `a3941a52145b3ddc5c98f7792d7bde24a6a09d65bbacf9f7b893ba8989541e7a` |
| Agent Skill ZIP | `8775abc5c5c19a1f5be0138818bcf9e620a87d5ebc3d20b898b17937545f9e5a` |
| Installed Windows executable | `8011d59a5ff9ba5fe52340c79b98e50957dc639971c34ea9593560f8f04d0293` |

Local verification used only version/help/offline discovery, not production mail
access or an implicitly approved user-profile action. Backups are recovery
material, not permission to bypass enrollment or restore consumed refresh tokens.
