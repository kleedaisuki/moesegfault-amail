# Review: workflow contract extraction stability (907ea3f)

## Scope and method

Reviewed commit `907ea3f245d14ad9a32fa39e3684a2bddaf1f97c`, all thirteen migrated contract-test files, the new extractor and synthetic fixtures, the independent workflow YAML guard, and the documented hosted feedback failure mechanism. This is static review only: no local tests, live provider calls, workflow dispatch, or production-source edits were performed. Other agents' uncommitted files were excluded.

## Decision

**Correction required before treating the shared extractor as a fail-closed safety boundary.** Ordinary repository-style plain two-space sibling insertion is correctly isolated and all pre-existing secret, guard, and order assertions are retained. One material unsupported-boundary case can silently merge distinct executable jobs.

## P2 — Quoted sibling job keys are absorbed into the preceding safety job

Location: `infra/tests/workflow_source.py:26` (the `starts` regular expression), with the returned slice constructed at lines 35–36. Confidence: high, established directly from the regex and slice semantics; no execution was used.

The matcher recognizes only unquoted identifiers at exactly two spaces. Valid YAML also permits quoted scalar job identifiers. For example:

```yaml
jobs:
  read-only:
    runs-on: ubuntu-latest
    steps:
      - run: echo safe
  "unrelated_new":
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    steps:
      - run: echo separate
  old-successor:
    runs-on: ubuntu-latest
    steps:
      - run: echo end
```

Here `starts` recognizes `read-only` and `old-successor`, but not `"unrelated_new"`. Consequently `job_block(source, "read-only")` includes the entire unrelated executable job, and `assertIn("github.event_name == 'workflow_dispatch'", block)` succeeds although the target has no manual-event guard. The adjacent job's credentials can likewise contaminate secret-scope checks. This is the same class of boundary contamination the change aims to remove, not merely a missing style fixture.

The independent `infra/workflow_lint/check.py` YAML guard does not prohibit quoted keys: it loads scalar keys normally and checks structure, duplicates, and dispatch-input count. Therefore that lane does not close this case. The helper documents a constrained layout, but currently does not reject unsupported sibling syntax; unsupported input silently falls into the prior job body. Similarly, the claimed rejection of odd-spacing layouts is not explicitly implemented or fixture-covered. Malformed indentation may fail another parser, but it should not be described as a property of this extractor.

Practical correction: retain the small raw-source helper, but make the supported layout an enforced precondition. Reject unsupported two-space job headers (including quoted keys) and unsupported section boundaries/indentation before slicing, or use a safe YAML parser's mapping-node source marks to locate actual sibling boundaries while keeping raw text for assertions. Do not merely broaden the identifier regex without also checking for silently ignored mapping headers. Add a quoted adjacent credential job and a guard moved to that job as negative fixtures, plus explicit odd-spacing and unsupported-section fixtures. Either reject these cases or isolate them correctly; they must not return a merged target block.

## Preserved behavior and useful improvements

- Every changed existing assertion remains present; the diff replaces extraction only and adds imports.
- Normal plain sibling identifiers with underscores and hyphens are recognized independently of caller-selected successor names.
- The new adjacent credential job fixture directly exercises the two demonstrated false-failure mechanisms: unrelated secret contamination and guard contamination.
- CRLF normalization, duplicate exact job names, duplicate exact `jobs` headers, missing targets/sections, and recognized inline job mappings have explicit fixture coverage.
- Nested shell and step lines remain deeper than two spaces in the supported layout and therefore cannot become normal sibling boundaries.
- The final recognized job stops at an ordinary unquoted top-level section.

## Validation limits and next step

No finding implies a current deployed workflow lost its guard; the risk is a regression-test false negative after a valid formatting change. The correction should receive independent static review followed by GitHub-hosted source checks and the independent YAML guard. This review does not verify hosted execution, the two historical run payloads, or unrelated provider diagnostics.
