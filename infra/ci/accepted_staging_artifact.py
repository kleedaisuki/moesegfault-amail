"""Promote unchanged, tested staging bytes without rebuilding or rewriting provenance.

A failed deployment does not invalidate successful source tests, but it is not
staging acceptance. Production additionally requires a separate successful real
semantic journey tied to the same original producer and exact runtime closure.
The original Worker manifest always retains its source/run/compiler identities.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

import worker_artifact as artifact

ROOT = artifact.ROOT
STATE = ROOT / ".temp/ci/accepted-staging-artifact.json"
ACCEPTANCE = ROOT / ".temp/ci/staging-acceptance/staging-semantic-acceptance.json"
REPO = "kleedaisuki/moesegfault-amail"
BRANCH = "codex/v0.3.1-semantic-consent"
REQUIRED = frozenset({"CLI (ubuntu-latest)", "CLI (windows-latest)", "CLI (macos-latest)",
                      "Astro release site", "Infrastructure probe unit tests", "Rust Worker (Wasm)",
                      "Build and unit-check Rust Worker modules", "OpenRouter 256D live contract",
                      "Assemble unpublished staging acceptance bundle"})
ACCEPTANCE_JOB = "Verify accepted staging semantic user journey"
CLOSURE = ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", ".cargo", "crates", "workers")
UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")


def github(path: str) -> dict[str, Any]:
    """Read bounded repository-owned GitHub metadata, never provider/error prose."""
    result = subprocess.run(["gh", "api", f"repos/{REPO}/actions/{path}"], cwd=ROOT,
                            capture_output=True, text=True, timeout=45, check=False)
    if result.returncode or len(result.stdout.encode()) > 1_048_576:
        raise ValueError("accepted_source_metadata_unavailable")
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise ValueError("accepted_source_metadata_invalid")
    return value


def rows(value: dict[str, Any], key: str) -> list[dict[str, Any]]:
    result = value.get(key)
    if (not isinstance(result, list) or type(value.get("total_count")) is not int
            or value["total_count"] != len(result) or len(result) > 100
            or not all(isinstance(row, dict) for row in result)):
        raise ValueError("accepted_source_inventory_incomplete")
    return result


def run_metadata(run_id: str) -> dict[str, Any]:
    if re.fullmatch(r"[1-9][0-9]{0,19}", run_id) is None:
        raise ValueError("accepted_source_run_invalid")
    value = github(f"runs/{run_id}")
    if (type(value.get("id")) is not int or str(value["id"]) != run_id
            or value.get("path") != ".github/workflows/ci.yml"
            or value.get("event") != "workflow_dispatch" or value.get("head_branch") != BRANCH
            or value.get("repository", {}).get("full_name") != REPO
            or value.get("status") != "completed" or value.get("run_attempt") != 1
            or type(value.get("run_attempt")) is not int
            or re.fullmatch(r"[0-9a-f]{40}", value.get("head_sha", "")) is None):
        raise ValueError("accepted_source_run_unverified")
    return value


def successful_jobs(run_id: str, required: frozenset[str]) -> None:
    listing = rows(github(f"runs/{run_id}/jobs?per_page=100"), "jobs")
    for name in required:
        found = [row for row in listing if row.get("name") == name]
        if (len(found) != 1 or found[0].get("status") != "completed"
                or found[0].get("conclusion") != "success"):
            raise ValueError("accepted_source_required_gate_failed")


def unique_artifact(run_id: str, sha: str, name: str) -> int:
    found = [row for row in rows(github(f"runs/{run_id}/artifacts?per_page=100"), "artifacts")
             if row.get("name") == name]
    if (len(found) != 1 or found[0].get("expired") is not False
            or type(found[0].get("id")) is not int or found[0]["id"] <= 0
            or found[0].get("workflow_run", {}).get("head_sha") != sha):
        raise ValueError("accepted_source_artifact_unverified")
    return found[0]["id"]


def producer(run_id: str) -> dict[str, Any]:
    """Source gates must all pass; a failed writer is explicitly not acceptance."""
    run = run_metadata(run_id)
    if run.get("conclusion") not in ("success", "failure"):
        raise ValueError("accepted_source_run_unverified")
    successful_jobs(run_id, REQUIRED)
    sha = run["head_sha"]
    return {"source_sha": sha, "run_id": run_id, "run_attempt": 1,
            "artifact_id": unique_artifact(run_id, sha, f"worker-native-modules-{sha}"),
            "cli_artifact_id": unique_artifact(run_id, sha, f"cli-candidate-v0.3.1-{run_id}")}


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=False, timeout=45)


def runtime_closure(source_sha: str, checkout_sha: str) -> None:
    """An accepted ancestor is reusable only when all runtime/build/config inputs match."""
    if any(re.fullmatch(r"[0-9a-f]{40}", sha) is None for sha in (source_sha, checkout_sha)):
        raise ValueError("accepted_source_revision_invalid")
    if (git("merge-base", "--is-ancestor", source_sha, checkout_sha).returncode
            or git("diff", "--quiet", source_sha, checkout_sha, "--", *CLOSURE).returncode
            or git("diff", "--quiet", "HEAD", "--", *CLOSURE).returncode
            or git("rev-parse", "HEAD").stdout.strip() != checkout_sha):
        raise ValueError("accepted_source_runtime_changed")


def acceptance(run_id: str, source: dict[str, Any], checkout_sha: str) -> dict[str, Any]:
    """A real successful staging journey is separate from successful source gates."""
    run = run_metadata(run_id)
    if run.get("conclusion") != "success":
        raise ValueError("accepted_staging_journey_required")
    successful_jobs(run_id, frozenset({ACCEPTANCE_JOB}))
    runtime_closure(source["source_sha"], checkout_sha)
    if (git("diff", "--quiet", source["source_sha"], run["head_sha"], "--", *CLOSURE).returncode
            or git("merge-base", "--is-ancestor", run["head_sha"], checkout_sha).returncode):
        raise ValueError("accepted_staging_journey_not_ancestor")
    return {"run_id": run_id, "source_sha": run["head_sha"],
            "artifact_id": unique_artifact(run_id, run["head_sha"], f"staging-semantic-acceptance-{run_id}")}


def context(purpose: str) -> dict[str, Any]:
    identity = artifact.context()
    if (os.getenv("GITHUB_REPOSITORY") != REPO or os.getenv("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or os.getenv("GITHUB_RUN_ATTEMPT") != "1"
            or os.getenv("AMAIL_ACCEPTED_ARTIFACT_PURPOSE") != purpose):
        raise ValueError("accepted_source_context_unverified")
    if purpose == "production":
        expected = {"GITHUB_REF": "refs/heads/main", "AMAIL_PRODUCTION_ENVIRONMENT": "production",
                    "AMAIL_PRODUCTION_CONFIRM": "RUN_PRODUCTION_V031",
                    "AMAIL_PRODUCTION_GRAPH_FREEZE": "FREEZE_PRODUCTION_GRAPH_WRITERS"}
    elif purpose == "staging-recovery":
        expected = {"GITHUB_REF": f"refs/heads/{BRANCH}",
                    "AMAIL_STAGING_CONFIRM": "RUN_STAGING_SEMANTIC_RECOVERY_V031"}
    else:
        raise ValueError("accepted_source_purpose_unreviewed")
    if any(os.getenv(key) != value for key, value in expected.items()):
        raise ValueError("accepted_source_context_unverified")
    return identity


def prepare(purpose: str, source_run: str, acceptance_run: str = "") -> None:
    identity = context(purpose)
    source = producer(source_run)
    runtime_closure(source["source_sha"], identity["source_sha"])
    journey = acceptance(acceptance_run, source, identity["source_sha"]) if purpose == "production" else None
    value = {"schema": "accepted-staging-artifact/v1", "purpose": purpose,
             "producer": source, "acceptance": journey, "orchestration": identity}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with STATE.open("x", encoding="utf-8") as file:
        json.dump(value, file, sort_keys=True)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"artifact_id={source['artifact_id']}\ncli_artifact_id={source['cli_artifact_id']}\n"
                     f"source_sha={source['source_sha']}\nsource_run_id={source['run_id']}\n")
        if journey is not None:
            output.write(f"acceptance_artifact_id={journey['artifact_id']}\nacceptance_run_id={journey['run_id']}\n")


def read_state() -> dict[str, Any]:
    if STATE.is_symlink() or STATE.stat().st_size > 16_384:
        raise ValueError("accepted_source_state_invalid")
    value = json.loads(STATE.read_text(encoding="utf-8"))
    if (not isinstance(value, dict)
            or set(value) != {"schema", "purpose", "producer", "acceptance", "orchestration"}
            or value.get("schema") != "accepted-staging-artifact/v1"
            or value.get("orchestration") != context(value.get("purpose", ""))):
        raise ValueError("accepted_source_state_invalid")
    source = value["producer"]
    if (not isinstance(source, dict)
            or set(source) != {"source_sha", "run_id", "run_attempt", "artifact_id", "cli_artifact_id"}
            or type(source.get("run_attempt")) is not int or source["run_attempt"] != 1
            or re.fullmatch(r"[1-9][0-9]{0,19}", source.get("run_id", "")) is None
            or any(type(source.get(key)) is not int or source[key] <= 0 for key in ("artifact_id", "cli_artifact_id"))):
        raise ValueError("accepted_source_state_invalid")
    runtime_closure(source["source_sha"], value["orchestration"]["source_sha"])
    if value["purpose"] == "production":
        verify_acceptance_receipt(value)
    return value


def verify_acceptance_receipt(state: dict[str, Any]) -> dict[str, Any]:
    journey, source = state["acceptance"], state["producer"]
    if (not isinstance(journey, dict) or set(journey) != {"run_id", "source_sha", "artifact_id"}
            or ACCEPTANCE.is_symlink() or ACCEPTANCE.stat().st_size > 16_384):
        raise ValueError("accepted_staging_receipt_invalid")
    value = json.loads(ACCEPTANCE.read_text(encoding="utf-8"))
    expected = {"schema": "staging-semantic-acceptance/v1", "source_run_id": source["run_id"],
                "source_sha": source["source_sha"], "run_id": journey["run_id"],
                "checkout_sha": journey["source_sha"]}
    if (not isinstance(value, dict) or set(value) != set(expected) | {"api_version", "maintenance_version", "sink_version"}
            or any(value.get(key) != item for key, item in expected.items())
            or any(not isinstance(value.get(key), str) or UUID.fullmatch(value[key]) is None
                   for key in ("api_version", "maintenance_version", "sink_version"))):
        raise ValueError("accepted_staging_receipt_invalid")
    return value


def restore() -> None:
    """Install original bytes under their actual original identity, never edit the manifest."""
    value = read_state()
    source = value["producer"]
    env = {**os.environ, "GITHUB_SHA": source["source_sha"], "GITHUB_RUN_ID": source["run_id"],
           "GITHUB_RUN_ATTEMPT": str(source["run_attempt"])}
    subprocess.run([os.sys.executable, str(ROOT / "infra/ci/worker_artifact.py"), "restore"],
                   env=env, cwd=ROOT, check=True, timeout=60)
    verify_installed()


def verify_installed() -> None:
    """Before each write, recheck current closure, original manifest and every installed byte."""
    value = read_state()
    source = value["producer"]
    path = artifact.FOLDER / "manifest.json"
    if artifact.FOLDER.is_symlink() or path.is_symlink() or path.stat().st_size > 262_144:
        raise ValueError("artifact_manifest_invalid")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    identity = {**value["orchestration"], "source_sha": source["source_sha"],
                "run_id": source["run_id"], "run_attempt": source["run_attempt"]}
    if (not isinstance(manifest, dict) or set(manifest) != set(identity) | {"files"}
            or any(type(manifest.get(key)) is not type(item) or manifest.get(key) != item for key, item in identity.items())):
        raise ValueError("artifact_provenance_mismatch")
    hashes = artifact.files(artifact.FOLDER)
    names = {path.relative_to(artifact.FOLDER).as_posix() for path in artifact.FOLDER.rglob("*") if path.is_file()}
    if (manifest["files"] != hashes or names != set(hashes) | {"manifest.json"}
            or artifact.files(ROOT) != hashes):
        raise ValueError("artifact_file_integrity_mismatch")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "restore"))
    parser.add_argument("--purpose", choices=("production", "staging-recovery"), default="production")
    parser.add_argument("--source-run-id", default="")
    parser.add_argument("--acceptance-run-id", default="")
    args = parser.parse_args()
    if args.operation == "prepare":
        prepare(args.purpose, args.source_run_id, args.acceptance_run_id)
    else:
        restore()


if __name__ == "__main__":
    main()
