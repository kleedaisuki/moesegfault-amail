"""Exercise candidate assembly with tiny files, not native builds or providers."""

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("cli_candidate", ROOT / "infra/ci/cli_candidate.py")
CANDIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CANDIDATE)


class CandidateTests(unittest.TestCase):
    """Keep publication metadata exact and reject mixed or modified producers."""

    def setUp(self):
        """Create public miniature producer artifacts entirely inside .temp."""
        (ROOT / ".temp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".temp", prefix="candidate-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "output"
        self.output.mkdir()
        skill = self.root / "skills/amail"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# Example skill\n", encoding="utf-8")
        self.info = {"schema": "amail-cli-candidate/v1", "version": "0.1.2",
                     "source_sha": "a" * 40, "run_id": "123", "run_attempt": 1,
                     "rust": "1.94.0", "publication": "unpublished-candidate"}
        for target in CANDIDATE.TARGETS:
            name = CANDIDATE.archive_name("0.1.2", target)
            archive = self.output / name
            archive.write_bytes(b"tiny native archive fixture")
            CANDIDATE.write_json(self.output / f"{target}.json", {
                **self.info, "target": target, "archive": name,
                "sha256": CANDIDATE.digest(archive)})
        for attribute, value in (("ROOT", self.root), ("OUTPUT", self.output)):
            mock = patch.object(CANDIDATE, attribute, value)
            mock.start()
            self.addCleanup(mock.stop)
        mock = patch.object(CANDIDATE, "context", return_value=self.info)
        mock.start()
        self.addCleanup(mock.stop)

    def test_bundle_has_skill_provenance_and_complete_checksums(self):
        """Every shipped file, including provenance, receives a checksum."""
        CANDIDATE.assemble()
        with zipfile.ZipFile(self.output / "amail-agent-skill-v0.1.2-candidate.zip") as skill:
            self.assertEqual(skill.namelist(), ["amail/SKILL.md"])
        info = json.loads((self.output / "candidate.json").read_text(encoding="utf-8"))
        self.assertEqual(info["publication"], "unpublished-candidate")
        self.assertEqual(info["targets"], list(CANDIDATE.TARGETS))
        checksums = (self.output / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
        expected = {path.name for path in self.output.iterdir()} - {"SHA256SUMS"}
        self.assertEqual({line.split("  ")[1] for line in checksums}, expected)
        for line in checksums:
            digest, name = line.split("  ")
            self.assertEqual(digest, CANDIDATE.digest(self.output / name))

    def test_refuses_modified_archive(self):
        """An upload/download byte change never produces an accepted bundle."""
        archive = self.output / CANDIDATE.archive_name("0.1.2", CANDIDATE.TARGETS[0])
        archive.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "candidate_producer_mismatch"):
            CANDIDATE.assemble()

    def test_refuses_other_run(self):
        """Correct bytes from an earlier run cannot silently join this candidate."""
        path = self.output / f"{CANDIDATE.TARGETS[0]}.json"
        info = json.loads(path.read_text(encoding="utf-8"))
        info["run_id"] = "122"
        CANDIDATE.write_json(path, info)
        with self.assertRaisesRegex(ValueError, "candidate_producer_mismatch"):
            CANDIDATE.assemble()

    def test_refuses_extra_files(self):
        """Only the expected producer file set enters the public review artifact."""
        (self.output / "unexpected.txt").write_text("not a candidate input", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "candidate_file_set_mismatch"):
            CANDIDATE.assemble()

    def test_native_archive_contains_only_public_payload(self):
        """The producer checks the executable version and preserves Unix execute bits."""
        for path in self.output.iterdir():
            path.unlink()
        source = self.root / "target/release/amail"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"tiny executable fixture")
        source.chmod(0o755)
        for name in ("README.md", "LICENSE"):
            (self.root / name).write_text(name, encoding="utf-8")
        with patch.object(CANDIDATE.subprocess, "check_output", side_effect=[
                "rustc fixture\nhost: x86_64-unknown-linux-gnu\n", "amail 0.1.2\n"]):
            CANDIDATE.binary()
        archive = self.output / CANDIDATE.archive_name("0.1.2", CANDIDATE.TARGETS[0])
        with tarfile.open(archive, "r:gz") as bundle:
            self.assertEqual(bundle.getnames(), ["amail", "README.md", "LICENSE"])
            readme = bundle.extractfile("README.md").read().decode("utf-8")
            for required in ("unpublished staging candidate", "defaults\nto production", "AMAIL_HOME",
                             ".temp/amail-staging-acceptance", "https://mail-staging.moesegfault.dev",
                             "https://identity-staging.moesegfault.dev", "amail-cli-staging",
                             "http://127.0.0.1/callback", "separate realm", "OpenRouter", "--semantic"):
                self.assertIn(required, readme)
            self.assertEqual((self.root / "README.md").read_text(), "README.md")
            # chmod on Windows does not model Unix executable permissions.
            if os.name != "nt":
                self.assertEqual(bundle.getmember("amail").mode & 0o111, 0o111)

    def test_native_archive_refuses_wrong_binary_version(self):
        """A stale dependency/build cache cannot be labeled as the current version."""
        source = self.root / "target/release/amail"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"stale executable fixture")
        for name in ("README.md", "LICENSE"):
            (self.root / name).write_text(name, encoding="utf-8")
        with patch.object(CANDIDATE.subprocess, "check_output", side_effect=[
                "host: x86_64-unknown-linux-gnu\n", "amail 0.1.0\n"]):
            with self.assertRaisesRegex(ValueError, "candidate_binary_version_mismatch"):
                CANDIDATE.binary()


if __name__ == "__main__":
    unittest.main()
