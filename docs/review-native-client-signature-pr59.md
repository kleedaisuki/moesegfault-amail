# Independent review: absent-host client-signature diagnostic (PR 59)

Reviewed PR 59 final head `7caa5be` (implementation `09fbfa13189ce0f82ea85aaeacd394dfa5bc983a`, final follow-up documentation only), in `.temp/native-tracing-foundation` on 2026-10-01. Scope: four changed paths, surrounding Provider/diagnostic/trigger/main code, workflow lock and capability ordering, tests and explicit interpretation ledger. Source-only: no provider requests, local runtime tests/builds, credential reads, deployments or merge.

## Verdict

**No demonstrated substantive blocker found.** This is a narrow, separately confirmed anonymous GET diagnostic, not a live invocation workaround or relaxation of normal artifact admission.

| Contract | Source evidence |
| --- | --- |
| Separate operation/confirmation | `main` requires hosted main, attempt 1 and exact operation-specific confirmation. The client-signature confirmation refuses deploy/trigger/collect/cleanup/default diagnosis. Workflow job independently enforces the same context. |
| Positive absence before GET | Both fixed script settings must return HTTP 404; successful settings, denied reads and any non-404 error refuse public access. Account subdomain is read from the provider and restricted to a fixed DNS-label grammar; no arbitrary URL/path input exists. |
| Writer scope | Diagnostic uses the unchanged workflow-level `amail-native-tracing-experiment` writer group, cancellation disabled. This excludes participating same-repository experiment writers; it is not proof against out-of-band account writers. No new concurrent provider writer was added. |
| Credential separation | Provider credentials exist only in the relevant diagnostic step/environment and are used for exact provider GET reads. The anonymous GET is a fresh Request/opener, without Authorization/cookie/body or provider token. Redirects remain disabled. |
| One bounded discriminating request | Three control-plane GET reads precede one bounded public GET. Variant adds only fixed self-identifying User-Agent, no arbitrary header input, retries, request sweep, policy change or route creation. Default-urllib profile remains available and normal canary POST is unchanged. |
| Truthful receipt | Receipt records source/run, checked absent state, fixed public hostname, chosen client profile and reviewed response facts. Raw error prose/challenge payload/cookies/Location values are excluded. A 404/1010/other result is an observation, not native/runtime/privacy acceptance. |
| Source regression contracts | New tests assert profile/header/method/body, one opener call, only provider GETs, refusal for present scripts/failed provider reads and operation-specific confirmation. They are hosted contracts, not proof of actual variant behavior. |

## Evidence/interpretation limits

Coordinator supplied actual baseline run `36877264235`: scripts absent, default anonymous GET HTTP403 with complete numeric body1010, no Worker invocation. This review did not fetch its receipt independently. Official [Cloudflare 1010 documentation](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/) attributes 1010 to browser-signature denial. That supports the chosen User-Agent discriminator, but does not identify the shared workers.dev policy owner or grant authority to modify their settings. It also does not retrospectively classify previous unparsed POST bodies.

A later variant404 would support header-sensitive denial on this **absent-host GET**, not successful live POST execution or native spans. Baseline and variant from different hosted runs can differ in source IP/edge/time; they are a useful discriminator, not a controlled same-session causal experiment. Do not sweep profiles or automatically recreate/retry the pair when1010 persists. Any ordinary client identity change and owned-custom-domain interoperability check remain separate product changes.

The next normal canary after integrating runtime/source changes needs the new full-main compiled artifact; this diagnostic provides no build reuse exemption. Native API availability, four cohort receipts, retained pair-wide native parentage/privacy records and receipt-owned cleanup still require actual admitted experiment evidence.
