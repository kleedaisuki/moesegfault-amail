# Independent workflow parser-stage guard

## Problem and boundary

GitHub rejected CI run `36748735128` before any job started: the workflow
declared 27 `workflow_dispatch` inputs, above the documented maximum of 25.
CI's own Infra tests cannot catch this failure because GitHub must accept
`ci.yml` before it can schedule those tests. This is a bootstrap dependency,
not a Rust build or provider latency problem.

`workflow-lint.yml` is a separate, small push/PR workflow with no dependency on
CI, no deployment, no environment, no application secrets, and read-only
repository permissions. It parses every `.yml` and `.yaml` workflow using
pinned PyYAML 6.0.3 BaseLoader, rejecting malformed YAML, duplicate mapping
keys, invalid checked container shapes, and more than 25 dispatch inputs.
Unquoted `on` remains a string rather than YAML 1.1's Boolean. Parsing never
executes YAML constructors, expressions, shell commands, or workflows.

The lane intentionally has no path filter: every supported branch push or PR
gets a visible result, without depending on heavy CI selection. Checkout is
pinned by commit and does not persist credentials. The check lane is cancelable
and independent of state-changing deployment concurrency groups. Target wall
time is under one minute after runner scheduling, with a two-minute job timeout;
actual timing still requires hosted evidence. A malformed guard workflow itself
can still prevent this guard from running; keeping its own configuration small
reduces, but does not eliminate, that bootstrap boundary.

## Verification and limitations

Hosted commands (do not run builds/tests on the developer workstation):

```sh
python -m pip install --only-binary=:all: -r infra/workflow_lint/requirements.txt
python -m unittest discover -s infra/workflow_lint -p 'test_*.py' -v
python infra/workflow_lint/check.py
```

Fixtures cover 25 accepted, 26/27 rejected, reusable inputs not subject to the
dispatch limit, quoted/unquoted and shorthand event declarations, duplicate
keys, malformed YAML, invalid container types, and misleading shell block text.
Tests are isolated from the existing dependency-free Infra discovery lane.
No local tests or builds were performed for implementation. This is a focused
early guard, not a complete Actions schema/expression validator, not proof of
deployment eligibility, and not a replacement for hosted execution and review.

Sources:

- [GitHub workflow syntax: workflow_dispatch inputs](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs): maximum 25 top-level inputs.
- [PyYAML Loader documentation](https://pyyaml.org/wiki/PyYAMLDocumentation#loader): BaseLoader produces only basic inert objects and does not resolve tags.
