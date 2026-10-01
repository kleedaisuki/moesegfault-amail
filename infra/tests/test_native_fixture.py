"""Source contracts for diagnostic-only same-compilation-input native replay."""

from pathlib import Path
import sys
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
import native_fixture as replay


class NativeFixtureTests(unittest.TestCase):
    """No new Rust/build input or arbitrary Node option can borrow old evidence."""

    def test_only_fixture_and_public_documentation_changes_can_replay(self):
        self.assertEqual(replay.compile_changes(["docs/trace.md", "infra/tests/worker-boundary/address-add.test.mjs",
                                                "infra/tests/worker-boundary/native-observer.mjs"]), [])
        for path in ("crates/mail-worker/src/lib.rs", "Cargo.lock", "rust-toolchain.toml", ".github/workflows/ci.yml",
                     "infra/ci/worker_artifact.py", "crates/mail-worker/src/api-entry.mjs", "unknown.txt"):
            self.assertEqual(replay.compile_changes([path]), [path])

    def test_fixture_is_one_owned_file_not_shell_flags_or_paths(self):
        self.assertEqual(replay.fixture("address-add.test.mjs").name, "address-add.test.mjs")
        for name in ("../address-add.test.mjs", "--test-name-pattern", "unknown.test.mjs", "a.test.mjs;echo secret"):
            with self.assertRaises(ValueError):
                replay.fixture(name)

    def test_incomplete_or_failed_producer_inventory_is_refused(self):
        for inventory in [{"total_count": 2, "jobs": []},
                          {"total_count": 1, "jobs": [{"name": "Build and unit-check Rust Worker modules", "conclusion": "failure"}]}]:
            with patch.object(replay, "api", side_effect=[
                    {"path": ".github/workflows/ci.yml", "status": "completed", "run_attempt": 1}, inventory]):
                with self.assertRaises(ValueError):
                    replay.prepare("123", "address-add.test.mjs")

    def test_workflow_is_read_only_and_not_a_promotion_or_build_gate(self):
        source = (ROOT / ".github/workflows/native-fixture.yml").read_text()
        self.assertNotIn("secrets.", source)
        self.assertNotIn("worker-build", source)
        self.assertNotIn("rustup", source)
        self.assertNotIn("wrangler", source)
        self.assertIn("persist-credentials: false", source)
        self.assertIn("not release evidence", source)
        self.assertIn("native_fixture.py restore", source)
        self.assertIn("artifact-ids: ${{ steps.build.outputs.artifact_id }}", source)


if __name__ == "__main__":
    unittest.main()
