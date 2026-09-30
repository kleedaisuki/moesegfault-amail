"""Exact Worker-cache projection contracts, executed on hosted runners only."""

import importlib.util
from pathlib import Path
import unittest
from unittest import mock


HELPER = Path(__file__).resolve().parents[1] / "ci/worker_cache_key.py"
SPEC = importlib.util.spec_from_file_location("worker_cache_key", HELPER)
KEY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(KEY)


def fixture(extra: str = "") -> str:
    """Return a bounded workflow with distinct non-building sibling jobs."""
    return (
        "name: synthetic\non:\n  workflow_dispatch:\n    inputs:\n      target:\n"
        "        options: [checks]\npermissions:\n  contents: read\njobs:\n"
        "  worker:\n    if: >-\n      inputs.target == 'checks'\n"
        "    runs-on: ubuntu-latest\n    steps:\n      - name: test\n"
        "        run: cargo test --locked\n"
        + extra + "  other:\n    steps:\n      - run: echo unrelated\n"
    )


class WorkerCacheKeyTests(unittest.TestCase):
    """Reuse requires exact compilation inputs, not unrelated manual jobs."""

    def test_sibling_and_dispatch_changes_do_not_change_projection(self) -> None:
        """Non-building trigger values/jobs cannot invalidate Worker outputs."""
        source = fixture()
        changed = source.replace("options: [checks]", "options: [checks, diagnostic]")
        changed = changed.replace("  other:\n", "  inserted:\n    runs-on: ubuntu-latest\n    env:\n      TOKEN: ${{ secrets.UNRELATED }}\n  other:\n")
        self.assertEqual(KEY.workflow_contract(source), KEY.workflow_contract(changed))

    def test_worker_and_permissions_changes_invalidate(self) -> None:
        """Whole job commands/configuration and inherited permission text bind."""
        source = fixture()
        for old, new in (
            ("cargo test --locked", "cargo test --locked --all-targets"),
            ("ubuntu-latest", "ubuntu-24.04"),
            ("contents: read", "contents: write"),
        ):
            with self.subTest(field=old):
                self.assertNotEqual(KEY.workflow_contract(source), KEY.workflow_contract(source.replace(old, new)))

    def test_unknown_inherited_and_dynamic_layout_disable_reuse(self) -> None:
        """Unsupported globals/aliases/runtime builds cannot reuse a static key."""
        source = fixture()
        invalid = [
            source.replace("jobs:\n", "env:\n  RUSTFLAGS: literal\njobs:\n"),
            source.replace("jobs:\n", "defaults:\n  run:\n    shell: bash\njobs:\n"),
            source.replace("jobs:\n", "future-build-setting: value\njobs:\n"),
            source.replace("permissions:\n", "permissions: &inherited\n"),
            source.replace("cargo test --locked", "echo ${{ vars.FLAGS }}"),
            source.replace("cargo test --locked", "echo ${{ inputs.flags }}"),
            source.replace("cargo test --locked", "echo ${{ github.sha }}"),
            source.replace("cargo test --locked", "echo $GITHUB_SHA"),
            source.replace("  other:\n", '  "other":\n'),
            source.replace("permissions:\n", "permissions:\n  contents: read\npermissions:\n"),
        ]
        for item in invalid:
            with self.subTest(source=item), self.assertRaises(ValueError):
                KEY.workflow_contract(item)

    def test_every_declared_source_identity_binds(self) -> None:
        """Root config absence, code trees, boundary and helper blobs bind keys."""
        identities = {name: "1" * 40 for name in KEY.REQUIRED}
        identities.update({name: "absent" for name in KEY.OPTIONAL})
        original = KEY.source_key("contract", identities)
        for name in identities:
            with self.subTest(name=name):
                changed = {**identities, name: "2" * 40}
                self.assertNotEqual(original, KEY.source_key("contract", changed))
        with self.assertRaises(ValueError):
            KEY.source_key("contract", {"Cargo.toml": "1" * 40})
        with self.assertRaises(ValueError):
            KEY.source_key("contract", {**identities, "crates": "absent"})

    def test_unsupported_read_produces_unique_unsaved_misses(self) -> None:
        """Failure never prints exception contents or shares a fallback key."""
        with mock.patch.object(KEY, "committed_key", side_effect=ValueError("PRIVATE_SENTINEL")):
            first, allowed = KEY.output_key()
            second, again = KEY.output_key()
        self.assertFalse(allowed)
        self.assertFalse(again)
        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^uncacheable-[0-9a-f]{32}$")

    def test_runtime_conditional_setup_is_uncacheable(self) -> None:
        """A conditional compiler setup must not vanish during validation."""
        for guard in (
            "vars.ENABLE_SPECIAL_FLAGS == 'true'",
            "${{ vars.ENABLE_SPECIAL_FLAGS == 'true' }}",
            "github.ref == 'refs/heads/main'",
            "steps.worker-bundler-cache.outputs.cache-hit != 'true'",
            ">-\n          vars.ENABLE_SPECIAL_FLAGS == 'true'",
        ):
            source = fixture().replace(
                "      - name: test\n",
                "      - name: Set compiler flags\n        if: " + guard + "\n",
            )
            with self.subTest(guard=guard), self.assertRaises(ValueError):
                KEY.workflow_contract(source)
        for name, guard in KEY.STEP_GUARDS.items():
            source = fixture().replace(
                "      - name: test\n", f"      - name: {name}\n        if: {guard}\n",
            ).replace("        run: cargo test --locked", KEY.STEP_OPERATIONS[name])
            self.assertIn(guard, KEY.workflow_contract(source))
            changed = source.replace("        if: " + guard, "        if: vars.FLAGS == 'true'")
            with self.subTest(step=name), self.assertRaises(ValueError):
                KEY.workflow_contract(changed)
            changed = source.replace(KEY.STEP_OPERATIONS[name], "        run: echo compiler setup")
            with self.subTest(operation=name), self.assertRaises(ValueError):
                KEY.workflow_contract(changed)

    def test_committed_records_cover_nested_inputs_and_absence(self) -> None:
        """The actual Git adapter binds exact objects, never working-tree edits."""
        rows = "\0".join(f"100644 blob {'1' * 40}\t{name}" for name in KEY.REQUIRED) + "\0"
        with mock.patch.object(KEY, "git_text", side_effect=[fixture(), rows]) as read:
            value = KEY.committed_key()
        self.assertRegex(value, r"^[0-9a-f]{64}$")
        self.assertEqual(read.call_args_list[0].args[0], ["show", "HEAD:.github/workflows/ci.yml"])
        self.assertIn("HEAD", read.call_args_list[1].args[0])

    def test_step_first_implicit_conditions_disable_reuse(self) -> None:
        """GitHub's implicit expressions remain dynamic without wrappers."""
        for guard in (
            "github.ref == 'refs/heads/main'",
            "inputs.enable_special_flags == true",
            "vars.ENABLE_SPECIAL_FLAGS == 'true'",
        ):
            source = fixture().replace("      - name: test\n", "      - if: " + guard + "\n")
            with self.subTest(guard=guard), self.assertRaises(ValueError):
                KEY.workflow_contract(source)
        for field in ('"if"', "'if'", "if "):
            source = fixture().replace(
                "      - name: test\n",
                "      - name: Set flags\n        " + field + ": github.ref == 'refs/heads/main'\n",
            )
            with self.subTest(field=field), self.assertRaises(ValueError):
                KEY.workflow_contract(source)

    def test_current_workflow_projection_is_cacheable(self) -> None:
        """Current supported layout must not silently fall back forever."""
        source = (HELPER.parents[2] / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        contract = KEY.workflow_contract(source)
        self.assertIn("Run built Rust Worker address-add boundary tests in workerd", contract)
        self.assertNotIn("staging-private-provider-error-capture:", contract)


if __name__ == "__main__":
    unittest.main()
