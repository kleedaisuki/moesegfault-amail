"""Select expensive PR source checks conservatively; never qualify a release.

Main/push/manual runs stay full. Infrastructure contracts always run. Unknown,
shared or workflow inputs request every expensive component. Failure to inspect
GitHub metadata or the complete Git diff falls back to full rather than skipping.
"""

import json
import os
from pathlib import Path
import re
import subprocess

COMPONENTS = ("cli", "worker", "site")
# Exact infrastructure/diagnostic consumers covered by mandatory hosted Python
# contracts and the independent workflow syntax guard, not build/native inputs.
# Do not generalize to *.py or workflows: build generators and source/release
# admission policy must continue to request full checks.
INFRASTRUCTURE_ONLY = {
    "crates/mail-worker/check_trace_sink_isolation.py",
    ".github/workflows/native-fixture.yml",
    ".github/workflows/native-tracing-canary.yml",
    "infra/ci/native_fixture.py",
}


def select(paths: list[str]) -> dict[str, bool]:
    """Map complete changed paths to consumers; additions/deletions use the same rule."""
    result = dict.fromkeys(COMPONENTS, False)
    for path in paths:
        if path in INFRASTRUCTURE_ONLY:
            continue
        if path.startswith("crates/amail/"):
            result["cli"] = True
        elif path.startswith(("crates/mail-worker/", "crates/trace-schema/", "workers/",
                              "infra/tests/worker-boundary/")):
            result["worker"] = True
        elif path.startswith("site/"):
            result["site"] = True
        elif path.startswith("infra/ci/") or path == "infra/tests/workflow_source.py":
            return dict.fromkeys(COMPONENTS, True)
        elif path.startswith("infra/"):
            # Python/provider/deployment contracts run in the existing mandatory
            # infrastructure job; they are not Rust or Astro compilation inputs.
            continue
        elif (path == "README.md" or path.startswith(("docs/", ".agents/skills/"))) and path.endswith(".md"):
            continue
        else:
            # Cargo/workspace/toolchain/workflow/shared/unknown changes fail full.
            return dict.fromkeys(COMPONENTS, True)
    return result


def current_scope() -> dict[str, bool]:
    """Read a complete NUL-delimited committed diff; never interpolate PR paths into shell."""
    full = dict.fromkeys(COMPONENTS, True)
    if os.getenv("GITHUB_EVENT_NAME") != "pull_request":
        return full
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        pull = event["pull_request"]
        base, head = pull["base"]["sha"], pull["head"]["sha"]
        if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value) for value in (base, head)):
            return full
        result = subprocess.run(["git", "diff", "--name-only", "-z", base, head, "--"],
                                capture_output=True, timeout=30, check=False)
        if result.returncode or len(result.stdout) > 8 * 1024 * 1024:
            return full
        if result.stdout and not result.stdout.endswith(b"\0"):
            return full
        paths = result.stdout.decode("utf-8").split("\0")[:-1]
        return select(paths)
    except (KeyError, TypeError, ValueError, OSError, subprocess.TimeoutExpired):
        return full


def main() -> None:
    """Emit only three fixed GitHub output assignments, no raw filenames or event payload."""
    for name, enabled in current_scope().items():
        print(f"{name}={str(enabled).lower()}")


if __name__ == "__main__":
    main()
