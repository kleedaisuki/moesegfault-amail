"""Replay one hosted native fixture against a verified earlier public build.

Diagnostic lane only: this never qualifies source CI, deployment or a release.
Compile-affecting/unknown changes require a new normal CI build. Test fixtures
can change independently, so an SDK-shape investigation need not rebuild Wasm.
"""

import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import native_suite
import worker_artifact

ROOT = worker_artifact.ROOT
IDENTITY = ROOT / ".temp/ci/native-fixture-build.json"
REPLAY_FILES = {".github/workflows/native-fixture.yml", "infra/ci/native_fixture.py",
                "infra/tests/test_native_fixture.py"}


def compile_changes(paths: list[str]) -> list[str]:
    """Allow diagnostic fixtures/docs only; unknown compiler inputs fail closed."""
    return [path for path in paths if not (
        path in REPLAY_FILES or path == "README.md"
        or path.startswith(("docs/", ".agents/skills/")) and path.endswith(".md")
        or path.startswith("infra/tests/worker-boundary/") and path.endswith(".mjs"))]


def fixture(name: str) -> Path:
    """Select one already assigned native test, never arbitrary Node flags/paths."""
    owned = {name for suite in native_suite.SUITES for name in native_suite.command(suite)[2:]}
    if name not in owned or not re.fullmatch(r"[a-z0-9-]+\.test\.mjs", name):
        raise ValueError("fixture_not_owned")
    return native_suite.BOUNDARY / name


def api(suffix: str):
    """Bound GitHub metadata reads; never print arbitrary API error responses."""
    repository = os.environ["GITHUB_REPOSITORY"]
    result = subprocess.run(["gh", "api", f"repos/{repository}/actions/{suffix}"],
                            capture_output=True, text=True, timeout=30, check=False)
    if result.returncode or len(result.stdout) > 1_048_576:
        raise ValueError(f"github_metadata_read_failed: exit={result.returncode}")
    return json.loads(result.stdout)


def prepare(run_id: str, name: str) -> None:
    """Identify one successful producer artifact; whole CI may have failed fixtures."""
    fixture(name)
    if not re.fullmatch(r"[1-9][0-9]{0,19}", run_id):
        raise ValueError("build_run_id_invalid")
    run = api(f"runs/{run_id}")
    if run.get("path") != ".github/workflows/ci.yml" or run.get("status") != "completed":
        raise ValueError("completed_source_workflow_required")
    jobs = api(f"runs/{run_id}/attempts/{run['run_attempt']}/jobs?per_page=100")
    if jobs.get("total_count") != len(jobs.get("jobs", [])):
        raise ValueError("complete_job_inventory_required")
    producers = [job for job in jobs.get("jobs", [])
                 if job.get("name") == "Build and unit-check Rust Worker modules"]
    if len(producers) != 1 or producers[0].get("conclusion") != "success":
        raise ValueError("successful_build_producer_required")
    listing = api(f"runs/{run_id}/artifacts?per_page=100")
    if listing.get("total_count") != len(listing.get("artifacts", [])):
        raise ValueError("complete_artifact_inventory_required")
    artifacts = [item for item in listing.get("artifacts", [])
                 if re.fullmatch(r"worker-native-modules-[0-9a-f]{40}", item.get("name", ""))
                 and not item.get("expired")]
    if len(artifacts) != 1 or type(artifacts[0].get("id")) is not int:
        raise ValueError("unique_live_build_artifact_required")
    item = artifacts[0]
    sha = item["name"].removeprefix("worker-native-modules-")
    IDENTITY.parent.mkdir(parents=True, exist_ok=True)
    identity = {"source_sha": sha, "run_id": run_id, "run_attempt": run["run_attempt"],
                "artifact_id": item["id"]}
    IDENTITY.write_text(json.dumps(identity), encoding="utf-8")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"artifact_id={item['id']}\n")
    print(json.dumps({"event": "native_fixture_build_selected", **identity, "diagnostic_only": True}))


def restore() -> None:
    """Prove no compilation input changed before restoring original run-bound bytes."""
    identity = json.loads(IDENTITY.read_text(encoding="utf-8"))
    build_sha = identity["source_sha"]
    fetch_env = os.environ.copy()
    token = fetch_env.get("GH_TOKEN")
    if token:
        # Ephemeral child environment, never command arguments or persisted Git config.
        credential = base64.b64encode(("x-access-token:" + token).encode()).decode()
        fetch_env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
                         GIT_CONFIG_VALUE_0="AUTHORIZATION: basic " + credential)
    subprocess.run(["git", "fetch", "--no-tags", "origin", build_sha], cwd=ROOT,
                   env=fetch_env, check=True, timeout=60)
    result = subprocess.run(["git", "diff", "--name-only", "-z", build_sha, "HEAD", "--"],
                            cwd=ROOT, capture_output=True, timeout=30, check=True)
    changed = compile_changes(result.stdout.decode("utf-8").split("\0")[:-1])
    if changed:
        raise ValueError("new_build_required: " + ", ".join(changed))
    # Keep the strict artifact helper unchanged; these are its original coordinates,
    # not a claim that the old build ran in this diagnostic workflow.
    env = {**os.environ, "GITHUB_SHA": build_sha, "GITHUB_RUN_ID": identity["run_id"],
           "GITHUB_RUN_ATTEMPT": str(identity["run_attempt"])}
    subprocess.run([sys.executable, str(ROOT / "infra/ci/worker_artifact.py"), "restore"],
                   cwd=ROOT, env=env, check=True, timeout=60)
    print(json.dumps({"event": "native_fixture_build_verified", **identity,
                      "fixture_source_sha": os.environ["GITHUB_SHA"], "diagnostic_only": True}))


def execute(name: str) -> None:
    """Run every test in the selected fixture; missing/skipped results are failures."""
    path = fixture(name)
    result = subprocess.run(["node", "--test", path.name], cwd=path.parent,
                            capture_output=True, text=True, timeout=300, check=False)
    print(result.stdout, end="")
    print(result.stderr, end="")
    counts = native_suite.counts(result.stdout, 1)
    if result.returncode:
        raise ValueError(f"fixture_failed: exit={result.returncode}")
    print(json.dumps({"event": "native_fixture_passed", "fixture": name, **counts,
                      "fixture_source_sha": os.environ["GITHUB_SHA"], "diagnostic_only": True}))


def main() -> None:
    """Hosted manual diagnostics only; no Rust compiler, provider secret or deploy."""
    if os.getenv("GITHUB_ACTIONS") != "true":
        raise SystemExit("Native tests belong on GitHub-hosted runners.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "restore", "execute"))
    parser.add_argument("--build-run-id", default="")
    parser.add_argument("--fixture", default="")
    args = parser.parse_args()
    if args.operation == "prepare":
        prepare(args.build_run_id, args.fixture)
    elif args.operation == "restore":
        restore()
    else:
        execute(args.fixture)


if __name__ == "__main__":
    main()
