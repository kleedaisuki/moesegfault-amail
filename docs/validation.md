# Product validation and release status

This is the single current acceptance ledger. Historical reviews/experiments are
in Git history, not competing current-state documents. Evidence recorded on
2026-10-02 is not a fresh inventory or permission to repeat production actions.

## Delivered v0.1.2 — current release

### Delivered v0.2.0 staging — fixed USD deployed; final mail recheck pending

The owner subsequently approved fixed USD tariffs: Free0, Lite1.50, Plus4.50
per month; overage0.001/recipient,0.15/GB-month,0.50/address-month. Currency
cutover is tracked in `v0.2.0/usd-cutover.md`; earlier CNY evidence below is not
reinterpreted as USD acceptance. Current local full infra suite233tests PASS.

Actual USD deployments passed: Mail source `27c5818` in
[37642433233](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37642433233),
and Billing/Subscribe source `86bb06e` in
[37641220454](https://github.com/kleedaisuki/moesegfault-subscriptions/actions/runs/37641220454).
Applied additive migrations0015/0006 preserve original CNY history, included
resource counters, existing addresses and paid grants. CNY consent does not
authorize USD spending. Current versions are recorded in `v0.2.0/usd-cutover.md`.

The real USD financial/trace portion of
[37644087065](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37644087065)
passed: normal browser USD approval, existing Lite grant, 14 actual excess
address-seconds, 2 USD micros acknowledged in two events through normal Cron,
all four meter addresses retired and budget restored zero. Separate historical
reads still returned exactly 6 CNY events / 22 CNY micros. Safe artifact
`11494520444` proves ordinary14-span and charged-origin18-span ancestry plus
one separately retained scheduled root. This is liability, not automatic payment.
The later mail probe failed on its obsolete CNY status assertion. The helper-only
correction at `aae6029` requires USD and rejects CNY; the remaining ordinary
mail/self-send acceptance must not repeat charged usage.

#### Historical CNY baseline and preceding delivery

The owner requested Billing integration and staging delivery on 2026-10-07, not
production publication. Candidate branch `codex/v0.2.0-billing` starts at
`b07646e04f1337b482011d63e0aeb40a9202c738`; coordinated Billing/Subscribe source is
`c77b7ddf19d64e5c71c281fd378cfb774d19a559` on
`codex/amail-v0.2.0-integration` in the subscriptions repository.

Hosted initial checks: [Mail 37614032629](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37614032629)
and [Billing 37614622042](https://github.com/kleedaisuki/moesegfault-subscriptions/actions/runs/37614622042).
The initial Mail run compiled native/Wasm and passed all CLI platforms plus
119/124 workerd cases, including the new Billing/outbox scenarios. Five legacy
HTTP/Cron races failed because their test barrier assumed D1 `meta.changes == 1`;
new atomic accounting triggers legitimately increase aggregate changes. The
fixture now checks the exact committed owner/key/provider transition instead,
without weakening interleaving, lease, deletion or GC assertions. Actual SQL
regressions distinguish top-level changes from trigger-inclusive total changes.

The initial Billing run passed Rust/Wasm and domain/frontend contracts but failed
the existing audit gate on newly reported `sharp < 0.35.5`. The targeted patched
override retains Wrangler and the audit gate. The subsequent Billing staging
delivery [37615238720](https://github.com/kleedaisuki/moesegfault-subscriptions/actions/runs/37615238720)
stopped on D1 migration parsing. Remote readback proved that the new tables had
not committed. Removing an ambiguous trigger CASE boundary preserved the same
contract; [37616090490](https://github.com/kleedaisuki/moesegfault-subscriptions/actions/runs/37616090490)
then successfully deployed Billing and Subscribe to staging from `3e2c4e8`.
The explicit staging Issues-capture disable patch deployed both new runtime
versions in [37617117905](https://github.com/kleedaisuki/moesegfault-subscriptions/actions/runs/37617117905),
then the workflow failed at an overly strict settings checker. No writer was
replayed: independent pure-read [37618095870](https://github.com/kleedaisuki/moesegfault-subscriptions/actions/runs/37618095870)
accepted those same serving versions under documented opt-in Issues/default-off
and disabled-Logs semantics. See the integration contract for exact safe flags.

Mail [37615319193](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37615319193)
passed the complete compiled/native/workerd/site gates at `00acf56`, including
the repaired interleaving and actual Queue trace cases, but stopped before the
first provider mutator: reviewed staging Queue ownership variables were missing.
Bounded inspection matched the exact source-owned predecessor graph. Those two
independently reviewed Queue/DLQ IDs are now provisioned and read back in GitHub's
staging environment. A focused regression preserves refusal when pins are absent;
no observed-ID fallback was introduced.

The next exact-source staging delivery
[37617246563](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37617246563)
completed successfully at source `938de595d48bae302b23e86fed1b1a1f0435b26a`.
Its credential-free compiled/native/workerd/site gates, immutable artifact restore,
additive D1 migrations, private sink, API/maintenance and retained adapter
readbacks all passed. Actual serving versions are API
`1f4a056f-5342-46a5-8e32-7eebaea5f7a2`, maintenance
`5281d8ef-f3c0-42d4-8331-bafa01923b40`, trace sink
`56c17824-679f-4427-bcc9-4584d2510208`, and staging site
`2312f7e5-b54b-4def-8a52-a78aacaf9db4`.

Independent live migration reads before/after the writer proved the same complete
15-address tuple set (zero missing/changed/new records), one resource owner with
exact Free defaults and no variable-spend consent. All baseline addresses were
already retired; ten-active-address grandfathering is separately covered by the
real migration SQL fixture, not claimed as populated live staging evidence.
Direct unauthenticated staging HTTP probes returned 426/required_client_version
for missing and old headers, and 401 for the current header without credentials.
The helper-only acceptance source repairs
return-path normalization, existing paid-grant recovery without reusing one-use
codes, and safe actionable retained-trace diagnostics. These changes do not alter
the deployed runtime. Exact-source producer
[37620361945](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37620361945)
passed at `de427af16097eff247ec33b831c829de89b56890`; its unpublished CLI/Skill
bundle is artifact `11482156851`.

The intended contract is Free/Lite/Plus, free incoming mail, no retained-message
count or per-account semantic-query quota, byte/address/outbound metering, human
browser consent, and unchanged Identity sectors. Existing addresses are preserved
on Free. HTTP producers keep provider capture off; private Mail Queue records and
typed Billing/Subscribe D1 spans provide content-free retention. Billing's existing
activation grants plus usage accrual do not constitute monetary collection.

Staging runtime deployment, migration, browser acceptance and retained end-to-end
tracing are accepted. The delivered public release and production runtime remain
v0.1.2. A single legitimate staging Lite issuance
was retrieved from the explicitly authorized owned mailbox through ordinary
amail search/ZIP operations and passed privately into the protected test secret;
no raw capability appeared in logs/artifacts or an agent context. First Lite
browser acceptance in [37619968691](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37619968691)
redeemed it, completed human approval and authoritative CLI projection; that
workflow later failed at a legitimate stale search snapshot. A fixed read-only
issuance/redemption join independently confirmed exactly one redemption, and the
temporary GitHub test secret was deleted. The harness now explicitly restarts
only classified stale first-page searches, retaining all original positive and
negative oracles and never retrying sends or unknown failures.

The subsequent complete native/browser/mail/trace journey
[37621170985](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37621170985)
finished **successfully**, using exact admitted `de427af` candidate bytes:

| Accepted boundary | Actual evidence |
| --- | --- |
| Human subscription | Cancellation, fresh approval, actual return-link navigation, CLI completed receipt and Lite status; `grant_source=existing`, no second code redemption |
| Retained cross-service tracing | Artifact `11482721812`: 14 validated persisted spans, CLI retained, human authorization retained, actual CLI → Mail → Billing and Subscribe approval ancestry |
| Inbound/archive/search | Real two-SMTP fixtures, ZIP/body/asset/receipt equality, reply relations, composed positive and discriminating negative searches, explicit read-state/delete behavior |
| Controlled outgoing delivery | One self-only held-policy send, lost-stdout receipt recovery, exact same-key replay, real delivered feedback/event and inbound archive, no second provider submission |
| Cleanup | Exact task-owned address/route retirement and no primary/cleanup error; unrelated mail and journals retained |

The latest local helper-only suite passes 227 infrastructure tests. An additional
explicitly opted-in real address-overage/normal-Cron/Billing-ledger acceptance is
executed in [37625486364](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37625486364)
from `9e91fa1`, but failed with `billing_metering_event_not_delivered`. The helper
completed independent mandatory task-address retirement and zero-budget restoration
before entering that failed delivery poll. Source diagnosis found that the real
scheduled Worker config omitted `IDENTITY_ISSUER`, required by the Billing bridge;
the native outbox fixture supplied that variable manually and masked the mismatch.
A staging-only correction and config-derived positive/negative native regression
passed in [37628266417](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37628266417),
source `d1291b80923d7d463e596bcd702a6e251039797f`. Only maintenance was replaced,
now serving `eb38afe1-51fe-4d6b-8e82-661b5932dcbf`; API/sink deployment identities,
queue graph, held send policy and five-minute cadence were bracketed unchanged.
Artifact `11485846948` records the safe repair evidence. Read-only diagnosis
[37627785234](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37627785234)
proved zero remaining addresses/budget and exactly 15 micros of pending local
liability. Post-repair [37629415153](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37629415153)
read three preserved events at attempt three, due after 13:50:40 UTC; the existing
Cron/backoff, not a database edit or manual scheduler, subsequently delivered them.
The final complete acceptance
[37630962022](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37630962022)
finished **SUCCESS** from exact `d1291b8` candidate bytes admitted through
[37628260838](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37628260838).
The latest unpublished CLI/Skill bundle is artifact `11485896406`; safe hosted
evidence is artifact `11486684051`. All earlier native/browser/mail/send recovery
oracles passed again, including exact task address/route cleanup.

| Final extra boundary | Actual accepted result |
| --- | --- |
| Real address overage | Four task addresses created/retired, 7 excess address-seconds, 7 CNY micros newly accrued |
| Historical backlog | Six period events delivered, including all three preserved first-run events; final Mail/Billing totals both 22 CNY micros |
| Consent restoration | Normal Manage UI returned budget to zero before delivery polling; authoritative Billing summary also reported zero |
| Human and CLI ancestry | 14 retained spans in the ordinary subscription witness; existing Lite grant, no code reuse |
| Actual asynchronous ancestry | 20 retained spans on the charged origin, real successful maintenance client → Billing usage server, linked to one exact separately retained scheduled root |
| Settlement meaning | `pending_settlement`, `payment_collection_verified=false`; no payment processor or automatic debit |

Final fixed readback
[37634410400](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37634410400)
confirmed Mail accrued 22 CNY micros and Billing exactly 22 micros across six
events, all outbox delivered markers present, all six actual Billing usage
request spans HTTP 200/success, budget zero and registered-address count zero.
The first 15 micros survived later consent reductions and settled into the
liability ledger through ordinary Cron/backoff, not an accounting edit.

Positive liabilities remain `pending_settlement`, never payment collection. No production
deployment, public Release/tag or Identity-sector change was performed.

### v0.1.2 publication evidence

The owner authorized formal publication on 2026-10-03. The
[v0.1.2 Release](https://github.com/kleedaisuki/moesegfault-amail/releases/tag/v0.1.2)
is public, nondraft and nonprerelease, published at `2026-10-03T07:04:34Z`.
The annotated tag, native assets, Skill and deployed site are tied to source
`805ac273fc00e85f773b9249587581a0dc274ce2`; the site serving version is
`bdf042b9-a535-4e4e-9a18-7fe25fcd267f`.

| Outcome | Actual evidence | Scope |
| --- | --- | --- |
| Accepted source | [PR #110](https://github.com/kleedaisuki/moesegfault-amail/pull/110), [37103712818](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37103712818), [main 37104349476](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37104349476) | Three CLI platforms, native Worker modules, Wasm/workerd, 157 infrastructure tests and both site states; production run independently gates its same-run modules |
| Owned production predecessor | [37104353086](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37104353086) | Read-only current active graph, allowed policy and retained external graph verified against the original successful production writer |
| Normal production upgrade | [37104468990](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37104468990), artifact `11267970678` | Additive index migration, exact API then scheduled-maintenance replacement, independent retained-adapter readbacks; overall SUCCESS |
| Formal Release and public bytes | [37104773263](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37104773263), overall SUCCESS | All five native builds/tests and attestations; Skill; seven public files; archives and public checksum manifest match immutable same-run bundle |
| Published website | Same successful tagged run | Exact home/manual/changelog HTTP 200, current published claims, all seven downloads, no noindex/candidate state, no-transform and exact release-source header |
| Actual hosted browser | [37105257856](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37105257856), artifact `11267707672` | All 12 cases at 320/390/768/1440 px pass; real Release metadata, source header, zero scripts, route-local CSS, navigation/focus/geometry |

Production API version is `50bd330d-2f9b-4102-8c8e-9bbaada927fe`
(deployment `4eee1ec6-8f70-47ee-98d8-e7ba4feb3f19`); maintenance version is
`293d4049-c56a-40ee-8bc3-ef345a7a4eb7`
(deployment `411db6fb-3028-44bd-98db-cb354bfbe922`). API Cron remains empty,
maintenance stays `*/5 * * * *`, and the private trace sink, Queue/DLQ,
ingress/lifecycle adapters, D1/R2, direct forwards and subscription were retained.
The complete private policy and external-graph fingerprints match the admitted
predecessor; allowed sending was preserved, never rewritten or re-granted.

An independent public download check verified all six archive checksums and GitHub
attestations against the exact tagged source and release workflow. The published
Skill's nine files match source bytes; the downloaded Windows executable reports
`amail 0.1.2` and exposes the eight-topic offline discovery index. Skill entry is
590 English words, with task-specific progressive references and byte-identical
public/local mirrors. No ordinary production mail was sent for this publication;
reuse the bounded staging and earlier production journeys below rather than
claiming a new production delivery test or autonomous-agent success rate.

The downloaded browser report independently confirms twelve cases, zero script
counts and zero failed checks. Representative 1440/320 home and 1440/390 manual
viewport screenshots were visually reviewed for release copy, readable CJK,
privacy notice, downloads and clipping; no new defect was observed. This bounded
review is not an exhaustive accessibility audit.

## Delivered v0.1.0 — historical release

| Outcome | Actual evidence | Scope |
| --- | --- | --- |
| Production online graph | [36938451911](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36938451911) | API, maintenance, ingress, lifecycle consumer and private trace graph |
| Two-owned-account journey | [36942533661](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36942533661) | Receive/send/reply, TEXT/HTML/assets, filters/automatic semantic indexing, read state, ZIP export, deletion/isolation and delivered feedback for the same two sends |
| Operational contacts | [36954714726](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36954714726) | Verified destination, four real role receipts, normal health and opt-in schedule |
| Public sending allowed | [36954757295](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36954757295) | Explicit operator action; no invented human response commitment |
| Tagged builds | [36954856681](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36954856681) | Five platforms and skill bundle |
| Public bytes | [36957203738](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36957203738), job 110682831501 | Six archives against original manifest; seven published files including checksums |
| Published website | Later ordinary access to home/manual/changelog | HTTP 200, published Release links, no candidate copy/noindex; manual seven downloads/14 fragments, changelog two fragments |

[Release v0.1.0](https://github.com/kleedaisuki/moesegfault-amail/releases/tag/v0.1.0)
uses tag/artifact source `9ffb3284ddaec485a61b1efb93e4d26141b670cb`.
Recovery source was separately `6414b2038e45a56ac7a5cd710c2fef21266eb678`;
tag/assets/provenance were not replaced. Site version:
`1d89ad97-3046-456e-b008-97078a8db677`.

The continuation remains **FAILURE**: first site smoke ran 0.420 s after deploy
and did not confirm published-copy readiness. Later public access closes that
bounded site outcome, not a rewritten all-green run or another deployment.
Historical held/unreleased snapshots are not current production state.

## Useful bounded evidence and limits

### v0.1.2 staging acceptance before publication

At this earlier stage the owner authorized staging testing/deployment only. Public production, stable
v0.1.0 Release/downloads and production sending policy were not changed. The final
site source is `25f22cd79a68452c73ff63e3ed695bcb1cbfde19`; the final user CLI
candidate/acceptance producer is helper-only source
`2ea0d09febcaa51c276de0e82e1bdf5074d16f17`. Mail runtime inputs are unchanged.

| Outcome | Actual evidence | Scope / limitation |
| --- | --- | --- |
| Final staging deployment | [37072106319](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37072106319), overall SUCCESS | Linux/Windows/macOS CLI, native Worker, Wasm/workerd (112 boundary tests), both site states, infrastructure and performance gates; installed runtime reused after exact owned graph admission; candidate site deployed and semantically verified |
| Staging-run candidate | [Artifact 11255765702](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37072106319/artifacts/11255765702) | Immutable same-run three-platform native archives, skill and checksums; manifest/source/checksums verified locally; `unpublished-candidate`, not the formal five-platform release gate |
| Final live browser | [37072847760](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37072847760), overall SUCCESS | Exact source and deployed revision; all 12 home/manual/changelog cases at 320/390/768/1440 px pass, zero client scripts and zero failed checks |
| First native candidate-byte journey | [37069775670](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37069775670), overall FAILURE | Same-source successful producer 37068720900 admitted the Windows release executable; normal login/discovery/policy/events/missing-intent and two-SMTP reply/ZIP/search/delete/owned-route cleanup passed; extra outbound probe stopped before send; guarded grant SQL may already have committed |
| Second native candidate-byte journey | [37072844102](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37072844102) | Overall FAILURE at `owned_send_grant_staging_canary_live_slot_or_hold_changed`; normal inbound journey passed again; guarded grant UPDATE executed, send not called; no outbound acceptance/feedback claim |
| Recovery checks producer | [37074671896](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37074671896), overall SUCCESS | Helper-only source `2ea0d09febcaa51c276de0e82e1bdf5074d16f17`; full source gates and [candidate artifact 11256560216](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37074671896/artifacts/11256560216); no provider/site deployment |
| Controlled native recovery journey | [37075181256](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37075181256), overall SUCCESS | Exact candidate bytes from successful same-source producer 37074671896; normal inbound journey plus one held-policy owned self-send, lost-stdout receipt recovery, exact same-key replay, delivered feedback/owner event, inbound archive and exact cleanup |

The final browser report is preserved locally under
`.temp/site-browser-37072847760/site-browser-evidence/report.json`; all twelve
`loading.scripts` counts are zero. The owner also visually reviewed representative
1440/320 home and 1440/390 manual screenshots from the earlier successful actual
staging browser run [37071618309](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37071618309),
finding no clipping, missing CJK glyphs or privacy-notice rendering problems.
Automated geometry/focus checks and bounded representative visual review are not
an exhaustive accessibility audit.

The final native log records candidate admission/extraction,
`progressive_discovery_policy_events_missing_intent_verified`, the two-SMTP
ZIP/reply/search/delete journey, `staging_owned_send_mapping_observed_for_fixture`,
`staging_owned_send_provider_to_rfc_mapping_not_asserted`, and
`staging_owned_send_receipt_replay_feedback_and_inbound_verified`. The optional
self-send used one fresh persisted UUID/ZIP only after a positive scoped grant and
held-policy readback. First stdout was deliberately discarded; server/local
receipt recovery then permitted only identical byte/key replay, preserving the
local/provider identifiers. Actual delivered outcome and owner-visible event,
self-received native ZIP/header/body, and exact task-created message/alias cleanup
passed. There were no no-resend or cleanup-failure markers. The existing grant
slot's atomic guard was retained; the prior unused slot expired normally, not by
an overwrite. Global public sending remained held. This is one owned synthetic
fixture, not a general deliverability SLA, a new send campaign, or production
mail acceptance. Its private provider-to-wire equality observation is not exposed
as raw identifiers or asserted as a global RFC identity contract.

The first browser run exposed provider-injected Web Analytics in browser-UA HTML,
although built assets contained no scripts, plus a keyboard Enter/hash observation
race. Staging-only generated headers now use
`Cache-Control: public, max-age=0, must-revalidate, no-transform`, the documented
[Cloudflare Web Analytics exclusion](https://developers.cloudflare.com/web-analytics/get-started/),
without changing public site headers or zone-wide analytics. The harness waits
for the exact `#main` URL before preserving its original main-focus assertion.
Run [37070636987](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37070636987)
submitted the corrected site but failed its immediate stale-revision smoke; that
failed run is not relabeled green. The final lane polls public GETs for at most
120 seconds, requiring all three exact revision/header/content/TOC contracts in
the same cycle. It never repeats a deploy to wait for CDN readiness.

The bounded graph now online is:

| Component | Serving version / Queue identity | Accepted boundary |
| --- | --- | --- |
| API | `01f14a8e-d5b1-41f9-9f8c-325c2e288ba7` | Fetch only, empty Cron, capture off |
| Maintenance | `3d23d537-6379-4fcb-84c2-2c1b8a9f4857` | Scheduled only, five-minute Cron, capture off |
| Ingress | `09c34d0f-1147-467c-85f0-e7711d96d8fd` | Email only, private same-realm API binding, capture off |
| Lifecycle | `63733c7c-6238-4522-be0f-befb5e8c4799` | Queue only, same-realm D1, capture off; exact domain/event subscription |
| Trace sink | `be786239-402d-4e72-89c9-0acbe88b0b86` | Queue only, empty Cron, separate `privacy_safe=true`; sanitized logs intentionally retained, `capture_off=false` |
| Trace Queue | `fcee510036af42c189e28c0b6ff9508e` | Bounded retention, exact API + maintenance producer pair |
| Trace DLQ | `f023f804b7bd4d8691fbfcb60416a001` | Bounded retention, no producers |

Staging D1/R2/Identity remain separate from production; general sending remains
held and no fake send/provider-feedback rows were seeded in live D1. Each native
journey verified PKCE login, progressive discovery, held policy/quota, owner events
and typed 404/stop for an unsubmitted intent. Its second SMTP fixture references
only the first fixture's proven DATA receipt; ZIP/metadata/search preserve the
RFC reply relation and exact fixture/route cleanup.

The two prior native failures were before send, not proof of absent grant writes.
The second failed at `owned_send_grant_staging_canary_live_slot_or_hold_changed`
after its guarded UPDATE. A routing read found ten list-matcher rules, excluding
the suspected null-shape cause from the observed inventory. No such speculative
normalization was made and no unknown provider submission was replayed.
The [D1 API metadata contract](https://developers.cloudflare.com/api/resources/d1/)
defines `meta.changes` through SQLite total changes, which include trigger writes.
A native SQLite 3.50.4 probe using the actual migration's gate/policy audit triggers
observed one direct gate UPDATE but total-change delta two, and no changes for a
second still-live conditional UPDATE. This exposed the helper's incorrect `meta.changes == 1`
acknowledgment check. The staging-owned UPDATE now returns its top-level gate ID
and requires exactly one integer ID 1, then the existing exact-scope readback;
aggregate counts do not identify the gate row. Actual-migration regression tests
also require a still-live second grant to return zero rows with zero mutations.
The original operator SQL is unchanged. These local results do not by themselves
prove either remote grant state: inspect the existing live grant/audit and allow
normal expiry, never overwrite it, before another authorized send attempt.
Actual inspection [37074323728](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37074323728)
then confirmed gate present, global held, live and unused grant, owned-case prefix,
exact latest matching audit, and the failed request's 22:37 UTC update window, with
323 seconds remaining. The failed acknowledgment had installed the grant and its
audit; no send followed. This closes the concrete aggregate-count diagnosis, not
outbound delivery acceptance. That unused slot was retained until normal expiry.

#### Migration and interruption evidence

The following history explains the retained ownership/witness, not repeated runtime
writes or competing current-state snapshots:

| Run | Actual result and retained evidence |
| --- | --- |
| [37046570528](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37046570528) | Initial legacy API `c3f6401a-1e84-4f51-91df-ae77d90683e9` fetch + scheduled/five-minute Cron, no maintenance/sink/trace Queues; existing private adapters |
| [37053907751](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37053907751) | Full source gates passed, trace Queues and sink submitted; failed because verifier demanded final producer pair in legitimate zero-producer preparation phase; remaining writes skipped |
| [37055035305](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37055035305), [37057224593](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37057224593) | Fresh exact private sink/Queue pins, zero producers, separate retained-log privacy predicate; no application activation |
| [37056569732](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37056569732), [37057818125](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37057818125) | Source/provenance checks passed but hosted job-log download failed before every provider write; actual CLI/token root cause not established |
| [37058454601](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37058454601) | Read admission passed after authenticated GitHub 302 and allowlisted unauthenticated signed-log download were separated; exact typed ownership proof retained |
| [37058617870](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37058617870) | API fetch-only and paused/active maintenance submitted; 1,864.625790695 monotonic seconds, 30 pinned Standard-model samples and both execution-lease counts zero/preserved; failed final graph's unrelated role-absence predicate |
| [37063591034](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37063591034) | Confirmed retained historical contact Worker has no Mail D1/R2/API-or-maintenance-or-sink service/trace Queue capability edge |
| [37065145834](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37065145834) | Full source and active graph gates passed; ingress/lifecycle submits and subscription succeeded; exact source-object equality rejected additive display metadata; site skipped |
| [37067988366](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37067988366) | Bounded schema diagnostic isolated the sole extra source key `name`; exact type/zone_id/domain selectors unchanged |
| [37068720900](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37068720900) | First complete successful staging continuation; all installed graph resources reused, candidate site deployed; followed by native/browser findings above |
| [37071404266](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37071404266) | Full read/provenance admission and routing diagnostic passed before final source producer; no provider mutation |

The initial drain witness combines documented Cron propagation up to 15 minutes,
Standard scheduled invocation wall time up to 15 minutes and a one-minute margin.
Immutable `resources.script_runtime.usage_model`, continuous version/Cron/hold
brackets and retained execution fences are required; elapsed time alone is not a
proof. Pending mailbox work was not cleared. Already-split reuse did not repeat
that initial wait or submit already accepted runtime versions.

The historical staging contact Worker was deliberately retained unchanged after
before/after serving/Cron/capability verification excluded all listed Mail edges.
Production still requires its original role absence. This is bounded capability
graph separation, not population/network isolation or contact-monitor correctness.
The lifecycle source matcher follows
[pinned Wrangler EmailSendingEventSource](https://github.com/cloudflare/workers-sdk/blob/wrangler%404.142.0/packages/wrangler/src/queues/subscription-types.ts):
exact type/zone_id/domain selectors plus only an optional bounded string display
`name`; unknown extras/wrong scope/type still fail. Queue defaults/configuration
were not changed to conceal a failed predicate.

Hosted synthetic Wasm/D1 tests cover broader outbound receipt/replay/outcome
contracts; actual native run `37075181256` additionally proves the bounded real
self-send receipt/replay/delivered-feedback journey described above. Its observed
provider-to-RFC comparison applies only to that synthetic fixture, never a global
provider identifier contract. No heavy local Rust/Wasm/browser build or local
provider/mail write was performed during this staging work.

Staging [36719116852](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36719116852),
source `17abe25`, passed one-principal native PKCE/two-message receive/search/ZIP/
cleanup and two `limit=1` exact-cosine pages:
`max_abs_error=0.00000000,count=2,order=true,origin_vector=true`; primary/cleanup
`none`. This is not a large-mailbox benchmark or proof of every tie/third-page/
tampered-cursor/ten-address case. Production isolation is real bounded evidence,
not exhaustive formal verification.

The owner's original account belongs to production Identity. Its historical
staging rejection was a realm mismatch, not a production password defect. The
synthetic production journey does not claim the owner's account was exercised.
Correlation is not a complete native Cloudflare trace waterfall. No measurement
establishes large-mailbox throughput or an indexing latency SLA.

### Normal production upgrade preparation and initial read-only failure

The newly authorized v0.1.2 publication requires a normal production upgrade,
not reuse of a bootstrap/API-only lane. Implementation now binds the original
successful online receipt from run `36938451911` / artifact `11199880674` and its
exact deployment/version/store/trace Queue pins. Its retained ingress/events/sink
and trace-schema component trees were compared against source
`45f8dc41c82866ce47877601340113e28e8fb99d`; only package version metadata differs.
This source check is not a fresh production inventory or permission to deploy.

156 focused infrastructure tests passed locally, including seven normal-upgrade
contracts: allowed/held exact policy reads, read/write authority separation,
preflight failure before mutation, migration/API/maintenance ordering, ambiguous
second-submit no retry, retained runtime change rejection and policy drift stop.
Actionlint and diff whitespace checks passed. No local heavy build, production
provider mutation, mail action or workflow dispatch was performed. Hosted full CI,
actual `production-inspect` and normal replacement results remain pending; release
publication/site evidence must likewise be recorded only after the owner's runs.
Those subsequent actual outcomes are now recorded in the current-release section.

Actual production inspection
[37104009114](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37104009114)
passed current policy/owned active graph reads but failed subscription admission
before any writes. The controller had invented a top-level `type=queues` field
and compared destination type to `queues` instead of documented `queues.queue`.
The narrow repair follows the
[Cloudflare subscription response contract](https://developers.cloudflare.com/api/resources/queues/subresources/subscriptions/methods/list/),
retains exact selectors/destination/events, and rejects duplicate identities or
extra paths related to the production domain/main or DLQ. Eight focused tests and
157 infrastructure tests pass; corrected actual read admission then succeeded in
`37104353086` before any normal production upgrade was dispatched.

## Verification proportional to value

The owner's preserved local audit records source-level repair candidates outside
this cleanup: orphan-object cleanup versus accepted-send projection race, allocation
atomicity, ZIP actual-byte cap, re-login marker ordering and no-op read-state
generation changes. They are not fixed by deleting infrastructure/tests/docs. The
untracked owner audit remains local and intact; triage these against product impact
before adding machinery or claiming resolution.

Use focused Rust business-contract tests, Worker/Wasm boundary checks, CLI
cross-platform checks and the site build in hosted CI. Local static syntax/link/
diff checks are fine; artifacts stay under root .temp/.cache. No per-patch audit
report, incident workflow or test of a test merely to inspect its spelling.
Repeat real mail only for a changed delivery boundary or new failure, using
authorized owned synthetic accounts and exact cleanup. Reuse successful evidence.

For this simplification, local static validation found no imports of deleted Python
modules; actionlint v1.7.11 accepted retained workflows (local shellcheck/pyflakes
disabled; normal hosted checks remain). The 52 focused infrastructure safety tests
and 22 Mail API privacy tests passed. A separate synthetic ZIP probe accepted
current six-tree and historical seven-tree bootstrap artifacts. Native JavaScript
syntax and local imports passed. This initial local verification did not execute
the hosted Rust/Wasm/runtime pipeline; premerge CI is a separate check. No provider
access/deployment or heavy local Rust/Wasm build occurred.

Premerge source `00d74df` passed [hosted checks 37035990692](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37035990692):
all three CLI platforms, Rust unit tests, Wasm builds, retained workerd boundaries,
infrastructure safety and both site states. Deployment/provider/mail jobs were
skipped. The retired Cargo target and test-only observer entry were corrected
before this pass; this is source acceptance, not production rollout evidence.

On 2026-10-03 the owner selected maintenance-only publication, preserving unchanged
live services. Source `c66dbba` passed [main CI 37038760121](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37038760121)
and [workflow guard 37038759966](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37038759966).
Application sources, production configs, migrations and site inputs are unchanged
from recorded production source `6414b203`; the lockfile only loses the retired
tracing experiment. No Worker/site deployment, policy change or provider write
was performed. Fresh exact-route GETs returned Mail health 200, anonymous address
list 401, and home/manual/changelog 200 with published v0.1.0 copy and Release links.
These public checks do not re-establish SMTP delivery or private graph inventory.
