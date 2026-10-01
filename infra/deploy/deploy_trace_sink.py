"""Deploy the private sink while retaining only its exact generated version pin."""
from __future__ import annotations
import argparse
import os
import subprocess
import sys

from tested_worker_artifact import require_artifact
from worker_deploy_result import DeploymentFailure, submit


def deploy(target: str) -> str:
    """Never retry an ambiguous deployment or expose provider/build output."""
    if target not in ("production", "staging"):
        raise ValueError("realm_unreviewed")
    require_artifact("trace_sink")
    command = ["wrangler", "deploy"]
    if target == "staging":
        command.extend(["--env", "staging"])
    return submit(command, target, "trace_sink")


def main() -> int:
    """Write the exact pin to GitHub step outputs; print only a fixed result."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, choices=("staging", "production"))
    args = parser.parse_args()
    try:
        output = os.environ.get("GITHUB_OUTPUT")
        if not output:
            raise ValueError("outputs_missing")
        try:
            version = deploy(args.target)
        except DeploymentFailure as error:
            if error.version is not None:
                with open(output, "a", encoding="utf-8") as destination:
                    destination.write(f"version={error.version}\n")
                print(f"trace_sink_deployment=recovery_version_captured version={error.version}")
            raise
        with open(output, "a", encoding="utf-8") as destination:
            destination.write(f"version={version}\n")
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired):
        print("trace_sink_deployment=UNVERIFIED", file=sys.stderr)
        return 1
    print("trace_sink_deployment=version_captured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
