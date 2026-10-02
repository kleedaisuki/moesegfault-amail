"""Package hosted native CLI candidates without publishing a tag or release.

Run ``binary`` after release-mode native tests/build, upload its output per runner,
then download those same-run artifacts and run ``assemble``. The bundle is review
material, not publication admission. Source/run metadata contains no credentials.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / ".temp/ci/cli-candidate"
TARGETS = ("x86_64-unknown-linux-gnu", "x86_64-pc-windows-msvc", "aarch64-apple-darwin")


def context() -> dict:
    """Bind review bytes to one hosted source SHA, run, attempt and compiler."""
    sha, run, attempt = (os.getenv(key, "") for key in
                         ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))
    if (os.getenv("GITHUB_ACTIONS") != "true" or not re.fullmatch(r"[0-9a-f]{40}", sha)
            or not re.fullmatch(r"[1-9][0-9]{0,19}", run)
            or not re.fullmatch(r"[1-9][0-9]{0,4}", attempt)):
        raise ValueError("hosted_candidate_context_required")
    with (ROOT / "crates/amail/Cargo.toml").open("rb") as file:
        version = tomllib.load(file)["package"]["version"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("candidate_version_invalid")
    with (ROOT / "rust-toolchain.toml").open("rb") as file:
        compiler = tomllib.load(file)["toolchain"]["channel"]
    return {"schema": "amail-cli-candidate/v1", "version": version,
            "source_sha": sha, "run_id": run, "run_attempt": int(attempt),
            "rust": compiler, "publication": "unpublished-candidate"}


def digest(path: Path) -> str:
    """Hash an ordinary bounded file without following a symlink."""
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256 * 1024 * 1024:
        raise ValueError(f"candidate_file_invalid: {path.name}")
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def write_json(path: Path, value: dict) -> None:
    """Write deterministic public metadata beside the review archives."""
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def archive_name(version: str, target: str) -> str:
    """Keep candidate names visibly distinct from public release archives."""
    extension = "zip" if "windows" in target else "tar.gz"
    return f"amail-v{version}-candidate-{target}.{extension}"


def binary() -> None:
    """Archive the actual native release binary and its public license/manual."""
    info = context()
    compiler = subprocess.check_output(["rustc", "-vV"], text=True)
    target = next(line.removeprefix("host: ") for line in compiler.splitlines()
                  if line.startswith("host: "))
    if target not in TARGETS:
        raise ValueError(f"candidate_host_unsupported: {target}")
    executable = "amail.exe" if "windows" in target else "amail"
    source = ROOT / "target/release" / executable
    inputs = [(source, executable), (ROOT / "README.md", "README.md"),
              (ROOT / "LICENSE", "LICENSE")]
    for path, _ in inputs:
        digest(path)
    version = subprocess.check_output([str(source), "--version"], text=True).strip()
    if version != f"amail {info['version']}":
        raise ValueError("candidate_binary_version_mismatch")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    archive = OUTPUT / archive_name(info["version"], target)
    if "windows" in target:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path, name in inputs:
                bundle.write(path, name)
    else:
        with tarfile.open(archive, "w:gz") as bundle:
            for path, name in inputs:
                bundle.add(path, arcname=name, recursive=False)
    write_json(OUTPUT / f"{target}.json", {**info, "target": target,
               "archive": archive.name, "sha256": digest(archive)})


def assemble() -> None:
    """Verify all three same-run producers, then add skill and bundle checksums."""
    info = context()
    expected = set()
    for target in TARGETS:
        metadata = OUTPUT / f"{target}.json"
        digest(metadata)
        producer = json.loads(metadata.read_text(encoding="utf-8"))
        archive = OUTPUT / archive_name(info["version"], target)
        if producer != {**info, "target": target, "archive": archive.name,
                        "sha256": digest(archive)}:
            raise ValueError(f"candidate_producer_mismatch: {target}")
        expected.update((metadata.name, archive.name))
    if {path.name for path in OUTPUT.iterdir()} != expected:
        raise ValueError("candidate_file_set_mismatch")
    skill = OUTPUT / f"amail-agent-skill-v{info['version']}-candidate.zip"
    paths = sorted((ROOT / "skills/amail").rglob("*"))
    if not (ROOT / "skills/amail/SKILL.md").is_file():
        raise ValueError("candidate_skill_missing")
    with zipfile.ZipFile(skill, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in paths:
            if path.is_symlink():
                raise ValueError("candidate_skill_symlink_refused")
            if path.is_file():
                digest(path)
                bundle.write(path, path.relative_to(ROOT / "skills").as_posix())
    write_json(OUTPUT / "candidate.json", {**info, "targets": list(TARGETS),
               "files": {path.name: digest(path) for path in sorted(OUTPUT.iterdir())}})
    checksums = "".join(f"{digest(path)}  {path.name}\n" for path in sorted(OUTPUT.iterdir()))
    (OUTPUT / "SHA256SUMS").write_text(checksums, encoding="utf-8")


def main() -> None:
    """Select the producer or assembly stage; no provider operations are present."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("binary", "assemble"))
    args = parser.parse_args()
    {"binary": binary, "assemble": assemble}[args.stage]()


if __name__ == "__main__":
    main()
