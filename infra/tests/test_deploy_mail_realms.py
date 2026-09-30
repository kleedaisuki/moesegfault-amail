"""Hosted synthetic isolated Mail deployment and redacted recovery contracts."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import check_staging
import deploy_production_mail as deployer

VERSION = "11111111-1111-4111-8111-111111111111"
PRIVATE = "synthetic-provider-body-confidential-marker"


class MailDeployTests(unittest.TestCase):
    """Default production and explicit staging never share an inferred realm."""

    def environment(self, target: str, output: Path) -> dict:
        """Provide synthetic realm-selected credentials through the workflow contract."""
        return {
            "GITHUB_REF": "refs/heads/main" if target == "production" else "refs/heads/codex/amail-v0.1.0",
            "GITHUB_OUTPUT": str(output),
            "OPENROUTER_API_KEY": f"{target}-synthetic-openrouter",
            "CF_EMAIL_ROUTING_TOKEN": f"{target}-synthetic-routing",
            "INGRESS_SECRET": f"{target}-synthetic-ingress",
            "AMAIL_STAGING_MAIL_DEPLOY_CONFIRM": "RUN_STAGING_TRACE_SINK_ROLLOUT",
            "AMAIL_TRACE_TOPOLOGY": "api-only",
            "AMAIL_TRACE_QUEUE_ID": "b" * 32,
        }

    def scenario(self, target: str, stdout: str, status: int, *, timeout: bool = False) -> tuple[int, str, str]:
        """Run a synthetic one-attempt deployment under repo .temp and inspect cleanup."""
        temporary = ROOT / ".temp"
        temporary.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary) as folder:
            root = Path(folder)
            (root / "crates/mail-worker").mkdir(parents=True)
            output = root / "step-output"
            environment = self.environment(target, output)
            seen = []

            def run(command, **kwargs):
                """Inspect the actual secret contract before replacing the provider operation."""
                prefix = ["wrangler", "deploy", "--env", "staging"] if target == "staging" else ["wrangler", "deploy"]
                self.assertEqual(command[:-2], prefix)
                self.assertEqual(command[-2], "--secrets-file")
                self.assertEqual(kwargs["cwd"], root / "crates/mail-worker")
                self.assertTrue(kwargs["capture_output"])
                self.assertEqual(kwargs["timeout"], 600)
                path = Path(command[-1])
                seen.append(path)
                self.assertEqual(path.parent, root / ".temp")
                expected = {key: environment[key] for key in ("OPENROUTER_API_KEY", "CF_EMAIL_ROUTING_TOKEN", "INGRESS_SECRET")}
                self.assertEqual(json.loads(path.read_text()), expected)
                self.assertNotIn("ROLE_FORWARD_DESTINATION", json.loads(path.read_text()))
                if timeout:
                    raise subprocess.TimeoutExpired(command, 600, output=PRIVATE)
                return subprocess.CompletedProcess(command, status, stdout, PRIVATE)

            captured = io.StringIO()
            argv = ["--target", "staging"] if target == "staging" else []
            with patch.object(deployer, "ROOT", root), patch.dict(os.environ, environment, clear=True), patch.object(deployer.subprocess, "run", side_effect=run) as call, redirect_stdout(captured):
                code = deployer.main(argv)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(len(seen), 1)
            self.assertFalse(seen[0].exists())
            logs = captured.getvalue()
            self.assertNotIn(PRIVATE, logs)
            for key in ("OPENROUTER_API_KEY", "CF_EMAIL_ROUTING_TOKEN", "INGRESS_SECRET"):
                self.assertNotIn(environment[key], logs)
            return code, logs, output.read_text() if output.exists() else ""

    def test_default_production_and_explicit_staging_capture_exact_pin(self):
        """Existing no-argument production behavior remains main-only and env-free."""
        for target in ("production", "staging"):
            code, logs, output = self.scenario(target, f"{PRIVATE}\nCurrent Version ID: {VERSION}\n", 0)
            self.assertEqual(code, 0)
            self.assertEqual(output, f"version={VERSION}\n")
            self.assertIn(f"{target}_api_deployment=version_captured", logs)

    def test_failed_command_retains_only_exact_recovery_pin(self):
        """A UUID returned on nonzero exit is recovery metadata, never acceptance or retry."""
        for target in ("production", "staging"):
            code, logs, output = self.scenario(target, f"Current Version ID: {VERSION}\n", 1)
            self.assertEqual(code, 1)
            self.assertEqual(output, f"version={VERSION}\n")
            self.assertIn("recovery_version_captured", logs)
            self.assertNotIn(f"{target}_api_deployment=version_captured\n", logs)

    def test_missing_duplicate_malformed_and_oversized_output_never_become_pins(self):
        """Only one bounded exact provider UUID is an output, including ambiguous failure."""
        values = (PRIVATE, f"Current Version ID: {VERSION}\n" * 2,
                  f"Current Version ID: {VERSION}suffix\n", "x" * 1048577 + f"Current Version ID: {VERSION}\n")
        for stdout in values:
            code, logs, output = self.scenario("staging", stdout, 0)
            self.assertEqual(code, 1)
            self.assertEqual(output, "")
            self.assertNotIn("recovery_version_captured", logs)
        code, _, output = self.scenario("staging", "", 0, timeout=True)
        self.assertEqual((code, output), (1, ""))

    def test_wrong_branch_confirmation_queue_and_missing_secret_precede_mutation(self):
        """Explicit staging selection cannot reach production by fallback or guesswork."""
        cases = (
            ("staging", "GITHUB_REF", "refs/heads/main"),
            ("production", "GITHUB_REF", "refs/heads/codex/amail-v0.1.0"),
            ("staging", "AMAIL_STAGING_MAIL_DEPLOY_CONFIRM", "wrong"),
            ("staging", "AMAIL_TRACE_TOPOLOGY", "api-role"),
            ("staging", "AMAIL_TRACE_QUEUE_ID", "missing"),
            ("staging", "INGRESS_SECRET", ""),
            ("production", "GITHUB_OUTPUT", ""),
        )
        for target, name, value in cases:
            environment = dict(self.environment(target, ROOT / ".temp/synthetic-unused-output"), **{name: value})
            argv = ["--target", target]
            with patch.dict(os.environ, environment, clear=True), patch.object(deployer.tempfile, "mkstemp") as write, patch.object(deployer.subprocess, "run") as run, redirect_stdout(io.StringIO()):
                self.assertEqual(deployer.main(argv), 1)
            write.assert_not_called()
            run.assert_not_called()

    def test_staging_isolation_failure_is_redacted_and_precedes_mutation(self):
        """The reused reviewed resource guard fails closed without publishing config values."""
        captured = io.StringIO()
        environment = self.environment("staging", ROOT / ".temp/synthetic-unused-output")
        with patch.dict(os.environ, environment, clear=True), patch.object(check_staging, "check", side_effect=ValueError(PRIVATE)), patch.object(deployer.tempfile, "mkstemp") as write, patch.object(deployer.subprocess, "run") as run, redirect_stdout(captured):
            self.assertEqual(deployer.main(["--target", "staging"]), 1)
        self.assertNotIn(PRIVATE, captured.getvalue())
        write.assert_not_called()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
