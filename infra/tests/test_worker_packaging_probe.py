"""Hosted contracts for a diagnostic that never uploads or borrows release authority."""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/tests"))
import worker_packaging_probe as probe
from validated_worker_build import REQUIRED


class PackagingProbeTests(unittest.TestCase):
    """Unknown source/graph changes fail rather than turning package hashes into acceptance."""

    def test_only_diagnostic_and_public_docs_can_differ(self):
        """Adapter/compiler/runtime/admission changes cannot use an older tested build."""
        self.assertEqual(probe.changed_inputs(list(probe.DIAGNOSTIC) + ["docs/packaging.md"]), [])
        for name in ("Cargo.lock", "rust-toolchain.toml", "crates/mail-worker/entry/api.mjs",
                     "crates/mail-worker/src/lib.rs", "workers/trace-sink/wrangler.toml",
                     "infra/ci/worker_artifact.py", "infra/ci/validated_worker_build.py",
                     ".github/workflows/ci.yml", "infra/tests/worker-boundary/pnpm-lock.yaml", "unknown"):
            self.assertEqual(probe.changed_inputs([name]), [name])

    def test_commands_always_dry_run_and_never_install_or_rebuild(self):
        """Only pinned package output is inspected, no secret file or normal deployment."""
        for realm in ("default", "staging"):
            command = probe.command(Path("source.toml"), Path(".temp/output"), realm)
            self.assertEqual(command[:3], ["wrangler", "deploy", "--dry-run"])
            self.assertIn("--outdir", command)
            self.assertIn("--metafile", command)
            self.assertEqual("--env" in command, realm == "staging")
            self.assertNotIn("--secrets-file", command)
            self.assertNotIn("--no-bundle", command)

    def test_output_bytes_and_single_module_graph_are_checked(self):
        """Missing/changed Wasm and ambiguous entrypoints are rejected before runtime."""
        folder = ROOT / ".temp"
        folder.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder) as temporary:
            output = Path(temporary)
            (output / "entry.js").write_text("export default {};", encoding="utf-8")
            (output / "hash.wasm").write_bytes(b"synthetic-wasm-bytes")
            digest = hashlib.sha256(b"synthetic-wasm-bytes").hexdigest()
            self.assertEqual(probe.packaged(output, digest)["wasm_sha256"], digest)
            for mutation in ("changed", "extra_entry", "missing"):
                with self.subTest(mutation=mutation):
                    (output / "hash.wasm").write_bytes(b"synthetic-wasm-bytes")
                    (output / "extra.js").unlink(missing_ok=True)
                    if mutation == "changed":
                        (output / "hash.wasm").write_bytes(b"modified")
                    elif mutation == "extra_entry":
                        (output / "extra.js").write_text("export default {};", encoding="utf-8")
                    else:
                        (output / "hash.wasm").unlink()
                    with self.assertRaises(ValueError):
                        probe.packaged(output, digest)

    def test_explicit_full_main_push_and_manual_runs_are_accepted(self):
        """One exact run is selected, without a push-only or ambiguous listing query."""
        sha = "a" * 40
        jobs = {"total_count": len(REQUIRED),
                "jobs": [{"name": name, "conclusion": "success"}
                         for name in REQUIRED]}
        artifacts = {"total_count": 1, "artifacts": [{"name": f"worker-native-modules-{sha}",
                                                     "expired": False, "id": 456}]}
        folder = ROOT / ".temp"
        folder.mkdir(exist_ok=True)
        for event in ("push", "workflow_dispatch"):
            with self.subTest(event=event), tempfile.TemporaryDirectory(dir=folder) as temporary:
                output = Path(temporary)
                run = {"id": 123, "head_sha": sha, "run_attempt": 1, "head_branch": "main",
                       "path": ".github/workflows/ci.yml", "event": event,
                       "status": "completed", "conclusion": "success"}
                with patch.object(probe, "api", side_effect=[run, jobs, artifacts]) as api, \
                        patch.object(probe.subprocess, "run", return_value=Mock(stdout=b"docs/packaging.md\0")), \
                        patch.object(probe, "FOLDER", output), patch.object(probe, "STATE", output / "state.json"), \
                        patch.dict(os.environ, {"GITHUB_SHA": "b" * 40, "GITHUB_OUTPUT": str(output / "outputs")}):
                    probe.prepare("123")
                    self.assertEqual(api.call_args_list[0].args, ("runs/123",))
                    self.assertEqual(api.call_count, 3)
                    state = json.loads((output / "state.json").read_text())
                    self.assertEqual(state["source_sha"], sha)
                    self.assertEqual(state["run_id"], "123")
                    self.assertEqual(state["artifact_id"], 456)

    def test_original_full_source_identity_and_compile_inputs_remain_strict(self):
        """Wrong coordinate, partial check inventory and unknown inputs cannot borrow bytes."""
        for run in ({"id": 124, "head_sha": "a" * 40}, {"id": 123, "head_sha": "bad"}):
            with patch.object(probe, "api", return_value=run):
                with self.assertRaisesRegex(ValueError, "original_source_run_coordinate_required"):
                    probe.prepare("123")
        with patch.object(probe, "api", side_effect=[
                {"id": 123, "head_sha": "a" * 40, "run_attempt": 1}, {}, {}]):
            with self.assertRaisesRegex(ValueError, "successful_exact_main_source_run_required"):
                probe.prepare("123")
        for inventory in ({"total_count": 1, "jobs": []}, {"total_count": 0, "jobs": []}):
            run = {"id": 123, "head_sha": "a" * 40, "run_attempt": 1, "head_branch": "main",
                   "path": ".github/workflows/ci.yml", "event": "workflow_dispatch",
                   "status": "completed", "conclusion": "success"}
            with patch.object(probe, "api", side_effect=[run, inventory, {}]):
                with self.assertRaises(ValueError):
                    probe.prepare("123")
        with patch.object(probe, "api", side_effect=[
                {"id": 123, "head_sha": "a" * 40, "run_attempt": 1}, {}, {}]), \
                patch.object(probe, "identity", return_value={}), \
                patch.object(probe.subprocess, "run", return_value=Mock(stdout=b"Cargo.lock\0")):
            with self.assertRaisesRegex(ValueError, "diagnostic_changed_compilation_or_unknown_input"):
                probe.prepare("123")

    def test_provider_capability_is_rejected_before_any_command(self):
        """The packager must never receive Cloudflare capabilities even accidentally."""
        with patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "synthetic"}), \
                patch.object(probe.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "provider_capability_refused"):
                probe.package()
            run.assert_not_called()

    def test_workflow_keeps_original_context_and_has_no_write_capability(self):
        """Independent diagnostic results cannot replace full CI or ordinary artifact gates."""
        source = (ROOT / ".github/workflows/native-fixture.yml").read_text(encoding="utf-8")
        self.assertFalse((ROOT / ".github/workflows/worker-packaging-probe.yml").exists())
        for forbidden in ("secrets.", "environment:", "contents: write", "actions: write", "worker-build --", "rustup", "--no-bundle"):
            self.assertNotIn(forbidden, source)
        self.assertIn("if: inputs.fixture == 'packaging'", source)
        self.assertIn("if: inputs.fixture != 'packaging'", source)
        self.assertIn('prepare --build-run-id "$BUILD_RUN_ID"', source)
        self.assertIn('native_fixture.py prepare --build-run-id "$BUILD_RUN_ID" --fixture "$FIXTURE"', source)
        self.assertNotIn("github.event.pull_request", source)
        self.assertIn("persist-credentials: false", source)
        self.assertIn("artifact-ids: ${{ steps.build.outputs.artifact_id }}", source)
        self.assertLess(source.index("worker_packaging_probe.py restore"), source.index("worker_packaging_probe.py package"))
        self.assertIn("shell: bash", source)
        self.assertIn("diagnostic, no deploy", source)
        native = (ROOT / "infra/tests/worker-packaging-probe.mjs").read_text(encoding="utf-8")
        self.assertIn("modules: [inspector, ...graph]", native)
        self.assertIn("modules: [observer, ...graph]", native)
        self.assertNotIn("mail-entry-split-observer", native)
        self.assertNotIn("build/worker/shim.mjs", native)


if __name__ == "__main__":
    unittest.main()
