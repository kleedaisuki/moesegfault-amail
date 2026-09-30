"""One bounded content-free provider read; encrypt minimized errors before disk."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

import staging_worker_r2_delivery_history as history
from staging_worker_r2_history_error import QUERY

CONFIRM = "CAPTURE_PRIVATE_WORKER_R2_ERROR_36751791789_ONCE"
WORKFLOW = ".github/workflows/private-provider-error-capture.yml"
MAX_ENVELOPE = 400_000


def project(status: int, raw: bytes) -> bytes:
    """Drop every field except HTTP status and the complete bounded error subtree."""
    history.need(len(raw) <= history.MAX_BODY and type(status) is int, "schema")
    payload = json.loads(raw, object_pairs_hook=history.unique_object,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    history.need(isinstance(payload, dict) and bool(payload.get("errors")), "schema")
    result = json.dumps({"http_status": status, "errors": payload["errors"]},
                        separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    history.need(len(result) <= history.MAX_BODY, "schema")
    return result


def validate_envelope(raw: bytes, metadata: dict, public_key: str) -> bytes:
    """Validate ciphertext-only output before any artifact filesystem write."""
    history.need(len(raw) <= MAX_ENVELOPE, "schema")
    outer = json.loads(raw, object_pairs_hook=history.unique_object)
    history.need(isinstance(outer, dict) and set(outer) == {"version", "header", "ciphertext", "tag"}
                 and type(outer["version"]) is int and outer["version"] == 1, "schema")
    binary = {}
    for name in ("header", "ciphertext", "tag"):
        history.need(isinstance(outer[name], str), "schema")
        binary[name] = base64.b64decode(outer[name], validate=True)
        history.need(base64.b64encode(binary[name]).decode() == outer[name], "schema")
    history.need(len(binary["ciphertext"]) == 262144 and len(binary["tag"]) == 16
                 and len(binary["header"]) <= 4096, "schema")
    header = json.loads(binary["header"], object_pairs_hook=history.unique_object)
    history.need(set(header) == {"algorithm", "fingerprint", "nonce", "wrapped_key", "provenance"}
                 and header["algorithm"] == "RSA-3072-OAEP-SHA256+A256GCM"
                 and header["provenance"] == metadata
                 and header["fingerprint"] == hashlib.sha256(base64.b64decode(public_key, validate=True)).hexdigest(), "schema")
    for field, length in (("nonce", 12), ("wrapped_key", 384)):
        decoded = base64.b64decode(header[field], validate=True)
        history.need(len(decoded) == length and base64.b64encode(decoded).decode() == header[field], "schema")
    return raw


def encrypt(projection: bytes, metadata: dict, key: str) -> bytes:
    """Anonymous stdin only; child inherits no provider or GitHub credentials."""
    env = {name: value for name, value in os.environ.items()
           if name in {"PATH", "SystemRoot", "HOME", "TMPDIR", "TEMP", "TMP", "DOTNET_ROOT"}}
    env.update(PRIVATE_CAPTURE_PUBLIC_KEY=key,
               PRIVATE_CAPTURE_METADATA=json.dumps(metadata, separators=(",", ":")))
    process = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File",
                              str(Path(__file__).with_name("private_provider_crypto.ps1")), "-Mode", "encrypt"],
                             input=projection, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             env=env, timeout=30, check=False)
    history.need(process.returncode == 0 and not process.stderr, "schema")
    return validate_envelope(process.stdout, metadata, key)


def destination() -> Path:
    """Refuse symlink/reparse ancestors and require one exact root-local artifact."""
    root = Path(__file__).resolve().parents[2]
    parent = root / ".temp" / "private-provider-diag"
    for path in (root / ".temp", parent, parent / "capture.enc.json"):
        history.need(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(), "scope")
    parent.mkdir(parents=True, exist_ok=True)
    path = parent / "capture.enc.json"
    history.need(path.resolve().parent == parent.resolve(), "scope")
    return path


def run() -> None:
    """Validate source/first attempt before the one nonredirecting GraphQL POST."""
    sha = os.environ.get("GITHUB_SHA", "")
    history.need(os.environ.get("PRIVATE_CAPTURE_CONFIRM") == CONFIRM
                 and os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
                 and os.environ.get("GITHUB_REPOSITORY") == history.REPOSITORY
                 and os.environ.get("GITHUB_REF") == "refs/heads/" + history.BRANCH
                 and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
                 and re.fullmatch(r"[0-9a-f]{40}", sha) is not None
                 and sha == os.environ.get("PRIVATE_CAPTURE_REVIEWED_SHA")
                 and os.environ.get("ACTIONS_RUNNER_DEBUG", "").lower() != "true"
                 and os.environ.get("ACTIONS_STEP_DEBUG", "").lower() != "true", "identity")
    key = os.environ.get("PRIVATE_CAPTURE_PUBLIC_KEY", "")
    history.need(0 < len(key) <= 2048, "credential")
    metadata = {"source_sha": sha, "capture_run": os.environ.get("GITHUB_RUN_ID", ""),
                "capture_attempt": "1", "original_run": history.RUN, "original_attempt": history.ATTEMPT,
                "workflow": WORKFLOW, "repository": history.REPOSITORY,
                "query_sha256": hashlib.sha256(QUERY.encode()).hexdigest()}
    history.need(re.fullmatch(r"[1-9][0-9]{0,19}", metadata["capture_run"]) is not None, "identity")
    # Capability/key validation with synthetic data happens before credentials/read.
    encrypt(b'{"synthetic":true}', metadata, key)
    path = destination()
    history.need(not path.exists(), "scope")
    window = history.historical_window(os.environ.get("GITHUB_TOKEN", ""))
    zone, token = os.environ.get("CF_ZONE_ID", ""), os.environ.get("CF_OBSERVABILITY_TOKEN", "")
    history.need(re.fullmatch(r"[0-9a-f]{32}", zone) is not None and bool(token), "credential")
    body = json.dumps({"query": QUERY, "variables": {"zoneTag": zone,
        "start": window[0].isoformat(timespec="seconds").replace("+00:00", "Z"),
        "end": window[1].isoformat(timespec="seconds").replace("+00:00", "Z")}}).encode()
    request = urllib.request.Request(history.API, data=body, method="POST", headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        response = history.OPENER.open(request, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        status = response.code if isinstance(response, urllib.error.HTTPError) else response.status
        raw = response.read(history.MAX_BODY + 1)
    ciphertext = encrypt(project(status, raw), metadata, key)
    with path.open("xb") as file:
        file.write(ciphertext)


def main() -> int:
    """Suppress all arbitrary errors; cleanup only the verified exact ciphertext path."""
    try:
        if sys.argv[1:] == ["cleanup"]:
            path = destination()
            path.unlink(missing_ok=True)
            history.need(not path.exists(), "scope")
            print("private_provider_capture=CLEANED")
        else:
            history.need(not sys.argv[1:], "scope")
            run()
            print("private_provider_capture=ENCRYPTED delivery=UNVERIFIED")
        return 0
    except Exception:
        print("private_provider_capture=UNVERIFIED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
