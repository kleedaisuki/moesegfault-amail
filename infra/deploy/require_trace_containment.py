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
from pin_staging_mail import SCRIPT, bindings_match, fetch, serving_deployment
sys.path.insert(0, str(Path(__file__).parents[2] / "crates/mail-worker"))
from check_observability import effective_api_settings, safe_observability, worker_readback

REPO = "kleedaisuki/moesegfault-amail"
UUID = r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"
KINDS = ("deploy-v1", "settings-v1")
SETTINGS_VERSION = "c3f6401a-1e84-4f51-91df-ae77d90683e9"
SETTINGS_MARKER = "staging_api_capture_off_attestation="
JOBS = {"deploy-v1": "Deploy isolated staging mail API",
        "settings-v1": "Apply isolated staging API capture-off settings"}


def gh(*args: str) -> str:
    """Capture bounded gh output, suppressing authentication/provider error bodies."""
    result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60, check=False)
    if result.returncode or len(result.stdout.encode()) > 16_777_216:
        raise ValueError("github_unavailable")
    return result.stdout


def settings_marker(log: str, version: str) -> bool:
    """Accept one exact helper attestation, allowing only hosted log line prefixes.

    A settings correction does not deploy a version. Mixed or duplicate marker
    kinds, version mismatch and deployment output therefore invalidate evidence.
    """
    marker = f"{SETTINGS_MARKER}settings-v1 version={version}"
    return (log.count(SETTINGS_MARKER) == 1 and "Current Version ID:" not in log
            and sum(re.search(r"(?:^|\s)" + re.escape(marker) + r"$", line) is not None
                    for line in log.splitlines()) == 1)


def immutable_evidence(run_id: str, version: str, *, kind: str = "deploy-v1") -> None:
    """Attest one explicitly selected immutable deployment or settings operation.

    The settings kind proves observability intent and unchanged serving code,
    never deployment of run-head Rust or its future Queue producer binding.
    There is no diagnostic fallback or automatic kind inference.
    """
    if kind not in KINDS or (kind == "settings-v1" and version != SETTINGS_VERSION):
        raise ValueError("evidence_kind_unverified")
    run = json.loads(gh("api", f"repos/{REPO}/actions/runs/{run_id}"))
    if (not isinstance(run, dict) or str(run.get("id")) != run_id
            or run.get("run_attempt") != 1
            or run.get("status") != "completed" or run.get("conclusion") != "success"
            or run.get("head_branch") != "codex/amail-v0.1.0"
            or run.get("path") != ".github/workflows/ci.yml"
            or (kind == "settings-v1" and run.get("event") != "workflow_dispatch")
            or not re.fullmatch(r"[0-9a-f]{40}", run.get("head_sha", ""))):
        raise ValueError("run_unverified")
    if kind == "settings-v1" and (not isinstance(run.get("repository"), dict)
            or run["repository"].get("full_name") != REPO):
        raise ValueError("run_unverified")
    jobs = json.loads(gh("api", f"repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100"))
    if (not isinstance(jobs, dict) or not isinstance(jobs.get("jobs"), list)
            or not all(isinstance(job, dict) for job in jobs["jobs"])
            or type(jobs.get("total_count")) is not int
            or jobs["total_count"] != len(jobs["jobs"])):
        raise ValueError("jobs_incomplete")
    matches = [job for job in jobs["jobs"] if job.get("name") == JOBS[kind]]
    if len(matches) != 1 or matches[0].get("conclusion") != "success":
        raise ValueError("deploy_job_unverified" if kind == "deploy-v1" else "settings_job_unverified")
    if kind == "settings-v1" and (type(matches[0].get("id")) is not int
            or matches[0]["id"] <= 0 or matches[0].get("status") != "completed"
            or matches[0].get("run_id") != int(run_id)
            or matches[0].get("run_attempt") != 1
            or matches[0].get("head_sha") != run["head_sha"]):
        raise ValueError("settings_job_unverified")
    log = gh("run", "view", run_id, "--repo", REPO, "--job", str(matches[0]["id"]), "--log")
    if kind == "deploy-v1":
        versions = re.findall(r"Current Version ID:\s*(" + UUID + r")(?=\s|$)", log)
        if versions != [version]:
            raise ValueError("deploy_version_unverified")
    elif not settings_marker(log, version):
        raise ValueError("settings_attestation_unverified")
    source = json.loads(gh("api", f"repos/{REPO}/contents/crates/mail-worker/wrangler.toml?ref={run['head_sha']}"))
    if not isinstance(source, dict) or source.get("encoding") != "base64":
        raise ValueError("source_unverified")
    config = tomllib.loads(base64.b64decode(source["content"]).decode())
    environments = config.get("env")
    stage = environments.get("staging") if isinstance(environments, dict) else None
    if (not isinstance(stage, dict) or stage.get("name") != SCRIPT
            or not safe_observability(stage.get("observability"))):
        raise ValueError("source_privacy_unverified")


def verify(run_id: str, version: str, account: str, token: str, *, kind: str = "deploy-v1") -> None:
    """Pin historical intent and explicit current capture-off before rollout mutation.

    Observability is non-versioned: the exact successful deployment provenance
    alone cannot prove its current state. Require the same strict Worker-level
    policy as the Mail API checker, bracketed by the identical single-100
    deployment/version pair. Legacy missing/null settings never supply positive
    evidence, and the independently captured Issues subsystem must be off.
    """
    immutable_evidence(run_id, version, kind=kind)
    before = serving_deployment(fetch(account, token, "deployments?per_page=1&page=1"))
    if before is None or before[1] != version:
        raise ValueError("serving_version_unverified")
    if kind == "settings-v1" and not bindings_match(
            fetch(account, token, f"versions/{version}"), version):
        raise ValueError("serving_bindings_unverified")
    settings = fetch(account, token, "settings")
    script_settings = fetch(account, token, "script-settings")
    worker = worker_readback(account, token, SCRIPT)
    if not effective_api_settings(worker, SCRIPT, settings, script_settings):
        raise ValueError("serving_privacy_unverified")
    after = serving_deployment(fetch(account, token, "deployments?per_page=1&page=1"))
    if before != after:
        raise ValueError("serving_version_changed")


def main() -> int:
    """Accept only immutable run/version pins and project deployment credentials."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--kind", choices=KINDS, default="deploy-v1")
    args = parser.parse_args()
    account, token = os.getenv("CLOUDFLARE_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_API_TOKEN", "")
    try:
        if not re.fullmatch(r"[1-9][0-9]{0,19}", args.run) or not re.fullmatch(UUID, args.version):
            raise ValueError("invalid_input")
        if not re.fullmatch(r"[0-9a-f]{32}", account) or not token:
            raise ValueError("credentials_missing")
        verify(args.run, args.version, account, token, kind=args.kind)
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired):
        print("trace_containment=UNVERIFIED")
        return 1
    print("trace_containment=match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
