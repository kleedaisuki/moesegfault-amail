"""Offline contract tests for the post-publish release asset gate."""

from __future__ import annotations

import hashlib
import copy
import importlib.util
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "release" / "verify_published_assets.py"
SPEC = importlib.util.spec_from_file_location("verify_published_assets", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
RECOVERY_SPEC = importlib.util.spec_from_file_location("recover_bundle", SCRIPT.with_name("recover_bundle.py"))
assert RECOVERY_SPEC and RECOVERY_SPEC.loader
RECOVERY = importlib.util.module_from_spec(RECOVERY_SPEC)
RECOVERY_SPEC.loader.exec_module(RECOVERY)
TAG = "v0.1.0"
TEMP_ROOT = pathlib.Path(__file__).resolve().parents[2] / ".temp"
TEMP_ROOT.mkdir(exist_ok=True)


def write_bundle(directory: pathlib.Path) -> None:
    """Create a valid synthetic seven-file download without network access."""

    lines = []
    for name in sorted(MODULE.expected_names(TAG)):
        data = f"synthetic:{name}".encode("ascii")
        (directory / name).write_bytes(data)
        lines.append(f"{hashlib.sha256(data).hexdigest()}  {name}\n")
    (directory / "SHA256SUMS").write_text("".join(lines), encoding="ascii")


class PublishedAssetIntegrityTest(unittest.TestCase):
    """A complete, canonical, byte-matching bundle is the only passing case."""

    def test_recovery_binds_original_tag_run_complete_jobs_and_live_bundle(self) -> None:
        """Only the same-repository failed release's complete tagged bundle is reused."""
        repository, source, run_id = "owner/repo", "a" * 40, 123
        run = {"id": run_id, "repository": {"full_name": repository}, "head_repository": {"full_name": repository},
            "path": ".github/workflows/release.yml", "event": "push", "head_branch": TAG, "head_sha": source,
            "status": "completed", "conclusion": "failure"}
        names = ["Verify release source", "Assemble and verify release bundle"] + [f"Build {target}" for target, _ in MODULE.TARGETS]
        jobs = [{"name": name, "status": "completed", "conclusion": "success"} for name in names]
        artifacts = [{"name": f"release-bundle-{TAG}", "id": 456, "expired": False}]
        self.assertEqual(RECOVERY.validate(run, jobs, artifacts, repository, TAG, source, run_id), 456)
        for field, value in (("id", 124), ("path", ".github/workflows/ci.yml"), ("event", "workflow_dispatch"),
                             ("head_branch", "main"), ("head_sha", "b" * 40), ("status", "in_progress"),
                             ("conclusion", "success"), ("repository", {"full_name": "other/repo"}),
                             ("head_repository", {"full_name": "other/repo"})):
            with self.subTest(field=field), self.assertRaises(ValueError):
                RECOVERY.validate(dict(run, **{field: value}), jobs, artifacts, repository, TAG, source, run_id)
        for mutation in ("missing", "duplicate", "failed", "running", "published", "expired", "bundle_missing", "bundle_duplicate"):
            altered_jobs, altered_artifacts = copy.deepcopy(jobs), copy.deepcopy(artifacts)
            if mutation == "missing":
                altered_jobs.pop()
            elif mutation == "duplicate":
                altered_jobs.append(copy.deepcopy(jobs[0]))
            elif mutation == "failed":
                altered_jobs[-1]["conclusion"] = "failure"
            elif mutation == "running":
                altered_jobs[-1]["status"] = "in_progress"
            elif mutation == "published":
                altered_jobs.append({"name": "Publish GitHub Release", "conclusion": "success"})
            elif mutation == "expired":
                altered_artifacts[0]["expired"] = True
            elif mutation == "bundle_missing":
                altered_artifacts.clear()
            else:
                altered_artifacts.append(copy.deepcopy(artifacts[0]))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                RECOVERY.validate(run, altered_jobs, altered_artifacts, repository, TAG, source, run_id)

    def test_recovery_requires_positive_release_absence(self) -> None:
        """Only an HTTP404 response, not transport/auth failure, means unpublished."""
        with patch.object(RECOVERY.subprocess, "run") as request:
            request.return_value.returncode = 1
            request.return_value.stdout = "HTTP/2.0 404 Not Found\n\n{}"
            RECOVERY.require_absent_release("owner/repo", TAG)
            for code, status in ((0, 200), (1, 403), (1, 500), (1, 0)):
                request.return_value.returncode = code
                request.return_value.stdout = f"HTTP/2.0 {status} unavailable"
                with self.subTest(status=status), self.assertRaises(ValueError):
                    RECOVERY.require_absent_release("owner/repo", TAG)

    def test_recovery_invalid_entry_is_denied_before_metadata_requests(self) -> None:
        """Numeric IDs and trusted main manual entry precede every GitHub read."""
        env = {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
            "GITHUB_REPOSITORY": "owner/repo", "RECOVER_RUN_ID": "123", "RELEASE_TAG": TAG, "RELEASE_SOURCE_SHA": "a" * 40}
        for field, value in (("GITHUB_EVENT_NAME", "push"), ("GITHUB_REF", "refs/heads/feature"),
                             ("RECOVER_RUN_ID", ""), ("RECOVER_RUN_ID", "123/other"), ("RECOVER_RUN_ID", "0")):
            with self.subTest(field=field, value=value), patch.dict("os.environ", dict(env, **{field: value}), clear=True), patch.object(RECOVERY, "api") as request:
                self.assertEqual(RECOVERY.main(), 1)
                request.assert_not_called()

    def test_recovery_workflow_preserves_candidate_and_existing_publish_chain(self) -> None:
        """Recovery skips rebuilding and never bypasses the real production gate."""
        from workflow_source import job_block
        text = (SCRIPT.parents[2] / ".github/workflows/release.yml").read_text(encoding="utf-8")
        preflight = job_block(text, "preflight")
        self.assertIn("workflow_dispatch:refs/heads/main)", preflight)
        self.assertIn('[[ "$RECOVER_RUN_ID" =~ ^[1-9][0-9]*$ ]]', preflight)
        self.assertIn('git rev-parse "v$version^{commit}"', preflight)
        self.assertIn('recover=false', preflight)
        self.assertIn('publish=false', preflight)
        for name in ("build", "assemble"):
            self.assertIn("if: needs.preflight.outputs.recover != 'true'", job_block(text, name))
        recovery = job_block(text, "recover-bundle")
        self.assertIn("if: needs.preflight.outputs.recover == 'true'", recovery)
        self.assertIn("artifact-ids: ${{ steps.recovery.outputs.artifact_id }}", recovery)
        self.assertIn("run-id: ${{ inputs.recover_run_id }}", recovery)
        self.assertIn("--trusted-manifest dist/SHA256SUMS", recovery)
        self.assertNotIn("cargo", recovery)
        publish = job_block(text, "publish")
        self.assertIn("needs.send-release-gate.result == 'success'", publish)
        self.assertIn("needs.assemble.result == 'success' || needs.recover-bundle.result == 'success'", publish)
        self.assertIn("gh release create", publish)
        self.assertIn("verify_published_assets.py", job_block(text, "verify-published"))
        self.assertIn("needs: verify-published", job_block(text, "launch-site"))

    def test_complete_bundle_passes(self) -> None:
        """The six expected archives and manifest verify without provider access."""

        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temporary:
            directory = pathlib.Path(temporary)
            write_bundle(directory)
            MODULE.verify(directory, TAG, trusted_manifest=directory / "SHA256SUMS")

    def test_missing_extra_and_renamed_assets_fail(self) -> None:
        """A matching digest list cannot excuse a wrong published asset set."""

        for mutation in ("missing", "extra", "renamed"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temporary:
                directory = pathlib.Path(temporary)
                write_bundle(directory)
                target = directory / sorted(MODULE.expected_names(TAG))[0]
                if mutation == "missing":
                    target.unlink()
                elif mutation == "extra":
                    (directory / "unexpected.zip").write_bytes(b"surprise")
                else:
                    target.rename(directory / "wrong-name.zip")
                with self.assertRaises(MODULE.AssetError):
                    MODULE.verify(directory, TAG, trusted_manifest=directory / "SHA256SUMS")

    def test_tampered_archive_fails(self) -> None:
        """Verify downloaded bytes rather than trusting manifest names alone."""

        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temporary:
            directory = pathlib.Path(temporary)
            write_bundle(directory)
            (directory / sorted(MODULE.expected_names(TAG))[0]).write_bytes(b"modified")
            with self.assertRaises(MODULE.AssetError):
                MODULE.verify(directory, TAG, trusted_manifest=directory / "SHA256SUMS")

    def test_replaced_bundle_and_manifest_fail_against_same_run_artifact(self) -> None:
        """A self-consistent replacement cannot impersonate the assembled manifest."""

        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temporary:
            directory = pathlib.Path(temporary) / "published"
            directory.mkdir()
            write_bundle(directory)
            trusted = pathlib.Path(temporary) / "trusted-manifest"
            trusted.write_bytes((directory / "SHA256SUMS").read_bytes())
            target = sorted(MODULE.expected_names(TAG))[0]
            replacement = b"replacement"
            (directory / target).write_bytes(replacement)
            manifest = (directory / "SHA256SUMS").read_text(encoding="ascii")
            old_digest = hashlib.sha256(f"synthetic:{target}".encode("ascii")).hexdigest()
            new_digest = hashlib.sha256(replacement).hexdigest()
            (directory / "SHA256SUMS").write_text(manifest.replace(old_digest, new_digest), encoding="ascii")
            with self.assertRaises(MODULE.AssetError):
                MODULE.verify(directory, TAG, trusted_manifest=trusted)

    def test_attestation_mode_checks_every_exact_tagged_source(self) -> None:
        """Manual site promotion binds each archive to the release workflow."""

        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temporary:
            directory = pathlib.Path(temporary)
            write_bundle(directory)
            with patch.object(MODULE.subprocess, "run") as attest:
                attest.return_value.returncode = 0
                MODULE.verify(directory, TAG, repository="owner/repo", source_digest="a" * 40)
            self.assertEqual(attest.call_count, 6)
            for call in attest.call_args_list:
                self.assertIn("--source-ref", call.args[0])
                self.assertIn("refs/tags/v0.1.0", call.args[0])
                self.assertIn("--source-digest", call.args[0])
                self.assertIn("a" * 40, call.args[0])
                self.assertEqual(call.kwargs["stdout"], MODULE.subprocess.DEVNULL)
            with patch.object(MODULE.subprocess, "run") as attest:
                attest.return_value.returncode = 1
                with self.assertRaises(MODULE.AssetError):
                    MODULE.verify(directory, TAG, repository="owner/repo", source_digest="a" * 40)
            self.assertEqual(attest.call_count, 1)

    def test_untrusted_or_partial_provenance_mode_fails(self) -> None:
        """No caller may accidentally omit or mix independent trust modes."""

        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temporary:
            directory = pathlib.Path(temporary)
            write_bundle(directory)
            for options in ({}, {"repository": "owner/repo"},
                            {"trusted_manifest": directory / "SHA256SUMS", "repository": "owner/repo", "source_digest": "a" * 40}):
                with self.subTest(options=options), self.assertRaises(MODULE.AssetError):
                    MODULE.verify(directory, TAG, **options)

    def test_malformed_duplicate_and_missing_checksums_fail(self) -> None:
        """Reject ambiguous manifests before any checksum can count as proof."""

        names = MODULE.expected_names(TAG)
        one = sorted(names)[0]
        digest = b"a" * 64
        valid_line = digest + b"  " + one.encode("ascii") + b"\n"
        for raw in (
            b"",
            valid_line + valid_line,
            valid_line.replace(b"  ", b" *"),
            valid_line.replace(one.encode("ascii"), b"../bad.zip"),
            valid_line.replace(b"a", b"A", 1),
            valid_line.rstrip(b"\n"),
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(MODULE.AssetError):
                    MODULE.parse_checksums(raw, names)

    def test_invalid_tag_and_symlink_fail(self) -> None:
        """Reject unsafe tags and non-regular downloaded assets."""

        with self.assertRaises(MODULE.AssetError):
            MODULE.expected_names("v0.1.0/../../escape")
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temporary:
            directory = pathlib.Path(temporary)
            write_bundle(directory)
            target = directory / sorted(MODULE.expected_names(TAG))[0]
            target.unlink()
            try:
                target.symlink_to(directory / "SHA256SUMS")
            except OSError:
                self.skipTest("symlinks unavailable on this platform")
            with self.assertRaises(MODULE.AssetError):
                MODULE.verify(directory, TAG, trusted_manifest=directory / "SHA256SUMS")


if __name__ == "__main__":
    unittest.main()
