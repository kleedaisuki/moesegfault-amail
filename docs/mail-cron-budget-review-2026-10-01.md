# Full Mail Cron budget review after late-provider orphan discovery

Date: 2026-10-01. Reviewed source: `e25013b4045eaf0570ff3796353f182125a4487d` (PR #17). This is a static resource model plus a **not-yet-run** provider-free workerd fixture. No local project test/build, provider inventory, provider mutation, deployment, or subscription inspection was performed. The actual account's Workers plan and effective `limits` are **unknown**; repository Wrangler files have no explicit CPU/subrequest limit override. Do not infer Paid from working DNS, bindings, or earlier deployment success.

This extends [routing reconciliation budget](routing-reconcile-subrequest-budget.md), rather than claiming its proposed optimization was a complete-Cron resource proof. In particular, the old document's large-send formula omitted the restricted-envelope UPDATE; the corrected accepted-send formula appears below.

## Decision

1. PR #17's address-phase external exchange cap is real: all list pages, fresh absence rechecks, scoped current-rule GETs and DELETEs debit one shared twenty-call allowance **before submission**, and redirects are manual. The ten-page/fifty-rule cap is not ten pages per address. At the planned approximately 404 zone rules it takes nine initial GETs; at the admitted five-hundred-rule cap it takes ten. Five GET+DELETE pairs fit after a ten-page inventory. There is no new deterministic external-50 overrun from the address change alone.
2. **Do not call the full Cron Free-safe or release-ready.** The combined handler has neither a shared D1 budget nor a shared elapsed-time/phase admission budget. Large accepted-send recovery can exceed the currently published D1 Paid 1,000-query bound on its own; even one maximum service-valid text send exceeds Free's published 50-query bound. This is a pre-existing release risk, not a reason to discard safe late-orphan convergence.
3. The incremental orphan audit is small but real: one extra due selection when the original batch is short, a provider inventory even on idle ticks, and up to two D1 statements per fifty provider-positive candidate keys. The source-admitted five-hundred-candidate bound is twenty discovery statements; under the documented two-hundred-rules-per-domain limit a single current Mail domain has at most four key batches/eight statements. No historical tombstone scan or per-tombstone egress is introduced.
4. Twenty successful embedding items plus twenty routing exchanges model forty external exchanges **only without embedding redirects**. `embed_classified` does not override `RequestRedirect::Follow` (workers-rs v0.8.3 default), and its provider response `json()` is unbounded. These are pre-existing hard-bound gaps; make embedding redirects manual and bound its response before advertising the forty-exchange/128-MB resource contract.

## Official limits: product-specific documentation remains inconsistent

Retrieved 2026-10-01 from primary sources:

| Resource | Free | Paid | Interpretation for this source |
| --- | --- | --- | --- |
| External subrequests/invocation | 50 | 10,000 by default | Redirect hops count; routing disallows them, embeddings currently follow. |
| Internal-service subrequests/invocation | 1,000 | Matches configured subrequest limit, default 10,000 | Do not confuse this with the separately documented D1 query limit. R2 and Queue calls also consume internal-service resources. |
| D1 queries/invocation | 50 | 1,000 | Current D1 limits page still publishes these values despite newer Workers/changelog limits. Until clarified or independently demonstrated on the actual account, use this stricter product bound. A local workerd pass cannot resolve remote enforcement. |
| CPU per five-minute Cron | 10 ms | 30 seconds (interval <1 hour) | Not the HTTP five-minute configurable maximum, and not the fifteen-minute wall allowance. No CPU profile is available. |
| Cron wall time | 15 minutes | 15 minutes | A hung awaited dependency can suppress every later maintenance phase. |
| Memory/isolate | 128 MB | 128 MB | Shared by concurrent invocations; body-byte caps are not peak-RSS measurements. |
| Simultaneous outgoing connections | 6 | 6 | Current handler awaits work serially; no deliberate fan-out >6 found. |

Sources: [Workers limits](https://developers.cloudflare.com/workers/platform/limits/), [D1 limits](https://developers.cloudflare.com/d1/platform/limits/), [2026 subrequest change](https://developers.cloudflare.com/changelog/post/2026-02-11-subrequests-limit/), [Workers Request redirects and credential forwarding](https://developers.cloudflare.com/workers/runtime-apis/request/), [workers-rs RequestInit v0.8.3](https://github.com/cloudflare/workers-rs/blob/v0.8.3/worker/src/request_init.rs), [Email Service limits](https://developers.cloudflare.com/email-service/platform/limits/). D1 Free daily row quotas now fail closed when reached, independently of per-invocation statements: [2026-09-01 enforcement](https://developers.cloudflare.com/changelog/product/d1/). Statements below are **binding calls**, not rows read/written, SQL trigger internal steps, duration, or measured provider limits.

## Source-derived whole-Cron inventory

`scheduled()` runs sequentially: address repair -> accepted outbound recovery -> semantic retry -> storage-ledger reconciliation -> deleted-content GC -> orphan-object GC -> search-job cleanup -> abuse retention. Catching a phase `Err` does not restore an exhausted platform budget or recover a terminated isolate.

| Phase | Conservative binding-statement bound in current source | Other work |
| --- | --- | --- |
| Address repair | <=160 loose upper bound: <=2 due selects +30 claims +20 discovery statements +90 conditional per-row writes +18 destructive-current-state reads | <=20 nonredirecting external exchanges. The upper bound sums mutually incompatible path maxima deliberately; it is an admission ceiling, not a measured achievable trace. A 500-zone-rule fixture with 200 strict retired own-domain candidates, 30 newly claimed rows and five deletions has 75 address statements: 2+30+8+30+5. |
| Accepted outbound recovery | <=1,402 for twenty maximum service-valid text drafts: 2 setup +20*(66 extra text-chunk INSERTs +4 other writes) | <=20 R2 GETs, ZIP decompression/HTML compilation serially per object. Each four-write group is restricted-envelope UPDATE + message INSERT + reservation UPDATE + send-state UPDATE. |
| Semantic retry | <=83: 2 initial reads +20*(claim +owner schedule +leased content read +success/failure write), plus at most one cooldown write before breaking | <=20 initial OpenRouter fetches; redirect hops not bounded by application allowance. Per-message cap four and global cap twenty are SQL-enforced. |
| Ledger reconciliation | 1 | Unbounded row update cardinality in a single statement. |
| Deleted-content collection | <=61: 1 select +20*3 deletes | <=40 R2 DELETEs. |
| Orphan-object collection | <=61: 1 select +20*(send-state read +2 deletes) | <=40 R2 DELETEs; accepted/unknown/submitting rows skip destructive work. |
| Search-job cleanup | 3 | Unbounded row UPDATE/DELETE cardinality despite the fixed call count. |
| Abuse retention | 3 | Each statement targets <=100 rows. |
| **Loose combined bound** | **<=1,774 binding statements** | <=100 R2 calls, additional Queue diagnostic batches, and modeled <=40 nonredirecting external fetches. |

### Maximum-send counterexample and client nuance

The service `archive::parse_draft` allows a 5-MiB compressed ZIP/12-MiB expanded content. `validate_draft` allows a total estimate of 4,000,000 bytes, so a text-only 4,000,000-byte body plus small manifest can be a valid service input. `text_parts` uses at most 60,000-byte UTF-8 pieces: 67 parts and 66 additional chunk INSERTs. Such a single accepted row takes up to **72 D1 calls including outbound phase setup**, before all other maintenance. Twenty rows take 1,402 calls before semantic/GC. This proves a static budget violation under the published D1 50/1,000 limits; it does not prove the deployed account has observed a particular exception.

The native CLI currently applies a narrower two-MiB cap to each explicit `body.txt`/`body.html`. A maximum explicit native text body therefore costs 34 extra chunk INSERTs and four writes: forty calls including the two phase-setup calls. **That narrower client contract does not make the complete Free Cron safe**: the other phases still run, twenty such recovered items cost 762 calls, and the service's accepted-input contract remains broader. Do not silently tighten valid service drafts as a resource fix or confuse the native client with the server admission boundary.

An address-only case already crosses Free's documented D1 50: thirty due marked retired rows with an empty inventory can issue one due SELECT +thirty claims +thirty marker-clear UPDATEs =61, excluding every other phase. This shape does not require large messages or discovery batches. Claiming fewer addresses alone cannot solve a single valid four-million-byte accepted send.

## Memory, CPU and cross-phase liveness

Routing bodies are incrementally capped at 256 KiB each; at most ten pages/five hundred typed rules remain in the complete inventory. At most roughly 2.5 MiB of raw paginated payload can contribute retained strings/structures per inventory, not an exact heap bound. Fresh absence inventory can coexist with the earlier inventory. JSON parsing, Vec growth, JS/Wasm copies, response chunks and allocator high-water marks add overhead. No material routing-only 128-MB counterexample is established by this review, and no peak memory was measured.

The dominant unmeasured risks are outbound ZIP/HTML parsing and unbounded embedding response JSON. Recovery buffers an R2 object before checking `MAX_ZIP`; a corrupt/unexpected stored object is not admitted by an incremental read bound. Valid service archives are bounded but HTML/CSS DOM expansion can cost CPU and memory beyond input byte size. Serial processing does not allocate twenty drafts simultaneously, but a Wasm allocator's retained high-water pages and concurrent requests still matter. Do not label byte caps a 128-MB guarantee.

All phases await dependencies without a shared deadline. A routing call can wait until the platform wall cutoff; its twenty-call limit does not guarantee embeddings, deletion or privacy retention run at all. Likewise an early accepted-send backlog can spend the whole D1/CPU allowance on every tick. Address within-batch typed deferral improves **address** fairness, not fairness among maintenance phases.

This distinction follows production's persistent desired-state controllers and modern liveness work: [Kubernetes controllers](https://kubernetes.io/docs/concepts/architecture/controller/) and [Anvil, OSDI 2024](https://www.usenix.org/conference/osdi24/presentation/sun-xudong). Durable work plus bounded invocations are necessary; eventual reconciliation still needs recurring service opportunities and explicit eventual-dependency-success assumptions. This project has not been formally verified by Anvil.

## Minimal enforceable design adjustment for review

Do not replace the state machine, weaken owned-ID proof, or increase arbitrary platform limits to hide the problem.

**Paid-first simple source bound (proposed, not implemented):** after verifying the real Workers tier and effective CPU settings, cap accepted outbound rows at **five per combined tick**, leaving the other existing row caps intact. At current service-valid maximum 66 chunk writes, this gives:

`160 address + (2 + 5*(66+4)) outbound +83 semantic +1 ledger +61 deleted +61 orphan +3 search +3 abuse =724 D1 calls`.

Reserve a conservative **800 binding-statement budget** per invocation, with the remaining 76 calls for future control work rather than a silent increase. Count every `first/all/run/batch` statement through a common invocation-local database wrapper (batch counts each statement, not one call). Admit an outbound item only after its parsed text-part count is known and its **entire** write group fits; the current five-row bound already accommodates every valid service text body. Preserve `accepted` for the next invocation if not admitted. Include the recent envelope UPDATE in the reservation. Reserve maintenance-phase slices before the early phases can consume them. No DB schema, API or CLI contract needs to change merely to cap this row count.

Five rows alone are a low-complexity **static count** repair, not a complete CPU/liveness guarantee. Use manual embedding redirects, an incremental embedding response cap, a finite provider-request timeout and a monotonic invocation deadline checked at work-item boundaries. Rotate which durable phase receives service first across ticks, or give each a reserved time slice; otherwise deadline exits always penalize the last phases. Never exit after partially committing a state transition without its existing durable journal. D1 individual calls can take up to thirty seconds and may not be immediately cancellable; leave deadline headroom for one in-flight operation and the runtime's limits. Only hosted/deployed CPU and tail-duration data can select a responsible wall/CPU slice.

**If Free is required:** a single maximum server-valid outbound item requires continuation for chunk writes or a separate higher-budget invocation; simply capping rows at one cannot satisfy 50. Split durable phases into dedicated per-item/continuation Queue consumers or scheduled invocations with <=40 D1 calls reserved below 50, plus measured CPU <10 ms. Independent invocations avoid an early phase consuming the later ones' budget, but require lease/idempotency/continuation contracts and hosted failure testing. Paid-first is materially simpler; tier selection is a product/operational decision, not an assumption made by this review.

## Provider-free hosted fixture and reproducibility

Changes are limited to `infra/tests/worker-boundary/address-add.test.mjs`: the existing synthetic provider gains an opt-in exact OpenRouter response, and one full-Cron fixture seeds 200 strict own-domain retired rules plus 300 rules split across two other synthetic domains, twenty documents across five owners, and one expired search job. It invokes the actual compiled Rust/Wasm scheduled entry through workerd/Miniflare, requires ten list pages +five scoped GET/DELETE pairs +twenty embeddings =forty external exchanges, all twenty vector commits, five owned removals and later search cleanup. Unmatched egress remains rejected; every value is synthetic and no real model service is called. Foreign rules bring the zone inventory to its admitted 500 cap without pretending one mail domain can have 500 rules.

This fixture **does not count actual D1 binding reads, enforce remote plan quotas, exercise R2/Queue load, measure CPU, or measure peak RSS**. The D1 figures above remain auditable source-derived statement counts. It is a focused semantic/external-counter regression, not a replacement for a deployed high-backlog test.

Reproduce on a GitHub-hosted runner only, after the existing Rust Wasm build/shim patch steps:

```sh
pnpm --dir infra/tests/worker-boundary install --frozen-lockfile
cd infra/tests/worker-boundary
node --test --test-name-pattern='full routing allowance plus twenty embeddings' address-add.test.mjs
# Then retain normal full workerd coverage:
pnpm test
```

Local static checks only: `node --check infra/tests/worker-boundary/address-add.test.mjs` and `git diff --check`. **No result for the new fixture is claimed.** Existing PR #17 hosted run [36799801416](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36799801416) now has a successful Rust Worker (Wasm) job including its built workerd step on exact head `e25013b4045eaf0570ff3796353f182125a4487d`. This unchanged-source pass does not execute this new fixture or establish full provider plan compliance. No performance speedup percentage, CPU millisecond value, or deployed subrequest exception is reported.
