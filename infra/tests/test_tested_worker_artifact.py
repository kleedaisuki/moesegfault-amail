"""Hosted synthetic pre-submit artifact checks, with no toolchain/provider calls."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import tested_worker_artifact as verifier


class TestedWorkerArtifactTests(unittest.TestCase):
    """Neither a valid original manifest nor intact installed Wasm alone suffices."""

    def setUp(self):
        """Inert public trees and hosted identity live exclusively under repo .temp."""
        (ROOT / ".temp").mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=ROOT / ".temp")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.folder = self.root / "artifact"
        self.root.joinpath("rust-toolchain.toml").write_text('[toolchain]\nchannel="1.98.1"\n')
        for tree in verifier.artifact.TREES:
            directory = self.root / tree
            (directory / "worker").mkdir(parents=True)
            (directory / "index.js").write_text("export default {};")
            (directory / "worker/shim.mjs").write_text("export default {};")
            (directory / "module.wasm").write_bytes(b"inert-public-fixture")
        for name in verifier.artifact.ENTRY_FILES:
            entry = self.root / name
            entry.parent.mkdir(parents=True, exist_ok=True)
            entry.write_text("export default class Entry {};")
        for patcher in (patch.object(verifier.artifact, "ROOT", self.root),
                        patch.object(verifier.artifact, "FOLDER", self.folder),
                        patch.dict(verifier.artifact.os.environ, {"GITHUB_ACTIONS": "true",
                                   "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123",
                                   "GITHUB_RUN_ATTEMPT": "1"}, clear=True)):
            patcher.start()
            self.addCleanup(patcher.stop)
        verifier.artifact.create()

    def test_exact_same_run_original_and_installed_modules_pass(self):
        """The byte check grants no runtime or business admission by itself."""
        for component in ("mail_api", "trace_sink", "mail_ingress", "mail_events"):
            verifier.require_artifact(component)

    def test_rebuilt_modified_missing_and_extra_installed_bytes_refuse(self):
        """A fresh manifest cannot bless post-test generated tree drift."""
        directory = self.root / verifier.artifact.TREES[0]
        path = directory / "index.js"
        original = path.read_bytes()
        for value in (b"rebuilt", None):
            path.write_bytes(value) if value is not None else path.unlink()
            with self.subTest(value=value), self.assertRaises(ValueError):
                verifier.require_artifact("mail_api")
            path.write_bytes(original)
        extra = directory / "extra.js"
        extra.write_text("export default {};")
        with self.assertRaises(ValueError):
            verifier.require_artifact("mail_api")

    def test_wrong_source_run_attempt_compiler_and_bundler_refuse(self):
        """Ordinary promotion never uses the canary's ancestor-diff exemption."""
        path = self.folder / "manifest.json"
        original = json.loads(path.read_text())
        for field, value in (("source_sha", "b" * 40), ("run_id", "124"), ("run_attempt", 2),
                             ("rust", "1.0.0"), ("worker_build", "0.0.1")):
            path.write_text(json.dumps({**original, field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                verifier.require_artifact("trace_sink")
        path.write_text(json.dumps(original))

    def test_changed_entry_boundary_refuses_even_with_intact_generated_modules(self):
        """A deploy may not introduce new handlers through post-test source edits."""
        path = self.root / verifier.artifact.ENTRY_FILES[-1]
        path.write_text("export * from '../build/worker/shim.mjs';")
        with self.assertRaisesRegex(ValueError, "artifact_file_integrity_mismatch"):
            verifier.require_artifact("mail_events")

    def test_original_extra_bytes_and_unknown_component_refuse(self):
        """A receipt selects only reviewed generated trees and explicit components."""
        (self.folder / "private.env").write_text("synthetic-private-marker")
        with self.assertRaises(ValueError):
            verifier.require_artifact("trace_sink")
        with self.assertRaises(ValueError):
            verifier.require_artifact("unknown")


if __name__ == "__main__":
    unittest.main()
