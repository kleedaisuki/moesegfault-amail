# Decision: distinguish synthetic experimentation from Mail privacy acceptance

Date: 2026-10-01. Base: `d3e2f7d5a585393e553284ed1e7ba40cd8b59bff`.
Status: **reviewed-scope recommendation, not deployment authorization or an
effective-settings/privacy attestation**. This investigation made no private
provider request, mutation, local project test/build, mail send, or push.
It reused the existing incident documents and inspected the Mail source/config
and containment gate before checking current public Cloudflare documentation.

## Decision in one paragraph

A successful, pinned Wrangler deployment with explicit
`observability.issues.enabled=false` implements Cloudflare's documented disable
procedure. It can supply **procedure-completed evidence**, even if a later GET
omits Issues. It cannot supply an explicit-disabled read observation or justify
interpreting omission as false. A genuinely isolated, entirely synthetic
experiment may proceed with the effective Issues state still unknown, because
its safety comes from excluding sensitive data and capabilities, not from
pretending the unknown switch is off. **The existing held
`amail-mail-staging` deployment is not such an experiment**: its public entry,
Identity authentication, Mail storage/bindings, and scheduled/background work
are not isolated by the outbound hold. Do not dispatch the existing staging
rollout as a synthetic-only privacy exception. Keep production/public release
blocked; the next decision-bearing step is the exact Worker's official Issues
setting page, followed by provider clarification if ambiguous, not another
equivalent API probe or an unmodified deployment.

## The requirement and the current evidence policy are different

The product requirement is that debugging/telemetry do not retain sensitive
mail content or secret-bearing user context outside the approved handling
boundary. The implementation uses typed Queue events plus a separate sink to
avoid public Fetch-context enrichment. Requiring every GET response to contain
the literal Boolean `issues.enabled=false` is our machine acceptance rule,
not an independently documented Cloudflare response guarantee.

The current [Get Worker API](https://developers.cloudflare.com/api/resources/workers/subresources/beta/subresources/workers/methods/get/)
allows an optional Issues object/flag without assigning absence a meaning.
The official [Issues investigation guide](https://developers.cloudflare.com/workers/observability/issues/investigate/)
explicitly documents false plus a Wrangler deployment as the disable procedure.
Its [overview](https://developers.cloudflare.com/workers/observability/issues/)
also explains that deployment without Issues opt-in turns off dashboard-enabled
Issues. Both raw official documents were freshly read from the Cloudflare
documentation repository when the rendered pages were unavailable:
[overview source](https://raw.githubusercontent.com/cloudflare/cloudflare-docs/production/src/content/docs/workers/observability/issues/index.mdx),
[investigation source](https://raw.githubusercontent.com/cloudflare/cloudflare-docs/production/src/content/docs/workers/observability/issues/investigate.mdx).

This supports a documented **operational procedure**, not a server
normalization rule. It does not establish that the spent PATCH applied the
member, nor that a version's bindings encode Worker-level observability.
Cloudflare's guide also makes Issues independent of Logs/tracing and permits
request/invocation context in failure occurrences. Logs=false alone is therefore
not the privacy boundary. Disabling collection does not erase old occurrences.

Use separate evidence fields instead of a misleading scalar pass:

| Evidence | Meaning | What it does not mean |
| --- | --- | --- |
| `disable_procedure=completed` | Exact reviewed source/config, supported deploy success and immutable operation provenance | Independent effective Issues-off readback |
| `issues_readback=omitted` | The independent current Worker GET lacks the object/member | Enabled, disabled, ignored write, or unavailable feature |
| `synthetic_window=passed` | Required safe events present and markers excluded in a complete bounded retained view | Exclusion for all future requests/failures |
| `sensitive_admission=excluded` | Reviewed capabilities, entry points and fixture ownership exclude sensitive data for this experiment | Privacy acceptance for another Worker or public Mail |

Changing the existing gate to recognize a new evidence kind would require
explicit design review and hosted contract tests. Do not reuse its `deploy-v1`
or `settings-v1` attestation to encode a weaker claim.

## Why held staging is not synthetic-only

At the inspected source, `crates/mail-worker/wrangler.toml` explicitly disables
Issues for both realms, but staging still declares a Custom Domain, Identity
issuer/client, Mail D1/R2, Email capability, a trace Queue producer and Cron.
The runtime accepts requests through `main -> dispatch` and emits diagnostics
after dispatch. The config does not establish a synthetic-admission quarantine.

- Global send hold restricts outbound submission; it does not stop inbound
  mail, bearer-bearing requests, mailbox reads, semantic background work, or
  scheduled storage/reconciliation paths.
- A synthetic test principal's real bearer token/password/OTP remains a secret.
  Fictional mail body markers do not make the invocation's whole context public.
- A public endpoint can receive unplanned requests. Review of our fixture does
  not control every caller's headers, path or body.
- Exact code/version/binding readback proves which program/capabilities are
  serving, not that independently captured Issues request context is absent.

Consequently the proposed full Mail rollout plus a canary cannot obtain
synthetic-only safety merely by keeping sending held. This conclusion is about
capabilities and admitted data, not a belief that missing Issues means enabled.

## A bounded experiment is possible, but its claim must stay bounded

If a separately reviewed synthetic experiment is worthwhile for another
question (for example Queue enrichment), it need not wait for a universal
all-off read representation. Its admission contract must instead include:

1. A separate fixed identity; no replacement/cutover of the current Mail Worker,
   Custom Domain, production operational forwards or routing ownership.
2. No public Fetch/preview entry, existing mailbox/Identity bindings, real
   account authentication, mail credentials, provider write capability or
   business scheduled/background triggers. All available invocation paths must
   be inventoried; `workers_dev=false` alone is insufficient.
3. Only generated nonsecret fixtures and a reviewed closed typed envelope enter
   the target. If a scoped binding/credential is technically unavoidable, its
   inclusion in request/platform context is a separate secret-handling review,
   not silently covered by the word synthetic.
4. Exact reviewed SHA/config, hosted checks, explicit Issues=false deployment,
   single-version/binding and Logs/traces/export readback, a writer freeze,
   one bounded run/window, full-record inspection with fixed-only public output,
   restoration/retention handling and an attributable owner.
5. Missing, incomplete or inaccessible retained evidence remains UNVERIFIED.
   A pass is about this target/window; do not transfer it to c3f, private-mail
   acceptance, production or release attestations.

This is **not** a recommended new probe simply to bypass the Issues dispute.
An empty/nonprivate experiment cannot distinguish disabled Issues from enabled
Issues that saw no eligible failure. A canary can reveal a leak; finite passing
executions are not a general proof of confidentiality. The underlying research
distinction is consistent with Clarkson and Schneider's
[Hyperproperties, Journal of Computer Security (2010)](https://www.cs.cornell.edu/fbs/publications/Hyperproperties.pdf):
information-flow requirements cannot generally be reduced to one execution's
ordinary trace property. This is a reasoning aid, not a claim that the Mail
system has been formally verified.

## One provider-supported next step, then stop

Read **the exact `amail-mail-staging` Worker's** official Observability -> Issues
setting/onboarding page without toggling it or opening occurrence details.
Record only identity/version bracket, UTC/operator and its bounded state
(`enable_control_present`, `enabled_control_present`, or `unresolved`). An empty
issue list is not setting evidence. If the UI only defaults the same missing
API field, it is not an independent authoritative answer.

If this remains ambiguous, ask Cloudflare support for the effective-state
contract using the existing accepted false write and omitted GET reproduction:
does the omitted field represent disabled state for this resource, and what
supported read surface confirms it after the documented disable procedure?
Keep the reproduction and run provenance private and metadata-only; omit mail,
tokens, provider bodies and occurrence context. A provider-confirmed contract
can justify a narrow new gate, with immutable provenance and freshness tests.
Do not repeat PATCH/create/list/deploy operations unchanged while awaiting it.

Underlying live outcomes remain exactly those in
[the current Worker correction](staging-current-worker-issues-alternative.md),
[omission semantics](issues-false-omission-semantics-2026-10-01.md),
[the create-time discriminator](staging-issues-no-route-discriminator-2026-10-01.md)
and [the release audit](release-gap-audit.md). The stopped create-time run did
not send a create POST. This reassessment invents no new live evidence and
does not supersede the Queue design's full retained-record acceptance.
