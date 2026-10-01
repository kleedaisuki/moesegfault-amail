"""Hosted source contracts for complete independent native matrix suites."""

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
import native_suite as suite
from workflow_source import job_block


def tap(count=7, **overrides):
    """Produce a synthetic top-level TAP summary without executing a runtime."""
    fields = {"tests": count, "pass": count, "fail": 0, "cancelled": 0, "skipped": 0, "todo": 0}
    return "\n".join(f"# {name} {value}" for name, value in {**fields, **overrides}.items()) + "\n"


class NativeSuiteTests(unittest.TestCase):
    """No disabled/orphaned suite or skipped test can masquerade as full acceptance."""

    def test_every_native_file_is_owned_once(self):
        """Historical budget reproduction joins CI; new test files need an owner."""
        files = [name for key in suite.SUITES for name in suite.command(key)[2:]]
        self.assertEqual(len(files), len(set(files)))
        self.assertEqual(set(files), {path.name for path in suite.BOUNDARY.glob("*.test.mjs")})
        self.assertEqual(sum(value[1] for value in suite.SUITES.values()), 165)

    def test_counts_reject_missing_partial_skipped_and_failed_tests(self):
        """Zero exit status does not excuse absent or skipped required coverage."""
        self.assertEqual(suite.counts(tap(), 7)["pass"], 7)
        for output in ("", tap(6), tap(**{"pass": 6}), tap(skipped=1), tap(cancelled=1),
                       tap(fail=1), tap(todo=1), tap() + "# tests 7\n"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                suite.counts(output, 7)

    def test_matrix_consumes_fixed_same_run_artifact_and_aggregate_is_strict(self):
        """Build once, independent runners, no provider credentials or skipped-as-pass gate."""
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        build, native, gate = (job_block(source, name) for name in ("worker-build", "worker-native", "worker"))
        self.assertIn("worker_artifact.py create", build)
        self.assertNotIn("pnpm test", build)
        self.assertIn("cache-workspace-crates: false", build)
        self.assertIn("artifact-ids: ${{ needs.worker-build.outputs.artifact_id }}", native)
        self.assertIn("worker_artifact.py restore", native)
        self.assertIn("max-parallel: 8", native)
        self.assertIn("fail-fast: false", native)
        self.assertNotIn("worker-build --release", native)
        self.assertNotIn("secrets.", native)
        self.assertIn("name: Rust Worker (Wasm)", gate)
        self.assertIn("always()", gate)
        self.assertIn('test "$BUILD_RESULT" = success', gate)
        self.assertIn('test "$NATIVE_RESULT" = success', gate)


if __name__ == "__main__":
    unittest.main()
