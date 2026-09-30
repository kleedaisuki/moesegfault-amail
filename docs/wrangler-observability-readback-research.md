# Wrangler observability serialization and effective readback

Investigated 2026-09-30. Scope: public upstream source and API contracts only;
no private Cloudflare API calls, local tests/builds, configuration changes,
deployments, or pushes. Repository inspected at `6f72a80`.

## Answer and decision boundary

Wrangler **4.142.0 does not remove explicit false properties from an
observability object when constructing upload metadata or the non-versioned
settings PATCH**. Observability is managed as a script-level, non-versioned
setting in the pinned implementation. Neither the documented version-detail
response nor its Wrangler type exposes observability. Consequently, version
identity alone cannot attest the effective logging state: read current
`/script-settings`, corroborate `/settings`, and bracket the reads with an
unchanged deployment containing precisely the expected version at 100%.

The official GET schemas allow an **absent** observability property. They do
not specify that omission means disabled and do not document a `null` value or
false-to-null normalization rule. Thus absence is a permitted response shape,
not by itself documented evidence of disabled capture. The present strict
checker can reject a legitimate disabled representation, but accepting every
missing/null representation without additional evidence would be unjustified.

The parent reports fixed-category live results from run `36730461386`:
`/settings` observability missing, `/script-settings` observability non-dict,
and stable 100% version prefix `c3f6401a`. These observations were not queried
or independently verified here. In particular **non-dict does not distinguish
missing, null, Boolean, number, or array**. The next discriminating probe should
report presence and JSON type only, separately per endpoint, plus unchanged
serving identity; it must not print raw metadata or response bodies. Provider
normalization remains an unresolved server behavior, not proof of an unsafe
deployment or permission to loosen the gate indiscriminately.

## Pinned source evidence

CI and `site/package.json` pin Wrangler 4.142.0. Upstream tag
`wrangler@4.142.0` resolves through annotated tag
`635ba310aa95a2c428298410444efff517f6c3ed` to commit
`f96458cefb7eaffc611f38f59f41d573dfa8b112`.

| Source at that commit | Relevant behavior |
| --- | --- |
| [`packages/wrangler/src/deployment-bundle/create-worker-upload-form.ts`](https://github.com/cloudflare/workers-sdk/blob/f96458cefb7eaffc611f38f59f41d573dfa8b112/packages/wrangler/src/deployment-bundle/create-worker-upload-form.ts) | Re-exports implementation from deploy-helpers; inspecting only the old Wrangler file would miss the actual serializer. |
| [`packages/deploy-helpers/src/deploy/helpers/create-worker-upload-form.ts`](https://github.com/cloudflare/workers-sdk/blob/f96458cefb7eaffc611f38f59f41d573dfa8b112/packages/deploy-helpers/src/deploy/helpers/create-worker-upload-form.ts#L906) | Metadata includes `...(observability && { observability })`. A nonempty object containing false flags is truthy; the object is passed unchanged. This does not establish how the server stores it. |
| [`packages/deploy-helpers/src/deploy/deploy.ts`](https://github.com/cloudflare/workers-sdk/blob/f96458cefb7eaffc611f38f59f41d573dfa8b112/packages/deploy-helpers/src/deploy/deploy.ts#L553-L565) | New versions/deployments API branch patches non-versioned settings after creating the deployment; sends `worker.observability ?? { enabled: false }`. An explicit object is preserved. PATCH errors in this branch are caught with a warning, so deploy success/version output is not sufficient settings evidence. |
| [`packages/deploy-helpers/src/deploy/helpers/versions-api.ts`](https://github.com/cloudflare/workers-sdk/blob/f96458cefb7eaffc611f38f59f41d573dfa8b112/packages/deploy-helpers/src/deploy/helpers/versions-api.ts#L164-L184) | `NonVersionedScriptSettings` includes `observability: Observability`; PATCH endpoint is `/accounts/{account}/workers/scripts/{name}/script-settings`, with `JSON.stringify(settings)`. JSON serialization retains Boolean false. |
| [`packages/wrangler/src/versions/deploy.ts`](https://github.com/cloudflare/workers-sdk/blob/f96458cefb7eaffc611f38f59f41d573dfa8b112/packages/wrangler/src/versions/deploy.ts#L604-L637) | `maybePatchSettings` removes undefined top-level entries only, passes `config.observability`, and labels the operation non-versioned. |
| [`packages/deploy-helpers/src/deploy/helpers/versions-types.ts`](https://github.com/cloudflare/workers-sdk/blob/f96458cefb7eaffc611f38f59f41d573dfa8b112/packages/deploy-helpers/src/deploy/helpers/versions-types.ts) | `ApiVersion.resources` has bindings, script and script_runtime; no observability member. |
| [`packages/wrangler/src/__tests__/versions/versions.deploy.test.ts`](https://github.com/cloudflare/workers-sdk/blob/f96458cefb7eaffc611f38f59f41d573dfa8b112/packages/wrangler/src/__tests__/versions/versions.deploy.test.ts#L1793-L1849) | Mock-based disabled-observability case expects the CLI to display enabled false. It supports client handling, not real server GET normalization. No upstream tests were executed. |

## Official REST contract versus inference

The current [Get Worker Script Settings](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/get/)
page documents **GET `/script-settings`**, despite its resource-path name.
Its result is `ScriptSetting`: optional logpush, observability, tags and tail
consumers. Observability, when present, is an object with a required Boolean
enabled; logs is optional and, when present, has required Boolean enabled and
invocation_logs. No disabled response example or normalization rule is given.

The [Get Worker Script and Version Settings](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/script_and_version_settings/methods/get/)
page documents **GET `/settings`**. It includes bindings/runtime metadata and
an optional observability object. The similar endpoint names are not evidence
of identical response shape. No version UUID parameter is provided by either
settings endpoint.

[Get Worker Script Version](https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/get/)
documents GET `/versions/{version_id}` with bindings, script and runtime
resources, not an observability setting. [Versions and deployments](https://developers.cloudflare.com/workers/versions-and-deployments/)
distinguishes uploaded versions from serving deployments; a deployment can
split traffic. The justified inference is that a frozen stable deployment plus
current non-versioned settings reads attests an observed interval, not an
immutable per-version observability snapshot or future privacy behavior.

## Reproduction without installing or executing a toolchain

Retrieve individual public files from
`https://raw.githubusercontent.com/cloudflare/workers-sdk/f96458cefb7eaffc611f38f59f41d573dfa8b112/`
using the paths above. Temporary downloaded artifacts are under repository
`.cache/observability-source/` (untracked); durable provenance is the immutable
upstream commit and line references. Useful text searches: `observability`,
`NonVersionedScriptSettings`, `script-settings`, `maybePatchSettings`, and
`canUseNewVersionsDeploymentsApi`.

Independent next checks must keep three claims distinct: (1) the reviewed
source sends disabled intent; (2) provider readback represents disabled
effective capture; (3) a whole-retained-record synthetic canary confirms no
new private HTTP context persists. This investigation resolves the first and
the endpoint/serving scope; it does not resolve the second or third.
