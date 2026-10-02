"""Admit a successful original tagged bundle for publication or site continuation.

Run from the main-only release recovery job. This reads GitHub metadata only;
artifact download and byte validation remain separate existing workflow steps.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

from verify_published_assets import REPOSITORY, SOURCE_DIGEST, TAG, TARGETS, expected_names


def validate(run: dict, jobs: list[dict], artifacts: list[dict], repository: str, tag: str, source: str, run_id: int) -> int:
    """Return one live bundle ID after binding the same-repository tag and jobs."""
    if (type(run.get("id")) is not int or run.get("id") != run_id
        or run.get("repository", {}).get("full_name") != repository
        or run.get("head_repository", {}).get("full_name") != repository
        or run.get("path") != ".github/workflows/release.yml"
        or run.get("event") != "push" or run.get("head_branch") != tag
        or run.get("head_sha") != source or run.get("status") != "completed"
        or run.get("conclusion") != "failure"):
        raise ValueError("untrusted recovery run")
    required = {"Verify release source", "Assemble and verify release bundle"} | {f"Build {target}" for target, _ in TARGETS}
    for name in required:
        matches = [job for job in jobs if job.get("name") == name]
        if len(matches) != 1 or matches[0].get("status") != "completed" or matches[0].get("conclusion") != "success":
            raise ValueError("original release bundle incomplete")
    if any(job.get("name") == "Publish GitHub Release" and job.get("conclusion") == "success" for job in jobs):
        raise ValueError("original release already published")
    matches = [artifact for artifact in artifacts if artifact.get("name") == f"release-bundle-{tag}"]
    if len(matches) != 1 or matches[0].get("expired") is not False or type(matches[0].get("id")) is not int or matches[0]["id"] <= 0:
        raise ValueError("original bundle unavailable")
    return matches[0]["id"]


def api(path: str, *, pages: bool = False):
    """Read authenticated GitHub JSON without printing bodies or CLI errors."""
    command = ["gh", "api", path] + (["--paginate", "--slurp"] if pages else [])
    return json.loads(subprocess.check_output(command, stderr=subprocess.DEVNULL, timeout=60))


def published_release_exists(repository: str, tag: str) -> bool:
    """Accept HTTP404 or exact public asset metadata, never claim byte integrity."""
    result = subprocess.run(["gh", "api", f"repos/{repository}/releases/tags/{tag}", "--include"], capture_output=True, text=True, timeout=60)
    if result.returncode == 1 and re.match(r"HTTP/[0-9.]+ 404\b", result.stdout):
        return False
    if result.returncode != 0 or not re.match(r"HTTP/[0-9.]+ 200\b", result.stdout):
        raise ValueError("release state not established")
    parts = result.stdout.replace("\r\n", "\n").split("\n\n", 1)
    if len(parts) != 2:
        raise ValueError("release response malformed")
    release = json.loads(parts[1])
    if not isinstance(release, dict) or release.get("tag_name") != tag or release.get("draft") is not False or release.get("prerelease") is not False:
        raise ValueError("release metadata mismatch")
    assets = release.get("assets")
    if not isinstance(assets, list) or len(assets) != 7 or any(not isinstance(asset, dict) or not isinstance(asset.get("name"), str) for asset in assets):
        raise ValueError("release assets malformed")
    if {asset["name"] for asset in assets} != expected_names(tag) | {"SHA256SUMS"}:
        raise ValueError("release asset names mismatch")
    return True


def main() -> int:
    """Export the artifact ID and existence flag; byte verification stays mandatory."""
    run_id = os.getenv("RECOVER_RUN_ID", "")
    repository = os.getenv("GITHUB_REPOSITORY", "")
    tag = os.getenv("RELEASE_TAG", "")
    source = os.getenv("RELEASE_SOURCE_SHA", "")
    try:
        if (os.getenv("GITHUB_EVENT_NAME") != "workflow_dispatch" or os.getenv("GITHUB_REF") != "refs/heads/main"
            or not re.fullmatch(r"[1-9][0-9]*", run_id) or not REPOSITORY.fullmatch(repository)
            or not TAG.fullmatch(tag) or not SOURCE_DIGEST.fullmatch(source)):
            raise ValueError("invalid recovery request")
        base = f"repos/{repository}/actions/runs/{run_id}"
        run = api(base)
        jobs = [job for page in api(f"{base}/jobs?filter=latest&per_page=100", pages=True) for job in page["jobs"]]
        artifacts = [artifact for page in api(f"{base}/artifacts?per_page=100", pages=True) for artifact in page["artifacts"]]
        artifact_id = validate(run, jobs, artifacts, repository, tag, source, int(run_id))
        exists = published_release_exists(repository, tag)
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"artifact_id={artifact_id}\n")
            output.write(f"release_exists={str(exists).lower()}\n")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError, OSError, subprocess.SubprocessError):
        print("release_recovery=denied", file=sys.stderr)
        return 1
    print("release_recovery=admitted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
