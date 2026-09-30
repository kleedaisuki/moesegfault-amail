"""Hosted synthetic immutable artifacts; no provider GET or executable invocation."""

from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
from urllib.error import HTTPError
import zipfile

import staging_ten_address_artifact as target
import staging_ten_address_manifest as manifest
from test_staging_ten_address_manifest import RUN

SHA = "a" * 40
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def archive(entries):
    """Make synthetic bytes in memory; no external ZIP tool is involved."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as value:
        for name, content in entries:
            value.writestr(name, content)
    return stream.getvalue()


def metadata(raw, *, recovery=True):
    """Model immutable Actions v4 API metadata at a known synthetic UTC instant."""
    return {"id": 123, "name": "ten-address-recovery-" + RUN if recovery else "amail-windows-smoke-" + SHA,
            "expired": False, "size_in_bytes": len(raw), "created_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(days=30 if recovery else 3)).isoformat(),
            "digest": "sha256:" + hashlib.sha256(raw).hexdigest(), "workflow_run": {
                "id": int(RUN), "head_sha": SHA, "head_branch": manifest.BRANCH.removeprefix("refs/heads/"),
                "repository_id": 1, "head_repository_id": 1}}


class ArtifactTests(unittest.TestCase):
    """Test fail-closed raw observations and archive trust boundaries."""

    def test_exact_ciphertext_archive_id_digest_and_metadata_readback(self):
        """Uploaded artifact success alone is weaker than independent complete readback."""
        content = b"synthetic private encrypted envelope"
        raw = archive([("manifest.bin", content)])
        value = metadata(raw)
        reader = mock.Mock(side_effect=[value, value])
        transport = mock.Mock(return_value=raw)
        result = target.Artifacts("private-token", read=reader, transport=transport).content(
            "123", RUN, SHA, NOW, recovery=True)
        self.assertEqual(result, content)
        self.assertEqual(reader.call_count, 2)
        self.assertTrue(reader.call_args.args[0].endswith("/artifacts/123"))
        transport.assert_called_once_with("123", "private-token", target.MAX_MANIFEST)

    def test_foreign_id_run_sha_branch_fork_name_or_retention_is_rejected(self):
        """Recovery binding rejects every authority-changing metadata coordinate."""
        raw = archive([("manifest.bin", b"synthetic")])
        original = metadata(raw)
        candidates = [dict(original, id=456), dict(original, expired=True), dict(original, digest=None),
                      dict(original, name="another"), dict(original, expires_at=(NOW + timedelta(days=29)).isoformat())]
        for field, value in (("id", 456), ("head_sha", "b" * 40), ("head_branch", "main"),
                             ("head_repository_id", 2)):
            changed = dict(original)
            changed["workflow_run"] = dict(original["workflow_run"], **{field: value})
            candidates.append(changed)
        for changed in candidates:
            transport = mock.Mock()
            with self.assertRaises(manifest.ContractFailure):
                target.Artifacts("private", read=lambda *args: changed, transport=transport).content(
                    "123", RUN, SHA, NOW, recovery=True)
            transport.assert_not_called()

    def test_changed_immutable_metadata_never_reaches_campaign(self):
        """Even valid content cannot substitute for an unchanged exact artifact relation."""
        raw = archive([("manifest.bin", b"synthetic")])
        value = metadata(raw)
        with self.assertRaisesRegex(manifest.ContractFailure, "artifact_metadata_changed"):
            target.Artifacts("private", read=mock.Mock(side_effect=[value, dict(value, updated_at="changed")]),
                             transport=lambda *args: raw).content("123", RUN, SHA, NOW, recovery=True)

    def test_tampered_traversal_duplicate_extra_directory_and_symlink_archives(self):
        """Never extractall; only one root file with matching digest may be consumed."""
        for entries in ([("../manifest.bin", b"x")], [("manifest.bin", b"x"), ("extra", b"x")],
                        [("manifest.bin/", b"x")]):
            raw = archive(entries)
            with self.assertRaisesRegex(manifest.ContractFailure, "artifact_contents_unverified"):
                target.single_file(raw, "manifest.bin", hashlib.sha256(raw).hexdigest(), target.MAX_MANIFEST)
        raw = archive([("manifest.bin", b"x")])
        with self.assertRaisesRegex(manifest.ContractFailure, "artifact_digest_mismatch"):
            target.single_file(raw + b"tampered", "manifest.bin", hashlib.sha256(raw).hexdigest(), target.MAX_MANIFEST)
        entry = zipfile.ZipInfo("manifest.bin")
        entry.create_system = 3
        entry.external_attr = (stat.S_IFLNK | 0o777) << 16
        raw = archive([(entry, b"target")])
        with self.assertRaisesRegex(manifest.ContractFailure, "artifact_contents_unverified"):
            target.single_file(raw, "manifest.bin", hashlib.sha256(raw).hexdigest(), target.MAX_MANIFEST)

    def test_signed_storage_origin_and_bearer_boundary(self):
        """Unsigned storage GET must not inherit GitHub bearer or follow another redirect."""
        location = "https://synthetic.blob.core.windows.net/results/private.zip?sig=private"
        target.signed_storage_url(location)
        for url in ("http://synthetic.blob.core.windows.net/x", "https://evil.test/x", "https://blob.core.windows.net/x",
                    "https://user:pass@synthetic.blob.core.windows.net/x", location + "#fragment"):
            with self.assertRaisesRegex(manifest.ContractFailure, "artifact_storage_origin_unverified"):
                target.signed_storage_url(url)
        response = mock.MagicMock()
        response.__enter__.return_value.status = 200
        response.__enter__.return_value.read.return_value = b"synthetic zip bytes"
        opener = mock.Mock(side_effect=[HTTPError("https://api.github.com/hidden", 302, "Found",
                                                 {"Location": location}, None), response])
        with mock.patch.object(target, "control_open", opener):
            self.assertEqual(target.download("123", "private-token", target.MAX_MANIFEST), b"synthetic zip bytes")
        first, second = [call.args[0] for call in opener.call_args_list]
        self.assertEqual(first.get_header("Authorization"), "Bearer private-token")
        self.assertIsNone(second.get_header("Authorization"))
        self.assertEqual(first.host, "api.github.com")
        self.assertEqual(second.host, "synthetic.blob.core.windows.net")

    def test_one_exact_tested_binary_artifact_written_without_override(self):
        """Only a digest-checked one-file CI archive supplies materialized executable bytes."""
        root = Path(__file__).resolve().parents[2] / ".temp"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="quota-artifact-unit-", dir=root) as directory:
            content = b"MZ synthetic nonexecutable fixture"
            raw = archive([("amail.exe", content)])
            value = metadata(raw, recovery=False)
            def reader(path, token):
                return {"total_count": 1, "artifacts": [value]} if "?per_page=" in path else value
            client = target.Artifacts("private", read=reader, transport=lambda *args: raw)
            destination = Path(directory) / "amail.exe"
            self.assertEqual(client.binary(RUN, SHA, destination, NOW), destination.resolve())
            self.assertEqual(destination.read_bytes(), content)
            with self.assertRaisesRegex(manifest.ContractFailure, "binary_materialization_unverified"):
                client.binary(RUN, SHA, destination, NOW)
            self.assertEqual(destination.read_bytes(), content)

    def test_truncated_duplicate_or_absent_binary_inventory_fails_closed(self):
        """No fallback latest/cache binary exists after artifact lookup uncertainty."""
        value = metadata(archive([("amail.exe", b"fixture")]), recovery=False)
        for listing in ({"total_count": 2, "artifacts": [value]}, {"total_count": 0, "artifacts": []},
                        {"total_count": 2, "artifacts": [value, value]}):
            transport = mock.Mock()
            client = target.Artifacts("private", read=lambda *args: listing, transport=transport)
            with self.assertRaises(manifest.ContractFailure):
                client.binary(RUN, SHA, Path("not-used/amail.exe"), NOW)
            transport.assert_not_called()
