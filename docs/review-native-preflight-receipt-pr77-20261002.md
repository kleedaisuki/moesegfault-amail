# Independent PR 77 receipt repair review

## Verdict and frozen coordinates

GO for the bounded source receipt repair only. No substantive defect found.
Reviewed clean worktree `.temp/native-retention-actual`, exact HEAD
`89f3a2462e3c0a5182770a6d26b45d4fd0a4c894`, against original main
`731c437786e5a521ab40c97838b11ccd002172b7`. This is not admission for a new
provider operation, Mail deployment, release or native-retention acceptance.

## Contracts traced

- `infra/deploy/native_tracing_experiment.py:deploy` writes build identity and
  orchestration identity with attempted / mutation_admitted=false before Provider
  construction or provider prereads. Build/environment receipt prerequisites remain
  before provider access. Ordinary configuration/read/schema exceptions persist
  refused without copying exception text; interruption leaves attempted, also a
  valid no-write boundary.
- Verified / mutation_admitted=true is persisted only after complete original
  preflight succeeds, before DNS create or Wrangler script deployment. Existing TLS,
  inventory completeness, conflict, exact script-404 and ownership gates are not
  weakened. Read admission still does not establish write permission.
- `Provider.request` copies fixed endpoint/resource enums, method, UTC times,
  monotonic duration, numeric HTTP status, bounded CF-Ray and numeric error codes.
  SSL settings and certificate inventory have separate fixed resource enums. No
  raw path/query/URL, body, credential, arbitrary error prose is newly retained.
  `control_plane_trace.response_facts` validates the public CF-Ray field.
- `cleanup` attempted/refused branch executes before Provider construction. It
  requires literal false mutation admission, empty versions and no DNS/Route/url/
  cases coordinates, refuses contradictions, records absence_verified=false, and
  does not write cleaned_at. Legacy absent-state and verified receipts retain the
  existing script/ingress recovery path. Unknown write receipts remain under
  nonce/exact ownership and single-attempt recovery contracts.
- The unchanged workflow always runs cleanup and artifact upload. New no-write
  receipt persistence can therefore survive the original ordinary preread failure.

## Independently inspected hosted evidence

[CI 36898299693](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36898299693)
and [syntax 36898299011](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36898299011)
are completed success on the exact reviewed HEAD, confirmed through GitHub metadata.
Infrastructure job 110490778035 logs were downloaded to the sibling
`hosted-infra-36898299693.log` review artifact. Discovery ran 1,151 tests in 9.910s;
new every-preread 403/timeout, TLS/schema/conflict, SSL 403/9109 sanitization,
missing-context, workers.dev compatibility and contradictory receipt fixtures all
passed. Existing first-DNS-write ordering, lost-create-ack, malformed-create-ack,
unknown-DNS cleanup and unknown-delete fixtures also passed. Tests use mocked
provider transport; they are source contracts, not provider acceptance.

The original [actual run 36896672169](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36896672169)
failed logs were independently inspected: zone GET returned 200; the next TLS
settings GET returned 403 / [9109], before mutations and before old receipt creation.
Its no-op cleanup is not provider absence verification. The historical artifact-zero
fact is documented in `docs/native-route-actual-36896672169.md`; this review's
additional GitHub artifact API read returned EOF, so it does not claim an independent
new artifact-list confirmation.

## Platform grounding and limits

[Cloudflare SSL settings API](https://developers.cloudflare.com/api/resources/ssl/subresources/universal/subresources/settings/methods/get/)
was checked: its accepted grants are SSL and Certificates Read or Write. Neither
that documentation nor the zone GET identifies the existing token's actual policy
or proves later provider read/write admission. No token/policy introspection was
performed. This finite state/receipt repair does not require a speculative new
tracing research mechanism; actual retained native records remain the missing
empirical evidence for any future extractor design.

Canonical repository maintainer/amail skills, infrastructure foundation and actual
failure/realm notes were read. The owner's original account is production Identity;
its rejected staging login is a realm mismatch, not an established authentication
bug. This review performs no provider operation, GHA dispatch, local project runtime,
local build/install or production edit. It assesses source plus existing hosted
fixtures only. Existing direct receipt writes are not made crash-atomic by this PR;
that pre-existing persistence characteristic is not claimed newly verified or fixed.
