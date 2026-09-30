# Review: one-account native quota CLI adapter

Reviewed commits: `8d3944427d862a2611d8462234dc5d83bff5423b` and fixture correction `acc68ea533d22b277818530716addd7d4b291962`.

## Decision

**GO for hosted source checks; NO-GO for live quota dispatch.** No substantive executable defect was found in this dormant adapter increment. This review does not attest a real native login, ten-address quota, deployed Identity revision, cleanup, remote refresh revocation, or artifact recovery.

## Scope and method

Static inspection covered the new adapter and synthetic tests, its design-document increment, the preceding Identity-provenance and complete-readback reviews, the controller's add/denial/recovery contracts, the existing native browser/login and credential helpers, selected-contact D1 query, CLI environment allowlist, and actual Rust CLI/Worker address/config/auth implementations. No local or live test, build, browser launch, provider request, account mutation, deployment, or production fix was performed.

## Contract assessment

* Normal login composes the existing native PKCE flow, using a fresh run-local browser and CLI home rather than an existing user session. Only the protected synthetic A username/password is submitted. Independent current Identity D1 readback requires A's verified contact, matching username and pairwise subject before login and requires the subject to remain equal afterward. The normal helper checks staging authorization coordinates and cross-process Mail resource authorization. This is an inferred relation through the exact fresh username login plus independent Identity ownership, not a claim that `auth status` exposes a token subject. The future wrapper still must establish the exact deployed Identity/Login revisions and CI-built binary.
* B absence and supported pending/verified B states do not supply authorization or become campaign prerequisites. The reused contact helper reads A and B but `selected_owner` selects A only; the tests explicitly exercise A alone and a pending B. Cross-owner isolation remains separate and unclaimed.
* Child processes use an argument vector, disabled stdin, private captured output, a finite timeout and the existing staging-only environment allowlist. Provider/GitHub/login Secrets are not inherited. No subprocess retry exists; process failures become the fixed ambiguous-outcome label, leaving the controller's manifest recovery rather than a replay as the next action.
* Address command spelling and compact output expectations match the current Rust CLI. Owner inventory consumes the full unpaginated JSONL address API, rejects duplicates, retired rows, cursor records and more than ten rows, and leaves equality with the manifest prefix to the controller. DELETE's required `deleting` response matches the current Worker, including already-retired responses; retirement remains an independently polled provider/D1 condition, not a CLI-output inference. Reserved-name and eleventh-address HTTP/code denial grammar remains the already reviewed controller oracle rather than a broad success-on-error parser here.
* Adds are restricted to the eleven exact derived candidates and source-owned reserved submissions. Deletes are restricted to the manifest candidate/reserved vocabulary. This vocabulary restriction is not sufficient ownership proof on its own: the existing controller recovery performs the immediate complete row/rule ownership audit before issuing the supported CLI DELETE. The adapter grants no direct mail-store write or provider-rule deletion capability.
* Successful and partially persisted native homes both enter normal local logout, with a second-process status check. Failure to prove local teardown remains a fixed cleanup failure. Only the freshly generated repository `.temp/ten-address-native-*` tree is removed; binary/home containment rejects resolved paths outside the repository `.temp` tree. Documentation correctly distinguishes local session removal from best-effort remote refresh revocation. Hard runner termination still needs separately implemented same-artifact recovery.
* `acc68ea` correctly isolates the platform fixture by replacing only this module's `os` binding rather than mutating the globally shared `os.name`, which would change `pathlib.Path` behavior on Linux. Its cleanup assertion checks the precise created directory instead of unrelated concurrent campaign directories.

## Evidence limits and next gate

The new tests were inspected, not executed. Hosted source checks must discover and pass these fixtures along with the existing manifest/controller/readback tests. Fixtures cover exact command restrictions, secret environment exclusion, ambiguous subprocess failure without replay, owner-list shape, staging session config, local logout and partial-login cleanup. They do not establish an end-to-end successful real account scope, current provider permission, or serving provenance.

Before live dispatch, independently review the assembled manual-only wrapper: exact successful source/binary provenance, effective Mail/Identity/Login serving versions and staging bindings/hold, complete stable baseline, immutable encrypted artifact upload/download validation, and same-artifact recovery that reacquires this exact owner before any cleanup. No workflow dispatch authority is added by these commits.
