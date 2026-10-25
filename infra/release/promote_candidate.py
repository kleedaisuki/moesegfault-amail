"""Package already-tested native executables without rebuilding or repeating tests.

The release archive is newly assembled and attested by the tagged workflow. Its
embedded provenance identifies the original native producer separately; neither
the candidate manifest nor executable bytes are relabelled as a new build.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tarfile
import tomllib
from typing import Any
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
import cli_candidate as candidate

PLATFORMS: tuple[tuple[str, str], ...] = (
    ("ubuntu-latest", "x86_64-unknown-linux-gnu"),
    ("ubuntu-24.04-arm", "aarch64-unknown-linux-gnu"),
    ("windows-latest", "x86_64-pc-windows-msvc"),
    ("macos-latest", "aarch64-apple-darwin"),
    ("macos-15-intel", "x86_64-apple-darwin"),
)
FOLDER = ROOT / ".temp/release-candidate"
ADMISSION = ROOT / ".temp/release-candidate-admission.json"
LIMIT = 128 * 1024 * 1024


def json_object(path: Path) -> dict[str, Any]:
    """Read one bounded public metadata object, never a linked path."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16_384:
        raise ValueError("release_candidate_metadata_unverified")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("release_candidate_metadata_unverified")
    return value


def record(tag: str) -> dict[str, Any] | None:
    """Only the explicitly recorded version reuses a tested native candidate."""
    if re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag) is None:
        raise ValueError("release_candidate_tag_unverified")
    path = ROOT / "infra/release/accepted-candidate.json"
    if not path.exists():
        return None
    value = json_object(path)
    if value.get("version") != tag[1:]:
        return None
    if (set(value) != {"schema", "version", "source_run", "source_sha", "staging_acceptance_run"}
            or value["schema"] != "amail-accepted-candidate/v1"
            or re.fullmatch(r"[0-9a-f]{40}", value.get("source_sha", "")) is None
            or any(not isinstance(value.get(key), str)
                   or re.fullmatch(r"[1-9][0-9]{0,19}", value[key]) is None
                   for key in ("source_run", "staging_acceptance_run"))):
        raise ValueError("release_candidate_record_unverified")
    return value


def matrix(reused: bool) -> dict[str, list[dict[str, str]]]:
    """Only previously unbuilt target platforms need a new native build."""
    return {"include": [{"os": system, "target": target} for system, target in PLATFORMS
                        if not reused or target not in candidate.TARGETS]}


def outputs(values: dict[str, str]) -> None:
    """Export only fixed public identities to GitHub Actions."""
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        for name, value in values.items():
            output.write(f"{name}={value}\n")


def admit(tag: str) -> dict[str, Any] | None:
    """Bind native reuse to accepted source gates and successful deployed acceptance."""
    value = record(tag)
    if value is None:
        outputs({"reuse_candidate": "false", "build_matrix": json.dumps(matrix(False))})
        return None
    import accepted_staging_artifact as accepted

    sha = os.environ.get("GITHUB_SHA", "")
    producer = accepted.producer(value["source_run"])
    if producer["source_sha"] != value["source_sha"]:
        raise ValueError("release_candidate_producer_unverified")
    accepted.runtime_closure(value["source_sha"], sha)
    journey = accepted.acceptance(value["staging_acceptance_run"], producer, sha)
    admission = {"record": value, "producer": producer,
                 "acceptance": journey, "release_sha": sha}
    ADMISSION.parent.mkdir(exist_ok=True)
    ADMISSION.write_text(json.dumps(admission, sort_keys=True) + "\n", encoding="utf-8")
    outputs({"reuse_candidate": "true", "build_matrix": json.dumps(matrix(True)),
             "source_run": value["source_run"], "cli_artifact_id": str(producer["cli_artifact_id"]),
             "acceptance_run": value["staging_acceptance_run"],
             "acceptance_artifact_id": str(journey["artifact_id"])})
    return admission


def verify_bundle(folder: Path, admission: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Verify the original complete native candidate file set and every byte."""
    value, producer = admission["record"], admission["producer"]
    with (ROOT / "rust-toolchain.toml").open("rb") as file:
        rust = tomllib.load(file)["toolchain"]["channel"]
    identity = {"schema": "amail-cli-candidate/v1", "version": value["version"],
                "source_sha": value["source_sha"], "run_id": value["source_run"],
                "run_attempt": producer["run_attempt"], "rust": rust,
                "publication": "unpublished-candidate"}
    names = {candidate.archive_name(value["version"], target) for target in candidate.TARGETS}
    names.update(f"{target}.json" for target in candidate.TARGETS)
    names.add(f"amail-agent-skill-v{value['version']}-candidate.zip")
    if (folder.is_symlink() or not folder.is_dir()
            or {path.name for path in folder.iterdir()} != names | {"candidate.json", "SHA256SUMS"}):
        raise ValueError("release_candidate_files_unverified")
    hashes = {name: candidate.digest(folder / name) for name in names}
    manifest = json_object(folder / "candidate.json")
    if manifest != {**identity, "targets": list(candidate.TARGETS), "files": hashes}:
        raise ValueError("release_candidate_manifest_unverified")
    checksums: dict[str, str] = {}
    for line in (folder / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if match is None or match[2] in checksums:
            raise ValueError("release_candidate_checksums_unverified")
        checksums[match[2]] = match[1]
    expected = {name: candidate.digest(folder / name) for name in names | {"candidate.json"}}
    if checksums != expected:
        raise ValueError("release_candidate_checksums_unverified")
    for target in candidate.TARGETS:
        name = candidate.archive_name(value["version"], target)
        metadata = json_object(folder / f"{target}.json")
        if metadata != {**identity, "target": target, "archive": name, "sha256": hashes[name]}:
            raise ValueError("release_candidate_native_producer_unverified")
    return identity, hashes


def executable(path: Path, target: str) -> bytes:
    """Read one bounded regular executable; never extract candidate paths to disk."""
    binary = "amail.exe" if "windows" in target else "amail"
    expected = {binary, "README.md", "LICENSE"}
    if "windows" in target:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if (len(entries) != 3 or {entry.filename for entry in entries} != expected
                    or any(entry.is_dir() or entry.file_size > LIMIT or entry.flag_bits & 1
                           or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG)
                           for entry in entries)):
                raise ValueError("release_candidate_archive_unverified")
            return archive.read(binary)
    with tarfile.open(path, "r:gz") as archive:
        entries = archive.getmembers()
        if (len(entries) != 3 or {entry.name for entry in entries} != expected
                or any(not entry.isfile() or entry.size > LIMIT for entry in entries)
                or archive.getmember(binary).mode & 0o111 == 0):
            raise ValueError("release_candidate_archive_unverified")
        stream = archive.extractfile(binary)
        if stream is None:
            raise ValueError("release_candidate_archive_unverified")
        return stream.read(LIMIT + 1)


def package(tag: str, output: Path) -> None:
    """Repackage tested executables with current public docs and honest provenance."""
    admission = json_object(ADMISSION)
    if (admission["record"] != record(tag) or admission["release_sha"] != os.environ.get("GITHUB_SHA")):
        raise ValueError("release_candidate_admission_changed")
    import accepted_staging_artifact as accepted

    accepted.runtime_closure(admission["record"]["source_sha"], admission["release_sha"])
    accepted.verify_acceptance_receipt(admission)
    _, hashes = verify_bundle(FOLDER, admission)
    if output.exists():
        raise ValueError("release_candidate_output_exists")
    output.mkdir(parents=True)
    for target in candidate.TARGETS:
        original = candidate.archive_name(admission["record"]["version"], target)
        content = executable(FOLDER / original, target)
        if not content or len(content) > LIMIT:
            raise ValueError("release_candidate_executable_unverified")
        provenance = {"schema": "amail-native-repack/v1", "target": target,
                      "executable_sha256": hashlib.sha256(content).hexdigest(),
                      "native_source_sha": admission["record"]["source_sha"],
                      "native_run_id": admission["record"]["source_run"],
                      "native_bundle_artifact_id": admission["producer"]["cli_artifact_id"],
                      "native_archive_sha256": hashes[original],
                      "acceptance_run_id": admission["record"]["staging_acceptance_run"],
                      "packaging_source_sha": admission["release_sha"],
                      "packaging_run_id": os.environ["GITHUB_RUN_ID"]}
        payload = {"amail.exe" if "windows" in target else "amail": content,
                   "README.md": (ROOT / "README.md").read_bytes(),
                   "LICENSE": (ROOT / "LICENSE").read_bytes(),
                   "BUILD-PROVENANCE.json": (json.dumps(provenance, sort_keys=True, indent=2) + "\n").encode()}
        extension = "zip" if "windows" in target else "tar.gz"
        destination = output / f"amail-{tag}-{target}.{extension}"
        write_archive(destination, payload)


def write_archive(path: Path, payload: dict[str, bytes]) -> None:
    """Write a small fixed public payload with executable permissions preserved."""
    if path.suffix == ".zip":
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in payload.items():
                archive.writestr(name, content)
        return
    with tarfile.open(path, "w:gz") as archive:
        for name, content in payload.items():
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode = len(content), 0o755 if name == "amail" else 0o644
            archive.addfile(entry, io.BytesIO(content))


def main() -> int:
    """Expose admission and packaging, not building, testing or publication."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("admit", "package"))
    parser.add_argument("tag")
    args = parser.parse_args()
    try:
        if args.phase == "admit":
            admit(args.tag)
        else:
            package(args.tag, ROOT / ".temp/reused-release")
    except Exception:
        print("release_candidate=UNVERIFIED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
