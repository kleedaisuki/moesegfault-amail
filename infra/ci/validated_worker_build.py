"""Admit a fully checked exact-main Worker artifact for isolated infrastructure use.

This is stronger than diagnostic fixture replay: full source CI must succeed on
the original compiled main SHA. A narrowly reviewed infrastructure-only change
may reuse it after successful exact-current source checks and unchanged build proof.
It does not admit Mail sending or general release promotion.
"""

import argparse
import base64
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


NON_BUILD_FILES = {
    ".github/workflows/native-tracing-canary.yml",
    "infra/ci/validated_worker_build.py", "infra/tests/test_validated_worker_build.py",
    "infra/deploy/native_tracing_experiment.py", "infra/tests/test_native_tracing_experiment.py",
    "infra/deploy/native_route_lifecycle.py", "infra/tests/test_native_route_lifecycle_contract.py",
}


def build_changes(paths: list[str]) -> list[str]:
    """Only reviewed experiment orchestration/docs may differ; tests/build inputs cannot."""
    return [path for path in paths if not (
        path in NON_BUILD_FILES or path == "README.md"
        or path.startswith(("docs/", ".agents/skills/")) and path.endswith(".md"))]


def unchanged_build(build_sha: str, checkout_sha: str) -> None:
    """Fetch original public coordinates with ephemeral credentials, then prove ancestry/input identity."""
    if not all(re.fullmatch(r"[0-9a-f]{40}", value) for value in (build_sha, checkout_sha)):
        raise ValueError("invalid_build_coordinate")
    env = os.environ.copy()
    if token := env.get("GH_TOKEN"):
        credential = base64.b64encode(("x-access-token:" + token).encode()).decode()
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
                   GIT_CONFIG_VALUE_0="AUTHORIZATION: basic " + credential)
    subprocess.run(["git", "fetch", "--no-tags", "--deepen=100", "origin", build_sha, checkout_sha], cwd=ROOT,
                   env=env, check=True, timeout=60)
    subprocess.run(["git", "merge-base", "--is-ancestor", build_sha, checkout_sha], cwd=ROOT,
                   check=True, timeout=30)
    result = subprocess.run(["git", "diff", "--name-only", "-z", build_sha, checkout_sha, "--"],
                            cwd=ROOT, capture_output=True, check=True, timeout=30)
    changed = build_changes(result.stdout.decode().split("\0")[:-1])
    if changed:
        raise ValueError("new_checked_build_required: " + ", ".join(changed))


def prepare(run_id: str) -> None:
    """Resolve fixed checked artifact bytes before injecting provider capabilities."""
    if (os.getenv("GITHUB_REF") != "refs/heads/main"
            or not re.fullmatch(r"[1-9][0-9]{0,19}", run_id)):
        raise ValueError("main_artifact_context_required")
    run = api(f"runs/{run_id}")
    jobs = api(f"runs/{run_id}/attempts/{run['run_attempt']}/jobs?per_page=100")
    artifacts = api(f"runs/{run_id}/artifacts?per_page=100")
    value = identity(run, jobs, artifacts, run.get("head_sha", ""))
    checkout_sha = os.environ["GITHUB_SHA"]
    if value["source_sha"] != checkout_sha:
        unchanged_build(value["source_sha"], checkout_sha)
    value.update(checkout_sha=checkout_sha, orchestration_run_id=os.environ["GITHUB_RUN_ID"])
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(value), encoding="utf-8")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"artifact_id={value['artifact_id']}\n")
    print(json.dumps({"event": "validated_worker_build_selected", **value}, sort_keys=True))


def restore() -> None:
    """Verify original compiler/source/run/file hashes, not an invented rebuilt identity."""
    value = json.loads(STATE.read_text(encoding="utf-8"))
    if value["checkout_sha"] != os.environ["GITHUB_SHA"]:
        raise ValueError("source_changed_before_artifact_restore")
    env = {**os.environ, "GITHUB_SHA": value["source_sha"], "GITHUB_RUN_ID": value["run_id"],
           "GITHUB_RUN_ATTEMPT": str(value["run_attempt"])}
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
