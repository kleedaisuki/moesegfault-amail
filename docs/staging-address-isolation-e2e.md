# Hosted staging address/quota/isolation acceptance

Status: **prepared harness and mock-only tests; no hosted execution, second
principal, new route, account registration, or SMTP submission performed**.
`infra/tests/staging_address_isolation_e2e.py` is deliberately separate from
the existing one-principal inbound probe. Do not equate a harness test with
deployed behavior.

## Why this is a separate manual campaign

The architecture contract is ten non-retired addresses per owner, reserved
local parts, globally unique/retired names, one enabled API-owned literal
Cloudflare rule per active address, and owner-scoped message operations. One
principal and one route cannot validate these claims. Filling ten routes is
real provider state and consumes staging capacity; only a manual staging
Environment dispatch after reviewed preflight is appropriate. The existing
inbound harness already checks deeper MIME/ZIP/search semantics; this probe
delivers one small synthetic message to discriminate cross-owner access.

## Second synthetic verified principal: explicit prerequisite

The currently verified synthetic staging principal **A** and its protected
`STAGING_E2E_USERNAME`/`STAGING_E2E_PASSWORD` are not principal B. Creating a
second CLI home with A's credential would be a false isolation test. B must be
registered through the normal *first-party staging Identity* registration,
contact challenge delivery and completion, followed by native Authorization
Code + S256 PKCE on the same hosted Windows runner, using an independently
verified email contact and separately protected staging Environment secrets
`STAGING_E2E_B_USERNAME`/`STAGING_E2E_B_PASSWORD`.

The existing private verification inbox Worker accepts **only**
`amail-e2e@moesegfault.dev`; that alias is already A's verified contact.
Therefore it cannot simply receive B's challenge. Before provisioning B,
review/deploy an isolated second exact verification recipient and private
inbox policy (for example `amail-e2e-b@moesegfault.dev`), with an explicit
literal route scoped to the brief verification window, private R2 UUID-keyed
MIME, provenance check, route settle wait, route removal/readback **before**
code completion, and object deletion. Follow
[`staging-identity-flow.md`](staging-identity-flow.md) and
[`staging-test-account.md`](staging-test-account.md) with B's separate contact.
The current exact-recipient Worker policy must be changed and reviewed first;
**do not** point a second alias at a Worker that rejects it, reuse A's contact,
create a verified D1 row, copy a token, or register B during this probe.
Record B's account/contact existence and verification through restricted
Identity readback with opaque identifiers only. After the campaign, revoke or
remove B through supported Identity account controls; if B is retained as a
regression account, document its owner, recovery, credential rotation and
expiry. Remove the second verification route and its private MIME regardless
of account outcome. This prerequisite is currently **open**.

## Hosted execution contract

The CI owner should add a **manual-only**, staging Environment-protected
Windows job, not modify the existing one-principal probe's meaning. Require a
literal `RUN_STAGING_ADDRESS_E2E` confirmation, two separately protected
synthetic credentials, Cloudflare SMTP/routing tokens and zone ID. Build/test
the CLI on GitHub Actions; invoke `staging_identity_cdp.native_login` twice
with **distinct** run directories and fresh browser profiles, then require
each `auth status` and authenticated `address list` in a new process. A
restricted Identity operator should attest the two immutable issuer/subject
pairs are distinct without printing them or token claims to Actions logs.
This separate-subject attestation is essential: the probe's B address/list
negative control alone cannot distinguish two empty homes belonging to A
before A creates an address.

Create the run directory only under repository `.temp`, copy the CI-built
`amail.exe` there, and pass the two `AMAIL_HOME` directories to:

```text
AMAIL_ADDRESS_E2E_CONFIRM=RUN_STAGING_ADDRESS_E2E
AMAIL_TEST_SMTP_TOKEN=<staging-only protected token>
CF_EMAIL_ROUTING_TOKEN=<protected token>
CLOUDFLARE_ZONE_ID=<zone id>
python infra/tests/staging_address_isolation_e2e.py --amail <repo .temp binary> --home-a <repo .temp A home> --home-b <repo .temp B home> --nonce <16 private lowercase hex>
```

This is an operator template, **not** a command to execute before B exists.
Neither credentials nor auth URLs belong in arguments, logs or artifacts.
Use a nonce privately reconstructible from protected run coordinates for
crash cleanup; do not use a guessable public run ID alone. Pin staging Mail,
Identity and Login deployed revisions separately from the checkout SHA.
Before invocation, require A and B address lists empty, all ten exact
candidate rules absent, zone capacity comfortably above ten, no concurrent
address campaigns, outbound held, and an operator ready to reconcile a
cancelled runner. A test account with existing aliases must not have them
deleted merely to satisfy this harness precondition.

The probe checks all 25 names in the current Worker `RESERVED` list, creates ten
`q0..q9` nonce-scoped addresses, waits for each `active`, audits every exact
enabled literal route and ingress target, retries the first add, requires the
eleventh to yield `address_limit`, B's collision to yield
`address_unavailable`, and B's attempt to retire A's address to yield
`not_found`. It waits 60 seconds for route propagation, sends one real SMTP
message to A, and checks that B cannot list/search, get, archive, mark or
delete it while A still observes it unread. This is a **serial** quota probe;
concurrent slot-race behavior remains a separate unverified claim. Failures
are fixed labels only, without raw CLI/provider text.

Before **every** mutating address request, including expected-failure reserved,
eleventh, B-collision, and retired-name re-add attempts, the probe records the
candidate and owner. It snapshots exact candidate rules before mutation.
`finally` attempts to delete the run-owned message and every newly owned
candidate under A or B, then requires both address lists and independently
paged Cloudflare rules to match the pre-run state for **every attempted**
candidate. It never automatically deletes a candidate with a pre-existing
route, notably an operational `postmaster` or `abuse` rule; if such a candidate
is unexpectedly owned or its route changes, the test fails with manual
reconciliation required. The foreign ZIP output path lives inside B's run
home and is unlinked unconditionally even if a buggy CLI writes it before
returning an error. A cancelled runner does not
execute `finally`: a restricted operator must reconstruct **only this run's
nonce-scoped aliases and inspect the attempted reserved candidates**, then
read back provider and API state and retire only run-created resources before
another run. Do not wildcard-delete routes or consume replacement aliases to
hide orphans. After cleanup, re-add of the first name must yield
`address_retired`. The final SMTP probe requires a **permanent 5xx RCPT
refusal**. A transient 4xx refusal is inconclusive, not a pass. If Cloudflare
accepts SMTP but later bounces or reports
`routing_unknown_address`, the script says
`retired_smtp_accepted_inconclusive`; inspect the provider event and absence
of A/B delivery privately and report transport-stage semantics precisely,
not a false RCPT-rejection pass. A route-absence assertion alone is not an
SMTP outcome.

## Evidence and limits

Record the Actions URL, checkout SHA, deployed Worker IDs, UTC time,
confirmed separate-subject boolean, fixed phase markers, expected/observed
typed codes, route-count delta, cleanup result and first failure in
`docs/validation.md`. The current six mock-only checks exercise negative
code matching, no-confirmation early exit, SMTP acceptance/4xx inconclusiveness,
and candidate/operator-route reconciliation:
`python -m unittest discover -s infra/tests -p test_staging_address_isolation_e2e.py -v`.
They do not prove real quota, provider rejection or principal isolation.
No D1 fixture or account bypass is part of this campaign.

The likely alternative is a smaller unit/contract test for ten-slot
concurrency, but it cannot test Cloudflare's literal routing or the actual
Identity-scoped API. Conversely, ten live routes measure deployed control
plane behavior but not all race schedules or provider delivery after every
route. Keep those claims separate and investigate only a concrete gap.
