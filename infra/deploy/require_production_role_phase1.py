"""Verify immutable production phase-one/privacy and promoted staged role evidence.

Realm-specific whole-record privacy attestations must be emitted by actual
acceptance harnesses. This consumer cannot turn configuration evidence into
privacy proof. Missing future production/staged harness evidence fails closed.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
from require_trace_containment import gh, REPO
from trace_rollout_attestation import UUID, ID
from require_role_trace_phase1 import exact_marker


def log(run_id: str, sha: str, branch: str, workflow: str, name: str) -> str:
    """Require one exact first-attempt successful run/job and complete bounded inventory."""
    if re.fullmatch(r"[1-9][0-9]{0,19}", run_id) is None or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise ValueError("evidence_unverified")
    run = json.loads(gh("api", f"repos/{REPO}/actions/runs/{run_id}"))
    if (not isinstance(run, dict) or str(run.get("id")) != run_id or run.get("run_attempt") != 1
            or run.get("status") != "completed" or run.get("conclusion") != "success"
            or run.get("event") != "workflow_dispatch" or run.get("head_branch") != branch
            or run.get("head_sha") != sha or run.get("path") != workflow
            or not isinstance(run.get("repository"), dict) or run["repository"].get("full_name") != REPO):
        raise ValueError("evidence_unverified")
    payload = json.loads(gh("api", f"repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100"))
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if (not isinstance(jobs, list) or len(jobs) > 100 or not all(isinstance(job, dict) for job in jobs)
            or type(payload.get("total_count")) is not int or payload["total_count"] != len(jobs)):
        raise ValueError("evidence_unverified")
    matches = [job for job in jobs if job.get("name") == name]
    if len(matches) != 1:
        raise ValueError("evidence_unverified")
    job = matches[0]
    if (type(job.get("id")) is not int or job["id"] <= 0 or job.get("run_id") != int(run_id)
            or job.get("run_attempt") != 1 or job.get("head_sha") != sha
            or job.get("status") != "completed" or job.get("conclusion") != "success"):
        raise ValueError("evidence_unverified")
    return gh("api", f"repos/{REPO}/actions/jobs/{job['id']}/logs")


def verify() -> None:
    """Require separate production deploy/privacy runs and exact-source staged role acceptance."""
    sha = os.getenv("GITHUB_SHA", "")
    deploy, privacy, staged = (os.getenv(key, "") for key in
                             ("AMAIL_PRODUCTION_PHASE1_RUN", "AMAIL_PRODUCTION_PRIVACY_RUN", "AMAIL_STAGED_ROLE_ACCEPTANCE_RUN"))
    source, sink = os.getenv("AMAIL_EXPECTED_WORKER_VERSION", ""), os.getenv("AMAIL_EXPECTED_TRACE_SINK_VERSION", "")
    queue, dlq = os.getenv("AMAIL_TRACE_QUEUE_ID", ""), os.getenv("AMAIL_TRACE_DLQ_ID", "")
    if (len({deploy, privacy, staged}) != 3 or any(UUID.fullmatch(value) is None for value in (source, sink))
            or any(ID.fullmatch(value) is None for value in (queue, dlq)) or queue == dlq):
        raise ValueError("evidence_pins_unverified")
    config_marker = f"production_trace_graph_attestation=api-only-v1 source={source} sink={sink} queue={queue} dlq={dlq}"
    privacy_marker = f"production_trace_sink_privacy_attestation=bounded-v1 source={source} sink={sink} queue={queue} dlq={dlq}"
    staged_marker = f"staging_role_operational_privacy_attestation=bounded-v1 source_sha={sha} email=pass cron=pass fault=pass rollback=pass"
    checks = (
        (deploy, "main", ".github/workflows/ci.yml", "Deploy mail API", "production_trace_graph_attestation=", config_marker),
        (privacy, "main", ".github/workflows/production-trace-privacy.yml", "Bounded production API and sink retained-record privacy", "production_trace_sink_privacy_attestation=", privacy_marker),
        (staged, "codex/amail-v0.1.0", ".github/workflows/staging-role-acceptance.yml", "Bounded staged role operational and whole-record privacy acceptance", "staging_role_operational_privacy_attestation=", staged_marker),
    )
    for run, branch, workflow, job, prefix, marker in checks:
        if not exact_marker(log(run, sha, branch, workflow, job), prefix, marker):
            raise ValueError("evidence_marker_unverified")


def main() -> int:
    """Suppress complete logs and provider data, leaving one fixed verdict."""
    try:
        verify()
    except (ValueError, TypeError, KeyError, OSError, subprocess.TimeoutExpired):
        print("production_role_provenance=UNVERIFIED")
        return 1
    print("production_role_provenance=immutable_phase1_privacy_and_staged_roles_verified")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
