# Candidate site compatibility lane

v0.1.0 is now published; [validation](validation.md) records the real release/site
outcome. Candidate deployment remains a narrowly scoped compatibility operation,
not the normal published-site path and not Mail/send authorization.

The v0.1.2 staging candidate uses the existing CI staging target, not this
production compatibility writer. It remains explicitly unpublished while public
v0.1.0 download links and pages stay untouched. Generated staging asset headers
pin `X-Amail-Candidate-Revision` to the deployed source SHA, scoped only to the
staging hostname. The existing `candidate_site.py --realm staging` smoke verifies
all three routes, current copy, navigation, exploration commands and TOC anchors;
HTTP 200 alone cannot admit stale candidate bytes. The browser workflow's bounded
`live-staging` target checks the same source pin and captures owner-review evidence.
Neither target is permission to publish a Release or test production mail.

A reviewed main-only manual candidate-site workflow may deploy truthful candidate
copy without claiming a Release exists. Exact source CI, explicit owner approval,
no conflicting site/tag writer and appropriate release-state checks remain required.
Never replace published pages with candidate copy as an incidental maintenance step.

AMAIL_RELEASE_STATE is fail-closed: candidate/unset renders prerelease copy;
published requires the real nondraft Release and expected assets. Unknown fails build.
Staging always uses candidate. Generated candidate headers add noindex/nofollow and
opaque source revision only to that candidate build, never shared source _headers.
A fresh published build must not inherit them. Source checks and hosted route smoke
cover home/manual/changelog, navigation, TOCs, status/links and live headers.

Release-backed published deployment checks actual public bytes/checksums before site
promotion. Token visibility is not inventory of every internal untagged draft.
After a too-early smoke inspect existing public routes; do not repeat deployment
or rewrite failed-run history merely to produce green CI.
