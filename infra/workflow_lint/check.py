"""Reject malformed workflow YAML and excess dispatch inputs without execution.

Usage: python infra/workflow_lint/check.py
This narrow guard does not evaluate GitHub expressions or replace hosted CI.
"""

from pathlib import Path
import sys

import yaml


MAX_DISPATCH_INPUTS = 25
WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


class WorkflowError(ValueError):
    """A workflow violates a checked parser-stage contract."""


class UniqueKeyLoader(yaml.BaseLoader):
    """Preserve scalar strings and reject ambiguous duplicate mapping keys."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict:
        """Build inert mappings only; duplicate keys must never overwrite policy."""
        result = {}
        for key_node, value_node in node.value:
            if not isinstance(key_node, yaml.ScalarNode):
                raise WorkflowError("mapping key must be a scalar")
            key = self.construct_scalar(key_node)
            if key in result:
                raise WorkflowError(f"duplicate mapping key at line {key_node.start_mark.line + 1}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def validate(source: str) -> None:
    """Check YAML structure and the documented 25 top-level dispatch-input limit.

    BaseLoader never instantiates tagged Python objects and keeps `on` a string.
    Null/empty dispatch declarations and shorthand events are valid. Reusable
    workflow_call inputs are not governed by the workflow_dispatch count limit.
    """
    try:
        workflow = yaml.load(source, Loader=UniqueKeyLoader)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        location = f" at line {mark.line + 1}" if mark else ""
        raise WorkflowError(f"invalid YAML{location}") from error
    if not isinstance(workflow, dict):
        raise WorkflowError("workflow root must be a mapping")
    if not isinstance(workflow.get("jobs"), dict) or not workflow["jobs"]:
        raise WorkflowError("jobs must be a nonempty mapping")
    events = workflow.get("on")
    if not isinstance(events, (str, list, dict)) or not events:
        raise WorkflowError("on must declare events")
    if not isinstance(events, dict) or "workflow_dispatch" not in events:
        return
    dispatch = events["workflow_dispatch"]
    if dispatch == "":
        return
    if not isinstance(dispatch, dict):
        raise WorkflowError("workflow_dispatch must be empty or a mapping")
    inputs = dispatch.get("inputs", {})
    if not isinstance(inputs, dict):
        raise WorkflowError("workflow_dispatch.inputs must be a mapping")
    if len(inputs) > MAX_DISPATCH_INPUTS:
        raise WorkflowError(f"workflow_dispatch inputs={len(inputs)} exceeds limit={MAX_DISPATCH_INPUTS}")


def main() -> int:
    """Inspect tracked-location YAML files and return nonzero for any failure."""
    paths = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    if not paths:
        print("workflow_guard: no workflow files", file=sys.stderr)
        return 1
    failures = 0
    for path in paths:
        try:
            validate(path.read_text(encoding="utf-8"))
        except (WorkflowError, OSError, UnicodeError) as error:
            print(f"workflow_guard: {path.name}: {error}", file=sys.stderr)
            failures += 1
    print(f"workflow_guard: files={len(paths)} failures={failures}")
    return int(failures != 0)


if __name__ == "__main__":
    sys.exit(main())
