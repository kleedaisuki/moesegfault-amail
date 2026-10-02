# Candidate site compatibility lane

v0.1.0 is now published; [validation](validation.md) records the real release/site
outcome. Candidate deployment remains a narrowly scoped compatibility operation,
not the normal published-site path and not Mail/send authorization.

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
