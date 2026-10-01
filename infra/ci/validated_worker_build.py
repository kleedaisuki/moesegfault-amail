"""Admit a fully checked exact-main Worker artifact for isolated infrastructure use.

This is stronger than diagnostic fixture replay: full source CI must succeed on
this exact main SHA. It does not admit Mail sending or general release promotion.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from native_fixture import api
import worker_artifact

ROOT = worker_artifact.ROOT
STATE = ROOT / ".temp/ci/validated-worker-build.json"
REQUIRED = {"Infrastructure probe unit tests", "CLI (ubuntu-latest)", "CLI (windows-latest)",
            "CLI (macos-latest)", "Astro release site", "Rust Worker (Wasm)",
            "Build and unit-check Rust Worker modules"}


def identity(run: dict, jobs: dict, artifacts: dict, sha: str) -> dict:
    """Whole-run success and exact source are necessary, not just one green producer."""
    if (run.get("path") != ".github/workflows/ci.yml" or run.get("status") != "completed"
            or run.get("conclusion") != "success" or run.get("head_branch") != "main"
            or run.get("head_sha") != sha or run.get("event") not in ("push", "workflow_dispatch")):
        raise ValueError("successful_exact_main_source_run_required")
    rows = jobs.get("jobs", [])
    if jobs.get("total_count") != len(rows):
        raise ValueError("complete_source_job_inventory_required")
    for name in REQUIRED:
        matches = [row for row in rows if row.get("name") == name]
        if len(matches) != 1 or matches[0].get("conclusion") != "success":
            raise ValueError(f"required_source_check_missing_or_failed: {name}")
    rows = artifacts.get("artifacts", [])
    if artifacts.get("total_count") != len(rows):
        raise ValueError("complete_source_artifact_inventory_required")
    matches = [row for row in rows if row.get("name") == f"worker-native-modules-{sha}" and not row.get("expired")]
    if len(matches) != 1 or type(matches[0].get("id")) is not int:
        raise ValueError("unique_exact_source_artifact_required")
    return {"source_sha": sha, "run_id": str(run["id"]), "run_attempt": run["run_attempt"],
            "artifact_id": matches[0]["id"]}


def prepare(run_id: str) -> None:
    """Resolve the fixed artifact ID before any provider capability is injected."""
    if (os.getenv("GITHUB_REF") != "refs/heads/main"
            or not re.fullmatch(r"[1-9][0-9]{0,19}", run_id)):
        raise ValueError("exact_main_artifact_context_required")
    run = api(f"runs/{run_id}")
    jobs = api(f"runs/{run_id}/attempts/{run['run_attempt']}/jobs?per_page=100")
    artifacts = api(f"runs/{run_id}/artifacts?per_page=100")
    value = identity(run, jobs, artifacts, os.environ["GITHUB_SHA"])
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(value), encoding="utf-8")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"artifact_id={value['artifact_id']}\n")
    print(json.dumps({"event": "validated_worker_build_selected", **value}, sort_keys=True))


def restore() -> None:
    """Validate original compiler/source/run/file hashes; never rebuild silently."""
    value = json.loads(STATE.read_text(encoding="utf-8"))
    if value["source_sha"] != os.environ["GITHUB_SHA"]:
        raise ValueError("source_changed_before_artifact_restore")
    env = {**os.environ, "GITHUB_RUN_ID": value["run_id"], "GITHUB_RUN_ATTEMPT": str(value["run_attempt"])}
    subprocess.run([sys.executable, str(ROOT / "infra/ci/worker_artifact.py"), "restore"],
                   env=env, cwd=ROOT, check=True, timeout=60)


def main() -> None:
    """Hosted artifact admission only; no provider or mailbox operation."""
    if os.getenv("GITHUB_ACTIONS") != "true":
        raise SystemExit("Hosted artifact context required.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "restore"))
    parser.add_argument("--source-run-id", default="")
    args = parser.parse_args()
    prepare(args.source_run_id) if args.operation == "prepare" else restore()


if __name__ == "__main__":
    main()
