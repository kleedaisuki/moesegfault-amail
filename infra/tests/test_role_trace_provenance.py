"""Hosted synthetic immutable deployment/privacy evidence and workflow contracts."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import require_role_trace_phase1 as provenance
import trace_rollout_attestation as attest

SHA = "a" * 40
SOURCE = "11111111-1111-4111-8111-111111111111"
SINK = "22222222-2222-4222-8222-222222222222"
QUEUE, DLQ = "b" * 32, "c" * 32


def run(run_id: str) -> dict:
    """Use a first-attempt protected manual run shape with no real account data."""
    return {"id": int(run_id), "run_attempt": 1, "status": "completed", "conclusion": "success",
            "event": "workflow_dispatch", "head_branch": "codex/amail-v0.1.0", "head_sha": SHA,
            "path": ".github/workflows/ci.yml", "repository": {"full_name": provenance.REPO}}


def job(job_id: int, run_id: str, name: str) -> dict:
    """Mirror version/revision identity fields separately from display name."""
    return {"id": job_id, "run_id": int(run_id), "run_attempt": 1, "head_sha": SHA,
            "status": "completed", "conclusion": "success", "name": name}


def fixture() -> dict:
    """Keep configuration evidence distinct from actual bounded retained privacy."""
    base = f"repos/{provenance.REPO}/actions/"
    return {base + "runs/123": run("123"), base + "runs/456": run("456"),
            base + "runs/123/jobs?per_page=100": {"total_count": 2, "jobs": [
                job(1, "123", provenance.JOBS["api"]), job(2, "123", provenance.JOBS["sink"])]},
            base + "runs/456/jobs?per_page=100": {"total_count": 1, "jobs": [job(3, "456", provenance.JOBS["canary"])]},
            base + "jobs/1/logs": f"2026-10-01T00:00:00Z Current Version ID: {SOURCE}\n",
            base + "jobs/2/logs": "timestamp " + attest.format_attestation("sink-deploy", SOURCE, SINK, QUEUE, DLQ) + "\n",
            base + "jobs/3/logs": "timestamp staging_trace_sink_hosted: bounded_retained_canary_verified\n" +
                "timestamp " + attest.format_attestation("sink-canary", SOURCE, SINK, QUEUE, DLQ) + "\n"}


class ProvenanceTests(unittest.TestCase):
    """No generic green run, retry or preflight can attest role privacy prerequisites."""

    def verify(self, evidence: dict) -> None:
        """Mock only bounded GitHub transport while exercising actual parser contracts."""
        def gh(*args: str) -> str:
            self.assertEqual(args[0], "api")
            value = evidence[args[1]]
            return value if isinstance(value, str) else json.dumps(value)
        with patch.object(provenance, "gh", side_effect=gh):
            provenance.verify("123", "456", SHA, SOURCE, SINK, QUEUE, DLQ)

    def test_exact_same_revision_deploy_and_privacy(self) -> None:
        """Shared-schema promotion binds independently successful first-attempt jobs."""
        self.verify(fixture())

    def test_wrong_revision_attempt_repository_branch_and_outcome_denied(self) -> None:
        """Historical success at another revision or repository is not this promotion."""
        base = f"repos/{provenance.REPO}/actions/"
        for field, bad in (("head_sha", "f" * 40), ("run_attempt", 2), ("event", "push"),
                           ("conclusion", "failure"), ("head_branch", "main"),
                           ("repository", {"full_name": "other/repository"}), ("path", "other.yml")):
            evidence = fixture()
            evidence[base + "runs/123"][field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.verify(evidence)
        for field, bad in (("head_sha", "f" * 40), ("run_attempt", 2), ("conclusion", "skipped"), ("run_id", 456)):
            evidence = fixture()
            evidence[base + "runs/123/jobs?per_page=100"]["jobs"][0][field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.verify(evidence)

    def test_incomplete_or_duplicate_job_inventory_denied(self) -> None:
        """Exact total counts and sole required job identity are mandatory."""
        path = f"repos/{provenance.REPO}/actions/runs/123/jobs?per_page=100"
        for rows, count in (([], 0), (fixture()[path]["jobs"], 3),
                            (fixture()[path]["jobs"] * 2, 4)):
            evidence = fixture()
            evidence[path] = {"jobs": rows, "total_count": count}
            with self.assertRaises(ValueError):
                self.verify(evidence)

    def test_wrong_missing_duplicated_or_kind_mismatched_markers_denied(self) -> None:
        """A green preflight or settings-only marker never substitutes for retained privacy."""
        base = f"repos/{provenance.REPO}/actions/jobs/"
        for job_id, log in ((1, f"Current Version ID: {SINK}\n"),
                            (1, f"Current Version ID: {SOURCE}\n" * 2),
                            (2, "trace_sink_deployment=version_captured\n"),
                            (3, "staging_trace_sink_hosted: preflight_verified\n"),
                            (3, fixture()[base + "3/logs"].replace(QUEUE, DLQ)),
                            (3, fixture()[base + "3/logs"] * 2)):
            evidence = fixture()
            evidence[base + f"{job_id}/logs"] = log
            with self.subTest(job_id=job_id), self.assertRaises(ValueError):
                self.verify(evidence)

    def test_credential_text_never_enters_markers(self) -> None:
        """Formatters accept only canonical non-secret pins and a closed kind enum."""
        for changes in (("unknown", SOURCE, SINK, QUEUE, DLQ),
                        ("sink-canary", "private", SINK, QUEUE, DLQ),
                        ("sink-deploy", SOURCE, SINK, QUEUE, QUEUE),
                        ("sink-deploy", SOURCE, "private", QUEUE, DLQ)):
            with self.assertRaises(ValueError):
                attest.format_attestation(*changes)

    def test_phase2_workflow_is_manual_and_markers_follow_their_oracles(self) -> None:
        """No push/general staging deployment introduces role; preflight has no privacy marker."""
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        role = workflow.split("\n  staging-role-monitor:\n", 1)[1].split("\n  deploy-trace-sink:\n", 1)[0]
        self.assertIn("inputs.target == 'staging-role-queue-rollout'", role)
        self.assertIn("github.event_name == 'workflow_dispatch'", role)
        self.assertIn("RUN_STAGING_ROLE_TRACE_ROLLOUT", role)
        self.assertNotIn("inputs.target == 'staging'", role)
        self.assertIn("AMAIL_ROLE_SINK_CANARY_RUN: ${{ inputs.trace_sink_canary_run }}", role)
        self.assertLess(role.index("require_role_trace_phase1.py"), role.index("wrangler d1 migrations apply"))
        self.assertLess(role.index("check_role_trace_rollout.py --phase before"), role.index("deploy_staging_role_monitor.py"))
        self.assertLess(role.index("deploy_staging_role_monitor.py"), role.index("check_role_trace_rollout.py --phase after"))
        sink = workflow.split("\n  staging-trace-sink:\n", 1)[1]
        self.assertLess(sink.index("--mode sink"), sink.index("trace_rollout_attestation.py --kind sink-deploy"))
        canary = (ROOT / ".github/workflows/staging-trace-sink-canary.yml").read_text(encoding="utf-8")
        self.assertIn("if: inputs.mode == 'canary'", canary)
        self.assertLess(canary.index("python infra/tests/staging_hosted_trace_sink_canary.py"),
                        canary.index("trace_rollout_attestation.py --kind sink-canary"))

    def test_smtp_caller_wires_both_required_readback_pins(self) -> None:
        """The legacy hosting wrapper passes exact immutable-role and reviewed-Queue pins."""
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        smtp = workflow.split("\n  staging-role-smtp:\n", 1)[1].split("\n  staging-role-timeout-audit:\n", 1)[0]
        step = smtp.split("      - name: Check deployed provenance and run one ID-bound SMTP probe\n", 1)[1]
        self.assertIn("AMAIL_EXPECTED_ROLE_WORKER_VERSION: ${{ inputs.role_version }}", step)
        self.assertIn("AMAIL_EXPECTED_TRACE_QUEUE_ID: ${{ vars.AMAIL_TRACE_QUEUE_ID_STAGING }}", step)
        self.assertIn("AMAIL_STAGING_ROLE_VERSION: ${{ inputs.role_version }}", step)
        self.assertIn("run: python workers/role-monitor/hosted_acceptance.py", step)


if __name__ == "__main__":
    unittest.main()
