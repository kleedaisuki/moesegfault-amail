# Independent workflow parser-stage guard review

## Scope and decision

Reviewed `f4e22503d4b2b2674e29947d2543da8569d3d8ec`: the independent workflow,
PyYAML dependency, loader/checker, synthetic fixtures, and design note. Inspected
the existing workflow event/container forms and the concurrent extraction of
Worker R2 dispatch inputs, without modifying those changes.

**Original GO withdrawn after hosted failure.** Run `36750216887` rejected the
guard itself at YAML line 26 before any job began. The reviewer missed the
colon-space sequence in the unquoted pip command; this was a concrete blocking
syntax defect, not merely an unverified hosted result. The correction and
current decision are recorded below. Other structural/security observations
remain applicable, but must not be read as proof that the original file ran.

No local tests, builds, live mutations, or pushes were performed. Inspection of
current workflow headers is not a substitute for the hosted parser result.

## Evidence

- The guard declares push on main/the project branch and unrestricted
  `pull_request`, rather than `workflow_dispatch` or `workflow_run`. It has no
  dependency on the accepted syntax or jobs of `ci.yml`; default-branch manual
  dispatch registration is not its bootstrap mechanism. GitHub still must
  accept the guard's own small workflow and normal repository/PR execution
  policy still applies.
- Its only action is a commit-pinned checkout with credential persistence off.
  The job requests only repository contents read, receives no application
  secrets, names no deployment environment, performs no cache save/restore,
  and invokes no provider or deployment command. PyYAML is exact-version pinned
  and installation permits binary distributions only. There is no newly shared
  build cache or release artifact that a PR could poison.
- `UniqueKeyLoader` subclasses BaseLoader, not the arbitrary-object Loader.
  Scalars, including `on`, stay strings. Mapping construction recursively
  rejects duplicate scalar keys rather than silently replacing an earlier
  input declaration; non-scalar mapping keys are rejected. YAML syntax errors
  yield fixed-location errors rather than leaking document content.
- The check counts the parsed `on.workflow_dispatch.inputs` mapping, with an
  inclusive maximum of 25. It does not count nested options, script block text,
  or `workflow_call` inputs. A missing inputs mapping defaults to empty, and
  an empty dispatch declaration is accepted. Both `.yml` and `.yaml` workflows
  in the repository's workflow directory are checked, including the guard.
- Fixtures exercise 25 accepted, 26 and the incident's 27 rejected, root and
  nested duplicates, shorthand/quoted events, malformed/container-invalid
  documents, reusable-workflow separation, and literal shell bodies. Existing
  workflows use ordinary event mappings, empty dispatch declarations, and
  nonempty jobs mappings; no merge-key or explicit-null compatibility obstacle
  was observed in their current headers.
- The lane is independent and concurrent, not a prerequisite that can prevent
  GitHub from attempting to parse another workflow. Its value is a visible,
  bounded diagnostic even when CI cannot schedule its own Infra tests. The
  design note appropriately limits the claim; expression/job schema errors
  remain outside this guard's contract.

## Minor documentation precision

`validate` says "Null/empty dispatch declarations" are valid, but BaseLoader
does not convert explicit YAML `null`/`~` into an empty value: the implementation
accepts an empty scalar (`workflow_dispatch:`), not arbitrary explicit-null
spellings. No existing workflow uses those spellings. Prefer "empty dispatch
declarations" in that docstring, or explicitly define/test additional forms
only if they become an intended GitHub-compatible contract. This is not a
blocker for the current repository or the 27-input regression.

## Hosted acceptance still required

Push the corrected immutable revision and require the independent syntax job
to run successfully, including its fixtures and all workflow files. The original
27-input `ci.yml` is expected to fail this guard until the separate extraction
reduces its inputs; that is detection, not a false positive. Record the source
SHA and workflow result before claiming the bootstrap failure is resolved.

## Focused correction review: ce1ff14

Reviewed `ce1ff149ab186d02862b808dd402a37d5936df57` after the demonstrated
parser-stage failure in `36750216887`.

**GO for another hosted push/PR validation of the corrected guard. No remaining
blocking defect found in this focused correction. Hosted success is not yet
established.**

- Original line 26 was a YAML plain scalar containing
  `--only-binary=:all:` followed by a space. The final colon-space sequence is
  forbidden inside that plain scalar. The correction changes `run` to a literal
  block scalar and indents the unchanged shell command beneath it, removing
  interpretation of its internal colons as YAML structure.
- The other two `run` commands do not contain colon-space sequences. The fix
  changes no event, permission, timeout, dependency, concurrency, credential,
  deployment, or cache behavior.
- Added fixtures validate the guard's own checked-out source and explicitly
  reject the incident's plain-scalar command while accepting its block-scalar
  representation. Their strings and file path correspond to the actual
  correction. No local fixture execution was performed.
- These fixtures cannot run before GitHub parses their containing workflow.
  They improve regression coverage after scheduling, not the fundamental
  bootstrap boundary. The design note now makes that limitation and the failed
  run explicit; another hosted run must demonstrate actual acceptance.

The earlier GO did not adequately inspect the guard's own YAML scalar syntax.
That review omission is acknowledged rather than relabeled as infrastructure
latency. Future review of this lane should explicitly inspect shell command
serialization alongside event/input structure.

## Primary references

- [GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs)
  documents the 25 top-level dispatch-input maximum and the separate default-
  branch condition for manual dispatch.
- [PyYAML Loader documentation](https://pyyaml.org/wiki/PyYAMLDocumentation#loader)
  documents BaseLoader's inert strings/lists/dictionaries and distinguishes it
  from Loader's arbitrary-object construction.
