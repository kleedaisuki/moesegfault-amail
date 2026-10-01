# Narrow documentation-only push filtering

## Decision and reason

PR #16 merged Skills/support Markdown on top of runtime PR #17 while its exact-main
Worker check was still running. The newer push entered the same cancelable source
check concurrency group, canceling useful runtime validation and starting another
full build. Avoiding that event is simpler than adding a change-classifier job or
altering cancellation rules for every build.

Only `.github/workflows/ci.yml` gains native `push.paths-ignore`. It applies to both
existing automatic branches, `main` and `codex/amail-v0.1.0`: GitHub cannot attach
different path filters to individual branches of one `push` declaration.

| Ignored pattern | Scope |
| --- | --- |
| `README.md` | Root project overview only |
| `docs/**.md` | Markdown research, decisions, reviews, and operating notes under root `docs/` |
| `.agents/skills/**.md` | Skills and their Markdown reference material |

No YAML is ignored, including Skills `agents/openai.yaml`. No broad `**.md`, entire
directory wildcard, workflow, script, manifest, lockfile, fixture, or runtime path
is ignored. Published Astro manual/changelog content under `site/` remains checked
and is not classified as inert documentation. Any mixed push with a path outside
the table still runs the original source checks. These allowlisted Markdown paths
are non-build inputs today; if a future runtime, packaging, or site pipeline starts
consuming them, remove the affected exclusion before introducing that dependency.

## Preserved behavior and evidence boundaries

* Pull-request events have **no path filters**. Existing job predicates, including
  the historical project-branch PR duplication exception, are unchanged. Ordinary
  PR heads still execute full source checks even for documentation-only diffs.
* Manual `workflow_dispatch target=checks` remains available on an immutable SHA
  for explicit source verification; all manual deployment/acceptance predicates,
  environment controls, and concurrency groups are unchanged.
* `workflow-lint.yml` is unmodified and continues its cheap independent validation
  on every configured push and PR, including documentation-only pushes.
* `release.yml` is unmodified: version-tag and manual package verification behavior
  remains independent. Main source checks did not run on tags before this change.
* A skipped push is **not a successful CI run** and creates no new Worker proof,
  Windows executable, release artifact, or runtime acceptance evidence. An earlier
  runtime run continuing after a later docs merge attests its own original SHA,
  not the new merge SHA. Do not mark the latter exact-main check green by inference.
* Quota admission requiring full feature-push CI and its Windows artifact must use
  a reviewed runtime/source revision that actually ran that lane. A docs-only
  feature push cannot supply it. Manual source checks do not automatically replace
  a gate that specifically requires feature-push artifact provenance.

## Provider semantics and bounded monitoring

GitHub evaluates push paths from its generated diff, not the commit message or
this repository's fixture model. Existing branch pushes use two-dot comparisons.
All returned changed paths must be ignored to suppress the run; a nonmatching path
triggers it. More than 1,000 commits or a diff-generation timeout forces a run.
The current GitHub.com English documentation describes a 3,000-file diff limit;
older/other-version documentation used 300. A runtime file beyond the evaluated
prefix can be missed. Keep reviews/pushes small (conservatively below 300 changed
paths); large changes require explicit hosted checks, not confidence from absent
events. Skipped workflows can leave required checks pending; no PR event path
filter is introduced here. Reference: [GitHub workflow syntax, paths and diff
comparisons](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore).

After hosted PR checks and merge, inspect the next genuine docs-only main push:
the syntax guard should run, heavyweight CI should be absent, and an older runtime
run should not be canceled by that absent event. Inspect the next genuine mixed
or runtime push for the normal CLI/Worker/site/infra source suite. Do not create a
provider deployment or gratuitous documentation commit just to exercise the filter.
If an unexpected run is absent, compare the complete push diff and use an explicit
hosted check at the intended SHA; this optimization is not an admission gate.

## Validation scope

`infra/tests/test_docs_push_filter_contract.py` is discovered by the existing hosted
Infrastructure unittest step. It checks the exact allowlist, unchanged unfiltered
PR/manual/lint/release declarations, and synthetic documentation-only/mixed/runtime
path fixtures without a new dependency. Its deliberately narrow pattern model is
not proof of GitHub event delivery or diff truncation. Local verification is limited
to Python AST parsing, inert YAML parsing when the parser is already available, and
`git diff --check`; no local project tests, builds, installs, deployment, or dispatch.
Hosted test execution and first real-event monitoring remain required.
