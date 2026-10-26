"""Reuse one tested Mail backend build without rebuilding unrelated components."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any

import accepted_staging_artifact as accepted
import worker_artifact as artifact

ROOT = artifact.ROOT
FOLDER = ROOT / ".temp/ci/mail-backend"
ADMISSION = ROOT / ".temp/ci/mail-backend-admission.json"
STAGING_RECEIPT = ROOT / ".temp/ci/mail-backend-staging/semantic-reuse-staging.json"
ACCEPTANCE = ROOT / ".temp/ci/mail-backend-staging/semantic-reuse-acceptance.json"
TREES = ("crates/mail-worker/build",)
ENTRIES = ("crates/mail-worker/entry/api.mjs", "crates/mail-worker/entry/maintenance.mjs")
BRANCH = "codex/semantic-index-reuse"
BUILD_JOB = "Semantic reuse backend build"
STAGING_JOB = "Semantic reuse staging admission"
PARTIAL_RUN = "40203420616"
PARTIAL_SOURCE = "f3f13e4776871b7ab4232e113bc62a592b63d0f3"


def identity() -> dict[str, Any]:
    return {**artifact.context(), "schema": "mail-backend-artifact/v1"}


def context(realm: str) -> None:
    confirmation = ("RESTORE_SEMANTIC_REUSE_STAGING_INGRESS" if realm == "staging"
                    and os.getenv("AMAIL_STAGING_INGRESS_RESTORE") == "true"
                    else "RUN_SEMANTIC_REUSE_" + realm.upper())
    expected = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": accepted.REPO,
                "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_RUN_ATTEMPT": "1",
                "GITHUB_REF": "refs/heads/" + (BRANCH if realm == "staging" else "main"),
                "AMAIL_BACKEND_HOTFIX": realm,
                "AMAIL_BACKEND_CONFIRM": confirmation}
    if (realm not in ("staging", "production")
            or any(os.getenv(key) != value for key, value in expected.items())
            or realm == "production" and os.getenv("AMAIL_PRODUCTION_GRAPH_FREEZE") != "FREEZE_PRODUCTION_GRAPH_WRITERS"):
        raise ValueError("mail_backend_context_unverified")


def hashes(base: Path) -> dict[str, str]:
    return artifact.files(base, trees=TREES, entries=ENTRIES)


def metadata(path: Path) -> dict[str, Any]:
    if path.is_symlink() or path.stat().st_size > 16_384:
        raise ValueError("mail_backend_metadata_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("mail_backend_metadata_invalid")
    return value


def create() -> None:
    value = {**identity(), "files": hashes(ROOT)}
    FOLDER.mkdir(parents=True, exist_ok=False)
    for name in value["files"]:
        target = FOLDER / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    (FOLDER / "manifest.json").write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def build_source(run_id: str, *, partial: bool = False) -> dict[str, Any]:
    if re.fullmatch(r"[1-9][0-9]{0,19}", run_id) is None:
        raise ValueError("mail_backend_run_invalid")
    value = accepted.github(f"runs/{run_id}")
    if (str(value.get("id")) != run_id or value.get("path") != ".github/workflows/ci.yml"
            or value.get("event") != "workflow_dispatch" or value.get("head_branch") != BRANCH
            or value.get("repository", {}).get("full_name") != accepted.REPO
            or value.get("status") != "completed" or value.get("conclusion") != ("failure" if partial else "success")
            or type(value.get("run_attempt")) is not int or value["run_attempt"] != 1
            or re.fullmatch(r"[0-9a-f]{40}", value.get("head_sha", "")) is None):
        raise ValueError("mail_backend_source_unverified")
    if partial and (run_id != PARTIAL_RUN or value["head_sha"] != PARTIAL_SOURCE):
        raise ValueError("mail_backend_partial_unreviewed")
    accepted.successful_jobs(run_id, frozenset({BUILD_JOB}))
    sha = value["head_sha"]
    return {"source_sha": sha, "run_id": run_id, "run_attempt": 1,
            "artifact_id": accepted.unique_artifact(run_id, sha, f"mail-backend-{sha}")}


def producer(run_id: str, acceptance_run: str = "") -> dict[str, Any]:
    """Actual staging success may finish the one fixed, tested partial build."""
    original = build_source(run_id, partial=run_id == PARTIAL_RUN)
    staging_run = acceptance_run or run_id
    if re.fullmatch(r"[1-9][0-9]{0,19}", staging_run) is None:
        raise ValueError("mail_backend_run_invalid")
    value = accepted.github(f"runs/{staging_run}")
    if (str(value.get("id")) != staging_run or value.get("status") != "completed" or value.get("conclusion") != "success"
            or value.get("head_branch") != BRANCH or value.get("event") != "workflow_dispatch"
            or value.get("path") != ".github/workflows/ci.yml"
            or value.get("repository", {}).get("full_name") != accepted.REPO
            or value.get("run_attempt") != 1):
        raise ValueError("mail_backend_source_unverified")
    accepted.successful_jobs(staging_run, frozenset({STAGING_JOB, "Semantic reuse live journey"}))
    sha = value["head_sha"]
    if (accepted.git("merge-base", "--is-ancestor", original["source_sha"], sha).returncode
            or accepted.git("diff", "--quiet", original["source_sha"], sha, "--", *accepted.CLOSURE).returncode):
        raise ValueError("mail_backend_runtime_changed")
    return {**original, "staging_run_id": staging_run, "staging_source_sha": sha,
            "receipt_id": accepted.unique_artifact(staging_run, sha, f"semantic-reuse-staging-{staging_run}"),
            "acceptance_id": accepted.unique_artifact(staging_run, sha, f"semantic-reuse-acceptance-{staging_run}")}


def admit(run_id: str, acceptance_run: str = "", *, resume: bool = False) -> None:
    context("staging" if resume else "production")
    original = build_source(run_id, partial=True) if resume else producer(run_id, acceptance_run)
    accepted.runtime_closure(original["source_sha"], identity()["source_sha"])
    ADMISSION.parent.mkdir(parents=True, exist_ok=True)
    ADMISSION.write_text(json.dumps({"producer": original, "orchestration": identity()}, sort_keys=True), encoding="utf-8")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write("".join(f"{key}={original[key]}\n" for key in
                             ("artifact_id", "run_id", "receipt_id", "acceptance_id", "staging_run_id") if key in original))


def original_identity() -> dict[str, Any]:
    current = identity()
    if os.getenv("AMAIL_BACKEND_HOTFIX") == "staging" and not ADMISSION.exists():
        context("staging")
        return current
    realm = os.environ.get("AMAIL_BACKEND_HOTFIX", "")
    context(realm)
    if ADMISSION.is_symlink() or ADMISSION.stat().st_size > 16_384:
        raise ValueError("mail_backend_admission_invalid")
    value = metadata(ADMISSION)
    if value.get("orchestration") != current:
        raise ValueError("mail_backend_admission_invalid")
    original = value["producer"]
    accepted.runtime_closure(original["source_sha"], current["source_sha"])
    if realm == "staging":
        if original.get("run_id") != PARTIAL_RUN or original.get("source_sha") != PARTIAL_SOURCE:
            raise ValueError("mail_backend_partial_unreviewed")
        return {**current, **{key: original[key] for key in ("source_sha", "run_id", "run_attempt")}}
    receipt = metadata(STAGING_RECEIPT)
    if (receipt.get("schema") != "semantic-index-reuse/v1" or receipt.get("realm") != "staging"
            or receipt.get("source_sha") != original["staging_source_sha"]
            or receipt.get("run_id") != original["staging_run_id"] or receipt.get("migration") != 19):
        raise ValueError("mail_backend_staging_receipt_invalid")
    check = metadata(ACCEPTANCE)
    core = {key: receipt[key] for key in ("realm", "run_id", "source_sha", "api_version", "maintenance_version", "sink_version")}
    if check != {**core, "schema": "semantic-index-reuse-acceptance/v1", "cli_release": "v0.3.1"}:
        raise ValueError("mail_backend_staging_acceptance_invalid")
    return {**current, **{key: original[key] for key in ("source_sha", "run_id", "run_attempt")}}


def verified() -> dict[str, str]:
    manifest = FOLDER / "manifest.json"
    if FOLDER.is_symlink() or manifest.is_symlink() or manifest.stat().st_size > 262_144:
        raise ValueError("mail_backend_manifest_invalid")
    value = json.loads(manifest.read_text(encoding="utf-8"))
    expected = original_identity()
    files = hashes(FOLDER)
    names = {path.relative_to(FOLDER).as_posix() for path in FOLDER.rglob("*") if path.is_file()}
    if (set(value) != set(expected) | {"files"}
            or any(type(value.get(key)) is not type(item) or value.get(key) != item for key, item in expected.items())
            or value["files"] != files or names != set(files) | {"manifest.json"}):
        raise ValueError("mail_backend_integrity_unverified")
    return files


def restore() -> None:
    files = verified()
    if any((ROOT / name).exists() for name in TREES):
        raise ValueError("mail_backend_existing_build_refused")
    for name in ENTRIES:
        if hashes_entry(ROOT / name) != files[name]:
            raise ValueError("mail_backend_entry_changed")
    for name in files:
        if name not in ENTRIES:
            target = ROOT / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(FOLDER / name, target)
    require()


def hashes_entry(path: Path) -> str:
    import hashlib
    if path.is_symlink() or not path.is_file():
        raise ValueError("mail_backend_entry_changed")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require() -> None:
    if verified() != hashes(ROOT):
        raise ValueError("mail_backend_installed_bytes_changed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("create", "admit", "admit-resume", "restore"))
    parser.add_argument("--source-run", default="")
    parser.add_argument("--acceptance-run", default="")
    args = parser.parse_args()
    if args.mode in ("admit", "admit-resume"):
        admit(args.source_run, args.acceptance_run, resume=args.mode == "admit-resume")
    else:
        {"create": create, "restore": restore}[args.mode]()
    print(f"mail_backend_artifact={args.mode}_verified")


if __name__ == "__main__":
    main()
