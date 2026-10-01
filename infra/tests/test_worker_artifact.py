"""Hosted-only generated-module provenance tests; fixtures stay inside the repo."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
import worker_artifact as artifact


class WorkerArtifactTests(unittest.TestCase):
    """No mailbox, provider credential, compiler or project runtime is needed."""

    def setUp(self):
        """Build tiny inert module files inside the allowed hosted temp directory."""
        (ROOT / ".temp").mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=ROOT / ".temp")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.folder = self.root / "artifact"
        self.root.joinpath("rust-toolchain.toml").write_text('[toolchain]\nchannel="1.98.1"\n', encoding="utf-8")
        for tree in artifact.TREES:
            folder = self.root / tree
            (folder / "worker").mkdir(parents=True)
            (folder / "index.js").write_text("export default {};", encoding="utf-8")
            (folder / "worker/shim.mjs").write_text("export {default} from '../index.js';", encoding="utf-8")
            (folder / "module.wasm").write_bytes(b"inert-fixture")
        for patcher in (patch.object(artifact, "ROOT", self.root), patch.object(artifact, "FOLDER", self.folder),
                        patch.dict(artifact.os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_SHA": "a" * 40,
                                   "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}, clear=True)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def remove_originals(self):
        """Remove only the exact fixture trees from the verified temporary root."""
        import shutil
        for tree in artifact.TREES:
            path = (self.root / tree).resolve()
            self.assertTrue(path.is_relative_to(self.root.resolve()))
            shutil.rmtree(path)

    def test_created_artifact_restores_exact_public_modules(self):
        """An artifact supplies code, not source configs, credentials or passed tests."""
        artifact.create()
        expected = artifact.files(self.root)
        self.assertEqual(artifact.files(self.folder), expected)
        self.assertNotIn("rust-toolchain.toml", json.loads((self.folder / "manifest.json").read_text())["files"])
        self.remove_originals()
        artifact.restore()
        self.assertEqual(artifact.files(self.root), expected)

    def test_wrong_source_run_attempt_or_policy_refuses_before_copy(self):
        """A same-named artifact is not a substitute for this producer identity."""
        artifact.create()
        self.remove_originals()
        file = self.folder / "manifest.json"
        original = json.loads(file.read_text())
        for key, value in (("source_sha", "b" * 40), ("run_id", "124"), ("run_attempt", 2),
                           ("rust", "1.0.0"), ("worker_build", "0.8.3")):
            changed = {**original, key: value}
            file.write_text(json.dumps(changed))
            with self.subTest(key=key), self.assertRaises(ValueError):
                artifact.restore()
            self.assertFalse((self.root / artifact.TREES[0]).exists())

    def test_modified_missing_or_extra_file_refuses(self):
        """Every byte and complete generated file set must match the receipt."""
        artifact.create()
        self.remove_originals()
        target = self.folder / artifact.TREES[0] / "index.js"
        original = target.read_bytes()
        target.write_bytes(b"modified")
        with self.assertRaises(ValueError):
            artifact.restore()
        target.write_bytes(original)
        extra = self.folder / "unexpected.json"
        extra.write_text("{}")
        with self.assertRaises(ValueError):
            artifact.restore()
        extra.unlink()
        target.unlink()
        with self.assertRaises(ValueError):
            artifact.restore()

    def test_existing_tree_and_wrong_execution_context_fail(self):
        """Never mix compiled outputs or run a hosted test operation accidentally locally."""
        artifact.create()
        with self.assertRaises(ValueError):
            artifact.restore()
        with patch.dict(artifact.os.environ, {"GITHUB_ACTIONS": "false"}):
            with self.assertRaises(ValueError):
                artifact.context()

    def test_generated_inputs_are_bounded_and_not_configs(self):
        """Selection protects config/data; SDK maps/licenses are valid generated files."""
        private = self.root / "private.env"
        private.write_text("inert fixture")
        generated = self.root / artifact.TREES[0] / "shim.mjs.map"
        generated.write_text("{}")
        artifact.create()
        manifest = json.loads((self.folder / "manifest.json").read_text())
        self.assertNotIn("private.env", manifest["files"])
        self.assertIn(generated.relative_to(self.root).as_posix(), manifest["files"])
        with patch.object(artifact, "LIMIT", 1), self.assertRaises(ValueError):
            artifact.files(self.root)


if __name__ == "__main__":
    unittest.main()
