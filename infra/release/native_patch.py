"""Admit exact reviewed native-only patches without repeating unrelated suites."""
from __future__ import annotations

from dataclasses import dataclass
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
APPROVAL: str = "crates/amail/src/approval.rs"


@dataclass(frozen=True)
class Patch:
    base: str
    previous_version: str
    source: str
    before: str
    after: str
    test_filter: str
    acceptance_kind: str


PATCHES: dict[str, Patch] = {
    VERSION: Patch(BASE, "0.3.1", PROFILES, "                && !generation.is_empty()\n", "",
                   FILTER, "permanent-acquire"),
    "0.3.3": Patch("e9d91c294c265be85540aa188748bd45110e12b8", "0.3.2", APPROVAL,
                   '("Referrer-Policy", "no-referrer")',
                   '("Referrer-Policy", "same-origin")', "approval::tests::", "approval"),
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, timeout=30).strip()


def production(source: str) -> str:
    return "\n".join(line for line in source.split("#[cfg(test)]", 1)[0].splitlines()
                     if line.strip() and not line.lstrip().startswith("//"))


def validate(before: dict[str, str], after: dict[str, str], changed: set[str]) -> None:
    old_manifest: dict[str, Any] = tomllib.loads(before[MANIFEST])
    new_manifest: dict[str, Any] = tomllib.loads(after[MANIFEST])
    version: str = new_manifest["package"].pop("version")
    patch: Patch | None = PATCHES.get(version)
    if patch is None or old_manifest["package"]["version"] != patch.previous_version:
        raise ValueError("native_patch_version_unverified")
    if changed != {patch.source, MANIFEST, "Cargo.lock"}:
        raise ValueError("native_patch_runtime_scope_changed")
    old_manifest["package"].pop("version")
    if old_manifest != new_manifest:
        raise ValueError("native_patch_dependencies_changed")
    old_lock: dict[str, Any] = tomllib.loads(before["Cargo.lock"])
    new_lock: dict[str, Any] = tomllib.loads(after["Cargo.lock"])
    for value, expected in ((old_lock, patch.previous_version), (new_lock, version)):
        packages: list[dict[str, Any]] = [row for row in value["package"] if row.get("name") == "amail"]
        if len(packages) != 1 or packages[0].pop("version") != expected:
            raise ValueError("native_patch_lock_unverified")
    if old_lock != new_lock:
        raise ValueError("native_patch_dependencies_changed")
    source: str = before[patch.source]
    if source.count(patch.before) != 1 or production(source.replace(patch.before, patch.after)) != production(after[patch.source]):
        raise ValueError("native_patch_implementation_changed")


def applies(head: str) -> bool:
    version: str = tomllib.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))["package"]["version"]
    patch: Patch | None = PATCHES.get(version)
    if patch is None:
        return False
    git("merge-base", "--is-ancestor", patch.base, head)
    changed: set[str] = set(git("diff", "--name-only", patch.base, head, "--", *RUNTIME).splitlines())
    before: dict[str, str] = {name: git("show", f"{patch.base}:{name}") + "\n" for name in changed}
    after: dict[str, str] = {name: (ROOT / name).read_text(encoding="utf-8") for name in changed}
    validate(before, after, changed)
    return True


def main() -> None:
    focused: bool = applies(os.environ["GITHUB_SHA"])
    version: str = tomllib.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))["package"]["version"]
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"focused_native={str(focused).lower()}\n")
        output.write(f"runtime_tag=v{'0.3.1' if focused else version}\n")
        patch: Patch | None = PATCHES.get(version) if focused else None
        output.write(f"focused_test_filter={patch.test_filter if patch else ''}\n")
        output.write(f"acceptance_kind={patch.acceptance_kind if patch else ''}\n")


if __name__ == "__main__":
    main()
