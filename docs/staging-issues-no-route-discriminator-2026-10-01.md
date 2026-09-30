# Issues-off evidence without another Mail settings PATCH

Date: 2026-10-01. Status: **design and public-contract investigation; no live
probe or cutover authorized or executed**. Inspected local source at
`2ff67e01544fe1b77de4c0fc05e55e71e54d1c12`; source was moving under parent
coordination, so this is an inspection snapshot, not a release pin. No private
provider request, provider mutation, local project test/build, mail experiment,
or raw request/mail/log retrieval was performed. Public Cloudflare documentation
and the existing cached official Issues source were consulted.

## Decision

The narrowest new discriminator is **one fresh, code-free, no-route Worker
creation with explicit all-off observability, followed by one separate current
Worker GET**. The new Workers API explicitly permits configuring a Worker before
uploading code. Start there, not with a full Mail clone or a domain switch.

If this yields explicit `issues.enabled=false`, a subsequent isolated deployment
can check whether that positive representation survives deployment. If it omits
Issues too, stop: repeated PATCHes, fresh names, delayed GET loops, or deploying
Mail would not gain the missing authority. Seek provider confirmation of the
effective-state contract using this zero-business-data reproduction.

This is an alternative to depending solely on the busy user's dashboard, **not
a claim that the alternative is guaranteed to return positive false**. The
official GET schema still makes Issues optional. It provides a controlled
comparison of create-time versus the already-spent update path.

**Evidence belongs to a Worker identity. A safe shadow never proves the original
`amail-mail-staging` safe.** A successful shadow read therefore cannot satisfy
the existing containment gate for c3f, authorize Queue rollout, or release
public sending. Actual candidate promotion or an original-resource correction
needs its own exact effective-state evidence.

## Reused facts and what changed

Reuse [current-Worker Issues correction](staging-current-worker-issues-alternative.md),
[omission semantics](issues-false-omission-semantics-2026-10-01.md),
[Wrangler serializer research](wrangler-observability-readback-research.md), and
[held staging promotion](held-staging-mail-promotion-2026-10-01.md).

- Current parent/Logs/traces false plus missing Issues is **unknown Issues
  state**, not established enabled and not established disabled.
- The accepted current-resource PATCH and its immediate/delayed readbacks are
  spent evidence. This document proposes no repeat or fallback write on Mail.
- Observability is Worker-level, not immutable version state. A source TOML,
  version upload, serving UUID, Audit success, or healthy HTTP response cannot
  replace the independent effective setting.
- The new opportunity is the documented separation between Worker creation,
  immutable version creation, and explicit deployment. We can investigate the
  representation without exposing a new Mail receiver or attaching Mail data.

The official [new API announcement](https://developers.cloudflare.com/changelog/post/2025-09-03-new-workers-api/)
documents creation without code, stable Worker identity, immutable version
resources and explicit deployment. It also specifies that deployments remain
on `/scripts/`; do not invent a Beta `/workers/.../deployments` endpoint.

## Public contract and isolation requirements

| Surface | Supported operation or setting | Evidence limit |
| --- | --- | --- |
| [Create Worker](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/create/) | `POST /accounts/{account}/workers/workers`, explicit observability Issues false and subdomain flags | A successful response may reflect write acceptance; it is not independent readback. |
| [Get Worker](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/get/) | GET by immutable ID or fixed name; top-level current observability | Optional Issues shape still has no documented omission-as-false rule. |
| [Create Worker Version](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/subresources/versions/methods/create/) | Code/config snapshot without moving serving traffic | Uploaded code is not current capture evidence. |
| [Workers deployment API](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/create/) | Explicit single-version 100% deployment under the script path | Deployment success alone does not establish capture settings. |
| [workers.dev](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/) | Explicit `workers_dev=false` / `subdomain.enabled=false` | Does not turn off other URL classes or service/event invocation paths. |
| [Version URLs](https://developers.cloudflare.com/workers/versions-and-deployments/version-urls/) | Explicit `preview_urls=false` / `subdomain.previews_enabled=false` | Omitting config does not reset an existing Version URL setting. |

Current workers.dev documentation expressly warns that disabling that route
does not disable Version, Preview, or Deployment URLs. **No-route cannot mean
only `routes=[]`.** For the proposed code-free probe, there is no executable
version to invoke; both subdomain flags must nevertheless be explicit false.
Before uploading any code, separately verify all currently supported invocation
paths are off, including any newer Preview/Deployment URL product controls not
fully represented by the legacy pair. A response URL/suffix being present is
not evidence the URL is live; inspect the flags. If the supported read surfaces
cannot establish isolation, keep the candidate code-free and stop progression.

For a later inert shadow deployment require no Custom Domain, zone route,
service caller, Queue consumer, Email Routing action, Cron, Durable Object,
workflow trigger, Tail consumer, or private binding/secret. No automated Builds
or unrelated operator may deploy it. Current Worker `references` helps identify
inbound references but is not a blanket proof of every URL/event product.

Issues detection is independent of Workers Logs/tracing and can retain
invocation/request context. Official [Investigate issues](https://developers.cloudflare.com/workers/observability/issues/investigate/)
documents explicit false plus Wrangler deployment as a disable procedure and
seven-day occurrence retention. Neither absence of failures nor expiry of old
occurrences proves effective off. Do not enable Issues, manufacture exceptions,
open occurrence bodies, or attach private mail to a differential test.

## One next discriminating test: create-time independent read

Prospective literal probe name: `amail-issues-contract-staging`. Treat it as a
separate resource, not an alias, replacement name, or configurable generic
deployment target. Its name must be fixed in a reviewed helper. Use one protected
staging manual first-attempt run at an exact reviewed SHA, with explicit
confirmation and the real external Mail/settings/routing writer freeze. Hosted
synthetic source tests must pass before provider credentials become available.
No local test/build is part of this proposal.

1. Privately verify the current Mail deployment still matches the approved c3f
   single-100 bracket, global send hold remains held, and no separately approved
   one-use send is active. This observes no new privacy acceptance. Shared writer
   concurrency is necessary but does not lock out out-of-band writers.
2. Read the exact probe name once. A typed successful existing Worker means
   `name_occupied`: stop, do not adopt or replace it. Only a reviewed provider
   not-found contract may mean absence; 403, transport error, arbitrary 404 body,
   malformed response or unavailable response remains UNVERIFIED. No list/name
   suffix search or create-after-failed-read fallback.
3. Create exactly once using the official Worker POST, with explicit parent,
   Logs, native traces and Issues `enabled=false`, `logpush=false`, empty tail
   consumers, empty tags, and both writable subdomain flags false. Include the
   reviewed source privacy preferences (`head_sampling_rate=1`, query redaction
   true, invocation logging false); do not copy Mail preview configuration or
   response-only URL/suffix fields. No `previews_base_config` or code/bindings.
4. Require a bounded successful provider envelope, expected fixed name and typed
   immutable ID, retained privately. An ambiguous POST stops without replay.
   Do not automatically delete in `finally`: it may be the only recoverable
   identity of a partially accepted operation.
5. GET that returned ID once, independently. Require same identity; explicit
   current parent/Logs/traces/Issues false; Logpush false; empty tail consumers;
   no unknown enabled export path; both subdomain flags false; no inbound
   references; and no deployed code. Validate raw JSON rather than SDK default
   objects. Record only fixed bins. Recheck original Mail deployment and hold;
   original bindings/domain/ingress must be unchanged.
6. End the experiment. If any capture/identity/isolation check fails, it remains
   UNVERIFIED. No PATCH, code upload, routing write, Mail/D1/R2/Email/Queue
   capability, HTTP request, SMTP fixture, toggle, polling, or automatic cleanup
   mutation is bundled into this first discriminator.

Possible fixed result: `staging_issues_create_probe=explicit_off|omitted|true|
unavailable|UNVERIFIED`, with separate `create`, `identity`, `isolation`,
`readback`, `original_pin`, `hold` bins. A valid observed omitted Issues can be
reported as `omitted`, but **never** an all-off attestation. Normalize all other
exception/provider details to closed categories. Preserve only non-secret
resource/run/SHA/UTC recovery pins in the approved restricted system-ID artifact;
no API body, unknown key/value, URL, identifier from a reference, error string,
traceback, mail address, subject, request header, cookie, bearer token, or SQL row
may enter logs/artifacts. Local temporary material stays under root `.temp` and
public source downloads under `.cache`.

### Interpretation

| Independent result | What we learned | Next move |
| --- | --- | --- |
| Explicit false before code | This account/API can represent off for this fresh Worker, at this instant | Separately approve inert no-route deployment and a new bracketed current GET; keep original unchanged. |
| Issues omitted again | Omission is not confined to the historical Mail PATCH path | Stop provider experiments; supply a zero-data reproduction to provider support. No assumption that this proves disabled. |
| Issues true | The observed resource is not explicitly off despite requested policy | Keep isolated; escalate create/read discrepancy, no Mail capability. |
| Identity/isolation/transport failure | The test cannot answer its question | Bounded private recovery by returned identity, no automatic second create. |

No published propagation deadline supports waiting until the desired answer
appears. A create response with false followed by an omitted independent GET is
still write-versus-read ambiguity. A code-free false GET is positive control-state
evidence for that resource, not proof of runtime retention behavior.

## Conditional continuation: from shadow to an actual Mail receiver

Only design the next slice after the first result warrants it. Two materially
different paths remain:

1. **Keep the existing Mail identity (lower maintenance cost).** A reviewed
   containment-only original deployment could use explicit false and independently
   read the original Worker. Shadow success merely increases confidence that the
   test is worth considering; it never bypasses its gate. Existing queue-api deploy
   helper does not implement this no-Queue slice. Do not pass an edited TOML to
   the existing full staging target or silently claim an executable path exists.
2. **Promote a separately attested candidate (higher migration cost).** If the
   candidate alone retains positive off evidence, use it as the actual receiver,
   not as an attestation proxy for original Mail. This is a fixed staging
   blue/green migration requiring review of every name-dependent checker,
   Queue producer attachment, ingress binding and domain writer. No generic
   arbitrary Worker-name input or name-based adoption mechanism is justified.

For the second path the invariant is: **every receiver allowed to see private
input is independently current-capture-off; every receiver with send capability
uses the same held staging Mail state; external hostname/auth/data contracts
remain unchanged**. A Mail candidate cannot remain a zero-capability probe once
it becomes a receiver, so each boundary requires its own acceptance:

```text
code-free probe, off observed
  -> inert code, all invocation paths off, off re-observed
  -> reviewed Mail runtime + staging-only bindings, routes/Cron/callers still off
  -> exact version/bindings/hold/capture acceptance + independently accepted sink
  -> restricted synthetic no-send privacy canary, versions/settings frozen
  -> exact existing Custom Domain attachment + ingress service-binding cutover
  -> exact graph/hold/settings readback + bounded source-relevant regression
```

Do not attach Mail secrets/D1/R2/Email/TRACE_EVENTS to the first probe. A later
candidate runtime/config pair must preserve HTTP/wire/OIDC contracts, existing
Mail D1/R2 and ingress secret, direct-forward policy and additive migrations.
Never substitute isolated role D1, create new addresses, or change operational
contact routes. Initially omit Cron: no-route does not stop scheduled jobs.
Before enabling candidate Cron, disable/reconcile predecessor schedules under
an independently reviewed transition; do not run two implicit background owners.

The existing `trace::flush` returns without a Queue when `TRACE_EVENTS` is absent;
that source behavior does not certify the whole runtime for a no-Queue rollout.
The required bundle, migrations and all affected handlers still need hosted
contracts. If the candidate is promoted with the actual queue-api graph, the
sink and Queue ownership must be accepted first; never deploy an uncontained
producer to collect evidence that would justify deploying it.

The official [Attach Worker Domain](https://developers.cloudflare.com/api/resources/workers/subresources/domains/methods/update/)
supports targeting hostname, service and zone, and
[Get Worker Domain](https://developers.cloudflare.com/api/resources/workers/subresources/domains/methods/get/)
provides separate attachment readback. This supports an exact-hostname switch,
**not a documented atomic exchange of all references**. Existing-domain
reassignment/conflict behavior and certificate/DNS preservation must be settled
from the supported provider contract before implementation; do not detach and
recreate DNS/certificates by assumption. Domain attachment plus ingress binding
plus Cron ownership are separate operations. Freeze users of that hostname and
test routes for the bounded transition; global send hold alone does not stop
HTTP access, incoming SMTP or background work. Drain/reconcile in-flight writes;
do not assume changing a service binding revokes an old in-flight invocation.

`workers/mail-ingress/wrangler.toml` names `MAIL_API -> amail-mail-staging`; its
`MAIL_API_ORIGIN` is the stable hostname. A promoted candidate requires an exact
staging service target change and deployed ingress binding readback. The Sending
event consumer uses the same staging D1, not a Mail service binding, so changing
the API name does not itself justify redeploying that consumer. Preserve the
existing Sending subscription and do not read Queue payloads.

Rollback cannot blindly send data back to the old c3f Worker whose Issues state
is unknown. Prepare an independently accepted compatible off receiver before
cutover, or choose a narrowly reviewed temporary fail-closed service outage with
explicit SMTP retry handling. Neither is already implemented. Keep additive
data, original direct forwards and unresolved-send reconciliation ownership;
never auto-delete predecessors, purge Queues or reset holds for convenience.

## Concrete source/workflow implications (not implemented here)

- Add one guarded hosted `staging-issues-create-probe` target and a small helper
  limited to the fixed probe Worker and code-free POST/GET contract. Use the
  established staging writer/acceptance concurrency after reconciling current
  workflow locks; the older record's `deploy-mail-staging` and current
  `staging-native-mail-acceptance` groups must not become parallel loopholes.
- Keep `effective_api_settings`'s positive false semantics. Reuse pure validation
  logic but do not replace its expected Mail name or introduce a missing-as-off
  fallback. Keep `safe_observability` source checks distinct from effective
  capture checks, because provider-normalized inert preferences can differ.
- Do not extend `require_trace_containment` to accept probe evidence. It supports
  only `deploy-v1` and `settings-v1`, anchored to actual Mail, and intentionally
  cannot authorize candidate promotion. A later promotion needs a distinct
  reviewed evidence kind with immutable run/SHA/job/identity/version provenance,
  exact active receiver graph and independent current readback; no mutable
  dashboard Boolean/Variable as an attestation.
- Hosted synthetic regressions: absence versus null/false/true; duplicate keys,
  bad envelope/identity, redirects, bounded transport; existing name cannot
  create/adopt; at most one POST/no PATCH; false write followed by omitted GET
  cannot attest; isolation flags/references unknown cannot pass; raw errors and
  sensitive sentinel fixtures never print; probe result cannot satisfy original
  containment. Author such tests only if the implementation slice is delegated.

## Provider-supported alternative if representation stays opaque

Ask Cloudflare to confirm effective meaning of missing/null Issues after an
explicit false Create or PATCH and identify a supported independent read surface
or a resource-bound explicit disabled confirmation. Supply only the synthetic
request projection, fixed response categories, protected account/resource/run
identity and UTC; never mail/occurrence/request bodies or credentials. A generic
support statement that Issues is opt-in is not resource-specific effective-state
proof. A published normalization contract can justify a narrowly scoped parser
change; an account/resource-specific signed/provider confirmation needs reviewed
scope, freshness and provenance before machine acceptance.

This operational question is about an observable control-plane contract, not an
unresolved algorithmic problem. The research contribution is the discriminating
experiment and explicit separation of **intent, accepted write, independent
current state, routing identity, and runtime retention**. No academic novelty,
behavioral absence test, or invented proof system should replace provider
semantics. The retained-record privacy canary remains additional acceptance,
and public sending remains held throughout every proposed stage.
