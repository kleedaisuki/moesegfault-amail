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

    def test_partial_build_and_successful_acceptance_keep_separate_identities(self) -> None:
        source = {"id": int(backend.PARTIAL_RUN), "head_sha": backend.PARTIAL_SOURCE,
                  "path": ".github/workflows/ci.yml", "event": "workflow_dispatch", "head_branch": backend.BRANCH,
                  "repository": {"full_name": backend.accepted.REPO}, "status": "completed",
                  "conclusion": "failure", "run_attempt": 1}
        acceptance = {**source, "id": 124, "head_sha": "b" * 40, "conclusion": "success"}
        with patch.object(backend.accepted, "github", side_effect=[source, acceptance]), \
             patch.object(backend.accepted, "successful_jobs") as gates, \
             patch.object(backend.accepted, "unique_artifact", side_effect=[11, 12, 13]), \
             patch.object(backend.accepted, "git", return_value=type("Result", (), {"returncode": 0})()):
            value = backend.producer(backend.PARTIAL_RUN, "124")
            self.assertEqual(value["source_sha"], backend.PARTIAL_SOURCE)
            self.assertEqual(value["run_id"], backend.PARTIAL_RUN)
            self.assertEqual(value["staging_run_id"], "124")
            self.assertEqual(value["staging_source_sha"], "b" * 40)
            gates.assert_any_call(backend.PARTIAL_RUN, frozenset({backend.BUILD_JOB}))
            gates.assert_any_call("124", frozenset({backend.STAGING_JOB, "Semantic reuse live journey"}))


if __name__ == "__main__":
    unittest.main()
