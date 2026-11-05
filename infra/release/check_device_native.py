"""Admit the original successful Linux native producer for deployed acceptance."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tomllib
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "8e5b9a98f265eb0102fd414dcb83027f7b13d8e8"
RUN = "42048951171"
ARTIFACT = 13426021821
SHA256 = "4d4d54088a4c942c201f1ae94837a5cfe58bce5f5c749dadb4a98497318399d3"
RUNTIME = ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", ".cargo", "crates", "workers")


def github(path: str) -> Any:
    return json.loads(subprocess.check_output([
        "gh", "api", f"repos/kleedaisuki/moesegfault-amail/actions/{path}"
    ], cwd=ROOT, text=True))


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def run() -> None:
    producer = github(f"runs/{RUN}")
    source: str = producer["head_sha"]
    if (producer["run_attempt"] != 1 or producer["path"] != ".github/workflows/ci.yml"
            or source != SOURCE):
        raise ValueError("native_producer_changed")
    jobs = github(f"runs/{RUN}/jobs?per_page=100")["jobs"]
    if not any(job["name"].endswith("/ Synthetic HTTPS device browser journey")
               and job["conclusion"] == "success" for job in jobs):
        raise ValueError("native_producer_not_accepted")
    artifact = github(f"artifacts/{ARTIFACT}")
    if (artifact["expired"] or artifact["workflow_run"]["id"] != int(RUN)
            or artifact["workflow_run"]["head_sha"] != source):
        raise ValueError("native_artifact_changed")
    git("merge-base", "--is-ancestor", source, "HEAD")
    changed = set(git("diff", "--name-only", source, "HEAD", "--", *RUNTIME).decode().splitlines())
    if changed - {"Cargo.lock", "crates/amail/Cargo.toml"}:
        raise ValueError("native_runtime_changed")
    for name in changed:
        before = tomllib.loads(git("show", f"{source}:{name}").decode())
        after = tomllib.loads((ROOT / name).read_text())
        if name == "Cargo.lock":
            for value in (before, after):
                next(row for row in value["package"] if row["name"] == "amail").pop("version")
        else:
            before["package"].pop("version")
            after["package"].pop("version")
        if before != after:
            raise ValueError("native_dependencies_changed")
    binary = ROOT / ".temp/device-native/target/debug/amail"
    if hashlib.sha256(binary.read_bytes()).hexdigest() != SHA256:
        raise ValueError("native_binary_changed")
    print(json.dumps({"event": "native_producer_verified", "source_sha": source,
                      "run_id": RUN, "artifact_id": ARTIFACT, "binary_sha256": SHA256}))


if __name__ == "__main__":
    run()
