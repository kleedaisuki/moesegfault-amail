"""Verify downloaded GitHub Release bytes before publishing the public site.

The checksum file is itself delivered by GitHub and is not a trust root. This
gate catches incomplete, renamed, or corrupted published assets; release
provenance and the trusted tag remain separate publication controls.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys


TAG = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?\Z")
CHECKSUM = re.compile(rb"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)\Z")
TARGETS = (
    ("x86_64-unknown-linux-gnu", ".tar.gz"),
    ("aarch64-unknown-linux-gnu", ".tar.gz"),
    ("x86_64-pc-windows-msvc", ".zip"),
    ("aarch64-apple-darwin", ".tar.gz"),
    ("x86_64-apple-darwin", ".tar.gz"),
)


class AssetError(Exception):
    """A released bundle violates the exact name or byte-integrity contract."""


def expected_names(tag: str) -> set[str]:
    """Return the five native archives and the agent skill for one safe tag."""

    if not TAG.fullmatch(tag):
        raise AssetError("invalid release tag")
    return {f"amail-{tag}-{target}{suffix}" for target, suffix in TARGETS} | {
        f"amail-agent-skill-{tag}.zip"
    }


def parse_checksums(raw: bytes, names: set[str]) -> dict[str, str]:
    """Accept only canonical GNU sha256sum lines for the expected six assets."""

    if not raw or len(raw) > 8192 or not raw.endswith(b"\n"):
        raise AssetError("invalid checksum manifest")
    checksums: dict[str, str] = {}
    for line in raw[:-1].split(b"\n"):
        match = CHECKSUM.fullmatch(line)
        if match is None:
            raise AssetError("invalid checksum manifest entry")
        name = match.group(2).decode("ascii")
        if name not in names or name in checksums:
            raise AssetError("unexpected or duplicate checksum entry")
        checksums[name] = match.group(1).decode("ascii")
    if checksums.keys() != names:
        raise AssetError("missing checksum entries")
    return checksums


def verify(directory: pathlib.Path, tag: str) -> None:
    """Require the exact seven downloaded files and hash each archive bytewise."""

    names = expected_names(tag)
    if not directory.is_dir() or directory.is_symlink():
        raise AssetError("release download directory is missing")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != names | {"SHA256SUMS"}:
        raise AssetError("published release asset names differ from the expected set")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise AssetError("published release contains a non-regular asset")
    checksums = parse_checksums((directory / "SHA256SUMS").read_bytes(), names)
    for name in sorted(names):
        with (directory / name).open("rb") as archive:
            digest = hashlib.file_digest(archive, "sha256").hexdigest()
        if digest != checksums[name]:
            raise AssetError("published release asset hash mismatch")


def main() -> int:
    """Print only fixed gate outcomes, never asset contents or release URLs."""

    if len(sys.argv) != 3:
        print("release_asset_integrity=failed reason=arguments", file=sys.stderr)
        return 1
    try:
        verify(pathlib.Path(sys.argv[1]), sys.argv[2])
    except (AssetError, OSError) as error:
        reason = "io" if isinstance(error, OSError) else "contract"
        print(f"release_asset_integrity=failed reason={reason}", file=sys.stderr)
        return 1
    print("release_asset_integrity=verified count=6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
