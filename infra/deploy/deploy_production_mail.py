"""Deploy production Mail once with private secrets and only an exact recovery pin."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from check_production_role_graph import ROOT
from trace_rollout_attestation import UUID


def main() -> int:
    """Never replay or print an ambiguous deployment; cleanup secret material always."""
    path = None
    try:
        if os.getenv("GITHUB_REF") != "refs/heads/main" or not os.getenv("GITHUB_OUTPUT"):
            raise ValueError("context_unverified")
        names = ("OPENROUTER_API_KEY", "CF_EMAIL_ROUTING_TOKEN", "INGRESS_SECRET")
        secrets = {name: os.getenv(name, "") for name in names}
        if not all(secrets.values()):
            raise ValueError("secrets_unverified")
        (ROOT / ".temp").mkdir(exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix="production-mail-secrets-", suffix=".json", dir=ROOT / ".temp")
        path = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            path.chmod(0o600)
            json.dump(secrets, destination)
        result = subprocess.run(["wrangler", "deploy", "--secrets-file", str(path)],
                                cwd=ROOT / "crates/mail-worker", capture_output=True,
                                text=True, timeout=600, check=False)
        versions = re.findall(r"Current Version ID:\s*(" + UUID.pattern.removesuffix(r"\Z") + r")(?=\s|$)", result.stdout + result.stderr)
        if len(versions) == 1:
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as destination:
                destination.write(f"version={versions[0]}\n")
            print(f"production_api_deployment=recovery_version_captured version={versions[0]}")
        if result.returncode or len(result.stdout) + len(result.stderr) > 1048576 or len(versions) != 1:
            raise ValueError("deployment_unverified")
    except (ValueError, OSError, subprocess.TimeoutExpired):
        print("production_api_deployment=UNVERIFIED")
        return 1
    finally:
        if path is not None:
            path.unlink(missing_ok=True)
    print("production_api_deployment=version_captured")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
