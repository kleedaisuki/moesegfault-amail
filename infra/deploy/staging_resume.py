"""Recover immutable ownership of the one reviewed sink-only staging interruption.

This is provenance admission, not a provider mutation or live graph attestation.
The caller must separately bracket the unchanged legacy API, private exact sink,
zero Queue producers and held sending before continuing with current tested bytes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
from inbox_worker_artifact import required_jobs, rows
from fresh_bootstrap_recovery import artifact, decode, members
from mail_lifecycle_receipt import github, REPO

ORIGIN_RUN = "37053907751"
ORIGIN_SHA = "b2dbd66d786a5a790dc55486ee27ae578690f0ea"
BRANCH = "codex/v0.1.2-agent-first-performance"
API_VERSION = "c3f6401a-1e84-4f51-91df-ae77d90683e9"
API_DEPLOYMENT = "8dc8ba02-5c4f-4c53-b0a9-f04b6a25a5cb"
SINK_VERSION = "be786239-402d-4e72-89c9-0acbe88b0b86"
QUEUE = "fcee510036af42c189e28c0b6ff9508e"
DLQ = "f023f804b7bd4d8691fbfcb60416a001"
SINK_JOB = "Deploy private staging privacy trace sink"
DEPLOY_STEP = "Deploy Queue-only trace consumer without secrets or HTTP route"
SKIPPED = {"Deploy isolated staging mail API", "Deploy isolated Rust staging SMTP ingress",
           "Deploy isolated Rust staging lifecycle consumer", "Deploy isolated staging release site",
           "Deploy private staging Identity verification inbox"}
RUNTIME = ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "rust-toolchain", ".cargo",
           "crates", "workers", "site", "infra/tests/worker-boundary")
CONTROL = {".github/workflows/ci.yml", "infra/deploy/staging_rollout.py",
           "infra/deploy/inspect_staging.py", "infra/deploy/staging_resume.py",
           "infra/tests/test_staging_resume.py", "infra/tests/test_staging_rollout.py"}
STATE = ROOT / ".temp/staging-resume.json"
LIMIT = 65_536


def git(*arguments: str) -> bytes:
    """Read the tracked tree with bounded output; missing history fails closed."""
    result = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True,
                            timeout=30, check=False)
    if result.returncode or len(result.stdout) > 1_048_576:
        raise ValueError("staging_resume_tree_unverified")
    return result.stdout


def exact_tree(current_sha: str) -> None:
    """Permit only reviewed orchestration/docs/tests changes, never ancestor trust."""
    if (not isinstance(current_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", current_sha)
            or git("rev-parse", "HEAD").decode().strip() != current_sha):
        raise ValueError("staging_resume_checkout_unverified")
    git("cat-file", "-e", ORIGIN_SHA + "^{commit}")
    if git("diff", "--name-only", "-z", ORIGIN_SHA, current_sha, "--", *RUNTIME):
        raise ValueError("staging_resume_runtime_changed")
    changed = git("diff", "--name-only", "-z", ORIGIN_SHA, current_sha).decode().split("\0")
    if any(name and name not in CONTROL and not (name.startswith("docs/") and name.endswith(".md"))
           for name in changed):
        raise ValueError("staging_resume_unreviewed_change")
    if git("diff", "--name-only", "-z", "HEAD"):
        raise ValueError("staging_resume_dirty_tracked_tree")


def origin(run: object, jobs: object, run_id: str) -> dict:
    """Admit only the terminal failed reviewed run at the sink-only boundary."""
    if (run_id != ORIGIN_RUN or not isinstance(run, dict) or type(run.get("id")) is not int
            or str(run["id"]) != run_id or type(run.get("run_attempt")) is not int
            or run["run_attempt"] != 1 or run.get("status") != "completed"
            or run.get("conclusion") != "failure" or run.get("event") != "workflow_dispatch"
            or run.get("head_branch") != BRANCH or run.get("head_sha") != ORIGIN_SHA
            or run.get("path") != ".github/workflows/ci.yml"
            or not isinstance(run.get("repository"), dict) or run["repository"].get("full_name") != REPO):
        raise ValueError("staging_resume_origin_unverified")
    listing = rows(jobs, "jobs")
    for name in required_jobs(listing) | SKIPPED | {SINK_JOB}:
        matches = [row for row in listing if row.get("name") == name]
        expected = "skipped" if name in SKIPPED else "failure" if name == SINK_JOB else "success"
        if (len(matches) != 1 or matches[0].get("status") != "completed"
                or matches[0].get("conclusion") != expected):
            raise ValueError("staging_resume_job_boundary_unverified")
    sink = next(row for row in listing if row["name"] == SINK_JOB)
    steps = sink.get("steps")
    matches = [row for row in steps if isinstance(row, dict) and row.get("name") == DEPLOY_STEP] if isinstance(steps, list) else []
    if (len(matches) != 1 or matches[0].get("status") != "completed"
            or matches[0].get("conclusion") != "success" or type(sink.get("id")) is not int
            or sink["id"] <= 0 or sink.get("run_id") != int(run_id) or sink.get("head_sha") != ORIGIN_SHA):
        raise ValueError("staging_resume_sink_submit_unverified")
    return sink


def sink_log(raw: bytes) -> str:
    """Extract one typed successful submit only; raw GitHub logs never leave here."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 8 * 1024 * 1024:
        raise ValueError("staging_resume_log_unverified")
    records = []
    for line in raw.splitlines():
        start = line.find(b'{')
        if start < 0:
            continue
        try:
            row = decode(line[start:])
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("operation") == "workers.deploy" and row.get("event") == "control_plane_end":
            records.append(row)
    expected = {"schema": "control-plane-span/v1", "event": "control_plane_end",
                "operation": "workers.deploy", "phase": "submit", "realm": "staging",
                "component": "trace_sink", "outcome": "success", "version": SINK_VERSION,
                "version_count": 1, "process_exit_code": 0, "source_sha": ORIGIN_SHA,
                "run_id": ORIGIN_RUN, "run_attempt": "1", "job": "staging-trace-sink"}
    if len(records) != 1 or any(records[0].get(key) != value or type(records[0].get(key)) is not type(value)
                                for key, value in expected.items()):
        raise ValueError("staging_resume_typed_submit_unverified")
    return records[0]["version"]


def predecessor(value: object) -> dict:
    """Require original absent resources and the exact legacy API capability pins."""
    if (not isinstance(value, dict) or set(value) != {"schema", "source_sha", "run_id", "scripts", "queues", "rollout", "old_usage_model"}
            or value.get("schema") != "staging-predecessor/v1" or value.get("source_sha") != ORIGIN_SHA
            or value.get("run_id") != ORIGIN_RUN or value.get("rollout") != "legacy"
            or value.get("old_usage_model") not in ("standard", "unbound")
            or not isinstance(value.get("scripts"), dict) or not isinstance(value.get("queues"), dict)):
        raise ValueError("staging_resume_predecessor_unverified")
    scripts = value["scripts"]
    if set(scripts) != {"amail-mail-staging", "amail-mail-maintenance-staging", "amail-inbound-staging", "amail-events-staging", "amail-trace-sink-staging"}:
        raise ValueError("staging_resume_predecessor_unverified")
    api = scripts["amail-mail-staging"]
    expected = {"present": True, "deployment": API_DEPLOYMENT, "version": API_VERSION,
                "handlers": ["fetch", "scheduled"], "crons": ["*/5 * * * *"], "capture_off": True,
                "usage_model": "standard"}
    if (not isinstance(api, dict) or api != expected
            or api.get("present") is not True or api.get("capture_off") is not True):
        raise ValueError("staging_resume_legacy_api_unverified")
    if any(scripts[name] != {"present": False} for name in ("amail-mail-maintenance-staging", "amail-trace-sink-staging")):
        raise ValueError("staging_resume_preexisting_resource")
    if value["queues"] != {name: {"present": False} for name in ("amail-trace-events-staging", "amail-trace-dlq-staging")}:
        raise ValueError("staging_resume_preexisting_resource")
    return value


def provision(value: object) -> None:
    """Accept exactly the two newly created distinct reviewed staging Queue IDs."""
    expected = [{"target": "staging", "queue_name": name, "queue_id": identity} for name, identity in
                (("amail-trace-events-staging", QUEUE), ("amail-trace-dlq-staging", DLQ))]
    if not isinstance(value, list) or len(value) != 2 or any(row not in expected for row in value) or value[0] == value[1]:
        raise ValueError("staging_resume_queue_ownership_unverified")


def artifact_value(listing: list[dict], name: str, filename: str) -> object:
    """Read one immutable named ZIP member without extraction or path aliases."""
    selected = artifact(listing, name, LIMIT * 2)
    raw = github(f"artifacts/{selected['id']}/zip", binary=True)
    admitted = members(raw, {filename}, LIMIT * 2, 1)
    if set(admitted) != {filename} or len(admitted[filename]) > LIMIT:
        raise ValueError("staging_resume_artifact_unverified")
    return decode(admitted[filename])


def recover(run_id: str) -> dict:
    """Resolve original ownership; never treat this receipt as a live graph check."""
    if run_id != ORIGIN_RUN:
        raise ValueError("staging_resume_run_unreviewed")
    current_sha = os.getenv("GITHUB_SHA", "")
    exact_tree(current_sha)
    sink = origin(github(f"runs/{run_id}"), github(f"runs/{run_id}/attempts/1/jobs?per_page=100"), run_id)
    listing = rows(github(f"runs/{run_id}/artifacts?per_page=100"), "artifacts")
    old = predecessor(artifact_value(listing, f"staging-rollout-predecessor-{run_id}", "staging-rollout-predecessor.json"))
    provision(artifact_value(listing, f"trace-queue-provision-staging-{run_id}-1", "trace-queue-provision-staging.json"))
    result = subprocess.run(["gh", "api", f"repos/{REPO}/actions/jobs/{sink['id']}/logs"],
                            capture_output=True, timeout=60, check=False)
    if result.returncode:
        raise ValueError("staging_resume_log_download_failed")
    version = sink_log(result.stdout)
    return {"origin_run": run_id, "source_sha": ORIGIN_SHA, "current_sha": current_sha,
            "predecessor": old, "queue": QUEUE, "dlq": DLQ, "sink_version": version}


def load_resume(run_id: str) -> dict:
    """Persist fresh provenance under repository scratch, not operator supplied JSON."""
    value = recover(run_id)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return value
