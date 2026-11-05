"""Admit exact reviewed native patches or accepted feature runtime closures."""
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


@dataclass(frozen=True)
class Feature:
    base: str
    previous_version: str
    test_filter: str
    acceptance_kind: str
    runtime_tag: str


# This complete runtime passed the focused native/Worker journeys in docs/validation.md.
# Only packaging its new version is admitted here; new implementation needs a new review.
FEATURES: dict[str, Feature] = {
    "0.4.0": Feature("52d9db3be04a05d7a872cca89b3ef3814908e459", "0.3.3",
                     "device_", "device-code", "v0.3.1"),
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


def validate_feature(before: dict[str, str], after: dict[str, str], changed: set[str], version: str) -> None:
    feature: Feature = FEATURES[version]
    if changed != {MANIFEST, "Cargo.lock"}:
        raise ValueError("feature_runtime_closure_changed")
    for name in (MANIFEST, "Cargo.lock"):
        old: dict[str, Any] = tomllib.loads(before[name])
        new: dict[str, Any] = tomllib.loads(after[name])
        old_package: dict[str, Any] = old["package"] if name == MANIFEST else next(row for row in old["package"] if row["name"] == "amail")
        new_package: dict[str, Any] = new["package"] if name == MANIFEST else next(row for row in new["package"] if row["name"] == "amail")
        if old_package.pop("version") != feature.previous_version or new_package.pop("version") != version:
            raise ValueError("feature_version_unverified")
        if old != new:
            raise ValueError("feature_dependencies_changed")


def reuses_worker_runtime() -> bool:
    version: str = tomllib.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))["package"]["version"]
    return version in FEATURES


def applies(head: str) -> bool:
    version: str = tomllib.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))["package"]["version"]
    selected: Patch | Feature | None = FEATURES.get(version) or PATCHES.get(version)
    if selected is None:
        return False
    git("merge-base", "--is-ancestor", selected.base, head)
    changed: set[str] = set(git("diff", "--name-only", selected.base, head, "--", *RUNTIME).splitlines())
    before: dict[str, str] = {name: git("show", f"{selected.base}:{name}") + "\n" for name in changed}
    after: dict[str, str] = {name: (ROOT / name).read_text(encoding="utf-8") for name in changed}
    if isinstance(selected, Feature):
        validate_feature(before, after, changed, version)
    else:
        validate(before, after, changed)
    return True


def main() -> None:
    focused: bool = applies(os.environ["GITHUB_SHA"])
    version: str = tomllib.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))["package"]["version"]
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"focused_native={str(focused).lower()}\n")
        feature: Feature | None = FEATURES.get(version) if focused else None
        runtime_tag: str = feature.runtime_tag if feature else f"v{'0.3.1' if focused else version}"
        output.write(f"runtime_tag={runtime_tag}\n")
        patch: Patch | Feature | None = (feature or PATCHES.get(version)) if focused else None
        output.write(f"focused_test_filter={patch.test_filter if patch else ''}\n")
        output.write(f"acceptance_kind={patch.acceptance_kind if patch else ''}\n")


if __name__ == "__main__":
    main()
