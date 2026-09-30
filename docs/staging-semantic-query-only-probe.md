# Bounded native semantic-query discriminator without another SMTP delivery

Status: **one hosted staging query-only pass; full semantic mail acceptance still unverified**.
This is a diagnostic follow-up to [hosted run 36677506793](staging-semantic-live-failure-36677506793.md),
whose semantic stage failed with an unclassified CLI label after successful
SMTP-to-ZIP acceptance. It neither retroactively diagnoses that failure nor
establishes full two-message semantic-search acceptance.

## Exact scope and preconditions

The manual `staging-semantic-query-only` workflow target uses the existing
verified synthetic **staging** Identity account. Its job has the same
`staging-native-mail-acceptance` concurrency group as the real SMTP E2E, but
receives only the two protected synthetic Identity credentials—**no SMTP,
Routing, D1 operator, or Cloudflare API token**. A separate literal
`RUN_STAGING_SEMANTIC_QUERY_ONLY` confirmation is required. The hosted Windows
job builds/tests the CLI, creates a new `.temp/staging-semantic-query-*` home,
performs actual browser-based native PKCE login, and removes that exact home
even after a failed probe. Secrets are removed from the Python environment
before browser/CLI child processes; the CLI receives only its staging endpoint
and telemetry-off configuration.

Before any semantic request, an **unfiltered, owner-scoped** ordinary search
must return zero active message rows and no continuation cursor. A nonempty
or ambiguous inventory stops the probe rather than examining any message.
The next and only semantic request uses one fixed synthetic query. Its
stdout/stderr are captured in memory; the public job log has only fixed
success/error labels, distinguishing initial POST from poll when the CLI's
reviewed grammar provides that evidence. It prints no query, address,
result, job ID, browser URL, bearer token, ZIP or provider text. No address or
mail state mutation is called. `search` itself is not a storage no-op: the
Worker reserves a daily search quota, creates a transient search job and
calls OpenRouter for a query embedding.

The relevant Worker source (`search_jobs::search`) executes
`platform::embed(env, term, "search_query")` **before** `advance` scans
messages; it does not short-circuit an empty mailbox. Therefore a successful
empty result would exercise query-embedding/provider/job plumbing **if and
only if the deployed Worker revision matches the reviewed source**. Pin the
100%-serving staging Mail Worker version immediately before a live dispatch;
without that readback, report only the observed API behavior, not a verified
OpenRouter call. This probe deliberately cannot test document indexing,
semantic score/order, lexical AND-composition, or exact cosine, because there
are no active documents. It also cannot establish why run 36677506793 failed.

## Hosted validation and launch discipline (historical)

`infra/tests/test_staging_semantic_query_only.py` is mock-only. GitHub Actions
must pass its infrastructure test job and CLI Windows build; no local heavy
test or developer-machine SMTP is required. An independent source review must
precede any dispatch. Once reviewed and pushed, a single manual call may be
made with `target=staging-semantic-query-only` and
`confirm=RUN_STAGING_SEMANTIC_QUERY_ONLY`. Do not supply `semantic=true` (that
input belongs to the full SMTP E2E), and do not replay this probe to make a
failure green. Record the checkout SHA, serving Worker version, Actions run,
fixed status/phase label, and whether the account inventory was empty; retain
no raw artifacts. If the account is not empty, inspect it only through an
authorized, separate workflow rather than weakening the empty-inventory gate.

## First live result (2026-09-30)

| Boundary | Recorded evidence |
| --- | --- |
| Checkout | `3dbc961b35408105f7f5bceb599fe32ccc536b04` |
| Serving-version pin | [run 36681988920](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36681988920), 100%-serving Mail version `a5429622-67ac-4570-b771-a50c3683e5d4`, `staging_mail_serving_pin=match` |
| Native query-only probe | [run 36682045842](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36682045842), Windows job `109779427733`, successful fixed result `staging_semantic_query_only=empty_query_completed_and_local_cleanup_passed` |

The fixed success label is emitted only after the owner-scoped ordinary
inventory was empty, the native PKCE semantic CLI request completed with an
empty result, and the temporary CLI home was removed. Under the pinned Worker
source, `search_jobs::search` embeds the query before scanning messages; thus
the completed request supports the narrower inference that query-embedding
and search-job plumbing worked for this empty-mail request. The fixed log
does not independently expose a provider receipt, and neither this result nor
the source ordering demonstrates document indexing, lexical AND composition,
semantic ranking/scores, or the cause of the earlier two-message failure.
No SMTP delivery or address creation was performed by this probe. Preserve
the earlier failure as a distinct, unresolved observation.
