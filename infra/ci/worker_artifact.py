"""Package public generated modules once; verify identity before native testing.

This is a same-run source-test artifact, not a deployment or release admission.
GitHub's fixed producer artifact ID establishes provenance; this manifest checks
the checkout, producer run, exact file set and contents without caching test results.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tomllib

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / ".temp/ci/worker-built"
TREES = ("crates/mail-worker/build", "workers/trace-sink/build", "workers/mail-ingress/build",
         "workers/mail-events/build", "workers/identity-test-inbox/build", "workers/role-monitor/build")
LIMIT = 32 * 1024 * 1024


def context() -> dict:
    """Bind a hosted artifact to the actual checked-out commit, run and attempt."""
    sha, run, attempt = (os.getenv(name, "") for name in ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))
    if (os.getenv("GITHUB_ACTIONS") != "true" or not re.fullmatch(r"[a-f0-9]{40}", sha)
            or not re.fullmatch(r"[1-9][0-9]{0,19}", run) or not re.fullmatch(r"[1-9][0-9]{0,4}", attempt)):
        raise ValueError("hosted_artifact_context_required")
    with (ROOT / "rust-toolchain.toml").open("rb") as file:
        rust = tomllib.load(file)["toolchain"]["channel"]
    if not isinstance(rust, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", rust):
        raise ValueError("explicit_rust_compiler_required")
    return {"schema": "worker-native-artifact/v1", "source_sha": sha, "run_id": run,
            "run_attempt": int(attempt), "worker_build": "0.8.5", "rust": rust}


def files(base: Path) -> dict[str, str]:
    """Hash only public module trees, refusing symlinks, extras and oversized data."""
    result, size = {}, 0
    for tree in TREES:
        folder = base / tree
        if not folder.is_dir() or folder.is_symlink():
            raise ValueError(f"module_tree_missing: {tree}")
        for path in sorted(folder.rglob("*")):
            if path.is_symlink():
                raise ValueError("module_symlink_refused")
            if path.is_dir():
                continue
            if not path.is_file() or path.suffix not in (".js", ".mjs", ".wasm", ".json", ".ts"):
                raise ValueError("module_file_unexpected")
            size += path.stat().st_size
            if size > LIMIT or len(result) >= 1000:
                raise ValueError("module_artifact_oversized")
            result[path.relative_to(base).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        if not (folder / "worker/shim.mjs").is_file() or not (folder / "index.js").is_file():
            raise ValueError(f"generated_entry_missing: {tree}")
    return result


def create() -> None:
    """Assemble generated code and provenance only, never configs or credentials."""
    identity, hashes = context(), files(ROOT)
    FOLDER.mkdir(parents=True, exist_ok=False)
    for name in hashes:
        destination = FOLDER / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    (FOLDER / "manifest.json").write_text(json.dumps({**identity, "files": hashes}, sort_keys=True), encoding="utf-8")
    print(json.dumps({"event": "worker_artifact_created", **identity, "file_count": len(hashes)}, sort_keys=True))


def restore() -> None:
    """Check all bytes before installing a fresh same-source native module tree."""
    manifest = FOLDER / "manifest.json"
    if FOLDER.is_symlink() or manifest.is_symlink() or manifest.stat().st_size > 262144:
        raise ValueError("artifact_manifest_invalid")
    value = json.loads(manifest.read_text(encoding="utf-8"))
    identity = context()
    if (not isinstance(value, dict) or set(value) != set(identity) | {"files"}
            or any(type(value.get(key)) is not type(expected) or value.get(key) != expected
                   for key, expected in identity.items())):
        raise ValueError("artifact_provenance_mismatch: expected checkout/run/compiler identity")
    hashes = files(FOLDER)
    actual = {path.relative_to(FOLDER).as_posix() for path in FOLDER.rglob("*") if path.is_file()}
    if value.get("files") != hashes or actual != set(hashes) | {"manifest.json"}:
        raise ValueError("artifact_file_integrity_mismatch: missing, extra or modified generated file")
    if any((ROOT / tree).exists() for tree in TREES):
        raise ValueError("artifact_existing_tree_refused")
    for name in hashes:
        destination = ROOT / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FOLDER / name, destination)
    print(json.dumps({"event": "worker_artifact_verified", **identity, "file_count": len(hashes)}, sort_keys=True))


def main() -> int:
    """A rejected artifact fails the native job without a provider operation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("create", "restore"))
    args = parser.parse_args()
    try:
        (create if args.operation == "create" else restore)()
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"event": "worker_artifact_failed", "operation": args.operation,
                          "error_type": type(error).__name__, "message": str(error)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
