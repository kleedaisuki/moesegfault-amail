"""Read back the accepted device backend before publishing its native client."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for directory in ("deploy", "operator", "provider", "ci"):
    sys.path.insert(0, str(ROOT / "infra" / directory))
import device_backend as backend


def github(path: str) -> Any:
    return json.loads(subprocess.check_output([
        "gh", "api", f"repos/kleedaisuki/moesegfault-amail/actions/{path}"
    ], text=True, cwd=ROOT))


def run() -> None:
    record: dict[str, Any] = json.loads((ROOT / "infra/release/device-backend.json").read_text())
    producer = github(f"runs/{record['run_id']}")
    if (producer["conclusion"] != "success" or producer["run_attempt"] != 1
            or producer["head_sha"] != record["source_sha"]
            or producer["head_branch"] != "main"
            or producer["path"] != ".github/workflows/ci.yml"):
        raise ValueError("device_backend_producer_unverified")
    subprocess.run(["git", "merge-base", "--is-ancestor", record["source_sha"], "HEAD"], cwd=ROOT, check=True)
    changed = subprocess.check_output([
        "git", "diff", "--name-only", record["source_sha"], "HEAD", "--",
        "Cargo.toml", "Cargo.lock", "rust-toolchain.toml", ".cargo", "crates", "workers"
    ], cwd=ROOT, text=True)
    if changed.strip():
        raise ValueError("device_backend_runtime_changed")
    artifacts = github(f"runs/{record['run_id']}/artifacts?per_page=100")["artifacts"]
    name = f"device-backend-production-{record['run_id']}"
    matches = [row for row in artifacts if row["name"] == name and not row["expired"]]
    if len(matches) != 1 or matches[0]["id"] != record["receipt_artifact_id"]:
        raise ValueError("device_backend_receipt_unverified")
    (ROOT / ".temp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="device-release-", dir=ROOT / ".temp") as folder:
        subprocess.run(["gh", "run", "download", str(record["run_id"]), "--name", name,
                        "--dir", folder], cwd=ROOT, check=True)
        receipt = backend.metadata(Path(folder) / "device-backend-production.json")
    expected = {"schema": "device-backend/v1", "realm": "production", "migration": 20,
                "source_sha": record["source_sha"], "run_id": str(record["run_id"]), "run_attempt": 1}
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError("device_backend_receipt_unverified")
    pins = {"amail-mail": receipt["api_version"],
            "amail-mail-maintenance": receipt["maintenance_version"],
            "amail-trace-sink": receipt["sink_version"]}
    actual, policy = backend.retained.observe("production", pins)
    digest = backend.retained.previous.prior.digest
    if (digest(actual["retained"]) != receipt["retained_fingerprint"]
            or digest(policy) != receipt["policy_fingerprint"]):
        raise ValueError("device_backend_retained_graph_changed")
    database = backend.DatabaseClient(os.environ["CLOUDFLARE_ACCOUNT_ID"],
                                      os.environ["CLOUDFLARE_API_TOKEN"], "production")
    backend.schema(database, "production", 20)
    backend.public_ready("production")
    print(json.dumps({"event": "device_backend_release_verified", "run_id": record["run_id"],
                      "api_version": receipt["api_version"], "migration": 20}))


if __name__ == "__main__":
    run()
