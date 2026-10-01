# Review: fixed candidate deployment and live browser evidence

## Decision and scope

**GO for the focused documentation-only PR. No substantive finding.** Reviewed
`e4aeb0fbe59fcb50e96658c2a6d956955d3089c7` against main `4370d2d` in
`.temp/site-live-candidate-evidence-review`. The four changed files are Markdown
only; this review adds no production change. Confidence is high for the fixed
run identity, observed workflow outcomes and evidence-boundary assessment.

## Independent evidence checked (2026-10-01 04:04–04:06 UTC)

Bounded read-only GitHub REST queries used `gh api` for the six explicitly named
runs, their jobs/steps, PR #24 and the live-browser artifact metadata. Selected
job-log lines were filtered in memory; no raw logs/provider responses were saved.
All six runs are attempt 1, branch main, exact source
`47d391615e671722c7f01bb7cf8963987f6150f9`.

| Evidence | Independent result |
| --- | --- |
| [PR #24](https://github.com/kleedaisuki/moesegfault-amail/pull/24) | Head `9eccc7e83adcdf25fbc585e4cae496d0a1b556f5`; exact merge source above; merged 03:34:05 UTC. |
| [Site CI 36811105233](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36811105233) | Push, completed success, `.github/workflows/site-ci.yml`; required `Astro candidate site source checks` job succeeded. |
| [Mail CI 36811105489](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36811105489) | Push, completed success, `.github/workflows/ci.yml`; not the required candidate-site workflow. |
| [Source preview 36811172838](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36811172838) | Dispatch, completed success; hosted preview build step succeeded. Separate from live acceptance. |
| [Rejected deploy 36811629173](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36811629173) | Dispatch, completed failure. Log identifies `SOURCE_CI_RUN_ID: 36811105489`; exact-source gate failed. Provider deployment and live smoke steps were skipped. This proves that run did not reach its provider mutation step, not global absence of other actors' mutations. |
| [Corrected deploy 36812171794](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36812171794) | Dispatch, completed success at 03:48:59 UTC. Input `36811105233`; both publication preflights passed with `published_release=not_visible tag=absent`. Version `6707f3ec-f28b-45be-8d85-a16811fd81ea`; 03:48:57 smoke `pages=3 toc=2 state=candidate`. |
| [Live browser 36812450154](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36812450154) | Dispatch, completed success at 03:52:57 UTC. Live identity step passed; preview build skipped. Artifact `site-browser-36812450154-1`, ID `11140635520`, not expired at inspection. |

The exact named hosted browser artifact was independently retrieved under the
review worktree's `.temp/browser-artifact`; its parsed report reproduced source
and deployedRevision equal to the exact SHA, live-candidate target, public base,
03:52:23.131–03:52:52.938 UTC interval, three routes at four widths, 12 cases,
78 passed checks, zero failures and 66 PNG files. The duplicate retrieval was
removed after verifying its resolved absolute path was inside this worktree;
the existing root-owned artifact remains available at the ledger's recorded path.
No screenshots were visually approved in this review.

Fresh tag-ref and release-by-tag GETs for v0.1.0 returned HTTP 404. This corroborates
continued token-visible nonpublication, not absence of hidden drafts or release
assets from every possible channel. The change correctly records the root's
04:00 observation as historical; this review does not retroactively certify its
timestamp. The fixed deploy's own two publication preflights independently agree.

## Contracts, links and history

- Inspected the gate's explicit `site-ci.yml` and exact job identity checks and
  the browser harness's declared contract. The incident attribution is
  consistent with the executable failure path; no gate relaxation is proposed.
- Checked local Markdown destinations in all changed files: none missing.
  Newly added current-ledger/browser anchors match their actual headings.
  Exact run and PR links resolve to the independently queried GitHub resources.
  Existing unrelated external links were not exhaustively revalidated.
- Earlier de2f150 deployment/version, dated DNS evidence and failed-browser
  observations remain in their original dedicated sections. Top-level current
  entries explicitly supersede them. The updated summary removes an obsolete
  current-state claim without erasing its historical source record.
- Automated checks are not inflated into human visual, screen-reader, clean
  archive installation, provider health/DNS, Mail delivery or public release
  acceptance. Newer main is expressly not claimed as deployed.
- No email-address strings occur in the four changed documents. Manual diff
  inspection found only public site/repository identities, CI/Worker identifiers
  and Secret names, not private addresses, credentials or secret values.
- `git diff --check 4370d2d e4aeb0f` passed. No project tests/build, dependency
  install, local browser execution, push, workflow dispatch, provider mutation,
  SMTP, tag or Release creation was performed.

## Remaining limits

This is evidence-documentation review, not independent live-site recertification
or a provider-wide audit. Mail sending remains held per the unchanged ledger;
no new send-policy attestation was queried. Future deployment still requires
fresh exact-source site CI and separate authorization. No correction is required
for this focused documentation PR.
