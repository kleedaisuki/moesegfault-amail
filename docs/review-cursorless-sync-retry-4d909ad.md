# Review: cursorless message-list stale retry (`4d909ad`)

Status: independent source review, 2026-09-29. No local tests, hosted calls, D1 queries, SMTP submissions, or production edits were performed in this review.

## Assessment

No substantive defect found in the reviewed change. `Api::messages` alone invokes `cursorless_list`, and `main.rs::sync` is its current caller. The first failure must be a typed `ApiFailure` from the HTTP client, with exactly status 409 and code `search_job_stale`, and the caller must provide no cursor. A successful retry is returned before `sync` emits a page or downloads any archive. The retry result is returned directly, so a repeated stale result fails after two GET attempts and one 100 ms pause. Cursor-bearing pages, `search_cursor_stale`, other 409s, other statuses, search-job calls, SMTP, and write operations are not retried by this change. Each GET keeps the pre-existing 30-second request timeout and its own telemetry record.

The new `ApiFailure` retains the pre-existing rendered CLI error prefix; the retry discriminator does not include or print the response body. The staging harness extends its allowlist only by the fixed public codes `search_job_stale` and `search_cursor_stale`, and its new test checks that an unknown response code remains `unknown_code` rather than printing arbitrary text. The new Rust tests cover success after one stale response, exhaustion, and negative status/code/cursor cases. `docs/cli-design.md` documents the user-visible retry bound and scope.

## Test boundary and residual risk

The Rust tests construct `ApiFailure` directly and call the retry helper, so they do not independently prove the HTTP parser-to-helper wiring. Source inspection shows that `execute_with_status` constructs the typed error and `Api::messages` wraps its JSON call with the helper. A mocked HTTP integration test would strengthen future regression protection but is not required to correct a demonstrated flaw. Existing arbitrary non-address `code` text in CLI stderr predates this patch; the new retry does not broaden it, and the hosted harness still allowlists loggable codes. No claim is made about the historical fifth staging run's exact 409 code or whether a single retry will resolve every concurrent-generation race.
