"""Verify downloaded GitHub Release bytes before publishing the public site.

The downloaded checksum file is not a trust root. The tag workflow compares it
to its immutable same-run bundle; the manual production path verifies each
archive's attestation against the release workflow, tag, and source SHA.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import subprocess
import sys


TAG = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?\Z")
CHECKSUM = re.compile(rb"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)\Z")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
SOURCE_DIGEST = re.compile(r"[0-9a-f]{40}\Z")
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


def verify(
    directory: pathlib.Path,
    tag: str,
    *,
    trusted_manifest: pathlib.Path | None = None,
    repository: str | None = None,
    source_digest: str | None = None,
) -> None:
    """Check bytes against a same-run manifest or tagged-source attestations."""

    names = expected_names(tag)
    if (repository is None) != (source_digest is None):
        raise AssetError("incomplete attestation source")
    if (trusted_manifest is None) == (repository is None):
        raise AssetError("exactly one release provenance mode is required")
    if repository is not None and not REPOSITORY.fullmatch(repository):
        raise AssetError("invalid attestation repository")
    if source_digest is not None and not SOURCE_DIGEST.fullmatch(source_digest):
        raise AssetError("invalid attestation source digest")
    if not directory.is_dir() or directory.is_symlink():
        raise AssetError("release download directory is missing")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != names | {"SHA256SUMS"}:
        raise AssetError("published release asset names differ from the expected set")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise AssetError("published release contains a non-regular asset")
    manifest = (directory / "SHA256SUMS").read_bytes()
    checksums = parse_checksums(manifest, names)
    if trusted_manifest is not None and manifest != trusted_manifest.read_bytes():
        raise AssetError("published manifest differs from same-run build artifact")
    for name in sorted(names):
        with (directory / name).open("rb") as archive:
            digest = hashlib.file_digest(archive, "sha256").hexdigest()
        if digest != checksums[name]:
            raise AssetError("published release asset hash mismatch")
        if repository is not None and source_digest is not None:
            result = subprocess.run(
                [
                    "gh", "attestation", "verify", str(directory / name),
                    "--repo", repository,
                    "--signer-workflow", f"{repository}/.github/workflows/release.yml",
                    "--source-ref", f"refs/tags/{tag}",
                    "--source-digest", source_digest,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if result.returncode != 0:
                raise AssetError("published release asset attestation failed")


def main() -> int:
    """Print only fixed gate outcomes, never asset contents or release URLs."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=pathlib.Path)
    parser.add_argument("tag")
    parser.add_argument("--trusted-manifest", type=pathlib.Path)
    parser.add_argument("--repo")
    parser.add_argument("--source-digest")
    args = parser.parse_args()
    try:
        verify(
            args.directory, args.tag,
            trusted_manifest=args.trusted_manifest,
            repository=args.repo,
            source_digest=args.source_digest,
        )
    except (AssetError, OSError) as error:
        reason = "io" if isinstance(error, OSError) else "contract"
        print(f"release_asset_integrity=failed reason={reason}", file=sys.stderr)
        return 1
    print("release_asset_integrity=verified count=6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
