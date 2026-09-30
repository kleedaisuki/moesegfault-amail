# Review: private-inbox preflight fixed-label diagnostics (`a012bbd`)

**Decision: GO for hosted CI and, after CI succeeds, one explicitly confirmed read-only B preflight. No substantive defect found in the focused change. This is not approval for an R2 write probe, principal registration/recovery, route creation, or public sending.**

## Scope and evidence

Reviewed the commit's three-file diff, `inspect_state()`, `read_only_preflight()` and `main()` in `infra/tests/staging_second_principal.py`, the source-controlled producer `workers/identity-test-inbox/check_config.py`, relevant mock contracts, and the guarded preflight/infra test steps in `.github/workflows/ci.yml`. No local tests, live provider requests, workflow dispatch, deployment, or push were performed. Unrelated concurrent worktree changes were excluded.

## Assessment

- The producer's expected failures contain fixed source strings or integer HTTP status values, not provider bodies. The consumer matches exact messages or a fully anchored fixed prefix plus one to three ASCII digits, returning only source-owned category strings. Provider-controlled text, unknown messages, internal multiline payloads, malformed decoding, and output above 4096 bytes cannot be forwarded. Surrounding whitespace is stripped; this permits the checker's normal final newline without permitting additional non-whitespace lines. Captured stdout is not printed either.
- Nonzero checker exits raise before route audits, Identity D1 reads, or R2 object listing. `OSError` and the existing 90-second subprocess timeout now have an explicit fixed subprocess category; exception text and timeout output are discarded. The subprocess still runs the exact repository checker with `--live --deployed`, no shell, and the checker still uses only source reads and provider GETs. No policy, credentials, account/route mutation, or R2 object mutation is introduced.
- The normal success path, zero exit status, read-only command confirmation, and later state classification remain unchanged. The generic failure label is deliberately refined for this internal diagnostic; no executable caller matching the old generic label was found in repository search. The public CLI/API is unaffected.
- Added tests cover phase-specific labels, unknown/private text, a multiline message, nonzero-exit short-circuit before routes/D1, and timeout. Existing contracts assert the checker flags and read-only route calls. Hosted infra discovery includes this suite; no passing hosted result for this revision is assumed here.

## Limits and next action

The categories identify the source checker phase, not a root cause. In particular, `HTTP200` with an invalid envelope is correctly a read failure, while `HTTP0` is the checker's transport-unavailable convention; no raw status or reply is disclosed. A subprocess timeout remains unable to localize the interrupted internal phase, by design. Mock tests do not prove deployed bindings, R2 privacy/lifecycle, token permissions, or B absence.

After hosted CI passes, one guarded `staging-second-principal-preflight` run with `READ_STAGING_SECOND_PRINCIPAL_PREFLIGHT` can discriminate the present read failure. Its result must guide the next correction; it must not be treated as permission to retry PUT or register B. The earlier aggregate probe failure is not proven identical to the separate checker failure.
