# Workers Issues: an accepted false write with an omitted readback

Investigated 2026-10-01 at repository revision `4cd5422`. Scope: public
Cloudflare documentation, published API schemas and pinned upstream client
source. No private provider request, mutation, deployment, local test or build
was performed. This supplements, but does not update or replace, the live
[current-Worker correction record](staging-current-worker-issues-alternative.md).

## Conclusion

**No examined public contract assigns `observability.issues` omission on a
current Worker GET the meaning disabled, default false, or feature unavailable.**
The write operation supports an explicit false flag, while the response schema
permits the object and flag to be absent. That is a representational gap, not
proof that the flag was ignored or that detection remains enabled.

Do not repeat either PATCH, reinterpret missing as false, or manufacture an
all-off attestation. Equally, do not describe the deployment as demonstrably
capturing Issues: the observation supports **unknown effective Issues state**.
The current strict positive-false acceptance requirement can reject a legitimate
provider-normalized disabled representation; this is an engineering evidence
policy, not a documented requirement that Cloudflare must return false.

## Live facts supplied by the parent

These facts were not independently re-queried in this investigation:

| Evidence | Reported observation | Limit |
| --- | --- | --- |
| [36761367007](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36761367007) | One current-Worker Beta PATCH accepted; separate readback began; aggregate UNVERIFIED | Write acceptance is not effective-state acceptance. |
| [36761475455](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36761475455) | Independent five-GET bracket stable at approved version `c3f6401a-1e84-4f51-91df-ae77d90683e9`, 100%; parent/Logs/traces false; Issues missing | Missing remains distinct from Boolean false. |
| Same readback | Query redaction false; invocation-log and persistence preferences true, under disabled capture flags | Stored preferences alone do not prove active Logs/traces. They also do not control independent Issues. |

This is new evidence after the historical legacy settings PATCH. It is not a
reason to perform a third equivalent mutation through another client.

## Authoritative public evidence

### 1. Response optionality is not a default rule

The [Get Worker reference](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/get/)
documents the current resource at
`GET /accounts/{account_id}/workers/workers/{worker_id}`. Its top-level
observability response permits an optional Issues object with an optional
Boolean enabled member. It describes what the member controls, but specifies
no interpretation for its absence. The generated example shows true, not a
disabled or omitted case.

The pinned official [Python Worker model](https://github.com/cloudflare/cloudflare-python/blob/c9dd8956de93575640e06ea28e802951175099a0/src/cloudflare/types/workers/beta/worker.py)
uses optional objects/Booleans initialized to `None`. These are client model
defaults, **not server defaults**. Raw missing, explicit null and false must
not be merged by an SDK or a `get(..., False)` helper.

The [Edit Worker reference](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/edit/)
accepts `observability.issues.enabled` and documents a partial update. It does
not state that false is ignored, normalized to omission, delayed for a specified
interval, or conditional on parent observability. No examined source establishes
those behaviors. The alternative correction already used this operation; its
acceptance does not resolve this undocumented response semantics.

### 2. Issues is independent and generally available

The official [Issues overview](https://developers.cloudflare.com/workers/observability/issues/)
documents opt-in through Wrangler, the dashboard and the Cloudflare CLI. It
states availability for all Workers accounts during open beta. Consequently a
general assumption that this account cannot use Issues is not justified.

The official [investigation guide](https://developers.cloudflare.com/workers/observability/issues/investigate/)
states detection is independent of Workers Logs/tracing. Detection can retain
failure/request context; occurrence details persist seven days. Its documented
disable path is explicit `observability.issues.enabled=false` followed by a
Wrangler deployment. That is a supported correction *procedure*, not a guarantee
of explicit false GET representation. Deployment also changes code/version state
and is not a safe substitute for the existing frozen settings-only boundary.

The overview notes that a later Wrangler deployment without Issues opt-in turns
off a dashboard-enabled setting. This supports default-off deployment behavior,
not a universal missing-GET-means-off rule.

Issues pages were unavailable in the web reader. Public raw documentation was
read instead; its production branch resolved during this investigation to
`5d3a1e49df20d3a1e0797b6edf29f39986723d54`. Reproducible sources:
[overview](https://github.com/cloudflare/cloudflare-docs/blob/5d3a1e49df20d3a1e0797b6edf29f39986723d54/src/content/docs/workers/observability/issues/index.mdx),
[investigation](https://github.com/cloudflare/cloudflare-docs/blob/5d3a1e49df20d3a1e0797b6edf29f39986723d54/src/content/docs/workers/observability/issues/investigate.mdx).
Existing cached files were reused; current public raw pages corroborated them.

### 3. Wrangler does not explain false disappearing

Reuse [the upstream serializer investigation](wrangler-observability-readback-research.md),
pinned to Wrangler 4.142.0 commit `f96458cefb7eaffc611f38f59f41d573dfa8b112`.
The [validator](https://github.com/cloudflare/workers-sdk/blob/f96458cefb7eaffc611f38f59f41d573dfa8b112/packages/workers-utils/src/config/validation.ts#L7622-L7696)
accepts the optional Issues object and validates enabled as Boolean; it does not
convert false to missing. The upload serializer and non-versioned-settings
serializer preserve a supplied observability object. These are open client
implementations, not evidence about Cloudflare's closed server storage/readback.

## Remaining competing explanations

| Hypothesis | Consistent with observed omission? | Established? |
| --- | --- | --- |
| Server returns no Issues object when disabled | Yes | No published normalization contract found. |
| Issues setting is stored separately and omitted by this GET adapter | Yes | No public implementation proof. |
| API accepted the object but ignored this particular member | Yes | Acceptance alone cannot exclude it; no evidence proves it. |
| Account rollout/capability affects the representation | Yes | Possible, but all-account availability makes a blanket unavailability claim unjustified. |

Repeated unchanged GETs cannot discriminate these explanations without a new
contract or independently observable state. Absence of detected failures is
also insufficient: no eligible traffic, delayed processing or sampling would
produce the same observation. Do not provoke a real private-mail exception to
test this uncertainty.

## Next discriminating step: official Dashboard, without mutation

Use the authenticated official Issues page for **the exact staging Worker**.
The documented dashboard destination is
`/?to=/:account/workers/services/view/:worker/production/issues?status=active`.
The `production` segment denotes that Worker's environment; it must not redirect
the investigator to the separate production Mail service.

1. Confirm the selected Worker/account against the existing serving bracket;
   do not expose private account identifiers or request context.
2. Read the setting/onboarding state, not merely whether the issue list is empty.
   The official overview describes an **Enable issues** control for the enabling
   path. Record only a bounded state such as `enable_control_present`,
   `enabled_control_present`, or `unresolved`. **Do not click a toggle.**
3. If read-only network inspection is available, inspect only the response that
   supplies this control state. Do not export HAR, cookies, raw API bodies or
   unrelated account requests. An undocumented endpoint is discovery evidence,
   not automatically a reviewed production health-check contract.
4. If the UI simply defaults an absent member to disabled, that is another
   client convention, not independent server proof. Record the ambiguity rather
   than accepting it. A distinct server-returned explicit disabled setting would
   materially narrow the problem, but any replacement attestation needs review
   of resource identity, authority and replay/provenance guarantees.

No distinct *publicly documented authoritative read-only Issues-setting
endpoint* was found in the examined Workers/observability API references or
Issues guides. A dashboard inspection is therefore a supported product-surface
discriminator, not a claim that a new REST endpoint is already known.

If the dashboard remains ambiguous, ask Cloudflare support to confirm the
documented effective meaning of omitted Issues after explicit false PATCH and
identify the supported effective-state read surface. Supply only the synthetic
reproduction contract and bounded run provenance privately; omit mail data and
credentials. A provider-confirmed normalization rule can justify a narrowly
reviewed gate change. Do not turn an unobservable representation into an endless
PATCH/deploy loop, and do not lower the privacy claim without evidence.

The [Audit resource history API](https://developers.cloudflare.com/api/resources/accounts/subresources/logs/subresources/audit/methods/history/)
is not a substitute: it returns matched audit entries, with optional request/
response maps, rather than a documented current configuration snapshot. Its
success or exact resource match alone would only repeat write-history evidence.

## Acceptance remains separate

Once effective Issues-off has defensible evidence, the whole-retained-record
privacy canary is still necessary. Neither source configuration, successful
write history, dashboard empty lists nor old-issue expiry proves that a request
was not retained. Queue rollout/public sending remain governed by their separate
existing acceptance gates.

## Supplemental non-dashboard discriminator

See [the no-route create-time design](staging-issues-no-route-discriminator-2026-10-01.md)
for a smaller prospective test using the documented ability to create a Worker
before code upload. One code-free, zero-business-data creation with explicit
Issues false plus one independent GET can compare create-time representation
against the spent Mail PATCH path. The [narrow implementation](staging-issues-create-probe.md)
and [independent static review](staging-issues-create-probe-review.md) are now
integrated; it has not been run or authorized and does not guarantee explicit
false readback. Its reviewed bounded complete inventory replaces the design's
unsupported exact-name not-found premise. Missing Issues still fails acceptance;
positive probe evidence belongs only to that probe identity and cannot attest
the original Mail Worker. The design also identifies conditional no-route
deployment/cutover obligations and a stop-to-provider-clarification boundary.
