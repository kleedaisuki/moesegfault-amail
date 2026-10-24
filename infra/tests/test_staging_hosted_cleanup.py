"""Owned hosted profile teardown precedes daemon stop and private-home removal."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/tests"))
import staging_hosted_e2e as hosted


class HostedCleanupTests(unittest.TestCase):
    def fixture(self, root: Path, *, authenticated: bool) -> tuple[Path, Path]:
        run_dir = root / "staging-hosted-e2e-fixture"
        home = run_dir / "amail-home-fixture"
        home.mkdir(parents=True)
        binary = run_dir / "amail.exe"
        binary.write_bytes(b"synthetic-placeholder")
        (home / "profiles.sqlite3").touch()
        if authenticated:
            (home / "auth.sqlite3").touch()
        return run_dir, binary

    def test_user_release_precedes_stop_and_private_removal(self) -> None:
        hosted.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=hosted.TEMP) as folder:
            run_dir, binary = self.fixture(Path(folder), authenticated=True)
            actions: list[tuple[str, ...]] = []

            def execute(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
                actions.append(tuple(args[1:]))
                environment = kwargs["env"]
                assert isinstance(environment, dict)
                self.assertNotIn("CLOUDFLARE_API_TOKEN", environment)
                return subprocess.CompletedProcess(args, 0, b"", b"")

            def remove(path: Path) -> None:
                actions.append(("remove",))

            with patch.object(hosted.subprocess, "run", side_effect=execute), \
                 patch.object(hosted.shutil, "rmtree", side_effect=remove):
                self.assertIsNone(hosted.cleanup_run(run_dir, binary, release_user=True))
            self.assertEqual(actions, [("profile", "release", "user"), ("daemon", "stop"), ("remove",)])

    def test_release_failure_does_not_skip_stop_or_mask_primary(self) -> None:
        hosted.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=hosted.TEMP) as folder:
            run_dir, binary = self.fixture(Path(folder), authenticated=True)
            with patch.object(hosted.subprocess, "run", side_effect=[
                    subprocess.CompletedProcess([], 1, b"", b"private-provider-prose"),
                    subprocess.CompletedProcess([], 0, b"", b"")]) as run, \
                 patch.object(hosted.shutil, "rmtree") as remove:
                cleanup = hosted.cleanup_run(run_dir, binary, release_user=True)
            self.assertEqual(run.call_count, 2)
            remove.assert_called_once_with(run_dir)
            primary = hosted.HostedProbeError("smtp_fixture_failed")
            failure = hosted.acceptance_failure(primary, cleanup)
            self.assertEqual(str(failure), "smtp_fixture_failed_cleanup_user_profile_cleanup_failed")
            self.assertNotIn("private", str(failure))
            self.assertIs(hosted.acceptance_failure(primary, None), primary)

    def test_no_release_without_auth_context_or_for_legacy_lane(self) -> None:
        hosted.TEMP.mkdir(exist_ok=True)
        for authenticated, release_user in ((False, True), (True, False)):
            with self.subTest(authenticated=authenticated, release_user=release_user), \
                 tempfile.TemporaryDirectory(dir=hosted.TEMP) as folder:
                run_dir, binary = self.fixture(Path(folder), authenticated=authenticated)
                with patch.object(hosted.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run, \
                     patch.object(hosted.shutil, "rmtree"):
                    self.assertIsNone(hosted.cleanup_run(run_dir, binary, release_user=release_user))
                self.assertEqual(run.call_args.args[0], [str(binary), "daemon", "stop"])
                self.assertEqual(run.call_count, 1)

    def test_login_failure_still_runs_teardown_and_keeps_both_safe_labels(self) -> None:
        class LoginFailure(Exception):
            pass

        identity = SimpleNamespace(ProbeError=LoginFailure, store_credential=Mock(),
                                   native_login=Mock(side_effect=LoginFailure("login_fixture_failed")))
        hosted.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=hosted.TEMP) as folder:
            run_dir, binary = self.fixture(Path(folder), authenticated=False)
            with patch.dict(sys.modules, {"staging_identity_cdp": identity}), \
                 patch.dict("os.environ", {"GITHUB_REF": "refs/heads/codex/v0.3.0-multitenant"}), \
                 patch.object(hosted, "validate_environment", return_value=("fixture", "synthetic-secret")), \
                 patch.object(hosted, "recoverable_run_nonce", return_value="a" * 16), \
                 patch.object(hosted.tempfile, "mkdtemp", return_value=str(run_dir)), \
                 patch.object(hosted, "selected_binary", return_value=binary), \
                 patch.object(hosted.shutil, "copy2"), \
                 patch.object(hosted, "cleanup_run", return_value=hosted.HostedProbeError(
                     "user_profile_cleanup_failed")) as cleanup:
                with self.assertRaisesRegex(hosted.HostedProbeError,
                        "^identity_login_fixture_failed_cleanup_user_profile_cleanup_failed$"):
                    hosted.execute()
            cleanup.assert_called_once_with(run_dir, binary, release_user=True)


if __name__ == "__main__":
    unittest.main()
