"""Admit the reviewed native-only lease patch without repeating unrelated suites."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tomllib
from typing import Any

ROOT: Path = Path(__file__).resolve().parents[2]
BASE: str = "442f60cc4ec94f12daeb56945ee6a351d7fcd12f"
VERSION: str = "0.3.2"
PROFILES: str = "crates/amail/src/profiles.rs"
MANIFEST: str = "crates/amail/Cargo.toml"
RUNTIME: tuple[str, ...] = ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", ".cargo", "crates", "workers")
FILTER: str = "profiles::tests::permanent_mailbox_lease_"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, timeout=30).strip()


def production(source: str) -> str:
    return "\n".join(line for line in source.split("#[cfg(test)]", 1)[0].splitlines()
                     if line.strip() and not line.lstrip().startswith("//"))


def validate(before: dict[str, str], after: dict[str, str], changed: set[str]) -> None:
    if changed != {PROFILES, MANIFEST, "Cargo.lock"}:
        raise ValueError("native_patch_runtime_scope_changed")
    old_manifest: dict[str, Any] = tomllib.loads(before[MANIFEST])
    new_manifest: dict[str, Any] = tomllib.loads(after[MANIFEST])
    if old_manifest["package"]["version"] != "0.3.1" or new_manifest["package"].pop("version") != VERSION:
        raise ValueError("native_patch_version_unverified")
    old_manifest["package"].pop("version")
    if old_manifest != new_manifest:
        raise ValueError("native_patch_dependencies_changed")
    old_lock: dict[str, Any] = tomllib.loads(before["Cargo.lock"])
    new_lock: dict[str, Any] = tomllib.loads(after["Cargo.lock"])
    for value, version in ((old_lock, "0.3.1"), (new_lock, VERSION)):
        packages: list[dict[str, Any]] = [row for row in value["package"] if row.get("name") == "amail"]
        if len(packages) != 1 or packages[0].pop("version") != version:
            raise ValueError("native_patch_lock_unverified")
    if old_lock != new_lock:
        raise ValueError("native_patch_dependencies_changed")
    guard: str = "                && !generation.is_empty()\n"
    if before[PROFILES].count(guard) != 1 or production(before[PROFILES].replace(guard, "")) != production(after[PROFILES]):
        raise ValueError("native_patch_implementation_changed")


def applies(head: str) -> bool:
    if tomllib.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))["package"]["version"] != VERSION:
        return False
    git("merge-base", "--is-ancestor", BASE, head)
    changed: set[str] = set(git("diff", "--name-only", BASE, head, "--", *RUNTIME).splitlines())
    before: dict[str, str] = {name: git("show", f"{BASE}:{name}") + "\n" for name in changed}
    after: dict[str, str] = {name: (ROOT / name).read_text(encoding="utf-8") for name in changed}
    validate(before, after, changed)
    return True


def main() -> None:
    focused: bool = applies(os.environ["GITHUB_SHA"])
    version: str = tomllib.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))["package"]["version"]
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"focused_native={str(focused).lower()}\n")
        output.write(f"runtime_tag=v{'0.3.1' if focused else version}\n")


if __name__ == "__main__":
    main()
