# Published-site live smoke review: `aaf6365`

Date: 2026-09-30. Scope: the changed production smoke steps in `ci.yml` and `release.yml`, their source tests, and the prior route-local finding in `review-site-route-local-state-3c0eeed.md`. This is a source review, not a hosted deployment or browser acceptance.

## Verdict: GO for this correction

The commit closes the prior P2 post-deploy route-local gap. Both production workflows now use the same script: one response body and its headers are saved for each exact route (`/`, `/manual/`, `/changelog/`), and every route must return HTTP 200, contain its own published-state phrase and an actual anchor `href` equal to the v0.1.0 tag URL, omit its candidate phrase, and omit `noindex` from the body and `X-Robots-Tag` response header. `curl` does not follow redirects, so a redirect cannot masquerade as the intended page. The staging deployment steps and staging-only `_headers` rule were not changed. No substantive defect was found in the reviewed change.

The GitHub Actions YAML parses, the literal Bash block contains a correctly aligned Python heredoc after YAML block stripping, and the two workflow scripts are byte-identical. The inline parser rejects `data-href` in place of `href`. The smoke files stay under the repository's `.temp` directory and are removed by the shell exit trap; neither HTML nor response headers are printed to CI logs on normal validation failure. The focused source tests pass (2/2), including candidate-copy, lookalike-link, HTML `noindex`, and header `noindex` failures for each route.

## Boundary

This gate verifies the deployed HTML response contract, not whether the GitHub Release target exists, published archive bytes match checksums, links are visually accessible, or a real user can complete installation. A status phrase or anchor located only in non-visible HTML could satisfy this textual check, as it could the pre-deploy checker; current templates are not known to do that. The earlier release-asset and cutover-date acceptance items remain separate. No live request, deploy, or Release download was performed in this review.
