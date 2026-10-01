# Independent review: narrow documentation push CI filtering

## Scope and verdict

Reviewed commit `2a99960d679dbfebaa56c89e6f83860ec60a1088` against main
`c6f93bf` in the isolated `.temp/docs-main-ci-filter` worktree on 2026-10-01.
Verdict: **GO for hosted source checks and normal reviewed integration**. No
substantive correctness finding was identified in the change. This is not a
provider deployment, release, actual event-delivery, or branch-protection attestation.

## Evidence and reasoning

* The complete workflow diff is six added lines under `on.push`; existing branch
  names remain `main` and `codex/amail-v0.1.0`. Only root `README.md`, Markdown
  under root `docs/`, and Markdown under `.agents/skills/` are ignored.
* GitHub documents that `**` includes slashes, patterns match whole root-relative
  paths, all changed paths must match `paths-ignore` to suppress the workflow,
  and a single unmatched path triggers it. Thus nested Markdown is covered while
  Python, YAML, JSON, TOML, Cargo inputs, runtime, unknown roots, published site
  Markdown, and mixed changes remain eligible. Quoted patterns are valid YAML.
* PR and dispatch event declarations, all job predicates, source/deployment
  concurrency expressions, Windows artifact predicates, and all other workflow
  files are unchanged. An absent heavy push run cannot enter its concurrency
  group or cancel the preceding heavy runtime run. The independent unfiltered
  `workflow-lint.yml` may cancel its own older lint run, not the heavy CI run.
* Ordinary PRs remain unfiltered and execute source checks. The historical
  `codex/amail-v0.1.0` PR job exclusion remains; this change neither removes nor
  fixes it. Current branch-protection settings were not queried. A required
  push-specific check could remain pending on an excluded push; the change must
  not be interpreted as supplying such a check.
* Release tags/manual packaging remain independently triggered. Root README is
  packaged by `release.yml` (lines 85-92), so "non-build documentation" should be
  understood as non-input to heavy automatic source checks, not never shipped.
  The unmodified release packaging lane still checks the actual release revision.
* `infra/tests/staging_ten_address_provenance.py::successful_source` independently
  requires push event, feature branch, exact checkout SHA, exact workflow, six
  successful real jobs, and completed encryption step. Windows artifact upload
  remains feature-push-only and SHA-named. A skipped docs SHA cannot substitute
  an earlier runtime run or a manual checks run for quota admission.
* The new test is discovered by existing Infrastructure `unittest discover`.
  Its fixed-glob synthetic matcher is consistent with these three simple
  patterns, explicitly disclaims general GitHub glob/event/concurrency modeling,
  and includes nested documents, mixed changes and important negative paths.
  Event-block extraction matches the current block-style YAML; it is a source
  contract, not a YAML parser. Independent hosted workflow-lint remains necessary.
* `git diff --check c6f93bf 2a99960` passed. No local project tests/builds,
  installations, provider mutations, dispatches, or pushes were performed.

## External contract

[Current official GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)
was inspected on 2026-10-01: path-filter behavior, root-relative whole paths,
`**` semantics, pending required checks, two-dot existing-branch diffs, more than
1,000 commits/diff timeout forcing execution, and the currently documented
3,000-file diff limit. The decision doc accurately distinguishes the current
limit from a conservative small-push policy. A runtime path omitted from the
provider-generated evaluated prefix cannot be proven safe by synthetic tests.

## Required follow-up and limits

Run the unchanged hosted source and syntax suites for the review candidate.
Observe the next genuine docs-only main push: independent syntax guard should
run, heavy CI should not, and a preceding runtime run should retain its original
SHA identity. Observe the next genuine mixed/runtime push for the full suite.
Do not create a gratuitous provider operation to test this optimization. Any
future build/site consumption of an ignored document requires reconsidering
that exclusion. No earlier run should be relabeled as exact-SHA success for a
later docs merge; use explicit hosted checks where exact source proof is needed.
