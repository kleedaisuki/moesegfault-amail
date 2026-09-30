# Bounded native semantic-query discriminator without another SMTP delivery

Status: **source prepared, not hosted CI or deployed evidence**. This is a
diagnostic follow-up to [hosted run 36677506793](staging-semantic-live-failure-36677506793.md),
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

## Hosted validation and launch discipline

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
