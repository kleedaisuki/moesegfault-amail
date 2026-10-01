"""Hosted source contracts for full-gate same-run promotion and release compiler."""

from pathlib import Path
import re
import unittest

from workflow_source import job_block

ROOT = Path(__file__).resolve().parents[2]
JOBS = ("deploy-worker", "deploy-ingress", "deploy-events", "staging-worker",
        "staging-ingress", "staging-events", "staging-identity-test-inbox",
        "deploy-trace-sink", "staging-trace-sink")


class DeploymentArtifactWorkflowTests(unittest.TestCase):
    """A deployment consumes this producer only after the complete Worker gate."""

    def test_all_ordinary_worker_deployments_use_exact_same_run_artifact(self):
        """No rebuild, ancestry exemption, arbitrary name or skipped-gate bypass exists."""
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for name in JOBS:
            block = job_block(source, name)
            with self.subTest(job=name):
                needs = re.search(r"^    needs: \[(.*?)\]$", block, re.MULTILINE)
                self.assertIsNotNone(needs)
                self.assertTrue({"worker", "worker-build"} <= set(needs[1].split(", ")))
                self.assertEqual(block.count("artifact-ids: ${{ needs.worker-build.outputs.artifact_id }}"), 1)
                self.assertEqual(block.count("python infra/ci/worker_artifact.py restore"), 1)
                self.assertIn("path: .temp/ci/worker-built", block)
                self.assertNotIn("worker-build --release", block)
                self.assertNotIn("cargo install worker-build", block)
                self.assertNotIn("validated_worker_build", block)
                self.assertNotIn("if: always()", block.split("    steps:", 1)[0])
                restore = block.index("python infra/ci/worker_artifact.py restore")
                for mutation in ("configure_sending_privacy.py", "ensure_email_events.py",
                                 "ensure_trace_queues.py", "migrations apply", "wrangler deploy",
                                 "deploy_production_mail.py", "deploy_trace_sink.py"):
                    if mutation in block:
                        self.assertLess(restore, block.index(mutation))

    def test_release_selects_the_same_checked_in_compiler_and_preserves_byte_verification(self):
        """Do not mutate stable; assembly and publication still consume fixed archives."""
        source = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        build = job_block(source, "build")
        self.assertNotIn("rustup update stable", source)
        self.assertIn("rustup show active-toolchain", build)
        self.assertIn("cargo test -p amail --locked --all-targets", build)
        self.assertIn("cargo build -p amail --locked --release", build)
        for name in ("assemble", "publish", "verify-published"):
            self.assertNotIn("cargo build", job_block(source, name))
        self.assertIn("verify_published_assets.py", job_block(source, "verify-published"))


if __name__ == "__main__":
    unittest.main()
