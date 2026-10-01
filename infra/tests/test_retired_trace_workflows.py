"""Keep completed, fixed-window research reads out of executable workflows.

The classifiers remain importable for synthetic safety regression coverage.
Retirement removes dispatch targets, jobs, and provider invocations rather than
leaving a secret-bearing disabled job beside normal acceptance operations.
"""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from workflow_source import jobs


ROOT = Path(__file__).resolve().parents[2]
RETIRED = {
    "staging-trace-marker-location": "staging_trace_marker_location.py",
    "staging-trace-marker-discriminator": "staging_trace_marker_discriminator.py",
    "staging-trace-security-events": "probe_staging_trace_security_events.py",
}


class RetiredTraceWorkflowTests(unittest.TestCase):
    """Require source-visible retirement without deleting historical evidence."""

    def test_no_workflow_exposes_or_invokes_completed_reads(self) -> None:
        """Catch renamed jobs, reusable callers, and accidental dispatch revival."""
        paths = sorted((ROOT / ".github/workflows").glob("*.y*ml"))
        self.assertTrue(paths)
        for path in paths:
            source = path.read_text(encoding="utf-8")
            for lane, script in RETIRED.items():
                with self.subTest(workflow=path.name, lane=lane):
                    self.assertNotIn(lane, source)
                    self.assertNotIn(script, source)
                    self.assertNotIn(script.removesuffix(".py"), source)

    def test_supported_consumers_and_recovery_are_not_retired(self) -> None:
        """Protect stable CI, product deployment, and already-owned recovery jobs."""
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        active = jobs(source)
        for job in (
            "changes", "cli", "worker-build", "worker-native", "worker", "dns",
            "site", "provider-live", "deploy-worker", "deploy-ingress",
            "deploy-events", "deploy-site", "deploy-trace-sink", "staging-worker",
            "staging-ingress", "staging-events", "staging-site", "staging-trace-sink",
            "release-ready", "staging-routing-write-recover", "staging-fifth-mail-cleanup",
            "staging-prior-alias-reconcile", "staging-hosted-alias-reconcile",
            "staging-trace-canary", "staging-trace-sink-canary", "staging-trace-http-compare",
        ):
            with self.subTest(job=job):
                self.assertIn(job, active)
        for name in (
            "release.yml", "native-fixture.yml", "native-tracing-canary.yml",
            "deploy-identity-test-inbox.yml", "staging-worker-r2-capability.yml",
            "staging-ten-address-acceptance.yml",
        ):
            self.assertTrue((ROOT / ".github/workflows" / name).is_file())

    def test_historical_classifiers_and_evidence_remain_available(self) -> None:
        """Preserve source contracts and provenance, not obsolete dispatch advice."""
        for path in (
            "infra/tests/staging_trace_marker_location.py",
            "infra/tests/staging_trace_marker_discriminator.py",
            "infra/provider/probe_staging_trace_security_events.py",
            "docs/staging-trace-canary.md",
            "docs/staging-trace-marker-second-discriminator.md",
            "docs/staging-trace-security-events-probe.md",
            "docs/maintenance-operational-lanes.md",
        ):
            self.assertTrue((ROOT / path).is_file())


if __name__ == "__main__":
    unittest.main()
