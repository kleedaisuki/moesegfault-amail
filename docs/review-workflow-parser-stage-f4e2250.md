# Independent workflow parser-stage guard review

## Scope and decision

Reviewed `f4e22503d4b2b2674e29947d2543da8569d3d8ec`: the independent workflow,
PyYAML dependency, loader/checker, synthetic fixtures, and design note. Inspected
the existing workflow event/container forms and the concurrent extraction of
Worker R2 dispatch inputs, without modifying those changes.

**GO for hosted push/PR validation. No substantive blocking defect found in the
reviewed change.** This does not certify successful hosted execution, complete
GitHub Actions schema validation, or the separate R2 workflow extraction.

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

## Primary references

- [GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs)
  documents the 25 top-level dispatch-input maximum and the separate default-
  branch condition for manual dispatch.
- [PyYAML Loader documentation](https://pyyaml.org/wiki/PyYAMLDocumentation#loader)
  documents BaseLoader's inert strings/lists/dictionaries and distinguishes it
  from Loader's arbitrary-object construction.
