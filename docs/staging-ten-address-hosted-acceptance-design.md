# B-only hosted ten-address and reserved-name acceptance

Status (2026-09-30): **design only; NO-GO for live dispatch**. This document
does not create a workflow, account, alias, provider rule, or acceptance result.
The assignment's safe-design fallback is used because B has not yet completed
normal verification and the hosted two-principal isolation acceptance has not
passed. No input boolean can substitute for either fact.

## Scope and source evidence

Use the already designated synthetic principal B, after the prerequisites in
[second-principal provisioning](staging-second-principal.md) and
[two-principal mailbox isolation](staging-two-principal-mail-isolation.md).
Do not create another principal, use the owner account, repeat SMTP fixtures,
or turn the existing `staging_address_isolation_e2e.execute` into the default
acceptance path. That older harness mixes A's quota, B ownership, SMTP and
retirement transport behavior. This narrower test uses **B only, ten temporary
literal routes, zero SMTP submissions and zero mail messages**.

The reviewed source observations motivating a separate path are:

* `staging_address_isolation_e2e.execute` puts ten aliases on A, requires SMTP,
  and records mutation intent only in a process-local dictionary. Cancellation
  loses that dictionary and its reserved-name baseline.
* `staging_hosted_e2e.execute` already implements normal B PKCE and restricted
  Identity readback binding each verified contact to its protected username
  and distinct principal/pairwise subject. Reuse this contract, not auth-store
  copying or a fabricated verified D1 row.
* `staging_mail_e2e.cf_rules` exhausts bounded count-consistent pages and rejects
  duplicate rule IDs; `assert_route` verifies the exact enabled API-owned rule
  and staging ingress action. Reuse these complete observations.
* `add_address` in `crates/mail-worker/src/lib.rs` returns HTTP 409 with
  `reserved_or_invalid_name` before address lookup, and `address_limit` when
  its owner-scoped insertion cannot claim a slot. Negative acceptance must
  match status and code, not merely a nonzero CLI exit or code substring.

The old harness remains prepared, not an executed ten-address result. Its
mock tests remain useful but do not prove the stronger hosted contract here.

## Mutation budget and prerequisite evidence

| Gate | Required evidence before any `address add` |
| --- | --- |
| Execution boundary | `workflow_dispatch` only; exact branch `refs/heads/codex/amail-v0.1.0`; staging Environment; literal `RUN_STAGING_TEN_ADDRESSES`; attempt 1 only; no push/schedule/reusable unconfirmed call |
| Hosted source | Green hosted CI for the exact checkout SHA, including synthetic denial/recovery contracts; CI-built Windows `amail.exe`; no local test/build |
| B readiness | Normal verified B contact, username binding, distinct A/B principal and pairwise subject via current Identity readback; fresh B native PKCE in this run; no account provision/recovery in quota job |
| Earlier isolation | A separately completed, successful guarded two-principal SMTP isolation run with checkout SHA and serving-version provenance recorded in `docs/validation.md`; fail closed until a source-reviewed machine-readable attestation exists, or keep dispatch unwired for an explicit parent/operator evidence review |
| Service provenance | Single 100% serving Mail version matches expected pin, staged Identity/Login revisions recorded; no concurrent staging deployment; recheck Mail serving pin before mutation and after cleanup |
| Empty B | API `address list` empty, owner-scoped D1 non-retired count zero, no preexisting provisioning/deleting/reconciliation row; do not delete data to make the precondition true |
| Provider capacity | Complete rule inventory, configured domain confirmed as `mail-staging.moesegfault.dev`, at least 12 free rule slots (10 planned + 2 reserve); no truncated/unknown matcher inventory |
| Global hold | Public sending remains held; staging-only resource bindings independently checked; no SMTP credential passed to this job |
| Recovery readiness | All candidate D1/provider baseline and exact B owner captured and durably sealed before mutation; protected recovery key available; upload confirmation established; same-run recovery procedure source-reviewed |

[Cloudflare's current limits](https://developers.cloudflare.com/email-service/platform/limits/)
document 200 routing rules per domain. Conservatively gate on **both** the
staging-domain count and total zone rule inventory staying at or below 188
before the ten-route campaign, unless a separately evidenced provider account
contract establishes a different shared ceiling. This can reject a safe run
but cannot invent headroom from a narrower subdomain filter. Count disabled
rules too. Unknown/multiple/nonliteral matchers must be classified explicitly
or fail closed, not silently omitted. The check is an admission observation,
not a provider reservation; the serial campaign must stop on capacity errors.

Use the existing `staging-native-mail-acceptance` concurrency group, with
`cancel-in-progress: false`, and ensure deployment jobs share an equivalent
exclusion. Workflow-level cancellation, manual deploys and Cron are not fully
prevented by a job lock, hence the independent pin and reconciliation gates.

## Exact candidate plan and private recovery manifest

Derive eleven lowercase local parts `qt0-<nonce>` through `qt10-<nonce>` from a
domain-separated HMAC of the protected recovery key, exact GitHub repository,
workflow run ID and original attempt 1. Use at least 128 private nonce bits.
The recovery command takes only numeric original run coordinates, never an
operator-supplied alias or owner. A restarted Actions attempt must refuse to
run the campaign; it may only dispatch the separate reconciliation target.

Freeze the 25 reserved names already declared in the existing harness as a
source oracle. Validate their equality against the Worker source during
hosted tests so a newly reserved microservice name cannot silently escape the
campaign. Check representative uppercase spellings while B is empty, before
quota filling, to separate normalization/reservation failures from the slot
limit. The static reserved candidates are not run-unique and therefore need
stronger recovery protection than nonce-scoped aliases.

Before the first mutating call, capture a versioned full-plan manifest:

* repository, exact checkout SHA, workflow identity, original run/attempt,
  UTC preflight time and deployed serving-version pins;
* exact issuer/subject owner B and protected username binding, in memory;
* all eleven nonce aliases and all reserved-name/normalization candidates;
* exact D1 baseline for every candidate, including absent vs retired/active
  state, owner, creation time, provider rule ID and reconciliation fields;
* complete exact provider rule baseline for every candidate, including any
  existing operational rule; store unrelated rules only as canonical digest;
* B's baseline owner count and the capacity/hold observations.

Seal this manifest using authenticated encryption with a **repository-level**
protected recovery key. The ciphertext can be retained as a short-lived
Actions artifact; plaintext remains only under repository `.temp` and must
never be uploaded or logged. Bind repository/run/attempt/schema as associated
data; reject swapped, truncated, duplicate-candidate or wrong-owner manifests.
Do not reuse a login password as an encryption key or rotate/delete the key
while a campaign may still need recovery. Implement this only with a reviewed
library and pinned hosted dependency, not handwritten cryptography.

The manifest-upload step must complete successfully **before** a later step
can load mutation credentials and start the campaign. A write in `finally`
or a post-job artifact upload is insufficient: a killed runner skips it.
Full candidate scope, not a best-effort list of acknowledged successes, covers
an unexpectedly successful reserved or eleventh-name call. Secret-free logs
can show only manifest-present/version/validated booleans and fixed labels.

## Minimal hosted sequence

1. Authenticate and perform every gate above. Capture and durably seal the
   complete pre-mutation manifest. Stop on any unknown state; no cleanup of
   unrelated baseline state is allowed.
2. While B has zero slots, submit each source-listed reserved local part plus
   representative case variants once. Require nonzero exit, **empty stdout**,
   bounded stderr parsed as exact HTTP 409/`reserved_or_invalid_name`. After
   each call require B's owner count unchanged and candidate D1/rule baseline
   unchanged. Stop immediately on unexpected success or side effect.
3. Add `qt0` through `qt9` serially, once each. For each, require the CLI's
   returned exact address, owner-scoped D1 state `active`, matching issuer/sub,
   one exact enabled API-owned ingress rule, and B's full list/count equal to
   the expected prefix. Activation polling is read-only; it must not replay
   `address add`. No success-path idempotent re-add is needed for this slice.
4. With all ten active simultaneously, snapshot all ten D1 rows and exact
   provider rules. Submit `qt10` **once** and require exact HTTP
   409/`address_limit`, empty stdout, no eleventh D1 row/rule, and ten-row
   owner/provider snapshots unchanged. This distinguishes genuine quota
   enforcement from a failed unrelated provider request or silent eviction.
5. Always enter exact-manifest reconciliation. Emit the success label only
   after cleanup and final serving-pin match. If primary acceptance succeeds
   but cleanup is uncertain, the overall run fails; it is not a pass.

Possible terminal labels: `ten_address_reserved_verified`,
`ten_address_limit_verified`, `ten_address_cleanup_verified`,
`ten_address_provenance_unverified`, `ten_address_mutation_ambiguous`,
`ten_address_cleanup_required`. They are fixed source-owned labels; no alias,
subject, owner, username, rule ID, timestamps, provider response, raw CLI
output, credentials or token claims are interpolated.

## Cancellation-safe reconciliation and ambiguity policy

Recovery loads and authenticates the exact original manifest and obtains a
fresh **normal B login**, with the same current verified owner binding. It
does not register an account, send SMTP, add an alias, or replay the failed
request. The source and staging bindings must still match the recovery
contract; a newer deployed revision needs deliberate review, not a wildcard
override of the pin.

For each candidate absent from both baseline D1 and provider rules, delete
through the supported B CLI only if current D1 proves the exact B owner,
creation time not before the manifest's preflight, and current rule is either
absent or the expected exact API-owned staging ingress rule bound by D1. A
foreign owner, altered provider action, inconsistent rule ID or unowned orphan
requires manual reconciliation, **never direct blanket provider deletion**.
For candidates with any preexisting D1 row or provider rule, preserve the
baseline and require its unchanged readback. In particular do not delete an
operational `abuse` or `postmaster` rule after a reserved-name regression.

Retirement is intentionally not database restoration: successful aliases
leave B-owned `retired` tombstones, with no rule ID, no reconciliation work and
zero non-retired B slots. Record this as the allowed final state rather than
claiming all D1 rows are absent. Assert no messages/storage were created (zero
SMTP budget), and compare unrelated provider state against its baseline
digest. A preexisting tombstone is never deleted. Read-only retries may wait
for the documented reconciliation deadline; uncertain DELETE is not blindly
resent. First inspect the exact row/rule; if still live, re-enter only the
reviewed same-manifest recovery path, not the quota campaign.

This follows [AWS's production retry guidance](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/):
an uncertain response is not evidence that the side effect did not happen.
The test uses the original resource identity for reconciliation and does not
consume new aliases to conceal ambiguous outcomes. The earlier two-principal
test supplies an independent security relation; this campaign supplies the
serial capacity boundary, not a concurrent-race proof.

## Hosted synthetic acceptance contracts before wiring

The future `test_staging_ten_address_*` suite must run only in hosted CI and
must contact no live service. Required failures and positive contracts:

* unconfirmed/nonbranch/attempt>1 dispatch stops before secret loading;
* absent, pending, wrong username or same-subject B fails before mutation;
* prior isolation provenance absent, wrong SHA or failed run is not a pass;
* split/mismatched Worker pin and a pin changed during the campaign fail;
* paged counts changing, duplicate IDs, unknown matchers, 189 rules, or
  existing candidate state fail closed; 188 complete conservative rules pass;
* ten serial allowed aliases pass; transport errors and generic 409 do not
  satisfy either negative oracle; unexpected stdout is failure;
* eleventh success/eviction, reserved success and a rejected call with side
  effects enter cleanup for the **entire** manifest candidate set;
* timeout immediately after a created alias, process cancellation after
  manifest upload and upload failure before mutation are recoverable without
  generating a new plan or repeating `add`;
* recovery rejects altered ciphertext, wrong run/owner, baseline operational
  rules, foreign rows and action/rule-ID mismatches; no wildcard deletion;
* retired tombstones are accepted only with zero live slots, no exact route,
  no pending reconciliation and unchanged unrelated/operational state;
* fixed-label failures never print mocked secrets, aliases or provider bodies.

Until these source, workflow and recovery contracts receive independent
review and hosted tests, **leave `ci.yml` dispatch options unchanged**. No new
secret is configured by this design. Once B verification and the smaller
isolation run are established, implement the dormant wrapper/manifest layer,
review it, run hosted CI, then permit one guarded campaign. Record checkout
SHA, deployed pins, Actions URL and privacy-safe outcome in validation notes.
No current result claims ten-address, reserved-name, concurrent quota races,
outbound ownership, production capacity or release readiness.
