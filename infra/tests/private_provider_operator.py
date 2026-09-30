"""Local-only key/artifact lifecycle; decrypted provider prose never leaves .NET."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import private_provider_capture as capture
import staging_worker_r2_delivery_history as history

CATEGORIES = frozenset({"unclassified", "authentication", "authorization_or_dataset_access",
                        "schema_or_field", "arguments_or_filter", "internal", "mixed"})
FILES = ("private.pk8", "public.spki", "created.utc", "capture.enc.json", "receipt.json", "receipt.next.json")
MAX_ARCHIVE = 600_000
JOB = "One-shot encrypted content-free provider error"


def session_path(session: str) -> Path:
    """Require one root-local nonlinked session; no user-provided paths."""
    history.need(re.fullmatch(r"[a-z0-9-]{1,40}", session) is not None
                 and os.environ.get("GITHUB_ACTIONS") != "true", "scope")
    root = Path(__file__).resolve().parents[2]
    path = root / ".temp" / "private-provider-diag" / session
    for item in (root / ".temp", path.parent, path, *(path / name for name in FILES)):
        history.need(not item.is_symlink() and not getattr(item, "is_junction", lambda: False)(), "scope")
    history.need(path.resolve().parent == (root / ".temp/private-provider-diag").resolve(), "scope")
    return path


def child(mode: str, session: str, data: bytes = b"") -> bytes:
    """Run fixed native helper, with no token/environment propagation or prose output."""
    env = {name: value for name, value in os.environ.items()
           if name in {"PATH", "SystemRoot", "HOME", "TMPDIR", "TEMP", "TMP", "DOTNET_ROOT"}}
    result = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File",
        str(Path(__file__).with_name("private_provider_crypto.ps1")), "-Mode", mode, "-Session", session],
        input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=60, check=False)
    history.need(result.returncode == 0 and not result.stderr and len(result.stdout) <= 128, "scope")
    return result.stdout.strip()


def token() -> str:
    """Use existing authenticated operator GH session, never CLI token arguments."""
    result = subprocess.run(["gh", "auth", "token"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=20, check=False)
    history.need(result.returncode == 0 and 0 < len(result.stdout) < 4096, "credential")
    return result.stdout.decode().strip()


def github(path: str, bearer: str, method: str = "GET", limit: int = 131072):
    """One authenticated GitHub request; reject redirects unless download handles it."""
    request = urllib.request.Request("https://api.github.com" + path, method=method, headers={
        "Authorization": "Bearer " + bearer, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"})
    with history.OPENER.open(request, timeout=20) as response:
        raw = response.read(limit + 1)
        history.need(len(raw) <= limit, "limit")
        return response.status, raw


def github_json(path: str, bearer: str) -> dict:
    """Bounded duplicate-free API provenance; never print returned values."""
    status, raw = github(path, bearer)
    history.need(status == 200, "provenance")
    value = json.loads(raw, object_pairs_hook=history.unique_object)
    history.need(isinstance(value, dict), "provenance")
    return value


def provenance(run_id: str, sha: str, bearer: str) -> dict:
    """Authenticate completed first-attempt capture and its one exact immutable artifact."""
    history.need(re.fullmatch(r"[1-9][0-9]{0,19}", run_id) is not None
                 and re.fullmatch(r"[0-9a-f]{40}", sha) is not None, "identity")
    base = f"/repos/{history.REPOSITORY}/actions/runs/{run_id}"
    run = github_json(base + "/attempts/1", bearer)
    history.need(run.get("id") == int(run_id) and run.get("run_attempt") == 1
                 and run.get("head_sha") == sha and run.get("head_branch") == history.BRANCH
                 and run.get("event") == "workflow_dispatch" and run.get("status") == "completed"
                 and run.get("conclusion") == "success"
                 and run.get("path") in (capture.WORKFLOW, capture.WORKFLOW + "@refs/heads/" + history.BRANCH), "provenance")
    jobs = github_json(base + "/attempts/1/jobs?per_page=100", bearer)
    entries = jobs.get("jobs")
    history.need(isinstance(entries, list) and type(jobs.get("total_count")) is int
                 and len(entries) == jobs["total_count"] <= 100, "provenance")
    matches = [job for job in entries if isinstance(job, dict) and job.get("name") == JOB]
    history.need(len(matches) == 1 and matches[0].get("head_sha") == sha
                 and matches[0].get("run_id") == int(run_id)
                 and matches[0].get("status") == "completed" and matches[0].get("conclusion") == "success", "provenance")
    listing = github_json(base + "/artifacts?per_page=100", bearer)
    artifacts = listing.get("artifacts")
    history.need(isinstance(artifacts, list) and type(listing.get("total_count")) is int
                 and len(artifacts) == listing["total_count"] <= 100, "provenance")
    matches = [artifact for artifact in artifacts if isinstance(artifact, dict)
               and artifact.get("name") == f"private-provider-error-{run_id}-1"]
    history.need(len(matches) == 1, "provenance")
    artifact = matches[0]
    binding = artifact.get("workflow_run")
    history.need(type(artifact.get("id")) is int and artifact["id"] > 0
                 and type(artifact.get("size_in_bytes")) is int and 0 < artifact["size_in_bytes"] <= MAX_ARCHIVE
                 and artifact.get("expired") is False and isinstance(binding, dict)
                 and binding.get("id") == int(run_id) and binding.get("head_sha") == sha
                 and binding.get("head_branch") == history.BRANCH
                 and re.fullmatch(r"sha256:[0-9a-f]{64}", artifact.get("digest", "")) is not None, "provenance")
    created = history.parse_time(artifact.get("created_at"))
    history.need(timedelta(0) <= datetime.now(timezone.utc) - created < timedelta(hours=24), "scope")
    return artifact


def download(artifact: dict, bearer: str) -> bytes:
    """Follow one HTTPS artifact redirect without credentials; bind archive digest."""
    path = f"/repos/{history.REPOSITORY}/actions/artifacts/{artifact['id']}/zip"
    try:
        github(path, bearer, limit=MAX_ARCHIVE)
    except urllib.error.HTTPError as error:
        history.need(error.code == 302, "provider")
        location = error.headers.get("Location", "")
        error.close()
    else:
        raise history.HistoryError("provider")
    url = urllib.parse.urlsplit(location)
    history.need(url.scheme == "https" and url.username is None and url.password is None
                 and url.port in (None, 443) and url.hostname is not None
                 and (url.hostname.endswith(".blob.core.windows.net")
                      or url.hostname.endswith(".actions.githubusercontent.com")), "scope")
    # Signed URL is private and never persisted or output. No auth header here.
    with history.OPENER.open(urllib.request.Request(location), timeout=20) as response:
        history.need(response.status == 200, "provider")
        archive = response.read(MAX_ARCHIVE + 1)
    history.need(len(archive) <= MAX_ARCHIVE and hashlib.sha256(archive).hexdigest()
                 == artifact["digest"][7:], "provenance")
    return archive


def envelope_from_zip(archive: bytes) -> bytes:
    """Read exactly one encrypted member in memory, never extract paths."""
    history.need(len(archive) <= MAX_ARCHIVE, "limit")
    with zipfile.ZipFile(io.BytesIO(archive)) as file:
        entries = file.infolist()
        history.need(len(entries) == 1, "scope")
        entry = entries[0]
        history.need(entry.filename == "capture.enc.json" and not entry.is_dir()
                     and not entry.flag_bits & 1 and entry.file_size <= capture.MAX_ENVELOPE
                     and stat.S_IFMT(entry.external_attr >> 16) in (0, stat.S_IFREG), "scope")
        raw = file.read(entry)
    history.need(len(raw) <= capture.MAX_ENVELOPE, "limit")
    return raw


def cleanup(session: str) -> None:
    """Delete only enumerated exact local files; reject extras instead of recursive removal."""
    path = session_path(session)
    if not path.exists():
        return
    history.need(path.is_dir() and {item.name for item in path.iterdir()} <= set(FILES), "scope")
    for name in FILES:
        target = path / name
        history.need(not target.exists() or target.is_file(), "scope")
        target.unlink(missing_ok=True)
        history.need(not target.exists(), "scope")
    path.rmdir()
    history.need(not path.exists(), "scope")


def record_receipt(folder: Path, state: dict, *, first: bool = False) -> None:
    """Flush one exact public receipt then atomically replace it; never truncate in place."""
    receipt, pending = folder / "receipt.json", folder / "receipt.next.json"
    history.need(not first or not receipt.exists(), "scope")
    with pending.open("xb") as file:
        file.write(json.dumps(state, separators=(",", ":")).encode())
        file.flush()
        os.fsync(file.fileno())
    os.replace(pending, receipt)
    # POSIX directory sync strengthens rename durability. Windows has no
    # portable Python directory-fsync; replacement is atomic, not a promise
    # against all power-loss/filesystem failure scenarios. Invalid receipts
    # always retain the key and fail closed instead of claiming cleanup.
    if os.name != "nt":
        descriptor = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def retire_remote(session: str) -> None:
    """Recover interrupted remote cleanup from public, authenticated coordinates only."""
    folder = session_path(session)
    receipt = folder / "receipt.json"
    # A session without capture coordinates may have been dispatched but never
    # inspected. Do not silently destroy the only key in that uncertain state.
    history.need(receipt.exists(), "scope")
    history.need(receipt.stat().st_size <= 1024, "scope")
    state = json.loads(receipt.read_bytes(), object_pairs_hook=history.unique_object)
    history.need(set(state) == {"artifact_id", "run_id", "source_sha"}
                 and (state["artifact_id"] is None or type(state["artifact_id"]) is int and state["artifact_id"] > 0)
                 and re.fullmatch(r"[1-9][0-9]{0,19}", state["run_id"]) is not None
                 and re.fullmatch(r"[0-9a-f]{40}", state["source_sha"]) is not None, "scope")
    bearer = token()
    base = f"/repos/{history.REPOSITORY}/actions/runs/{state['run_id']}"
    run = github_json(base + "/attempts/1", bearer)
    history.need(run.get("id") == int(state["run_id"]) and run.get("head_sha") == state["source_sha"]
                 and run.get("head_branch") == history.BRANCH and run.get("run_attempt") == 1
                 and run.get("event") == "workflow_dispatch", "provenance")
    listing = github_json(base + "/artifacts?per_page=100", bearer)
    entries = listing.get("artifacts")
    history.need(isinstance(entries, list) and type(listing.get("total_count")) is int
                 and len(entries) == listing["total_count"] <= 100, "provenance")
    name = f"private-provider-error-{state['run_id']}-1"
    matches = [item for item in entries if isinstance(item, dict)
               and (item.get("id") == state["artifact_id"] if state["artifact_id"] is not None else item.get("name") == name)]
    history.need(len(matches) <= 1, "provenance")
    if not matches:
        return
    artifact = matches[0]
    binding = artifact.get("workflow_run")
    history.need(artifact.get("name") == name and type(artifact.get("id")) is int and artifact["id"] > 0
                 and isinstance(binding, dict) and binding.get("id") == int(state["run_id"])
                 and binding.get("head_sha") == state["source_sha"], "provenance")
    path = f"/repos/{history.REPOSITORY}/actions/artifacts/{artifact['id']}"
    status, raw = github(path, bearer, "DELETE")
    history.need(status == 204 and not raw, "provider")
    try:
        github(path, bearer)
    except urllib.error.HTTPError as error:
        history.need(error.code == 404, "provider")
        error.close()
    else:
        raise history.HistoryError("provider")


def inspect(session: str, run_id: str, sha: str) -> str:
    """Authenticate/classify privately and delete remotely; retain one offline session."""
    folder = session_path(session)
    created = datetime.fromisoformat((folder / "created.utc").read_text())
    history.need(timedelta(0) <= datetime.now(timezone.utc) - created < timedelta(hours=24), "scope")
    public = (folder / "public.spki").read_text()
    history.need(re.fullmatch(r"[1-9][0-9]{0,19}", run_id) is not None
                 and re.fullmatch(r"[0-9a-f]{40}", sha) is not None, "identity")
    # Persist public recovery intent before the first API/provenance request.
    # Every subsequent interruption keeps enough coordinates to retire the
    # exact artifact, including when its numeric ID has not been learned yet.
    record_receipt(folder, {"artifact_id": None, "run_id": run_id, "source_sha": sha}, first=True)
    bearer = token()
    artifact = provenance(run_id, sha, bearer)
    record_receipt(folder, {"artifact_id": artifact["id"], "run_id": run_id, "source_sha": sha})
    encrypted = envelope_from_zip(download(artifact, bearer))
    metadata = {"source_sha": sha, "capture_run": run_id, "capture_attempt": "1",
                "original_run": history.RUN, "original_attempt": history.ATTEMPT,
                "workflow": capture.WORKFLOW, "repository": history.REPOSITORY,
                "query_sha256": hashlib.sha256(capture.QUERY.encode()).hexdigest()}
    capture.validate_envelope(encrypted, metadata, public)
    # Persist only authenticated ciphertext and public recovery coordinates.
    (folder / "capture.enc.json").write_bytes(encrypted)
    category = child("classify", session, encrypted).decode("ascii")
    history.need(category in CATEGORIES, "schema")
    status, body = github(f"/repos/{history.REPOSITORY}/actions/artifacts/{artifact['id']}", bearer, "DELETE")
    history.need(status == 204 and not body, "provider")
    try:
        github(f"/repos/{history.REPOSITORY}/actions/artifacts/{artifact['id']}", bearer)
    except urllib.error.HTTPError as error:
        history.need(error.code == 404, "provider")
        error.close()
    else:
        raise history.HistoryError("provider")
    return category


def classify_local(session: str) -> str:
    """Reuse the same authenticated encrypted capture without any network request."""
    folder = session_path(session)
    created = datetime.fromisoformat((folder / "created.utc").read_text())
    history.need(timedelta(0) <= datetime.now(timezone.utc) - created < timedelta(hours=24), "scope")
    receipt = folder / "receipt.json"
    encrypted_file = folder / "capture.enc.json"
    history.need(receipt.stat().st_size <= 1024 and encrypted_file.stat().st_size <= capture.MAX_ENVELOPE, "scope")
    state = json.loads(receipt.read_bytes(), object_pairs_hook=history.unique_object)
    history.need(set(state) == {"artifact_id", "run_id", "source_sha"}
                 and type(state["artifact_id"]) is int and state["artifact_id"] > 0
                 and re.fullmatch(r"[1-9][0-9]{0,19}", state["run_id"]) is not None
                 and re.fullmatch(r"[0-9a-f]{40}", state["source_sha"]) is not None, "scope")
    metadata = {"source_sha": state["source_sha"], "capture_run": state["run_id"], "capture_attempt": "1",
                "original_run": history.RUN, "original_attempt": history.ATTEMPT,
                "workflow": capture.WORKFLOW, "repository": history.REPOSITORY,
                "query_sha256": hashlib.sha256(capture.QUERY.encode()).hexdigest()}
    encrypted = encrypted_file.read_bytes()
    capture.validate_envelope(encrypted, metadata, (folder / "public.spki").read_text())
    category = child("classify", session, encrypted).decode("ascii")
    history.need(category in CATEGORIES, "schema")
    return category


def main() -> int:
    """Only closed status/category output, including every failure path."""
    try:
        args = sys.argv[1:]
        history.need(len(args) in (2, 4), "scope")
        mode, session = args[:2]
        if mode == "keygen" and len(args) == 2:
            path = session_path(session)
            history.need(not path.exists(), "scope")
            history.need(child("keygen", session) == b"private_provider_key=GENERATED", "scope")
            print("private_provider_operator=KEY_GENERATED")
        elif mode == "cleanup" and len(args) == 2:
            retire_remote(session)
            cleanup(session)
            print("private_provider_operator=CLEANED")
        elif mode == "inspect" and len(args) == 4:
            category = inspect(session, args[2], args[3])
            print("private_provider_operator=LOCAL_RETAINED remote=CLEANED errors=" + category + " delivery=UNVERIFIED")
        elif mode == "classify" and len(args) == 2:
            category = classify_local(session)
            print("private_provider_operator=LOCAL_RETAINED errors=" + category + " delivery=UNVERIFIED")
        else:
            raise history.HistoryError("scope")
        return 0
    except Exception:
        print("private_provider_operator=UNVERIFIED cleanup=UNVERIFIED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
