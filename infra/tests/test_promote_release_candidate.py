"""Incremental release packaging preserves the tested native bytes and their origin."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("promote_candidate", ROOT / "infra/release/promote_candidate.py")
assert SPEC is not None and SPEC.loader is not None
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class PromoteCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        (ROOT / ".temp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".temp", prefix="release-promotion-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / ".temp/release-candidate"
        self.folder.mkdir(parents=True)
        self.admission_file = self.root / ".temp/admission.json"
        for name, value in (("ROOT", self.root), ("FOLDER", self.folder), ("ADMISSION", self.admission_file)):
            replaced = patch.object(release, name, value)
            replaced.start()
            self.addCleanup(replaced.stop)
        (self.root / "rust-toolchain.toml").write_text('[toolchain]\nchannel="1.98.1"\n', encoding="utf-8")
        (self.root / "README.md").write_text("Public tagged manual\n", encoding="utf-8")
        (self.root / "LICENSE").write_text("Public license\n", encoding="utf-8")
        self.record: dict[str, Any] = {
            "schema": "amail-accepted-candidate/v1", "version": "0.3.1", "source_run": "101",
            "source_sha": "a" * 40, "staging_acceptance_run": "102",
        }
        self.producer = {"source_sha": "a" * 40, "run_id": "101", "run_attempt": 1,
                         "artifact_id": 200, "cli_artifact_id": 201}
        self.admission = {"record": self.record, "producer": self.producer,
                          "release_sha": "c" * 40,
                          "acceptance": {"run_id": "102", "source_sha": "b" * 40, "artifact_id": 202}}
        self.identity = {"schema": "amail-cli-candidate/v1", "version": "0.3.1", "source_sha": "a" * 40,
                         "run_id": "101", "run_attempt": 1, "rust": "1.98.1", "publication": "unpublished-candidate"}

    def write_record(self) -> None:
        path = self.root / "infra/release/accepted-candidate.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.record), encoding="utf-8")

    def bundle(self) -> None:
        for target in release.candidate.TARGETS:
            archive = release.candidate.archive_name("0.3.1", target)
            binary = "amail.exe" if "windows" in target else "amail"
            release.write_archive(self.folder / archive, {
                binary: ("native-" + target).encode(), "README.md": b"Staging candidate docs",
                "LICENSE": b"Original license",
            })
            metadata = {**self.identity, "target": target, "archive": archive,
                        "sha256": release.candidate.digest(self.folder / archive)}
            (self.folder / f"{target}.json").write_text(json.dumps(metadata), encoding="utf-8")
        (self.folder / "amail-agent-skill-v0.3.1-candidate.zip").write_bytes(b"candidate skill")
        hashes = {path.name: release.candidate.digest(path) for path in self.folder.iterdir()}
        (self.folder / "candidate.json").write_text(json.dumps({
            **self.identity, "targets": list(release.candidate.TARGETS), "files": hashes,
        }), encoding="utf-8")
        checksums = "".join(f"{release.candidate.digest(path)}  {path.name}\n" for path in sorted(self.folder.iterdir()))
        (self.folder / "SHA256SUMS").write_text(checksums, encoding="utf-8")

    def test_reuse_matrix_builds_only_the_two_missing_native_targets(self) -> None:
        targets = {entry["target"] for entry in release.matrix(True)["include"]}
        self.assertEqual(targets, {"aarch64-unknown-linux-gnu", "x86_64-apple-darwin"})
        self.assertEqual(len(release.matrix(False)["include"]), 5)

    def test_pending_acceptance_cannot_silently_fall_back_to_rebuilding(self) -> None:
        self.record["staging_acceptance_run"] = None
        self.write_record()
        with self.assertRaisesRegex(ValueError, "release_candidate_record_unverified"):
            release.record("v0.3.1")

    def test_other_release_versions_keep_the_existing_native_path(self) -> None:
        self.write_record()
        self.assertIsNone(release.record("v0.3.0"))

    def test_admission_uses_original_source_and_separate_successful_acceptance(self) -> None:
        self.write_record()
        output = self.root / ".temp/outputs"
        accepted = SimpleNamespace(producer=Mock(return_value=self.producer), runtime_closure=Mock(),
                                   acceptance=Mock(return_value=self.admission["acceptance"]))
        with patch.dict(sys.modules, {"accepted_staging_artifact": accepted}), patch.dict(os.environ, {
            "GITHUB_SHA": "c" * 40, "GITHUB_OUTPUT": str(output),
        }):
            actual = release.admit("v0.3.1")
        self.assertEqual(actual, self.admission)
        accepted.runtime_closure.assert_called_once_with("a" * 40, "c" * 40)
        accepted.acceptance.assert_called_once_with("102", self.producer, "c" * 40)
        self.assertIn("cli_artifact_id=201\n", output.read_text())
        self.assertIn("acceptance_artifact_id=202\n", output.read_text())

    def test_all_original_bundle_files_are_checked_before_native_reuse(self) -> None:
        self.bundle()
        identity, hashes = release.verify_bundle(self.folder, self.admission)
        self.assertEqual(identity, self.identity)
        name = release.candidate.archive_name("0.3.1", release.candidate.TARGETS[0])
        (self.folder / name).write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "release_candidate_manifest_unverified"):
            release.verify_bundle(self.folder, self.admission)
        self.assertEqual(len(hashes), 7)

    def test_wrong_native_producer_is_rejected_even_with_matching_file_hashes(self) -> None:
        self.bundle()
        self.admission["producer"]["run_attempt"] = 2
        with self.assertRaisesRegex(ValueError, "release_candidate_manifest_unverified"):
            release.verify_bundle(self.folder, self.admission)

    def test_archive_paths_and_links_cannot_enter_a_repack(self) -> None:
        path = self.folder / "foreign.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("../amail.exe", b"untrusted")
            archive.writestr("README.md", "readme")
            archive.writestr("LICENSE", "license")
        with self.assertRaisesRegex(ValueError, "release_candidate_archive_unverified"):
            release.executable(path, "x86_64-pc-windows-msvc")

    def test_packaging_preserves_native_bytes_and_differentiates_origin_from_packaging(self) -> None:
        self.bundle()
        self.write_record()
        self.admission_file.write_text(json.dumps(self.admission), encoding="utf-8")
        accepted = SimpleNamespace(runtime_closure=Mock(), verify_acceptance_receipt=Mock())
        output = self.root / "reused"
        with patch.dict(sys.modules, {"accepted_staging_artifact": accepted}), patch.dict(os.environ, {
            "GITHUB_SHA": "c" * 40, "GITHUB_RUN_ID": "303",
        }):
            release.package("v0.3.1", output)
        accepted.verify_acceptance_receipt.assert_called_once_with(self.admission)
        self.assertEqual(len(list(output.iterdir())), 3)
        for target in release.candidate.TARGETS:
            suffix = "zip" if "windows" in target else "tar.gz"
            path = output / f"amail-v0.3.1-{target}.{suffix}"
            if suffix == "zip":
                with zipfile.ZipFile(path) as archive:
                    content = {name: archive.read(name) for name in archive.namelist()}
            else:
                with tarfile.open(path, "r:gz") as archive:
                    content = {}
                    for entry in archive.getmembers():
                        stream = archive.extractfile(entry)
                        assert stream is not None
                        content[entry.name] = stream.read()
                    self.assertEqual(archive.getmember("amail").mode, 0o755)
            binary = "amail.exe" if suffix == "zip" else "amail"
            self.assertEqual(content[binary], ("native-" + target).encode())
            self.assertEqual(content["README.md"], (self.root / "README.md").read_bytes())
            origin = json.loads(content["BUILD-PROVENANCE.json"])
            self.assertEqual(origin["native_source_sha"], "a" * 40)
            self.assertEqual(origin["packaging_source_sha"], "c" * 40)
            self.assertEqual(origin["native_run_id"], "101")
            self.assertEqual(origin["packaging_run_id"], "303")
            self.assertEqual(origin["executable_sha256"], hashlib.sha256(content[binary]).hexdigest())


if __name__ == "__main__":
    unittest.main()
