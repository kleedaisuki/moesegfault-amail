"""Offline contract tests for the post-publish release asset gate."""

from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import sys
import tempfile
import unittest


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "release" / "verify_published_assets.py"
SPEC = importlib.util.spec_from_file_location("verify_published_assets", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
TAG = "v0.1.0"


def write_bundle(directory: pathlib.Path) -> None:
    """Create a valid synthetic seven-file download without network access."""

    lines = []
    for name in sorted(MODULE.expected_names(TAG)):
        data = f"synthetic:{name}".encode("ascii")
        (directory / name).write_bytes(data)
        lines.append(f"{hashlib.sha256(data).hexdigest()}  {name}\n")
    (directory / "SHA256SUMS").write_text("".join(lines), encoding="ascii")


class PublishedAssetIntegrityTest(unittest.TestCase):
    """A complete, canonical, byte-matching bundle is the only passing case."""

    def test_complete_bundle_passes(self) -> None:
        """The six expected archives and manifest verify without provider access."""

        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            write_bundle(directory)
            MODULE.verify(directory, TAG)

    def test_missing_extra_and_renamed_assets_fail(self) -> None:
        """A matching digest list cannot excuse a wrong published asset set."""

        for mutation in ("missing", "extra", "renamed"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                directory = pathlib.Path(temporary)
                write_bundle(directory)
                target = directory / sorted(MODULE.expected_names(TAG))[0]
                if mutation == "missing":
                    target.unlink()
                elif mutation == "extra":
                    (directory / "unexpected.zip").write_bytes(b"surprise")
                else:
                    target.rename(directory / "wrong-name.zip")
                with self.assertRaises(MODULE.AssetError):
                    MODULE.verify(directory, TAG)

    def test_tampered_archive_fails(self) -> None:
        """Verify downloaded bytes rather than trusting manifest names alone."""

        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            write_bundle(directory)
            (directory / sorted(MODULE.expected_names(TAG))[0]).write_bytes(b"modified")
            with self.assertRaises(MODULE.AssetError):
                MODULE.verify(directory, TAG)

    def test_malformed_duplicate_and_missing_checksums_fail(self) -> None:
        """Reject ambiguous manifests before any checksum can count as proof."""

        names = MODULE.expected_names(TAG)
        one = sorted(names)[0]
        digest = b"a" * 64
        valid_line = digest + b"  " + one.encode("ascii") + b"\n"
        for raw in (
            b"",
            valid_line + valid_line,
            valid_line.replace(b"  ", b" *"),
            valid_line.replace(one.encode("ascii"), b"../bad.zip"),
            valid_line.replace(b"a", b"A", 1),
            valid_line.rstrip(b"\n"),
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(MODULE.AssetError):
                    MODULE.parse_checksums(raw, names)

    def test_invalid_tag_and_symlink_fail(self) -> None:
        """Reject unsafe tags and non-regular downloaded assets."""

        with self.assertRaises(MODULE.AssetError):
            MODULE.expected_names("v0.1.0/../../escape")
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            write_bundle(directory)
            target = directory / sorted(MODULE.expected_names(TAG))[0]
            target.unlink()
            try:
                target.symlink_to(directory / "SHA256SUMS")
            except OSError:
                self.skipTest("symlinks unavailable on this platform")
            with self.assertRaises(MODULE.AssetError):
                MODULE.verify(directory, TAG)


if __name__ == "__main__":
    unittest.main()
