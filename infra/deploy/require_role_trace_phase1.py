"""Attest immutable phase-one rollout and bounded privacy before role integration.

Only first-attempt successful branch-local runs at this exact source revision are
accepted. API/sink/role share one schema; same-revision promotion prevents a new
role producer from silently targeting an older incompatible sink. Whole-record
privacy evidence is separate from deployment and configuration evidence.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from require_trace_containment import gh, REPO
from trace_rollout_attestation import format_attestation, DEPLOY_MARKER, CANARY_MARKER, UUID

JOBS = {"api": "Deploy isolated staging mail API",
        "sink": "Deploy private staging privacy trace sink",
        "canary": "Reuse branch-local Queue trace sink privacy acceptance / Hosted bounded trace sink privacy canary"}


def completed_run(run_id: str, sha: str) -> dict:
    """Require exact repository, workflow, branch, revision and immutable attempt."""
    if (re.fullmatch(r"[1-9][0-9]{0,19}", run_id) is None
            or re.fullmatch(r"[0-9a-f]{40}", sha) is None):
        raise ValueError("run_unverified")
    run = json.loads(gh("api", f"repos/{REPO}/actions/runs/{run_id}"))
    if (not isinstance(run, dict) or str(run.get("id")) != run_id
            or run.get("run_attempt") != 1 or run.get("status") != "completed"
            or run.get("conclusion") != "success" or run.get("event") != "workflow_dispatch"
            or run.get("head_branch") != "codex/amail-v0.1.0" or run.get("head_sha") != sha
            or run.get("path") != ".github/workflows/ci.yml"
            or not isinstance(run.get("repository"), dict)
            or run["repository"].get("full_name") != REPO):
        raise ValueError("run_unverified")
    return run


def successful_job_log(run_id: str, sha: str, name: str) -> str:
    """Reject incomplete inventories, duplicate jobs and retried/mismatched jobs."""
    payload = json.loads(gh("api", f"repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100"))
    rows = payload.get("jobs") if isinstance(payload, dict) else None
    if (not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows)
            or type(payload.get("total_count")) is not int or payload["total_count"] != len(rows)):
        raise ValueError("jobs_unverified")
    matches = [row for row in rows if row.get("name") == name]
    if len(matches) != 1:
        raise ValueError("job_unverified")
    job = matches[0]
    if (type(job.get("id")) is not int or job["id"] <= 0
            or job.get("run_id") != int(run_id) or job.get("run_attempt") != 1
            or job.get("head_sha") != sha or job.get("status") != "completed"
            or job.get("conclusion") != "success"):
        raise ValueError("job_unverified")
    return gh("api", f"repos/{REPO}/actions/jobs/{job['id']}/logs")


def exact_marker(log: str, prefix: str, marker: str) -> bool:
    """Count one exact result line; command echoes and duplicate markers are invalid."""
    return (log.count(prefix) == 1
            and sum(re.search(r"(?:^|\s)" + re.escape(marker) + r"$", line) is not None
                    for line in log.splitlines()) == 1)


def verify(phase1_run: str, canary_run: str, sha: str, source: str, sink: str,
           queue: str, dlq: str) -> None:
    """Bind accepted privacy evidence to the exact promoted API, sink and Queue IDs."""
    deploy = format_attestation("sink-deploy", source, sink, queue, dlq)
    canary = format_attestation("sink-canary", source, sink, queue, dlq)
    if phase1_run == canary_run:
        raise ValueError("evidence_kinds_unverified")
    completed_run(phase1_run, sha)
    completed_run(canary_run, sha)
    api_log = successful_job_log(phase1_run, sha, JOBS["api"])
    versions = re.findall(r"Current Version ID:\s*(" + UUID.pattern.removesuffix(r"\Z") + r")(?=\s|$)", api_log)
    if versions != [source]:
        raise ValueError("api_version_unverified")
    sink_log = successful_job_log(phase1_run, sha, JOBS["sink"])
    if not exact_marker(sink_log, DEPLOY_MARKER, deploy):
        raise ValueError("sink_attestation_unverified")
    privacy_log = successful_job_log(canary_run, sha, JOBS["canary"])
    if (not exact_marker(privacy_log, CANARY_MARKER, canary)
            or "staging_trace_sink_hosted: bounded_retained_canary_verified" not in privacy_log):
        raise ValueError("privacy_attestation_unverified")


def main() -> int:
    """Fail closed with a single fixed result; retained/provider logs stay in memory."""
    try:
        verify(os.getenv("AMAIL_ROLE_PHASE1_RUN", ""), os.getenv("AMAIL_ROLE_SINK_CANARY_RUN", ""),
               os.getenv("GITHUB_SHA", ""), os.getenv("AMAIL_EXPECTED_WORKER_VERSION", ""),
               os.getenv("AMAIL_EXPECTED_TRACE_SINK_VERSION", ""),
               os.getenv("AMAIL_TRACE_QUEUE_ID", ""), os.getenv("AMAIL_TRACE_DLQ_ID", ""))
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired):
        print("role_trace_phase1_provenance=UNVERIFIED")
        return 1
    print("role_trace_phase1_provenance=immutable_deploy_and_bounded_privacy_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
