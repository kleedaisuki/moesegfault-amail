"""Offline safety tests for the hosted, staging-only SMTP probe gate."""

from __future__ import annotations

from datetime import datetime, timezone
import io
import os
import subprocess
import unittest
import urllib.error
from unittest.mock import MagicMock, Mock, patch

import hosted_acceptance as hosted


NOW = datetime(2026, 9, 29, 5, 0, tzinfo=timezone.utc)
VERSION = "023e105f-2a42-4f8b-a1c1-73f6a2a30c0f"
SHA = "a" * 40


class HostedRoleAcceptanceTests(unittest.TestCase):
    """Only a pinned successful deployment may reach the one-message harness."""

    def test_successful_job_requires_same_sha_and_complete_inventory(self) -> None:
        """A successful run alone cannot substitute for its deploy job."""

        run = {
            "conclusion": "success", "status": "completed",
            "head_branch": "codex/amail-v0.1.0", "event": "push",
            "path": ".github/workflows/ci.yml",
            "head_sha": SHA,
        }
        job = {
            "id": 77,
            "name": hosted.JOB_NAME, "head_sha": SHA,
            "status": "completed", "conclusion": "success",
            "started_at": "2026-09-29T05:00:00Z",
            "completed_at": "2026-09-29T05:10:00Z",
            "steps": [{
                "name": hosted.DEPLOY_STEP, "conclusion": "success",
                "started_at": "2026-09-29T05:04:00Z",
                "completed_at": "2026-09-29T05:06:00Z",
            }],
        }
        with patch.object(hosted, "github_get", side_effect=[run, {"total_count": 1, "jobs": [job]}]):
            deployed = hosted.successful_deploy_job(
                "kleedaisuki/moesegfault-amail", 42, "token", "codex/amail-v0.1.0"
            )
        self.assertEqual(deployed.started, NOW)
        self.assertEqual(deployed.ended.minute, 10)
        self.assertEqual(deployed.job_id, 77)
        job["head_sha"] = "b" * 40
        with patch.object(hosted, "github_get", side_effect=[run, {"total_count": 1, "jobs": [job]}]):
            with self.assertRaisesRegex(hosted.GateError, "deploy_job_not_successful"):
                hosted.successful_deploy_job("kleedaisuki/moesegfault-amail", 42, "token", "codex/amail-v0.1.0")
        run["path"] = ".github/workflows/ci.yml.evil"
        with patch.object(hosted, "github_get", return_value=run):
            with self.assertRaisesRegex(hosted.GateError, "deploy_run_wrong_workflow"):
                hosted.successful_deploy_job("kleedaisuki/moesegfault-amail", 42, "token", "codex/amail-v0.1.0")

    def test_logged_version_is_unique_within_exact_deploy_step(self) -> None:
        """An out-of-band deployment in the job window cannot self-attest."""

        job = hosted.DeployedJob(NOW, NOW.replace(minute=10), 77,
                                  NOW.replace(minute=4), NOW.replace(minute=5))
        lines = (
            "2026-09-29T05:01:00Z Current Version ID: 11111111-1111-4111-8111-111111111111\n"
            f"2026-09-29T05:05:00.8395859Z Current Version ID: {VERSION}\n"
        )
        with patch.object(hosted, "github_job_log", return_value=lines):
            self.assertEqual(hosted.logged_version("repo", job, "token"), VERSION)
        with patch.object(hosted, "github_job_log", return_value=lines + lines.splitlines()[1] + "\n"):
            with self.assertRaisesRegex(hosted.GateError, "deploy_log_version_ambiguous"):
                hosted.logged_version("repo", job, "token")

    def test_job_log_redirect_does_not_forward_bearer(self) -> None:
        """GitHub's signed-storage redirect receives no Actions bearer token."""

        url = "https://logs.actions.githubusercontent.com/restricted?sig=opaque"
        redirect = urllib.error.HTTPError("https://api.github.com", 302, "Found",
                                           {"Location": url}, None)
        opener = Mock()
        opener.open.side_effect = redirect
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b"fixed log only"
        with patch.object(hosted.urllib.request, "build_opener", return_value=opener), \
             patch.object(hosted.urllib.request, "urlopen", return_value=response) as storage:
            self.assertEqual(hosted.github_job_log("repo", 77, "secret"), "fixed log only")
        self.assertEqual(storage.call_args.args[0].full_url, url)
        self.assertNotIn("Authorization", storage.call_args.args[0].headers)

    def test_active_version_requires_one_full_traffic_version(self) -> None:
        """A staged 50/50 rollout is not an acceptable SMTP test target."""

        value = {"deployments": [{"versions": [{"percentage": 100, "version_id": VERSION}],
                                  "created_on": "2026-09-29T05:05:00Z"}]}
        with patch.object(hosted.probe.AUDIT, "api_get", return_value=value):
            self.assertEqual(hosted.active_version("a" * 32, "token")[0], VERSION)
        value["deployments"][0]["versions"][0]["percentage"] = 50
        with patch.object(hosted.probe.AUDIT, "api_get", return_value=value):
            with self.assertRaisesRegex(hosted.GateError, "worker_version_not_full_traffic"):
                hosted.active_version("a" * 32, "token")

    def test_gates_block_without_freeze_and_before_send(self) -> None:
        """A missing external freeze acknowledgement never contacts SMTP."""

        env = {"AMAIL_STAGING_ROLE_CONFIRM": hosted.CONFIRM,
               "AMAIL_STAGING_ROLE_FREEZE": ""}
        with patch.dict(os.environ, env, clear=True), patch.object(hosted.probe, "preflight") as preflight:
            with self.assertRaisesRegex(hosted.GateError, "external_freeze_not_attested"):
                hosted.gates()
            preflight.assert_not_called()

    def test_gates_require_version_created_during_passed_job(self) -> None:
        """A matching UUID from another deployment job must not unlock send."""

        env = {
            "AMAIL_STAGING_ROLE_CONFIRM": hosted.CONFIRM,
            "AMAIL_STAGING_ROLE_FREEZE": hosted.FREEZE,
            "AMAIL_STAGING_ROLE_DEPLOY_RUN": "42",
            "AMAIL_STAGING_ROLE_VERSION": VERSION,
            "GITHUB_REPOSITORY": "kleedaisuki/moesegfault-amail",
            "GITHUB_REF_NAME": "codex/amail-v0.1.0",
            "GITHUB_TOKEN": "token",
            "CLOUDFLARE_API_TOKEN": "provider-token",
        }
        with patch.dict(os.environ, env, clear=True), \
             patch.object(hosted.probe, "credentials", return_value=("zone", "routing", "a" * 32)), \
             patch.object(hosted, "successful_deploy_job", return_value=hosted.DeployedJob(
                 NOW, NOW, 77, NOW, NOW)), \
             patch.object(hosted, "logged_version", return_value=VERSION), \
             patch.object(hosted, "active_version", return_value=(VERSION, NOW.replace(hour=6))), \
             patch.object(hosted.probe, "preflight") as preflight:
            with self.assertRaisesRegex(hosted.GateError, "worker_deployment_not_from_successful_job"):
                hosted.gates()
            preflight.assert_not_called()

    def test_marker_failure_demands_restricted_route_recovery(self) -> None:
        """An ambiguous create may not be called successful on an ephemeral runner."""

        marker = unittest.mock.Mock()
        marker.exists.return_value = True
        output = io.StringIO()
        with patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "synthetic-test-token"}), \
             patch.object(hosted, "gates", return_value=("zone", "routing", "account", VERSION)), \
             patch.object(hosted.probe, "MARKER", marker), \
             patch.object(hosted.probe.ROUTE, "reconcile", return_value="enabled"), \
             patch.object(hosted, "active_version", return_value=(VERSION, NOW)), \
             patch.object(hosted.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)), \
             patch("sys.stderr", output):
            self.assertEqual(hosted.main(), 1)
        self.assertIn("route_recovery_required", output.getvalue())
        self.assertNotIn("routing", output.getvalue())

    def test_green_result_is_explicitly_machine_d1_only(self) -> None:
        """SMTP plus D1 never claims Cron Past Events or destination Inbox."""

        marker = unittest.mock.Mock()
        marker.exists.return_value = False
        output = io.StringIO()
        with patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "synthetic-test-token"}), \
             patch.object(hosted, "gates", return_value=("zone", "routing", "account", VERSION)), \
             patch.object(hosted.probe, "MARKER", marker), \
             patch.object(hosted.probe.ROUTE, "reconcile", return_value="absent"), \
             patch.object(hosted, "active_version", return_value=(VERSION, NOW)), \
             patch.object(hosted.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), \
             patch("sys.stdout", output):
            self.assertEqual(hosted.main(), 0)
        self.assertIn("machine_d1_only", output.getvalue())
        self.assertIn("external_inbox=not_checked", output.getvalue())


if __name__ == "__main__":
    unittest.main()
