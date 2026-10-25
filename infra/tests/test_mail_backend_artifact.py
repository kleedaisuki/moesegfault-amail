"""The narrow backend artifact retains original bytes and the six-tree default."""
from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
import mail_backend_artifact as backend
import worker_artifact as original


class BackendArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        (ROOT / ".temp").mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=ROOT / ".temp")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for tree in original.TREES:
            path = self.root / tree
            (path / "worker").mkdir(parents=True)
            (path / "index.js").write_text("public", encoding="utf-8")
            (path / "worker/shim.mjs").write_text("public", encoding="utf-8")
        for name in original.ENTRY_FILES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("public", encoding="utf-8")

    def test_default_artifact_still_covers_all_six_trees_and_entries(self) -> None:
        values = original.files(self.root)
        self.assertEqual(len(values), 2 * len(original.TREES) + len(original.ENTRY_FILES))
        narrowed = backend.hashes(self.root)
        self.assertEqual(len(narrowed), 4)
        self.assertTrue(all(name.startswith("crates/mail-worker/") for name in narrowed))

    def test_manifest_keeps_original_identity_and_rejects_modified_bytes(self) -> None:
        identity = {"schema": "mail-backend-artifact/v1", "source_sha": "a" * 40,
                    "run_id": "123", "run_attempt": 1, "worker_build": "0.8.5", "rust": "1.98.1"}
        folder = self.root / ".temp/artifact"
        with ExitStack() as stack:
            stack.enter_context(patch.object(backend, "ROOT", self.root))
            stack.enter_context(patch.object(backend, "FOLDER", folder))
            stack.enter_context(patch.object(backend, "identity", return_value=identity))
            stack.enter_context(patch.object(backend, "original_identity", return_value=identity))
            backend.create()
            manifest = (folder / "manifest.json").read_bytes()
            backend.require()
            self.assertEqual((folder / "manifest.json").read_bytes(), manifest)
            (self.root / "crates/mail-worker/build/index.js").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "installed_bytes_changed"):
                backend.require()
            value = json.loads(manifest)
            value["run_attempt"] = True
            (folder / "manifest.json").write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "integrity_unverified"):
                backend.verified()


if __name__ == "__main__":
    unittest.main()
