"""Restore reviewed Windows candidate bytes for the existing hosted staging journey.

Admission reads one successful exact-source CI run and immutable artifact ID.
Extraction verifies the small candidate bundle and writes only its amail.exe under
repository .temp. It never creates a Release, selects production or sends mail.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import zipfile

import cli_candidate as candidate

ROOT = candidate.ROOT
BUNDLE = ROOT / ".temp/staging-cli-bundle"
BINARY = ROOT / ".temp/staging-cli/amail.exe"
ADMISSION = ROOT / ".temp/staging-cli-admission.json"
REPO = "kleedaisuki/moesegfault-amail"


def github(path: str) -> dict:
    """Read bounded GitHub JSON without copying token or error prose into logs."""
    result = subprocess.run(["gh", "api", f"repos/{REPO}/{path}"],
                            capture_output=True, text=True, timeout=60, check=False)
    if result.returncode or len(result.stdout.encode()) > 1_048_576:
        raise ValueError("candidate_github_unavailable")
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise ValueError("candidate_github_shape")
    return value


def admit(run_id: str) -> dict:
    """Admit only an exact successful same-SHA candidate producer, not ancestry."""
    if (os.getenv("GITHUB_ACTIONS") != "true"
            or not re.fullmatch(r"[1-9][0-9]{0,19}", run_id)):
        raise ValueError("candidate_hosted_context_required")
    run = github(f"actions/runs/{run_id}")
    if (str(run.get("id")) != run_id or run.get("status") != "completed"
            or run.get("conclusion") != "success" or run.get("head_sha") != os.getenv("GITHUB_SHA")
            or run.get("head_branch") != "codex/v0.2.0-billing"
            or run.get("path") != ".github/workflows/ci.yml"
            or run.get("event") != "workflow_dispatch"
            or type(run.get("run_attempt")) is not int or run["run_attempt"] < 1):
        raise ValueError("candidate_source_run_unverified")
    artifacts = github(f"actions/runs/{run_id}/artifacts?per_page=100")
    rows = artifacts.get("artifacts")
    if (not isinstance(rows, list) or type(artifacts.get("total_count")) is not int
            or artifacts["total_count"] != len(rows) or len(rows) > 100):
        raise ValueError("candidate_artifacts_incomplete")
    matches = [row for row in rows if isinstance(row, dict)
               and row.get("name") == f"cli-candidate-v0.2.0-{run_id}"]
    if (len(matches) != 1 or matches[0].get("expired") is not False
            or type(matches[0].get("id")) is not int or matches[0]["id"] < 1
            or matches[0].get("workflow_run", {}).get("head_sha") != run["head_sha"]):
        raise ValueError("candidate_artifact_unverified")
    info = {**candidate.context(), "run_id": run_id, "run_attempt": run["run_attempt"]}
    value = {"identity": info, "artifact_id": matches[0]["id"]}
    ADMISSION.parent.mkdir(exist_ok=True)
    candidate.write_json(ADMISSION, value)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"artifact_id={value['artifact_id']}\n")
    return value


def extract() -> None:
    """Verify every bundle checksum/provenance, then extract one exact executable."""
    if (ROOT / ".temp").is_symlink() or BUNDLE.is_symlink():
        raise ValueError("candidate_extract_path_unverified")
    admission = json.loads(ADMISSION.read_text(encoding="utf-8"))
    info = admission["identity"]
    current = candidate.context()
    if any(info.get(key) != value for key, value in current.items() if key not in ("run_id", "run_attempt")):
        raise ValueError("candidate_checkout_changed")
    manifest = json.loads((BUNDLE / "candidate.json").read_text(encoding="utf-8"))
    expected_files = {candidate.archive_name(info["version"], target) for target in candidate.TARGETS}
    expected_files.update(f"{target}.json" for target in candidate.TARGETS)
    expected_files.add(f"amail-agent-skill-v{info['version']}-candidate.zip")
    hashes = {name: candidate.digest(BUNDLE / name) for name in expected_files}
    if manifest != {**info, "targets": list(candidate.TARGETS), "files": hashes}:
        raise ValueError("candidate_manifest_unverified")
    expected_files.update(("candidate.json", "SHA256SUMS"))
    if {path.name for path in BUNDLE.iterdir()} != expected_files:
        raise ValueError("candidate_bundle_file_set_unverified")
    checksums = {}
    for line in (BUNDLE / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if match is None or match[2] in checksums:
            raise ValueError("candidate_checksums_unverified")
        checksums[match[2]] = match[1]
    expected_hashes = {name: candidate.digest(BUNDLE / name) for name in expected_files - {"SHA256SUMS"}}
    if checksums != expected_hashes:
        raise ValueError("candidate_checksums_unverified")
    for target in candidate.TARGETS:
        archive = candidate.archive_name(info["version"], target)
        producer = json.loads((BUNDLE / f"{target}.json").read_text(encoding="utf-8"))
        if producer != {**info, "target": target, "archive": archive, "sha256": hashes[archive]}:
            raise ValueError("candidate_producer_unverified")
    archive = candidate.archive_name(info["version"], "x86_64-pc-windows-msvc")
    with zipfile.ZipFile(BUNDLE / archive) as zipped:
        entries = zipped.infolist()
        verify_windows_entries(entries)
        if BINARY.parent.is_symlink() or BINARY.is_symlink():
            raise ValueError("candidate_extract_path_unverified")
        BINARY.parent.mkdir(exist_ok=True)
        BINARY.write_bytes(zipped.read("amail.exe"))
    actual = subprocess.check_output([str(BINARY), "--version"], text=True, timeout=30).strip()
    if actual != f"amail {info['version']}":
        raise ValueError("candidate_binary_version_unverified")


def verify_windows_entries(entries: list[zipfile.ZipInfo]) -> None:
    """Require the small produced Windows payload: unencrypted regular files only."""
    if (len(entries) != 3 or {entry.filename for entry in entries} != {"amail.exe", "README.md", "LICENSE"}
            or any(entry.is_dir() or entry.file_size > 256 * 1024 * 1024
                   or entry.flag_bits & 1
                   or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG)
                   for entry in entries)):
        raise ValueError("candidate_windows_archive_unverified")


def main() -> int:
    """Expose fixed admission/extraction phases; no fallback rebuild is performed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("admit", "extract"))
    parser.add_argument("--run", default="")
    args = parser.parse_args()
    try:
        admit(args.run) if args.phase == "admit" else extract()
    except Exception:
        print("staging_cli_candidate=UNVERIFIED")
        return 1
    print(f"staging_cli_candidate={args.phase}_verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
