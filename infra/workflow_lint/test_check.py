"""Synthetic regression fixtures for the independent parser-stage guard."""

import unittest

from check import WORKFLOWS, WorkflowError, validate


def workflow(inputs: int, event: str = "workflow_dispatch") -> str:
    """Generate synthetic inputs without fixtures outside the repository."""
    declarations = "".join(f"      input_{index}: {{type: string}}\n" for index in range(inputs))
    return f"on:\n  {event}:\n    inputs:\n{declarations}jobs:\n  check: {{runs-on: ubuntu-latest}}\n"


class WorkflowGuardTests(unittest.TestCase):
    """Catch the exact rejected workflow and YAML ambiguity independently."""

    def test_guard_workflow_itself(self) -> None:
        """Include the guard's own source in the hosted regression fixtures."""
        validate((WORKFLOWS / "workflow-lint.yml").read_text(encoding="utf-8"))

    def test_pip_colon_option_requires_block_scalar(self) -> None:
        """A shell colon followed by space must not become YAML mapping syntax."""
        header = "on: push\njobs:\n  check:\n    steps:\n"
        command = "python -m pip install --only-binary=:all: -r requirements.txt"
        with self.assertRaisesRegex(WorkflowError, "invalid YAML"):
            validate(header + "      - run: " + command + "\n")
        validate(header + "      - run: |\n          " + command + "\n")

    def test_dispatch_limit_inclusive(self) -> None:
        """The documented 25-input maximum remains accepted."""
        validate(workflow(25))

    def test_dispatch_over_limit(self) -> None:
        """Reject the first excess input and the observed 27-input incident."""
        for count in (26, 27):
            with self.subTest(count=count), self.assertRaisesRegex(WorkflowError, "exceeds limit=25"):
                validate(workflow(count))

    def test_reusable_inputs_not_dispatch(self) -> None:
        """Do not impose a dispatch-only limit on workflow_call."""
        validate(workflow(27, "workflow_call"))

    def test_empty_and_shorthand_events(self) -> None:
        """Common event forms and quoted/unquoted on keys remain valid."""
        for events in ("on: push", "on: [push, pull_request]", "on:\n  workflow_dispatch:", "'on':\n  workflow_dispatch: {}"):
            with self.subTest(events=events):
                validate(events + "\njobs:\n  check: {}\n")

    def test_duplicate_keys(self) -> None:
        """Reject duplicates at the root and nested input declarations."""
        for source in ("on: push\non: pull_request\njobs: {check: {}}", "on:\n  workflow_dispatch:\n    inputs:\n      x: {}\n      x: {}\njobs: {check: {}}"):
            with self.subTest(source=source), self.assertRaisesRegex(WorkflowError, "duplicate"):
                validate(source)

    def test_malformed_and_invalid_structure(self) -> None:
        """Fail closed before counting inputs if YAML or container types fail."""
        for source in ("on: [push", "- push", "on: push\njobs: []", "on: {}\njobs: {check: {}}", "on:\n  workflow_dispatch: []\njobs: {check: {}}", "on:\n  workflow_dispatch:\n    inputs: []\njobs: {check: {}}"):
            with self.subTest(source=source), self.assertRaises(WorkflowError):
                validate(source)

    def test_block_body_not_counted(self) -> None:
        """Shell text that resembles declarations does not affect YAML counts."""
        validate("on: push\njobs:\n  check:\n    steps:\n      - run: |\n          workflow_dispatch:\n            inputs:\n              fake: data\n")


if __name__ == "__main__":
    unittest.main()
