"""Focused exact-source candidate admission and Windows release-byte restoration."""
import json
import os
import stat
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
import cli_candidate as candidate
import staging_cli as staging


class StagingCandidateTests(unittest.TestCase):
    """The native acceptance harness must use reviewed bytes, never a fresh rebuild."""

    def context(self) -> dict:
        """Supply synthetic public metadata only."""
        return {"schema": "amail-cli-candidate/v1", "version": "0.1.2", "source_sha": "a" * 40,
                "run_id": "123", "run_attempt": 1, "rust": "1.90.0", "publication": "unpublished-candidate"}

    def test_admission_refuses_failed_or_different_source_runs(self):
        """Ancestry, successful artifacts in a failed run or cache are not admission."""
        run = {"id": 123, "status": "completed", "conclusion": "success", "head_sha": "a" * 40,
               "head_branch": "codex/v0.2.0-billing", "path": ".github/workflows/ci.yml",
               "event": "workflow_dispatch", "run_attempt": 1}
        for field, value in (("conclusion", "failure"), ("head_sha", "b" * 40), ("head_branch", "main")):
            with patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_SHA": "a" * 40}, clear=True), \
                 patch.object(staging, "github", return_value=dict(run, **{field: value})):
                with self.assertRaises(ValueError):
                    staging.admit("123")

    def test_admission_selects_one_immutable_artifact_from_the_successful_run(self):
        """Run identity and artifact SHA are positively checked before download."""
        run = {"id": 123, "status": "completed", "conclusion": "success", "head_sha": "a" * 40,
               "head_branch": "codex/v0.2.0-billing", "path": ".github/workflows/ci.yml",
               "event": "workflow_dispatch", "run_attempt": 1}
        artifacts = {"total_count": 1, "artifacts": [{"id": 456, "name": "cli-candidate-v0.2.0-123",
            "expired": False, "workflow_run": {"head_sha": "a" * 40}}]}
        (ROOT / ".temp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder:
            output = Path(folder) / "output"
            with patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_SHA": "a" * 40,
                                         "GITHUB_OUTPUT": str(output)}, clear=True), \
                 patch.object(staging, "github", side_effect=(run, artifacts)), \
                 patch.object(candidate, "context", return_value=self.context()), \
                 patch.object(staging, "ADMISSION", Path(folder) / "admission.json"):
                self.assertEqual(staging.admit("123")["artifact_id"], 456)
            self.assertEqual(output.read_text(), "artifact_id=456\n")

    def test_extraction_uses_checked_windows_bytes_and_rejects_tampering(self):
        """Validate exact bundle, producer identities and every checksum before execution."""
        (ROOT / ".temp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".temp") as folder:
            folder = Path(folder)
            bundle, binary = folder / "bundle", folder / "binary/amail.exe"
            bundle.mkdir()
            context = self.context()
            for target in candidate.TARGETS:
                name = candidate.archive_name(context["version"], target)
                archive = bundle / name
                if "windows" in target:
                    with candidate.zipfile.ZipFile(archive, "w") as zipped:
                        for path, data in (("amail.exe", b"reviewed-release-bytes"), ("README.md", b"public"), ("LICENSE", b"public")):
                            zipped.writestr(path, data)
                else:
                    archive.write_bytes(b"public-unix-archive")
                candidate.write_json(bundle / f"{target}.json", {**context, "target": target,
                                     "archive": name, "sha256": candidate.digest(archive)})
            # The existing assembly routine creates the real skill/manifest/checksums.
            with patch.object(candidate, "OUTPUT", bundle), patch.object(candidate, "context", return_value=context):
                candidate.assemble()
            admission = folder / "admission.json"
            candidate.write_json(admission, {"identity": context, "artifact_id": 456})
            current = dict(context, run_id="789")
            with patch.object(staging, "BUNDLE", bundle), patch.object(staging, "BINARY", binary), \
                 patch.object(staging, "ADMISSION", admission), \
                 patch.object(candidate, "context", return_value=current), \
                 patch.object(staging.subprocess, "check_output", return_value="amail 0.1.2\n") as execute:
                staging.extract()
                self.assertEqual(binary.read_bytes(), b"reviewed-release-bytes")
                self.assertEqual(execute.call_args.args[0][0], str(binary))
                archive = bundle / candidate.archive_name("0.1.2", "x86_64-pc-windows-msvc")
                archive.write_bytes(b"tampered")
                execute.reset_mock()
                with self.assertRaises(ValueError):
                    staging.extract()
                execute.assert_not_called()

    def test_windows_payload_rejects_encryption_symlink_and_duplicate_entries(self):
        """Authenticated bytes must still preserve the produced native ZIP contract."""
        def entries():
            """Default ZipInfo mode zero is compatible with Windows producers."""
            return [candidate.zipfile.ZipInfo(name) for name in ("amail.exe", "README.md", "LICENSE")]
        staging.verify_windows_entries(entries())
        regular = entries()
        regular[0].external_attr = (stat.S_IFREG | 0o755) << 16
        staging.verify_windows_entries(regular)
        symlink = entries()
        symlink[0].external_attr = (stat.S_IFLNK | 0o777) << 16
        encrypted = entries()
        encrypted[0].flag_bits = 1
        for changed in (symlink, encrypted, entries() + [candidate.zipfile.ZipInfo("amail.exe")]):
            with self.assertRaises(ValueError):
                staging.verify_windows_entries(changed)


if __name__ == "__main__":
    unittest.main()
