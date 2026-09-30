"""Deploy the private sink while retaining only its exact generated version pin."""
from __future__ import annotations
import argparse
import os
import re
import subprocess
import sys

UUID = r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"


def deploy(target: str) -> str:
    """Never retry an ambiguous deployment or expose provider/build output."""
    command = ["wrangler", "deploy"]
    if target == "staging":
        command.extend(["--env", "staging"])
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=600)
    if result.returncode or len(result.stdout) + len(result.stderr) > 1_048_576:
        raise ValueError("deployment_unverified")
    versions = re.findall(r"Current Version ID:\s*(" + UUID + r")(?=\s|$)", result.stdout + result.stderr)
    if len(versions) != 1:
        raise ValueError("deployment_unverified")
    return versions[0]


def main() -> int:
    """Write the exact pin to GitHub step outputs; print only a fixed result."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, choices=("staging", "production"))
    args = parser.parse_args()
    try:
        output = os.environ.get("GITHUB_OUTPUT")
        if not output:
            raise ValueError("outputs_missing")
        version = deploy(args.target)
        with open(output, "a", encoding="utf-8") as destination:
            destination.write(f"version={version}\n")
    except (ValueError, OSError, subprocess.TimeoutExpired):
        print("trace_sink_deployment=UNVERIFIED", file=sys.stderr)
        return 1
    print("trace_sink_deployment=version_captured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
