"""Exact immutable GitHub artifact readback for binary and encrypted quota recovery.

Upload remains the reviewed upload-artifact action, before campaign credentials.
This module GETs metadata/content only: no upload, deletion, shell extraction or
fallback artifact search after ambiguity. Signed storage URLs are never logged
or sent a GitHub bearer token. Missing digest/provenance fails closed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import io
from pathlib import Path
import re
import stat
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request
import zipfile

import staging_ten_address_manifest as manifest
from staging_mail_e2e import control_open
from staging_worker_created_r2 import github_json

require = manifest.require
MAX_BINARY = 200 * 1024 * 1024
MAX_MANIFEST = manifest.LIMIT + 4096
RECOVERY_WORKFLOW = ".github/workflows/staging-ten-address-acceptance.yml"


def timestamp(value: object) -> datetime:
    """Require aware provider timestamps without formatting observed metadata."""
    require(isinstance(value, str), "artifact_time_unverified")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        raise manifest.ContractFailure("artifact_time_unverified") from None
    require(result.tzinfo is not None, "artifact_time_unverified")
    return result.astimezone(timezone.utc)


def metadata(value: dict, artifact: str, run: str, checkout: str, name: str,
             now: datetime, *, recovery: bool) -> str:
    """Bind immutable ID, original run/branch/SHA, digest and explicit retention."""
    manifest.coordinates(run, "1")
    require(isinstance(artifact, str) and re.fullmatch(r"[1-9][0-9]{0,19}", artifact) is not None
            and isinstance(checkout, str) and re.fullmatch(r"[a-f0-9]{40}", checkout) is not None
            and isinstance(now, datetime) and now.tzinfo is not None,
            "artifact_provenance_unverified")
    require(isinstance(value, dict) and value.get("id") == int(artifact) and value.get("name") == name
            and value.get("expired") is False and type(value.get("size_in_bytes")) is int
            and 0 < value["size_in_bytes"] <= (MAX_MANIFEST if recovery else MAX_BINARY)
            and isinstance(value.get("workflow_run"), dict), "artifact_provenance_unverified")
    relation = value["workflow_run"]
    require(relation.get("id") == int(run) and relation.get("head_sha") == checkout
            and relation.get("head_branch") == manifest.BRANCH.removeprefix("refs/heads/")
            and type(relation.get("repository_id")) is int and relation["repository_id"] > 0
            and relation.get("head_repository_id") == relation["repository_id"],
            "artifact_provenance_unverified")
    created, expires = timestamp(value.get("created_at")), timestamp(value.get("expires_at"))
    require(created <= now + timedelta(seconds=60) and expires > now
            and expires > created and (not recovery or expires - created >= timedelta(days=30)),
            "artifact_lifetime_unverified")
    digest = value.get("digest")
    require(isinstance(digest, str) and re.fullmatch(r"sha256:[a-f0-9]{64}", digest) is not None,
            "artifact_digest_unverified")
    return digest.removeprefix("sha256:")


def signed_storage_url(value: str) -> None:
    """Allow only documented HTTPS Actions storage origins, without userinfo/fragment."""
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        valid = (parsed.scheme == "https" and parsed.port in (None, 443) and not parsed.username
                 and not parsed.password and not parsed.fragment and parsed.path.startswith("/")
                 and (host.endswith(".blob.core.windows.net")
                      or host == "results-receiver.actions.githubusercontent.com"))
    except Exception:
        valid = False
    require(valid, "artifact_storage_origin_unverified")


def download(artifact: str, token: str, limit: int) -> bytes:
    """Take one authenticated API redirect, then one bounded unsigned storage GET.

    Both requests reject subsequent redirects. The first bearer is confined to
    api.github.com; signed URLs are never persisted or emitted. No retry occurs.
    """
    require(isinstance(artifact, str) and re.fullmatch(r"[1-9][0-9]{0,19}", artifact) is not None
            and isinstance(token, str) and bool(token) and limit in (MAX_MANIFEST, MAX_BINARY),
            "artifact_download_capability_invalid")
    request = Request(f"https://api.github.com/repos/{manifest.REPOSITORY}/actions/artifacts/{artifact}/zip",
                      headers={"Authorization": "Bearer " + token,
                               "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with control_open(request, timeout=25):
            raise manifest.ContractFailure("artifact_redirect_unverified")
    except HTTPError as error:
        require(error.code == 302, "artifact_redirect_unverified")
        location = error.headers.get("Location", "")
    except manifest.ContractFailure:
        raise
    except Exception:
        raise manifest.ContractFailure("artifact_download_unverified") from None
    signed_storage_url(location)
    try:
        with control_open(Request(location, headers={"Accept": "application/zip"}), timeout=90) as response:
            require(response.status == 200, "artifact_download_unverified")
            raw = response.read(limit + 1)
    except manifest.ContractFailure:
        raise
    except Exception:
        raise manifest.ContractFailure("artifact_download_unverified") from None
    require(isinstance(raw, bytes) and 0 < len(raw) <= limit, "artifact_download_oversized")
    return raw


def single_file(raw: bytes, expected: str, digest: str, limit: int) -> bytes:
    """Digest-check exact ZIP bytes, then read one non-link root entry without extractall."""
    require(isinstance(raw, bytes) and len(raw) <= limit
            and isinstance(digest, str) and re.fullmatch(r"[a-f0-9]{64}", digest) is not None
            and hashlib.sha256(raw).hexdigest() == digest, "artifact_digest_mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            require(len(entries) == 1, "artifact_contents_unverified")
            entry = entries[0]
            require(entry.filename == expected and not entry.is_dir()
                    and not entry.flag_bits & 1 and stat.S_IFMT(entry.external_attr >> 16) != stat.S_IFLNK
                    and 0 < entry.file_size <= limit, "artifact_contents_unverified")
            contents = archive.read(entry)
    except manifest.ContractFailure:
        raise
    except Exception:
        raise manifest.ContractFailure("artifact_contents_unverified") from None
    require(len(contents) == entry.file_size and len(contents) <= limit, "artifact_contents_unverified")
    return contents


class Artifacts:
    """Read immutable metadata/content from the exact repository; never mutate artifacts."""

    def __init__(self, token: str, *, read: Callable = github_json,
                 transport: Callable = download):
        """Inject hosted synthetic readers only; live defaults retain bearer boundaries."""
        require(isinstance(token, str) and bool(token), "artifact_capability_invalid")
        self._token, self._read, self._transport = token, read, transport

    def _get(self, artifact: str) -> dict:
        """Require a numeric artifact ID before building any provider URL."""
        require(isinstance(artifact, str) and re.fullmatch(r"[1-9][0-9]{0,19}", artifact) is not None,
                "artifact_provenance_unverified")
        try:
            return self._read(f"/repos/{manifest.REPOSITORY}/actions/artifacts/{artifact}", self._token)
        except Exception:
            raise manifest.ContractFailure("artifact_metadata_unverified") from None

    def content(self, artifact: str, run: str, checkout: str, now: datetime, *, recovery: bool) -> bytes:
        """Compare exact metadata around downloaded, digest-checked one-file content."""
        name = ("ten-address-recovery-" + run if recovery else "amail-windows-smoke-" + checkout)
        first = self._get(artifact)
        expected = metadata(first, artifact, run, checkout, name, now, recovery=recovery)
        limit = MAX_MANIFEST if recovery else MAX_BINARY
        try:
            raw = self._transport(artifact, self._token, limit)
        except Exception:
            raise manifest.ContractFailure("artifact_download_unverified") from None
        content = single_file(raw, "manifest.bin" if recovery else "amail.exe", expected, limit)
        second = self._get(artifact)
        require(manifest.canonical(first) == manifest.canonical(second), "artifact_metadata_changed")
        return content

    def binary(self, source_run: str, checkout: str, destination: Path, now: datetime) -> Path:
        """Find one exact tested artifact and write a new owned repository .temp file.

        Caller must independently validate successful_source before this method;
        no binary is executed by this module. File bytes come from the exact
        digest-checked archive, not a caller-supplied path or cache entry.
        """
        manifest.coordinates(source_run, "1")
        require(re.fullmatch(r"[a-f0-9]{40}", checkout) is not None, "artifact_provenance_unverified")
        try:
            listing = self._read(f"/repos/{manifest.REPOSITORY}/actions/runs/{source_run}/artifacts?per_page=100", self._token)
        except Exception:
            raise manifest.ContractFailure("artifact_metadata_unverified") from None
        require(isinstance(listing, dict) and type(listing.get("total_count")) is int
                and 0 <= listing["total_count"] <= 100 and isinstance(listing.get("artifacts"), list)
                and len(listing["artifacts"]) == listing["total_count"]
                and all(isinstance(value, dict) for value in listing["artifacts"]), "artifact_inventory_incomplete")
        matches = [value for value in listing["artifacts"] if value.get("name") == "amail-windows-smoke-" + checkout]
        require(len(matches) == 1 and type(matches[0].get("id")) is int, "binary_artifact_unverified")
        contents = self.content(str(matches[0]["id"]), source_run, checkout, now, recovery=False)
        root = Path(__file__).resolve().parents[2] / ".temp"
        resolved = destination.resolve()
        require(root.resolve() == root and root in resolved.parents and not destination.is_symlink()
                and destination.name == "amail.exe", "binary_destination_unverified")
        try:
            with destination.open("xb") as output:
                output.write(contents)
        except Exception:
            raise manifest.ContractFailure("binary_materialization_unverified") from None
        return resolved
