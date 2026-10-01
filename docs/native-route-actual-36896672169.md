# Actual native Route preflight refusal: run 36896672169

Status: actual hosted no-write preflight refusal; native API, retained spans and
privacy remain unexecuted. This is not a deployed Route/permission/cleanup verdict.
Recorded from the exact completed GitHub run and accepted source; no provider API
was called by this observer, and no local runtime/build/install/tests were run.

## Identity and actual boundary

| Coordinate | Observed fact |
| --- | --- |
| Workflow | `native-tracing-canary.yml`, `RUN_NATIVE_TRACING_ROUTE_CANARY`, attempt 1 |
| Actual operation | [36896672169](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36896672169) |
| Orchestration source | `731c437786e5a521ab40c97838b11ccd002172b7` (merged PR 74) |
| Original fully checked build | CI `36890517434`, source `5a2396a7c5d3527b9988c55984abb4a84159d327` |
| Consumed build artifact | `11175843705`; restore and every-byte verification passed |
| Build verifier facts | `worker-native-artifact/v1`, 35 files, Rust `1.98.1`, worker-build `0.8.5` |
| Run time | 2026-10-01 17:04:23--17:05:08 UTC; job 17:04:31--17:05:07 UTC |
| Hosted source checks | Successful before provider capabilities |
| Failure | Second preflight provider GET, Universal SSL settings, HTTP 403 / code 9109 |
| Native cases/collection | Both trigger modes and collection skipped |
| Safe receipt artifact | None: upload reports no `experiment.json`; artifact API `total_count=0` |

The actual GHA date is October 1 UTC (October 2 in Asia/Singapore), not an inferred
date from the task label. The downloaded compiled artifact is not a tracing receipt.

Actual control-plane records in the deploy step (not synthetic unit-test output):

| Operation | UTC interval | Status / duration | Public correlation |
| --- | --- | --- | --- |
| Exact zone GET | 17:05:03.122352--17:05:04.108674 | 200 / 986.343 ms | CF-Ray `a43d0ccadc7faccd-DFW`, span `895bca8c228945f5` |
| Universal SSL settings GET | 17:05:04.108937--17:05:04.372597 | 403 / 263.680 ms; HTTPError; `[9109]` | CF-Ray `a43d0cd0f97267c5-DFW`, span `562e0855794e42c1` |

Both have trace ID `b6a457e250b742a5985d5c635b60b2ae`. No arbitrary provider
prose, credential, user identity, mail, exception body or account ID is copied here.

## What the failure does and does not establish

`infra/deploy/native_tracing_experiment.py:deploy()` constructs the provider,
then calls `ingress.preflight()` before creating its receipt. The current
`preflight()` checks the exact zone object and then calls `ssl_ready()`;
the refused settings GET occurs before certificate inventory, DNS/Route/domain
inventories and initial script absence checks. All source mutation paths follow
successful full preflight and receipt creation. Consequently this invocation
performed no DNS create, pair deployment, Route create, public POST or DELETE.

The zone response passed the source's expected account/active/full/unpaused checks;
zone access is not evidence of SSL-read access or DNS/Route write capability.
The SSL refusal is not proof that Universal SSL is disabled or absent. Certificate
coverage, DNS/Route conflicts and script absence remain unverified in this run.
The Rust getter, service binding, sampling, async context, fixed exception and
provider span representation were never exercised. There is no actual retained
native shape from which to derive an extractor.

The always-cleanup step is green, but `cleanup()` returns immediately when the
receipt file is missing. Its success means **no cleanup was needed for this
source-proven no-write path**, not a new provider verification of resource absence.
There is no owned object, unknown mutation or unresolved cleanup from this run.
Do not infer that the reserved hostname is globally free without fresh admitted
inventories in any later operation.

## Discriminating next actions

1. Preserve a safe preflight receipt before reads and record a typed attempted /
   refused / verified boundary, preserving the original build and orchestration
   identities. Retain only fixed endpoint, method, timestamps, HTTP/error-code
   facts and public causal coordinates. Do not store raw exception/provider text.
2. A preflight-refused receipt must explicitly mean no mutation admitted. Cleanup
   must not turn that new receipt into script GETs/deletes or claim verified
   resource absence. Existing attempted/unknown-write recovery remains separate.
3. The root may resolve the exact existing credential's admitted SSL-read
   capability through the owner-approved policy. The documented settings endpoint
   accepts `SSL and Certificates Read` or `SSL and Certificates Write`; this
   observation does not identify the token's actual grants and does not justify
   minting a token, adding Secrets, broad policy introspection or bypassing TLS.
4. Do not redispatch this same failing operation as a diagnostic. No header/WAF/
   global-fetch changes or workers.dev replay can resolve a control-plane GET
   refusal. If the root later admits an operation after resolving this boundary,
   retain all full prereads and source-owned single-attempt write/cleanup gates.
5. Only actual four-case and scoped retained-record evidence can support the
   next typed native-extractor implementation. Until then, async/error/privacy
   acceptance and Mail debug/deploy/send/release remain deferred.

The bounded source receipt repair is actionable from this run; implementation
requires root approval and hosted regression evidence. It must cover early GET
403, failed/malformed inventories, no provider cleanup for preflight refusal and
unchanged unknown-write recovery. This note is evidence, not authorization.

## Sources and reproduction

Read-only GitHub observations used:

```powershell
gh run view 36896672169 --json status,conclusion,createdAt,updatedAt,headSha,jobs,url
gh run view 36896672169 --log-failed
gh api repos/kleedaisuki/moesegfault-amail/actions/runs/36896672169/artifacts
```

Full logs contain credential-free unit-test fixtures as well as actual operations;
classify only deploy-step `cloudflare.canary` records as the actual prereads.
The source files are `infra/deploy/native_tracing_experiment.py`,
`infra/deploy/native_route_lifecycle.py` and `.github/workflows/native-tracing-canary.yml`.

Primary documentation checked 2026-10-02:
[Universal SSL settings API and accepted permissions](https://developers.cloudflare.com/api/resources/ssl/subresources/universal/subresources/settings/methods/get/).
This finite failure requires operational permission/receipt reasoning, not a new
academic tracing mechanism or guessed telemetry framework.
