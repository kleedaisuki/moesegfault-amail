# Independent pre-merge privacy and side-effect boundary review

Date: 2026-10-01. Reviewed PR #1 source
`1a77a5034de6d7bcd7946a2e8927e984b2b91e26` relative to main
`c08a1b6bb6a7181a62d12d6ddd3a46babd4826be`.

## Assessment

**No new demonstrated P0/P1 defect was found in this bounded holistic review.**
This is not merge authorization, a full security audit, live privacy acceptance,
or permission to deploy, publish a Release/tag, or enable public sending.
Later source changes require review of their own exact SHA.

The important qualification is that **merging this tree is not equivalent to
authorizing no provider activity**: it installs an hourly production contact
health workflow on the default branch. Its intended effects are described below.

## Method and reused knowledge

Filename-first inspection located and reused the reconciliation review, API
containment review, Issues omission investigation, private-provider capture
security/lifecycle/readiness records, outbound policy, and candidate-site
publication records. This review does not repeat their exhaustive individual
implementation assessments or transfer their verdicts to unchanged live state.

Inspection used Git object reads at the fixed source, workflow triggers/job
guards/artifact selectors, API configuration and capture checker, outbound
migration/admission call sites, candidate copy/state, and both packaged Skill
blobs. A bounded committed-tree credential-pattern scan found no PEM private
key, GitHub token, OpenRouter token, or long JWT-shaped match; output was
restricted to locations, never candidate credential contents. Tracked filenames
showed no committed mail ZIP/EML or private-key file. This is not an entropy
scanner, history audit, or proof that all arbitrary private information is absent.

No project tests/builds, dependency installation, private provider request,
GitHub log/artifact download, deployment, workflow dispatch, or production
modification was performed. Only this review document is authored.

## Boundary evidence

| Boundary | Source evidence | Conclusion and limit |
| --- | --- | --- |
| Main push versus deployment | `ci.yml` deploy jobs require `workflow_dispatch`; production jobs additionally require main; `site-candidate.yml` is manual/main-only | Main push runs source CI, not Mail/site deployment. Tag pushes remain a separate Release event. |
| Automatic post-merge operations | `direct-contact-health.yml:5-7,30-49`; `direct_contact_health.py` `optional_held_policy`, `refresh`, `WRITE_SQL` | An hourly main schedule has no approval environment. With production repository secrets it reads D1; an adopted contract additionally permits routing inventory GETs and a scoped D1 health/audit write. It never creates routes, sends mail, or unholds policy. |
| Unadopted scheduled path | Health helper checks schema, actual singleton inventory, empty readiness view where applicable, and global hold | Unadopted plus proven held returns without health writes; missing/malformed schema or unproved hold fails closed. This does not make the workflow offline: provider-backed D1 reads still occur. |
| Default public sending | `0006_outbound_abuse.sql` seeds global `held` and unset release gates; `lib.rs` checks policy before admission and again before provider submission | A clean migration does not open public sending. Operator workflow actions and existing deployed DB values are distinct from migration defaults. No live policy was read. |
| API retained context | Both realms in `crates/mail-worker/wrangler.toml` explicitly disable parent capture, Logs, invocation logs, traces and Issues | Source is no longer the historical all-on configuration. `capture_disabled(..., complete=True)` requires literal false sections; omitted Issues cannot become false acceptance. Live omitted Issues remains unknown, not proved enabled or disabled. |
| Public CI artifact boundary | `ci.yml` uploads exact Windows binary, exact encrypted `capture.enc.json`, and exact queue provisioning receipt paths | No broad `.temp`/workspace upload is present in inspected CI selectors. Ciphertext upload has one-day retention and exact cleanup; queue receipts are infrastructure identities, not message bodies. This does not audit historical artifacts. |
| Private provider failure output | `private_provider_capture.py` captures child stdout/stderr, bounds provider response, writes validated ciphertext only, and emits fixed outcome labels under exception | No raw provider error output path was observed in this inspected wrapper. Native crypto and operator lifecycle remain subject to their existing scoped reviews and hosted evidence. |
| Candidate availability language | `site/src/releaseState.ts` defaults to candidate; home discloses automatic third-party indexing and candidate service-not-open notice; candidate workflow explicitly builds candidate | Source integration does not itself claim v0.1 publication, Mail availability, or open sending. Previously deployed candidate SHA is not replaced by merging source. |
| Agent Skill consistency | Both `skills/amail/SKILL.md` and `.agents/skills/amail/SKILL.md` have blob `cdde89c32285fb7916d5f1ad912252fa407b8741` | Packaged/development Skill text agrees: no implicit authorization for send/delete/register; irreversible send requires recipient/content checks; holds cannot be bypassed; background indexing and retained semantic query/vector are disclosed. |

Committed synthetic staging contacts, public operational addresses, provider
resource IDs and historical GitHub run IDs are deliberate documented test or
infrastructure identifiers, not evidence of committed user mail or credentials.
No real user recipient/body was demonstrated by this bounded inspection; the
claim must not be generalized to all historical repository content.

## Required operator awareness, not a newly invented defect

Before treating a merge as source-only, explicitly acknowledge the scheduled
health helper's intended production reads and conditional health writes. If the
actual authorization is **zero live provider activity after merge**, the hourly
job must be held through an explicitly reviewed activation gate or repository
configuration before merging. Do not silently remove the intentional health
renewal from an already adopted contract: its expiry is an outbound readiness
condition. Choosing either behavior belongs to the operator/root, not this
reviewer.

Continue to separate source CI, merge approval, deployment approval, effective
Issues evidence, controlled SMTP/R2 acceptance, Release publication and public
send authorization. Six hosted source checks reported by root are not live
acceptance evidence and were not independently retrieved here.

## External contract check

GitHub's [workflow events reference](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
confirms scheduled workflows run from the latest default-branch commit, which
is why adding the hourly file has a post-merge operational implication even
without a push-deploy job. Existing provider evidence and the response/write
schema distinction are retained in
[Issues omission semantics](issues-false-omission-semantics-2026-10-01.md);
the public Issues page failed to load during this review, so no new provider
guarantee is inferred. An academic survey would not resolve these concrete
workflow/optional-field contracts; none is manufactured for this bounded pass.
