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

    def test_incomplete_or_unavailable_exact_source_inventory_is_refused(self):
        """Missing original full-main evidence cannot be replaced by newest/cached bytes."""
        for listing in ({"total_count": 1, "workflow_runs": []}, {"total_count": 0, "workflow_runs": []}):
            with patch.object(probe.subprocess, "run", return_value=Mock(stdout=b"docs/packaging.md\0")), \
                    patch.object(probe, "api", return_value=listing):
                with self.assertRaises(ValueError):
                    probe.prepare("a" * 40)

    def test_provider_capability_is_rejected_before_any_command(self):
        """The packager must never receive Cloudflare capabilities even accidentally."""
        with patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "synthetic"}), \
                patch.object(probe.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "provider_capability_refused"):
                probe.package()
            run.assert_not_called()

    def test_workflow_keeps_original_context_and_has_no_write_capability(self):
        """Independent diagnostic results cannot replace full CI or ordinary artifact gates."""
        source = (ROOT / ".github/workflows/worker-packaging-probe.yml").read_text(encoding="utf-8")
        for forbidden in ("secrets.", "environment:", "contents: write", "actions: write", "worker-build --", "rustup", "--no-bundle"):
            self.assertNotIn(forbidden, source)
        self.assertIn("github.event.pull_request.base.sha", source)
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
