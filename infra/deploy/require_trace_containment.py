"""Require immutable hosted containment evidence and its still-serving safe API version.

No provider/GitHub response, log, source or unknown identifier is printed.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from pin_staging_mail import fetch, serving_deployment
sys.path.insert(0, str(Path(__file__).parents[2] / "crates/mail-worker"))
from check_observability import safe_settings

REPO = "kleedaisuki/moesegfault-amail"
UUID = r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"


def gh(*args: str) -> str:
    """Capture bounded gh output, suppressing authentication/provider error bodies."""
    result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60, check=False)
    if result.returncode or len(result.stdout.encode()) > 16_777_216:
        raise ValueError("github_unavailable")
    return result.stdout


def immutable_evidence(run_id: str, version: str) -> None:
    """Attest successful exact run/source/deploy job and its sole emitted version ID."""
    run = json.loads(gh("api", f"repos/{REPO}/actions/runs/{run_id}"))
    if (not isinstance(run, dict) or str(run.get("id")) != run_id
            or run.get("run_attempt") != 1
            or run.get("status") != "completed" or run.get("conclusion") != "success"
            or run.get("head_branch") != "codex/amail-v0.1.0"
            or run.get("path") != ".github/workflows/ci.yml"
            or not re.fullmatch(r"[0-9a-f]{40}", run.get("head_sha", ""))):
        raise ValueError("run_unverified")
    jobs = json.loads(gh("api", f"repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100"))
    if (not isinstance(jobs, dict) or not isinstance(jobs.get("jobs"), list)
            or not all(isinstance(job, dict) for job in jobs["jobs"])
            or type(jobs.get("total_count")) is not int
            or jobs["total_count"] != len(jobs["jobs"])):
        raise ValueError("jobs_incomplete")
    matches = [job for job in jobs["jobs"] if job.get("name") == "Deploy isolated staging mail API"]
    if len(matches) != 1 or matches[0].get("conclusion") != "success":
        raise ValueError("deploy_job_unverified")
    log = gh("run", "view", run_id, "--repo", REPO, "--job", str(matches[0]["id"]), "--log")
    versions = re.findall(r"Current Version ID:\s*(" + UUID + r")(?=\s|$)", log)
    if versions != [version]:
        raise ValueError("deploy_version_unverified")
    source = json.loads(gh("api", f"repos/{REPO}/contents/crates/mail-worker/wrangler.toml?ref={run['head_sha']}"))
    if not isinstance(source, dict) or source.get("encoding") != "base64":
        raise ValueError("source_unverified")
    config = tomllib.loads(base64.b64decode(source["content"]).decode())
    stage = config.get("env", {}).get("staging", {})
    if not safe_settings({"observability": stage.get("observability")}):
        raise ValueError("source_privacy_unverified")


def verify(run_id: str, version: str, account: str, token: str) -> None:
    """Pin stable 100% traffic and safe script/settings before any rollout mutation."""
    immutable_evidence(run_id, version)
    before = serving_deployment(fetch(account, token, "deployments?per_page=1&page=1"))
    if before is None or before[1] != version:
        raise ValueError("serving_version_unverified")
    if not all(safe_settings(fetch(account, token, suffix)) for suffix in ("settings", "script-settings")):
        raise ValueError("serving_privacy_unverified")
    after = serving_deployment(fetch(account, token, "deployments?per_page=1&page=1"))
    if before != after:
        raise ValueError("serving_version_changed")


def main() -> int:
    """Accept only immutable run/version pins and project deployment credentials."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    account, token = os.getenv("CLOUDFLARE_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_API_TOKEN", "")
    try:
        if not re.fullmatch(r"[1-9][0-9]{0,19}", args.run) or not re.fullmatch(UUID, args.version):
            raise ValueError("invalid_input")
        if not re.fullmatch(r"[0-9a-f]{32}", account) or not token:
            raise ValueError("credentials_missing")
        verify(args.run, args.version, account, token)
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired):
        print("trace_containment=UNVERIFIED")
        return 1
    print("trace_containment=match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
