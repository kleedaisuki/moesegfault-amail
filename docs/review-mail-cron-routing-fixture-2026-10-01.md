# Independent review: Cron Routing hosted deadline fixture

Date: 2026-10-01. Worktree: `.temp/cron-liveness-implementation`.
Base `13b2c284`; reviewed committed HEAD
`4fe000b0f6e42d43d304cba4060f4c8b3714ca08`, including fixture commit `4fe000b`
and production source `f4a1dcd` only as context for expected observations.
No production implementation approval is implied by this fixture review.

Initial snapshot SHA-256:

| File | SHA-256 |
| --- | --- |
| `routing-deadline-observer.mjs` | `72267F7544D5ED52126DE35727271F8512B9F267DCDC02008FA20F1AFB44E90C` |
| `routing-deadline.test.mjs` | `585F7A43B2CDB145874F9F286E7FF99AE92C3923DB74243EBB5799980BC5DADB` |

## Decision and actionable finding

**GO for exact-head nondeploying hosted source CI at
`3d95e3dc19ee2182ffdfe3a878d25874227c8394`.** The initial P2 discriminator gap
below is resolved; no remaining substantive fixture blocker was found. Approval
does not authorize merge/deploy and is not hosted-runtime pass evidence.

### Resolved P2: The initial body-stall window accepted a freshly reset body timer

Location: `routing-deadline.test.mjs`, header/body stall loop: body response's
`sleep(3000)` and common elapsed assertion `>=9000 && <16000`.
Confidence: high; independent arithmetic and unchanged remaining assertions.

The body case claims to distinguish one total ten-second exchange deadline from
a body timer reset after headers. However, an incorrect implementation with
three seconds of headers followed by a fresh ten-second body timer would return
around thirteen seconds. It would pass the 9-16 second window, exact attached
signal abort, pending native reader/cancel/release, two priority releases and
five SQL assertions. Thus a meaningful regression in this central contract is
not rejected by the candidate fixture.

Keep the overhead window but consume enough header time (for example seven
seconds) that a reset body timer exceeds sixteen seconds, or choose a justified
body-case upper bound below thirteen seconds. Update fixture notes to match the
chosen scenario. The header case should remain its independent ten-second
discriminator. Do not claim a runtime result from this static correction.

Independently re-reviewed correction `3d95e3d`: only body-case header delay and
its explanatory comment change from three to seven seconds; fixture notes table
is synchronized. The incorrect reset now takes approximately seventeen seconds
before returning, outside the unchanged sixteen-second upper bound, while the
correct shared timer remains ten seconds. Native prefix and pending-read checks
still require headers actually to arrive before timeout. The header-stall case,
SQL/priority/abort assertions and production source `f4a1dcd` are unchanged.
This resolves the concrete coverage gap without loosening evidence.

Final test SHA-256:
`D2987ECE66CE6438739046E43E30766258F9F857E3069D62C33A801AE5295263`.
Observer retains its initial hash above. Both modules' `node --check` and
`git diff --check` were rerun successfully at the exact corrected HEAD.

## Contracts independently checked

- Searched relevant notes first and reused `embedding-cancellation-oracle-2026-10-01.md`
  and existing native liveness review. Inspected full modules, package/CI changes,
  exact production submission/repair/reader paths, and cached workers-rs sources.
- Observer imports the real built shim. Its context/env constructor and inherited
  `super.scheduled(event)` retain worker-build 0.8.5's generated call to
  `exports.scheduled(event, this.env, this.ctx)`. Date slot `1680000000000` has
  residue zero under five-minute division and correctly selects Addresses first.
  No synthetic clock, producer policy flags or production observer import exists.
- D1 constructor is preserved; bind returns another observed native statement;
  first/all/run call real executors with their native receiver. Batch validates
  observed members, records SQL once per statement and unwraps exact native
  prepared objects into one real transaction. Setup/readback use original bindings.
- Pinned workers-rs `global.rs` attaches the exact supplied signal to native fetch's
  second init object. Observer tags that signal before awaiting real fetch and
  associates the unchanged response body and native reader via WeakMaps. Read,
  cancel, release and abort wrappers call the native receiver and preserve values
  and promise rejection. They do not perform cancellation themselves.
- Byte totals record fulfilled native chunks, not Node chunk counts. lateReads
  detects a read submitted after cap crossing or cancellation. The body test
  requires positive bytes and at least two reads; because its source supplies only
  a prefix and never closes before teardown, this establishes a pending next read,
  not successful EOF. Successful inventories are no-abort/no-cancel controls.
- Source owns the acquired reader outside the raced future, drops the losing
  exchange before abort/cleanup, then initiates cancellation and releases the lock.
  Promise settlement is observed without awaiting beyond the deadline. Native
  cancellation settlement can fulfill or reject after abort; the body tests allow
  exactly one settlement and require release. This remains hosted-runtime evidence
  pending, especially its native promise timing relative to stats retrieval.
- Timeout originates in outer select's closed error and maps to Timeout. The
  nested body error carries cap/read failures, not the fixed timeout marker. No
  header/body classifier defect follows from that nesting in the current source.
- Cap is checked against native Uint8Array length before chunk copy into Wasm.
  Oversize fixture requires crossed cap, zero subsequent reads, one fulfilled
  cancellation, one release, no repair and future rather than priority retry slots.
  Node source teardown is explicitly not a provider-stoppage oracle. It merely
  disposes independent bridge resources and does not supply production cleanup.
- Ten two-second pages require complete 500-rule inventory and a real promotion
  after the fifteen-second soft slice, not inventory-only progress. The second
  claimed row is exact-slot priority-released and a fast following turn claims
  only that row. Favorable owned rules on page one make the thirty-second case
  reject partial authority; a rolling inventory deadline would promote and fail.
- Ten 3.2-second pages start the tenth exchange nominally at 28.8 seconds and abort
  under the original thirty-second deadline. The narrow 1.2-second start margin
  is honestly documented as hosted overload sensitivity, not a production defect.
- Unknown DELETE test separately asserts synthetic side-effect acceptance, native
  body timeout, deleting journal with original future slot, no immediate retry,
  and later retirement/null rule from complete successful absence inventory without
  another DELETE. Fixture due expiry does not rewrite production time or state.
- Exact address SQL expectations were independently derived:

| Invocation | SQL | Derivation |
| --- | ---: | --- |
| Slow complete inventory | 7 | initial SELECT + two claims + lifetime discovery + second SELECT + promotion + second-row release |
| Fast second-row promotion | 5 | initial SELECT + one claim + discovery + second SELECT + promotion |
| Header/body/inventory timeout | 5 | initial SELECT + two claims + two releases, no discovery/repair |
| Unknown DELETE | 5 | initial SELECT + claim + discovery + second SELECT + desired-state SELECT before DELETE |
| Immediate absent inventory | 2 | initial and second SELECT; no due claim/discovery |
| Due absent inventory | 4 | initial SELECT + claim + second SELECT + retired UPDATE |
| Oversize or redirect | 3 | initial SELECT + two claims, no discovery/repair/releases |

- Strict stub permits only exact synthetic-zone list pages or one known-ID
  GET/DELETE; every other egress increments an asserted counter and throws.
  Each test gets fresh D1/R2, actual migrations, asserted global held state,
  blocked embedding work and no EMAIL binding. Observer output contains only
  counts/times/fixed synthetic identities, not tokens, headers or body content.
- CI retains the broad default suite and previous five real accepted-item
  liveness cases before the new separate seven-test step after worker-build.
  The fixture adds no dependencies or deployment entrypoint.

## Validation and boundaries

Both modules passed `node --check`; `git diff --check` passed. No local runtime
test/build, commit, push, merge, deployment or provider action was performed.
Only this review artifact was written. After resolving the discriminator gap,
exact-head nondeploying hosted CI remains required; no native compatibility,
CPU/RSS, physical remote cancellation, hard 120-second bound or production pass
is asserted from this source review.

Checked official [native reader contract](https://developers.cloudflare.com/workers/runtime-apis/streams/readablestreamdefaultreader/)
and [Miniflare scheduled API](https://developers.cloudflare.com/workers/testing/miniflare/core/scheduled/).
The existing cancellation note preserves exact pinned upstream bridge evidence.
No new academic claim is made by this scoped fixture assessment.
