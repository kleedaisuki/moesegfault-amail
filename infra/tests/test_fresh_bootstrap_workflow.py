"""Hosted source contracts for the protected first-held bootstrap workflow."""

from pathlib import Path
import re
import unittest

from workflow_source import job_block, jobs

ROOT = Path(__file__).resolve().parents[2]
TARGET = "production-fresh-bootstrap"


class FreshBootstrapWorkflowTests(unittest.TestCase):
    """Same-run full checks and the existing workflow writer lock precede credentials."""

    def setUp(self):
        """Select the protected producer by its externally established receipt identity."""
        self.source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        selected = [body for body in jobs(self.source).values()
                    if re.search(r"^    name: Fresh held production bootstrap$", body, re.MULTILINE)]
        self.assertEqual(len(selected), 1, "protected first-receipt producer must be unique")
        self.block = selected[0]

    def test_full_same_run_gate_is_required_and_selected_for_manual_target(self):
        """A skipped CLI/site/infrastructure job is not complete original-run admission."""
        header = self.block.split("    steps:", 1)[0]
        match = re.search(r"^    needs: \[(.*?)\]$", header, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertTrue({"cli", "worker", "worker-build", "site", "dns"}
                        <= set(match[1].split(", ")))
        self.assertIn("workflow_dispatch", header)
        self.assertIn(TARGET, header)
        self.assertIn("refs/heads/main", header)
        self.assertIn("environment: production", header)
        self.assertNotIn("always()", header)
        for name in ("cli", "worker-build", "worker", "site", "dns"):
            gate_header = job_block(self.source, name).split("    steps:", 1)[0]
            with self.subTest(gate=name):
                self.assertIn(TARGET, gate_header)

    def test_artifact_is_fixed_same_run_and_restored_before_any_secret(self):
        """No producer-by-name lookup, floating build or early provider capability exists."""
        self.assertEqual(self.block.count(
            "artifact-ids: ${{ needs.worker-build.outputs.artifact_id }}"), 1)
        self.assertEqual(self.block.count("python infra/ci/worker_artifact.py restore"), 1)
        self.assertIn("path: .temp/ci/worker-built", self.block)
        restore = self.block.index("python infra/ci/worker_artifact.py restore")
        provider = self.block.index("python infra/deploy/fresh_mail_bootstrap.py")
        self.assertLess(restore, provider)
        for secret in re.finditer(r"\$\{\{\s*secrets\.", self.block):
            self.assertLess(restore, secret.start(), "provider credentials must stay in a late step")
        for forbidden in ("worker-build --release", "cargo install worker-build",
                          "rustup update stable", "toolchain: stable", "source_run_id",
                          "validated_worker_build", "github-script"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.block)

    def test_workflow_writer_lock_is_shared_without_nested_reentrant_group(self):
        """The one workflow owner serializes fresh and established production writers."""
        prefix = self.source.split("\njobs:", 1)[0]
        lock = prefix.split("\nconcurrency:", 1)[1]
        self.assertIn(TARGET, lock)
        self.assertIn("amail-production-graph-writer", lock)
        self.assertIn("inputs.target == 'production'", lock)
        self.assertIn("inputs.target == 'production-api-only-maintenance'", lock)
        self.assertNotIn("    concurrency:", self.block)
        self.assertNotIn("cancel-in-progress: true", self.block)

    def test_first_receipt_is_owned_attempt_one_artifact_not_activation(self):
        """A held initial receipt is separate from existing activation/rollback operations."""
        self.assertIn("github.run_attempt", self.block)
        self.assertIn("RUN_FRESH_HELD_PRODUCTION_BOOTSTRAP", self.block)
        self.assertIn("FREEZE_PRODUCTION_GRAPH_WRITERS", self.block)
        self.assertIn("actions/upload-artifact@v4", self.block)
        self.assertIn("mail-fresh-bootstrap-${{ github.run_id }}-1", self.block)
        self.assertNotIn("overwrite: true", self.block)
        self.assertNotIn("continue-on-error: true", self.block)
        self.assertNotIn("deploy_production_mail.py", self.block)
        self.assertNotIn("--activate", self.block)
        self.assertNotIn("--rollback", self.block)

    def test_recovery_is_durable_readonly_lane_with_shared_graph_lock(self):
        """Prior intent is admitted on a credential-free tested path, never a new epoch."""
        source = (ROOT / ".github/workflows/fresh-mail-bootstrap-recovery.yml").read_text(encoding="utf-8")
        self.assertIn("prior_run:", source)
        self.assertIn("OBSERVE_FRESH_BOOTSTRAP_NO_REPLAY", source)
        self.assertIn("group: amail-production-graph-writer", source)
        self.assertIn("cancel-in-progress: false", source)
        self.assertIn("refs/heads/main", source)
        self.assertIn("github.run_attempt == 1", source)
        check = source.index("python -m unittest discover")
        self.assertLess(check, source.index("secrets.CLOUDFLARE_API_TOKEN"))
        self.assertIn('--recover-run "$PRIOR_RUN"', source)
        for forbidden in ("wrangler deploy", "migrations apply", "worker-build", "OPENROUTER_API_KEY",
                          "CLOUDFLARE_SECRET_ACCESS_KEY", "receipt.json", "overwrite: true"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
