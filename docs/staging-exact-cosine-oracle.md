# Protected staging oracle for exact semantic scores

Status (2026-09-30): **v5 origin-vector oracle source revised; hosted tests,
review, and live exact-cosine attestation pending**. A guarded v4 live attempt at
[`11127a8`, run 36699356379](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36699356379)
aborted with fixed label `query_vector_unstable`: its two independent
OpenRouter query embeddings differed in rounded `f32` bits, before the first
exact-oracle CLI page. This is an oracle precondition failure, **not** a
measured Worker cosine failure. No v4 cursor, second page, score comparison,
or exact-cosine acceptance was obtained. Native PKCE, two SMTP fixtures,
ZIP retrieval, and the basic two-message semantic check passed in that run;
the exact route was retired and cleanup reported `none`. Do not repeat those
passed stages merely to turn this aborted oracle green.

The historical v4 implementation commits to the 256 rounded `f32` coordinates with the
exact byte stream specified below,
rejects vector drift with `search_cursor_vector_changed` (409) before any row
scan, and retains only the digest in a completed job. No deployed result is
inferred from this source change. This
narrows gate 4 in [the staging E2E plan](staging-e2e-plan.md). The later
[guarded run 36682429638](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36682429638/attempts/1)
passed real SMTP-to-ZIP, two-message semantic ranking/filter behavior, and
cleanup. It did **not** capture the query vector actually used for scoring,
independently prove cosine, or exercise a cursor. The earlier
[failed semantic run](staging-semantic-live-failure-36677506793.md) remains a
separate historical observation. No new live probe is authorized by this note.

## Current v5 protected oracle

The [v5 origin-vector decision](semantic-pagination-vector-snapshot-decision.md)
supersedes the v4 operator procedure below. After the first authenticated
`limit=1` CLI page, the operator parses the v5 cursor privately and reads the
actual first-page normalized query vector from its completed origin job. The
fixed D1 `SELECT` is constrained by exact origin UUID and owner issuer/subject;
it extracts only `query_vector`, model, input version, commitment, and origin
state metadata from `state_json`. It **does not select the per-origin MAC key**
or make an independent OpenRouter request. The operator recomputes the v4
vector commitment over the actual origin vector and owner/request binding,
then requests page 2 with the unmodified cursor. A successful second page
shows the Worker accepted the cursor MAC; synthetic hosted tamper tests, not
this restricted operator, exercise MAC rejection directly.

The complete two-document, owner-scoped vector snapshot and generation are
read before page 1 and checked again after page 2. Both public scores are
recomputed from the first-page origin vector and the stored document vectors,
with absolute tolerance `1e-5`, exact page union, filter, score order, and
nonmutation checks. The origin vector is also re-read at the end. Missing or
malformed origin state fails closed as `oracle_vector_unavailable`; a changed
origin or document snapshot fails closed. This is a two-document exact-score
attestation, not a large-corpus performance claim. The outcome no longer says
`provider_repeatable`: cross-request bitwise repeatability was never a
necessary condition for v5 pagination. The Actions execution step no longer
receives a separate OpenRouter key for this oracle; the Worker still uses its
own provider secret on the first page. Real v5 deployment and a fresh guarded
run remain necessary before any live exactness claim.

The following v4 design and run history is retained for provenance, **not**
as the current execution procedure.

## State and provenance: the limiting fact

| State | Source and lifetime | Operator consequence |
| --- | --- | --- |
| Document vectors | `messages.embedding_json` holds 256 `f32` coordinates with `embedding_model`, `embedding_dimensions`, and `embedding_input_version`. Automatic Cron writes them; they remain while the active message exists. Soft deletion hides the row, and garbage collection later physically deletes it. | Read a complete, owner-scoped, **active** snapshot before either fixture is deleted. A post-cleanup read is not a valid historical score oracle. |
| Query vector | `search_jobs.state_json.query_vector` receives the normalized, `f32`-rounded OpenRouter `search_query` embedding. On a complete job, `advance_claimed` clears it; a fast semantic POST then deletes its transient job row. A `202` job retains it only while unfinished, at most until the 24-hour job expiry/scrub. | The normal two-message search is expected to finish in the POST. Neither CLI JSONL nor a later D1 read contains the vector **actually scored**; however, CLI JSONL **does** emit `next_cursor` as a separate final record. Racing an in-flight D1 read is not a deterministic acceptance test. |
| Scores and cursors | The Worker computes all-coordinate cosine with `f64` accumulation from the two persisted `f32` vectors. It ranks by score, then received time and ID. The public v3 cursor contains the last score bits, generation, and query hash but **no query-vector identity**. | A score match against a fresh provider embedding is conditional on provider determinism, not proof of the unseen Worker vector. Each semantic cursor POST independently re-embeds, so multi-page exactness also needs vector stability across pages. |

These are source-level conclusions from `crates/mail-worker/src/platform.rs`,
`src/lib.rs` (`cosine_exact`, `delete_message`, `garbage_collect`),
`src/search_jobs.rs` (`search`, `advance_claimed`, `result_page`), and migrations
`0001_initial.sql`, `0005_search_jobs.sql`, `0007_embedding_work.sql`. The
source itself is not a deployed proof; pin the 100%-serving staging Worker
version to the reviewed revision immediately before a probe.

## Architecture choice: semantic v4 vector commitment, not a server snapshot

Choose a **v4 semantic cursor** containing a fixed-length SHA-256 commitment
to the exact query-vector bytes used to rank its page. The digest input is
domain-separated and includes the owner/request-bound canonical query hash,
model slug, query input-version tag, dimension count, and each of the 256
normalized `f32` coordinates in specified little-endian IEEE-754 order. Use
the *in-memory vector that `scan_batch` receives*, not provider raw JSON or a
fresh embedding. This is a one-way commitment, **not** encryption or a vector
serialized into the cursor. A private operator who independently obtains the
same vector can recompute it; a different vector cannot plausibly collide.
Owner/request binding avoids a reusable cross-account vector fingerprint.
The digest is sensitive query-derived metadata: never log it, expose it in
telemetry, or put the entire cursor in an artifact.

The v4 canonical digest preimage is exactly: ASCII
`amail-semantic-query-v4` then NUL; the 64-byte lowercase ASCII canonical
owner/request query hash then NUL; model UTF-8 byte length as `u32` little
endian and the model bytes; query input version `1` as `u32` little endian;
dimension count `256` as `u32` little endian; then all 256 `f32::to_bits()`
values as `u32` little endian in coordinate order. The cursor stores the
lowercase 64-hex SHA-256 digest. The extra optional field is omitted entirely
from emitted v3 lexical cursors, preserving their existing encoding.

`SearchState` must retain only this digest after clearing `query_vector` at
completion so an already-completed durable job can replay the same v4 cursor.
Fast jobs are still deleted. For a subsequent page, parse the v4 cursor and
validate owner/filter/generation **before** provider work; after embedding,
compute the commitment and compare it **before scanning any row**. A mismatch
returns a typed HTTP 409 such as `search_cursor_vector_changed`; it spends at
most one admitted provider request and cleans the transient preparing job,
but cannot return a silent partial page. The CLI must surface this as a
restart-from-first-page condition, not auto-append a new first page to output
from the old vector. The immutable cursor cannot itself prevent provider drift;
it converts drift from undetectable wrong pagination into an explicit failure.

This is smaller than persisting a server-owned query snapshot for every
cursor: no new table, job lifetime, vector retention, or lookup on each page.
The trade-off is an OpenRouter embedding call per page and failure rather than
transparent continuation if the provider changes vectors. A server-owned
snapshot is preferable only if real drift or page cost is measured to matter;
then it needs opaque, owner-scoped, expiring cursor state, generation checks,
quota/garbage collection, and an explicit migration. Do **not** put 256 raw
coordinates in a public base64 cursor or weaken the existing no-query-in-log
boundary to simplify testing.

Compatibility: v3 **lexical** cursors can keep their current meaning. A v3
**semantic** cursor cannot prove which vector set its last-score boundary, so
it must fail with a typed stale/restart error rather than silently continue.
This repository has no production Mail release; staging cursors are ephemeral
and no durable user data is deleted by rejection. The CLI currently retries
only a *cursorless* `search_job_stale` list; it must not silently retry a
cursorful v3/v4 mismatch. If a future production deployment has issued v3
semantic cursors, this is a narrow, visible pagination compatibility break
to announce and handle explicitly; unbounded v3 acceptance is not a safe
compatibility strategy because v3 has no issuance time or vector commitment.
Existing saved v3 cursors should receive an actionable `search_cursor_stale`
or `search_cursor_upgrade_required`, not a panic or ambiguous 400.

The bounded hosted test matrix for the eventual implementation is: (1) exact
same `f32` vector accepts page 2; (2) one changed coordinate, model slug, or
input-version tag returns the typed 409 **before** `scan_batch`; (3) tampered
or malformed digest returns a fixed invalid/stale code and never echoes the
cursor; (4) v3 lexical continuation still works while v3 semantic returns an
actionable restart; (5) completed `202` replay regenerates the identical v4
cursor without retaining raw query coordinates; (6) cursorless `200` search
still deletes its transient job; (7) CLI never concatenates old-page and
restarted-new-page rows; (8) logs/traces/telemetry contain neither vector,
digest, query, nor raw cursor. These are acceptance specifications, **not
tests performed** by this design note.

## Smallest protected oracle after v4: one existing two-mail fixture

Integrate an **optional restricted operator score check** after the existing
two delivered ZIPs and automatic indexing are verified, before `mark`,
`delete`, or address retirement. It must not weaken the existing E2E cleanup
`finally`: failure still retires the exact run-owned route and removes only
run-owned messages. The protected job has real native-PKCE authorization for
the public search and staging **D1 Read** access for a fixed, parameterized
SELECT. Cloudflare's [D1 query API](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/)
accepts a scoped API token and SQL parameters; use only an embedded SELECT
template, never a workflow-supplied SQL string. Keep the D1 and OpenRouter
secrets in the GitHub staging environment, not in CLI/Chrome subprocesses.
Do not upload a raw D1 response, provider response, HTTP page, or CLI archive.

1. Pin Worker revision; require the existing pre-mutation owner inventory was
   empty, and now the complete unfiltered owner inventory contains **exactly**
   the two run-owned active messages. Read the owner `search_generation` before
   the snapshot. Independently SELECT only their ID, timestamp,
   `embedding_json`, model, dimensions and input version from staging D1,
   constrained by the authenticated synthetic `(owner_iss, owner_sub)`, exact
   run-owned mailbox, `deleted_at IS NULL`, and fixed run IDs. Reject zero,
   missing, duplicate, or unexpected rows. No subject/body or other account
   rows may enter the operator process.
2. Require both D1 vectors parse as 256 finite nonzero `f32` values; model
   equals `qwen/qwen3-embedding-8b`, dimensions 256, input version 1. The
   provider request uses the *identical* private synthetic query string,
   `model`, `dimensions=256`, `input_type=search_query`, and
   `provider={zdr:true,data_collection:"deny"}` as Worker source, with cache
   disabled. Normalize returned `f64` values and round each coordinate to
   `f32` exactly as `platform::embed_classified` does. Independently request
   the vector twice; require coordinate-wise `f32` identity. A mismatch is
   `query_vector_unstable`, not a score failure to paper over with tolerance.
   OpenRouter documents the [embedding request parameters](https://openrouter.ai/docs/api/api-reference/embeddings/create-embeddings),
   but it does not make this repeatability check a contract for a different
   Worker request or a later provider route.
3. Issue authenticated native CLI semantic search (the CLI uses HTTP internally) with the exact same
   restrictive mailbox/title/unread predicates and **`limit=1`**, capturing
   response pages privately, including each CLI JSONL `next_cursor` record. Require
   the first page has exactly one hit and a v4 cursor whose vector commitment
   matches the independently rounded provider vector. This binds the oracle
   to the *Worker's actual query vector* without retaining it in D1. Request
   the next page with the identical filter and limit. Require one other hit,
   no cursor, no duplicate, and no read mutation; the Worker's v4 guard must
   reject a changed page-2 vector. The complete union must equal the D1
   owner-scoped snapshot. Independently calculate
   `dot(q,d)/sqrt(dot(q,q)*dot(d,d))` using ordered `f64` sums over all 256
   rounded coordinates; reject a zero norm and compare each public score to
   its expected value within predeclared absolute `1e-5` (the existing
   `check_exact_pages` helper uses this tolerance). Compare descending
   `(score, received_at, id)` order across both pages, including a negative
   filter control.
   Require expected scores sufficiently separated for ordering to discriminate
   (`> 2e-5`); otherwise label the order check inconclusive rather than pass.
4. Re-read owner generation and the two rows' active/vector metadata, and
   require the generation and vector values are unchanged. The automatic
   indexer's vector write increments generation; a mid-check write must fail
   the snapshot, not be treated as a user-facing search defect. Finish before
   normal fixture cleanup. The process emits only fixed phase labels, the
   count 2, bounded maximum absolute score error, order boolean, and
   `provider_repeatable=true/false`. It never emits query, vectors, IDs,
   addresses, SQL parameters, response bodies, tokens, or their hashes.

Implementation wiring (source only, not a live acceptance): `workflow_dispatch`
`target=staging-e2e`, `semantic=true`, `exact_cosine=true`,
`exact_cosine_confirm=RUN_STAGING_EXACT_COSINE`, and the existing
`confirm=RUN_STAGING_E2E` run the protected oracle on **the same two SMTP
fixtures**, between semantic checks and mark/delete. The existing cleanup
`finally` still runs after an oracle failure. The GitHub `staging` environment
provides `OPENROUTER_API_KEY` only to the final E2E step under this opt-in;
the existing D1-scoped `CLOUDFLARE_API_TOKEN` and native CLI session are used
without extracting OAuth tokens. The harness first requires an empty full
owner inventory, then exactly the two run-owned active messages. Its fixed
embedded D1 SELECTs are parameterized. The two separately requested provider
vectors must be bit-identical after `f32` rounding, and the first-page v4
commitment must match. The private CLI pages, vectors, IDs and cursors never
leave process memory or enter an Actions artifact. Only fixed labels and a
bounded maximum absolute score error are printed. If the provider vectors
differ, the outcome is `query_vector_unstable`, not a cosine failure.

After reviewed v4 source is serving, a matching commitment plus complete D1
snapshot and two pages is a **conclusive two-document, same-vector cosine
and pagination oracle**, subject to the standard cryptographic collision
assumption. It detects wrong metadata, malformed vectors, incorrect cosine,
wrong scores/order, ignored predicates, missing/duplicate rows, and provider
drift between the two pages. It does **not** prove exhaustive ranking or
resource behavior at a large mailbox scale. Before v4 deployment, the same
read-only D1/provider comparison remains useful but may only be labeled
`conditional_cosine_score_match`: no cursor commits to the Worker's actual
vector. Neither label may be inferred from the already completed live run.

## Separate scale oracle if needed: captured 202 checkpoint

If v4 cannot be shipped or the claim must include a large corpus, use a
separate, bounded synthetic staging fixture that deterministically returns
HTTP `202` **after** its query vector has been written to a running
`search_jobs` row. The fixture
may be D1-seeded under an audited operator credential, but its write setup
must be distinguished from the read-only score oracle and from real SMTP
ingress acceptance. Size it from hosted measurements against the production
scan budget; do not invent thousands of SMTP deliveries, race a millisecond
window, or lower production budgets merely to manufacture `202`.

The restricted operator receives the authenticated `job_id` privately from
the 202, then reads **only** that exact owner/job `state_json.query_vector`
while state is `running` or `advancing`. Validate model, 256 finite `f32`
coordinates, job generation, and exact synthetic query identity without
logging any of them. Separately SELECT the complete eligible document vector
snapshot under the same owner/filter/high-water/generation. Poll the job to
200, and before mutation compare all returned scores and order with an
independent implementation (`infra/tests/staging_semantic_e2e.py` can be the
starting helper), require no missing/duplicate rows, and then verify the
expected vector scrub on completion. One D1 snapshot and a 202 response are
necessary; a terminal `done` row is too late. Repeated D1 read attempts have
a fixed deadline and are capped; if the vector has already been scrubbed,
report `oracle_vector_unavailable`, never infer it from a fresh embedding.

Without v4, obtain the **actual** query vector used for *each* cursor
POST/job and require all page vectors are byte-identical `f32`, or recompute
the appropriate page against its own vector and prove cursor partition
completeness. The current v3 cursor binds text/hash/generation but not a
vector; a provider/model revision between pages could theoretically change
scores and cause skips or duplicates despite an unchanged mailbox. No live
drift is observed. Do not claim cursor correctness from the existing one-page
helper or assume provider determinism is permanent.

## Rejected shortcuts and acceptance outputs

| Shortcut | Why it is insufficient |
| --- | --- |
| Assert two scores are finite and sorted | A constant, approximate, or wrong-vector implementation can satisfy it. |
| Re-embed the query once after the Worker returns 200 without a v4 commitment | The Worker vector is gone; OpenRouter routing/revision may differ. |
| Read `search_jobs` after a fast POST or a completed 202 | Fast jobs are deleted and completed jobs scrub their vector. |
| Treat soft-deleted rows as a snapshot | Deleted rows are excluded from search and may be garbage-collected at any time. |
| Emit query/vector/hash to public Actions logs | Creates a mail-derived privacy leak and still may not prove in-Worker provenance. |
| Force a `202` through a staging-only budget override in product code | Changes the tested behavior and widens maintenance/abuse surface solely for an oracle. |

Recorded outputs must distinguish `(a)` deployed two-message semantic behavior,
`(b)` conditional score calibration under v3, and `(c)` same-vector exact
cosine plus two-page pagination under independently verified v4 commitment.
None may be promoted from mock tests or source inspection alone. The next
cheapest discriminating step is a reviewed v4 implementation, hosted unit and
cross-platform tests (including digest mismatch, v3 restart, completion
replay, and no vector logging), followed by a *single* guarded two-message
staging E2E with this read-only operator phase before deletion—not a broad
second SMTP campaign solely to establish a query-vector oracle. Only if
large-mailbox exactness is a separate release claim should an operator fund
the larger 202 fixture.
