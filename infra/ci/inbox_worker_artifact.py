"""Admit exact-current-main full CI modules for the standalone staging inbox.

This consumer preserves the workflow's existing deployment identity. It never
borrows an ancestor, treats a green producer as full CI, or rebuilds absent bytes.
Original build identity is preserved alongside the distinct orchestration run.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import worker_artifact

ROOT = worker_artifact.ROOT
STATE = ROOT / ".temp/ci/inbox-worker-artifact.json"
REPO = "kleedaisuki/moesegfault-amail"
REQUIRED = {"Infrastructure probe unit tests", "CLI (ubuntu-latest)", "CLI (windows-latest)",
            "CLI (macos-latest)", "Astro release site", "Rust Worker (Wasm)",
            "Build and unit-check Rust Worker modules"}


LEGACY_NATIVE_JOBS = {f"Native workerd ({name})" for name in
                      ("core", "entry", "liveness", "accepted", "routing", "embedding", "diagnostics", "budget")}


def required_jobs(jobs: list[dict]) -> set[str]:
    """Require all historical matrix members when admitting an old producer run.

    Current producers execute runtime tests before artifact upload. Older runs
    delegated those tests; their immutable metadata must still prove every lane.
    """
    names = {row.get("name") for row in jobs}
    return REQUIRED | LEGACY_NATIVE_JOBS if names & LEGACY_NATIVE_JOBS else REQUIRED


def api(suffix: str):
    """Bound GitHub metadata reads without copying arbitrary API error bodies."""
    repository = os.environ["GITHUB_REPOSITORY"]
    result = subprocess.run(["gh", "api", f"repos/{repository}/actions/{suffix}"],
                            capture_output=True, text=True, timeout=30, check=False)
    if result.returncode or len(result.stdout) > 1_048_576:
        raise ValueError(f"github_metadata_read_failed: exit={result.returncode}")
    return json.loads(result.stdout)


def rows(value: object, key: str) -> list[dict]:
    """A bounded complete inventory is mandatory; no pagination/truncation inference."""
    if (not isinstance(value, dict) or not isinstance(value.get(key), list)
            or type(value.get("total_count")) is not int or value["total_count"] != len(value[key])
            or len(value[key]) > 100 or not all(isinstance(row, dict) for row in value[key])):
        raise ValueError("complete_source_inventory_required")
    return value[key]


def identity(run: object, jobs: object, artifacts: object, sha: str) -> dict:
    """Match exact source, repository, completed full gates and immutable producer ID."""
    if (not re.fullmatch(r"[0-9a-f]{40}", sha) or not isinstance(run, dict)
            or type(run.get("id")) is not int or run["id"] <= 0 or run.get("run_attempt") != 1
            or type(run.get("run_attempt")) is not int
            or run.get("path") != ".github/workflows/ci.yml" or run.get("status") != "completed"
            or run.get("conclusion") != "success" or run.get("head_branch") != "main"
            or run.get("head_sha") != sha or run.get("event") not in ("push", "workflow_dispatch")
            or not isinstance(run.get("repository"), dict) or run["repository"].get("full_name") != REPO):
        raise ValueError("successful_exact_main_source_required")
    listing = rows(jobs, "jobs")
    for name in required_jobs(listing):
        matches = [row for row in listing if row.get("name") == name]
        if (len(matches) != 1 or matches[0].get("status") != "completed"
                or matches[0].get("conclusion") != "success"):
            raise ValueError("complete_successful_source_gate_required")
    matches = [row for row in rows(artifacts, "artifacts")
               if row.get("name") == f"worker-native-modules-{sha}"]
    if (len(matches) != 1 or matches[0].get("expired") is not False
            or type(matches[0].get("id")) is not int or matches[0]["id"] <= 0):
        raise ValueError("unique_nonexpired_source_artifact_required")
    return {"source_sha": sha, "run_id": str(run["id"]), "run_attempt": 1,
            "artifact_id": matches[0]["id"]}


def select(run_id: str, sha: str) -> dict:
    """An optional explicit run preserves operator control; no input selects exact source only."""
    if run_id:
        if not re.fullmatch(r"[1-9][0-9]{0,19}", run_id):
            raise ValueError("source_run_id_invalid")
        candidates = [api(f"runs/{run_id}")]
    else:
        listing = api(f"workflows/ci.yml/runs?branch=main&head_sha={sha}&status=success&per_page=100")
        candidates = [row for row in rows(listing, "workflow_runs") if type(row.get("id")) is int and row["id"] > 0]
        candidates = sorted(candidates, key=lambda row: row["id"], reverse=True)
        candidates = candidates[:5]
    for run in candidates:
        if (not isinstance(run, dict) or type(run.get("id")) is not int
                or run.get("head_sha") != sha or run.get("run_attempt") != 1):
            continue
        try:
            value = identity(run, api(f"runs/{run['id']}/attempts/1/jobs?per_page=100"),
                             api(f"runs/{run['id']}/artifacts?per_page=100"), sha)
        except ValueError:
            if run_id:
                raise
            continue
        if run_id and value["run_id"] != run_id:
            raise ValueError("source_run_coordinate_mismatch")
        return value
    raise ValueError("full_exact_current_main_ci_required_no_ancestor_fallback")


def prepare(run_id: str) -> None:
    """Resolve trusted immutable producer bytes before any inbox/provider step."""
    sha = os.environ.get("GITHUB_SHA", "")
    if (os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("GITHUB_REF") != "refs/heads/main"
            or os.getenv("GITHUB_REPOSITORY") != REPO or not re.fullmatch(r"[0-9a-f]{40}", sha)
            or not re.fullmatch(r"[1-9][0-9]{0,19}", os.getenv("GITHUB_RUN_ID", ""))):
        raise ValueError("hosted_main_inbox_context_required")
    value = {**select(run_id, sha), "checkout_sha": sha,
             "orchestration_run_id": os.environ["GITHUB_RUN_ID"]}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as destination:
        destination.write(f"artifact_id={value['artifact_id']}\nrun_id={value['run_id']}\n")
    print(json.dumps({"event": "inbox_exact_source_artifact_selected", **value}, sort_keys=True))


def restore() -> None:
    """Restore the original production component trees under original run/compiler/hash identity."""
    value = json.loads(STATE.read_text(encoding="utf-8"))
    fields = {"source_sha", "run_id", "run_attempt", "artifact_id", "checkout_sha", "orchestration_run_id"}
    if (os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("GITHUB_REF") != "refs/heads/main"
            or not isinstance(value, dict) or set(value) != fields
            or value.get("checkout_sha") != os.environ["GITHUB_SHA"]
            or value.get("source_sha") != os.environ["GITHUB_SHA"]
            or value.get("orchestration_run_id") != os.environ["GITHUB_RUN_ID"]
            or not isinstance(value.get("run_id"), str) or not re.fullmatch(r"[1-9][0-9]{0,19}", value["run_id"])
            or type(value.get("run_attempt")) is not int or value["run_attempt"] != 1
            or type(value.get("artifact_id")) is not int or value["artifact_id"] <= 0):
        raise ValueError("inbox_artifact_identity_changed_before_restore")
    env = {**os.environ, "GITHUB_RUN_ID": value["run_id"], "GITHUB_RUN_ATTEMPT": str(value["run_attempt"])}
    subprocess.run([sys.executable, str(ROOT / "infra/ci/worker_artifact.py"), "restore"],
                   env=env, cwd=ROOT, check=True, timeout=60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "restore"))
    parser.add_argument("--source-run-id", default="")
    args = parser.parse_args()
    prepare(args.source_run_id) if args.operation == "prepare" else restore()
