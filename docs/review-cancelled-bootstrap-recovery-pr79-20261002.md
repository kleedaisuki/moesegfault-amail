# Independent cancelled bootstrap recovery review

Date: 2026-10-02
Reviewed head: `dbd12f595d1762268aff2e216537646fa0646e46`
Base: `c874231ea744edf687af655310ae8d69cc8255c9`
Worktree: `.temp/bootstrap-cancelled-recovery`
Decision: **GO for this bounded source delta. No substantive defect identified.**

## Scope and method

Independently inspected the exact base-to-head diff, the full recovery loader, relevant `Bootstrap.recover` / `recover_main` implementation, `create_scope` / `reconcile_scope`, epoch/scope contracts, readonly recovery workflow, and synthetic fixtures. Consulted the inherited accepted controller review at `.temp/fresh-bootstrap-controller-review/review.md` and current infrastructure ledger. `git diff --check` reported no whitespace errors. Production source was not modified.

This is static source review only. No local tests, builds, installation, runtime invocation, GitHub dispatch, or provider operations were performed. No hosted test result or real cancelled-run artifact/readback acceptance is asserted. A GO here is not permission to bootstrap, replay, adopt, activate, or merge without the owner's separate hosted acceptance.

## Evidence supporting GO

1. **Cancellation only widens the terminal-state admission set.** `fresh_bootstrap_recovery.py:34-62` admits completed cancelled runs/jobs through the same `TERMINAL` set as success/failure/timeout. Original repository, main branch, dispatch event, exact workflow path, first attempt, exact run/source binding, unique completed creator job, and all original successful completed source jobs remain required. Skipped and unfinished producers remain refused.
2. **Original ownership and module provenance remain mandatory.** `controller` requires the closed epoch and positive admission prefix; the epoch must equal the original run/source. `load` retains the original immutable module artifact ID comparison and full manifest/compiler/run identity plus module-byte verification in `original`. No current inventory, new run identity, or caller-supplied coordinate is substituted.
3. **Absent scope evidence now fails before extraction/provider access.** In `load`, after controller validation and before module download/extraction, a recorded create-scope intent without `controller.scope.jsonl` raises `fresh_recovery_scope_unavailable`. Missing artifacts raise `fresh_recovery_artifact_unavailable`; partial admission remains `fresh_recovery_admission_unavailable`. Malformed/truncated JSON and invalid journal prefixes are rejected by the existing closed-schema validation before destination creation. A complete prefix ending in submit intent is intentionally admissible interruption evidence, not inferred ownership.
4. **Recovery reads only positively captured store coordinates.** The unchanged `reconcile_scope` observes a D1 UUID or R2 name only when the corresponding positive creation record exists, verifies the original identity/timestamp, and leaves unknown or failed-read state unresolved. An ambiguous R2 intent alone produces no R2 GET and remains UNKNOWN. `Bootstrap.recover` does not call writer paths; result grants remain replay false, receipt/activation/adoption NOT_GRANTED. Scope recovery writes no receipt.
5. **The positive fixture actually crosses the loader/controller boundary.** `test_cancelled_creator_observes_only_captured_identity_without_writes` calls the actual `admission.load`, then actual `Bootstrap(...).recover` with a get-only fake. It asserts the exact captured D1 route, one GET, D1 observed, ambiguous R2 UNKNOWN, no adoption/replay/activation/receipt, empty pins, and no receipt file. GitHub/module downloads are mocked, not the controller recovery method. The fake has no write capabilities.
6. **Negative fixtures preserve the relevant refusal boundaries.** Added cancellation fixtures cover absent recovery artifact, partial admission, missing scope, truncated controller/scope bytes, invalid attempt/epoch prefix, failed/cancelled/skipped/missing or unfinished original source gate. Existing origin, duplicate creator, original module ID, and artifact validity tests now exercise cancellation too.

## Platform context and residual limits

GitHub's [workflow cancellation reference](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-cancellation) describes signal escalation, process-tree killing and forced termination. Thus cancellation is not a remote transaction rollback; the design's separation of terminal state from positive ownership evidence is appropriate. The [official upload-artifact documentation](https://github.com/actions/upload-artifact) documents immutable artifact behavior and bounded retention. Neither cancellation handling nor artifact upload conditions guarantee retained complete evidence after every interruption. The new runbook correctly leaves absent/malformed/expired evidence unresolved rather than authorizing replacement.

Hosted execution of the exact head remains necessary to confirm the synthetic tests/imports and actual CI contracts. Real force-stop/upload behavior and Cloudflare observations remain separate integration evidence. This review deliberately does not reopen inherited controller findings already resolved in the accepted base, or claim universal recovery/production readiness.
