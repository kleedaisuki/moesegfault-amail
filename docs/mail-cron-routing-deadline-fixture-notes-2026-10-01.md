# Cron Routing deadline hosted fixture

Date: 2026-10-01. Status: authored and syntax/static checked only. No local
project runtime tests, builds, provider calls, deployments, commits, or pushes.
An exact-head hosted result is required before calling these tests passing.

## Boundary and reuse

`infra/tests/worker-boundary/routing-deadline.test.mjs` runs the existing built
Rust/Wasm shim through the pinned Miniflare/workerd dependency. Its companion
`routing-deadline-observer.mjs` subclasses and forwards that unchanged shim.
The isolated `pnpm test:routing-deadline` script is a separate non-deploying step
in the existing source Worker CI job, after bundling. It is not added to the
broad boundary suite and is not an operator/provider workflow.

The fixture reuses `migration-fixture.mjs`, `worker-module-rules.mjs`, the
maintenance-liveness fixture's native D1 proxy pattern, and the native observer
approach established by [the embedding cancellation investigation](embedding-cancellation-oracle-2026-10-01.md).
Its first-entitlement expectations come from [the admission policy](mail-cron-admission-policy-notes-2026-10-01.md).

Every test constructs fresh synthetic D1/R2 bindings and applies real migrations.
The migration's global send policy is asserted `held`; no EMAIL binding exists.
Embedding work is locally blocked. Network calls are accepted only for exact
synthetic zone list URLs or the single fixture's known-ID GET/DELETE URL. There
is no fallback forwarding. Identity, SMTP, external embedding and redirect
egress fail the fixture. Setup and database readback use unwrapped bindings and
do not enter statement counters. The historical scheduled slot satisfies
`floor(slot / 300000) % 8 == 0`, so addresses enters first even on delayed runs.

## Discriminators and exact authored expectations

Counts below are expectations to be checked in hosted execution, not observed
measurements. Every invocation also requires a later native provider-event
cleanup submission and verifies deletion of the seeded old event. Native Routing
submission count must equal strict-stub request count and remain at most twenty.

| Scenario / invocation | Routing requests | Address SQL submissions | Expected result |
| --- | ---: | ---: | --- |
| Ten valid 50-rule pages, each delayed 2 s | 10 | 7 | First row becomes active after a complete real >20 s inventory; second remains provisioning and priority due |
| Fast following invocation | 1 | 5 | Only second row is claimed/promoted; first is not replayed |
| Headers hang | 1 | 5 | Exact attached native signal aborted once around 10 s; both unattempted rows priority released |
| Headers take 7 s, then body prefix + hang | 1 | 5 | Same overall 10 s timer (<16 s including overhead); an incorrect restarted 10 s body timer needs >=17 s and fails; native prefix/read/cancel/release plus both row releases |
| Ten pages delayed 3.2 s each | 10 | 5 | Original inventory deadline aborts last exchange around 30 s; neither row promoted or treated as absent |
| DELETE accepted, acknowledgement body hangs | 3 | 5 | List + owned GET + one DELETE; journal stays deleting with its finite future slot |
| Immediate tick after unknown DELETE | 1 | 2 | Inventory only; current lease is not claimed/retried |
| Due tick after successful empty inventory | 1 | 4 | Deleting becomes retired with no saved rule and no second DELETE |
| Oversized streamed inventory | 1 | 3 | Native 256 KiB crossing, no subsequent native read, one fulfilled cancel and one lock release; no repair |
| Foreign 302 redirect | 1 | 3 | Redirect is not followed and cannot authorize any repair |

The successful ten-page inventory contains 500 unique rules: two exact enabled
owned rules and 498 clearly unowned fillers. Both favorable owned rules are on
the first page; the 30 s test therefore checks that even favorable partial
inventory cannot authorize promotion. The 20 s test is specifically **inventory
plus useful first repair**, not inventory-only replay. Provisioning with a
validated enabled rule promotes directly from inventory; no unnecessary per-ID
GET is added merely to make a test look more substantial.

For the two-row scenarios the exact counted lease contract is:

```text
initial SELECT bind: scanAt
each claim:         due = scanAt + 300000, expected old cutoff = scanAt
priority release:   due = scanAt - 1, expected exact old slot = scanAt + 300000
```

The slow success's seven address statements are initial SELECT, two claims,
one positive-inventory lifetime-discovery SELECT, second due SELECT, one
promotion, and one release. A timed-out initial inventory has initial SELECT,
two claims, two releases and no discovery or row repair. Non-time failures
(oversize/redirect) preserve the established finite future slots; their three
statements are initial SELECT and two claims. A genuinely attempted unknown
DELETE retains its future slot rather than being misclassified as unattempted.
The due tick in the DELETE test advances the fixture row with setup SQL rather
than substituting a production clock or adding a production test knob.

## Native evidence and observer invariants

The observer tags only exact synthetic Routing fetch signals and returned native
response streams. WeakMaps associate the acquired native reader and exact signal
with each native exchange. It records fixed numeric counts: byte totals, reads
after the byte-cap crossing or cancellation, acquisition, cancel promise
settlement, successful release, abort calls and aborted attached signals. It
never performs cancellation, rewrites fetch arguments, substitutes streams,
injects timeouts, or changes the production clock. SQL proxies preserve native
constructor identity, bind semantics and actual native batch submissions.

Successful inventories are a negative control: no abort or cancel is expected.
For body timeout, native cancellation may fulfill or reject after an already
aborted native stream; exactly one settled cancellation and one release are
required. The oversize test requires fulfilled native cancellation, not merely a
call. Coalesced native chunks are allowed; the fixture does not hard-code a read
count or assume Node chunk boundaries survive the bridge.

Node outbound-service `ReadableStream.cancel()` is deliberately **not** used as
the cancellation oracle. Independent teardown closes hanging Node sources and
resolves hanging synthetic header responses so the bridge can be disposed. This
is fixture resource cleanup, not evidence that a real provider stopped work.
The rationale and exact pinned upstream source mapping are preserved in the
embedding cancellation note linked above. The relevant native API contract is
[Cloudflare's reader documentation](https://developers.cloudflare.com/workers/runtime-apis/streams/readablestreamdefaultreader/).

## Time windows and limitations

Timing is measured around the scheduled invocation, not Miniflare construction
or migrations: slow success >=20 s and <35 s; a header/body timer >=9 s and
<16 s; original full-inventory cutoff >=29 s and <39 s. Upper bounds include
hosted RPC/timer overhead; exact timeout constants are additionally discriminated
by attached signal abort and safe journal outcomes. A separately rolling 30 s
timer would finish all pages without abort and wrongly promote, so it fails even
though 32 s alone would fit the generous wall-time upper bound.

The ten 3.2 s-page assertion expects page ten to start before 30 s. Substantial
host overload consuming the approximately 1.2 s gap before that last page can
cause a pre-submit denial instead, which is safe production behavior but would
fail this focused exact-count discriminator. Investigate hosted evidence rather
than automatically loosening counts or adding sleeps until green.

These tests do not prove a hard global 120 s bound, arbitrary external-clock
behavior, real-provider physical cessation, platform-buffer memory bounds, or
every foreground/mutation error mapping. They do not directly expose the
internal call-budget debit for pre-submit denial; the hosted oracle counts
actual native submissions while source policy tests own zero-debit admission.
The isolated fixture adds native oversize and redirect coverage; it does not
claim a lying Content-Length transport test. A Node bridge can enforce or
rewrite HTTP framing independently, so such a fixture requires a separately
validated native transport mechanism rather than a misleading Node header.
Existing broad address tests continue to cover inventory scope/caps and
foreground behavior. No new dependency or production configuration is added.

## Verification actually performed

- `node --check infra/tests/worker-boundary/routing-deadline.test.mjs`
- `node --check infra/tests/worker-boundary/routing-deadline-observer.mjs`
- `git diff --check` (shared worktree; only existing CRLF normalization warnings)

No runtime pass is claimed. The next step is exact-head hosted source CI using
the existing build step and new isolated script, followed by review of timing,
native cancellation/abort counts and exact journal/statement evidence.
