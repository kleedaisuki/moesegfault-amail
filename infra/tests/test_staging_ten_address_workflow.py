"""Hosted static quota workflow/key-helper contracts; no provider or helper execution."""

from pathlib import Path
import re
import unittest

from workflow_source import job_block

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / ".github/workflows/staging-ten-address-acceptance.yml"


class WorkflowTests(unittest.TestCase):
    """Keep mutation authority explicit, bounded and independent of full CI deployment."""

    def setUp(self):
        """Read only the relevant source workflow and its own job block."""
        self.source = PATH.read_text(encoding="utf-8-sig")
        self.job = job_block(self.source, "quota")

    def test_manual_only_confirmed_first_attempt_staging_bound(self):
        """A push/schedule/retry cannot create ten provider routes."""
        trigger = self.source.split("on:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertIn("  workflow_dispatch:", trigger)
        self.assertNotRegex(trigger, r"(?m)^  (?:push|pull_request|schedule|workflow_call):")
        self.assertIn("github.event_name == 'workflow_dispatch'", self.job)
        self.assertIn("github.ref == 'refs/heads/codex/amail-v0.1.0'", self.job)
        self.assertIn("github.run_attempt == 1", self.job)
        self.assertIn("environment: staging", self.job)
        self.assertIn("runs-on: windows-latest", self.job)
        self.assertIn("timeout-minutes: 80", self.job)
        self.assertIn("group: staging-native-mail-acceptance", self.job)
        self.assertIn("cancel-in-progress: false", self.job)
        self.assertIn("RUN_STAGING_TEN_ADDRESSES", self.job)
        self.assertIn("RECOVER_STAGING_TEN_ADDRESSES", self.job)

    def test_immutable_exact_cipher_upload_precedes_mutator_and_readback(self):
        """No post-job/wildcard plaintext artifact can masquerade as durable recovery."""
        prepare = self.job.index("id: prepare")
        upload = self.job.index("id: recovery_artifact")
        campaign = self.job.index("id: campaign")
        self.assertLess(prepare, upload); self.assertLess(upload, campaign)
        uploader = self.job[upload:campaign]
        self.assertIn("uses: actions/upload-artifact@v4", uploader)
        self.assertIn("path: .temp/ten-address-recovery-${{ github.run_id }}/manifest.bin", uploader)
        self.assertIn("include-hidden-files: true", uploader)
        self.assertIn("if-no-files-found: error", uploader)
        self.assertIn("overwrite: false", uploader)
        self.assertIn("retention-days: 30", uploader)
        self.assertNotIn("secrets.", uploader)
        self.assertNotIn("path: .temp/\n", uploader)
        self.assertIn("steps.recovery_artifact.outputs.artifact-id != ''", self.job[campaign:])
        self.assertIn("ORIGINAL_ARTIFACT_ID: ${{ steps.recovery_artifact.outputs.artifact-id }}", self.job[campaign:])
        self.assertIn("'--artifact-id', $env:ORIGINAL_ARTIFACT_ID", self.job[campaign:])
        self.assertIn("quota_campaign_not_executed", self.job)

    def test_same_manifest_recovery_and_generation_survive_cancellation(self):
        """Recovery is explicit and never automatically resends ambiguous deletes."""
        recovery = self.job[self.job.index("id: recovery"):]
        self.assertIn("if: inputs.mode == 'recover'", recovery)
        self.assertIn("'recover', '--source-run'", recovery)
        self.assertIn("'--prior-run', $env:PUBLIC_PRIOR_RUN", recovery)
        self.assertIn("'--artifact-id', $env:PUBLIC_ARTIFACT_ID", recovery)
        self.assertIn("if: always() && inputs.mode == 'accept'", self.job)
        self.assertIn("ten_address_immutable_recovery_artifact_retained", self.job)
        self.assertEqual(self.job.count("AMAIL_TEN_ADDRESS_KEY_GENERATION: ten-address-v1"), 3)
        self.assertEqual(self.job.count("secrets.AMAIL_TEN_ADDRESS_RECOVERY_KEY_V1"), 3)
        self.assertNotIn("delete-artifact", self.source)
        self.assertNotIn("overwrite: true", self.source)
        self.assertNotIn("AMAIL_TEST_SMTP_TOKEN", self.source)
        self.assertNotIn("--body", self.source)

    def test_source_and_crypto_tests_before_any_secret_capability(self):
        """Fresh hosted synthetic checks run before real provider/native credentials."""
        tests = self.job.index("Run synthetic quota composition and real cipher tests before Secrets")
        first_secret = self.job.index("secrets.")
        self.assertLess(tests, first_secret)
        self.assertIn("python infra/tests/staging_ten_address_crypto_check.py -v", self.job)
        self.assertIn("-p 'test_staging_ten_address*.py'", self.job)
        self.assertNotIn("cargo build", self.job)
        self.assertNotIn("wrangler", self.job)
        self.assertNotIn("--deploy", self.job)
        self.assertIn("contents: read", self.source)
        self.assertIn("actions: read", self.source)

    def test_optional_empty_queue_argument_is_not_misparsed_by_native_shell(self):
        """Only pass --queue-id when it has a validated nonempty value."""
        self.assertEqual(self.job.count("if ($env:PUBLIC_QUEUE_ID) { $arguments += @('--queue-id', $env:PUBLIC_QUEUE_ID) }"), 3)
        self.assertEqual(self.job.count("python infra/tests/staging_ten_address_acceptance.py @arguments"), 3)

    def test_key_creation_is_source_only_non_overwriting_private_stdin(self):
        """One project-scoped versioned key is generated only by an explicit administrator."""
        helper = (ROOT / "infra/deploy/create_ten_address_recovery_key.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("CREATE_STAGING_TEN_ADDRESS_RECOVERY_KEY_V1", helper)
        self.assertIn("AMAIL_TEN_ADDRESS_RECOVERY_KEY_V1", helper)
        self.assertIn("permissions.admin -ne $true", helper)
        self.assertLess(helper.index("ten_address_recovery_key_already_present"), helper.index("RandomNumberGenerator"))
        self.assertIn("RandomNumberGenerator]::GetBytes(32)", helper)
        self.assertIn("$process.StandardInput.Write($InputValue)", helper)
        self.assertNotIn("'--body'", helper)
        self.assertNotIn("--env", helper)
        self.assertNotIn("Set-Content", helper)
        self.assertNotRegex(helper, r"Write-(?:Output|Host).*\$(?:hex|bytes|InputValue)")
        self.assertIn("WindowStyle]::Hidden", helper)
        self.assertIn("CreateNoWindow = $true", helper)
        self.assertIn("ZeroMemory($bytes)", helper)
        self.assertNotIn("create_ten_address_recovery_key.ps1", self.job)
