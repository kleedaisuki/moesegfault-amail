"""Read-only GitHub source/release preflight for a main-only candidate deploy.

Required environment: GH_TOKEN, GITHUB_REPOSITORY, GITHUB_SHA, GITHUB_REF,
SOURCE_CI_RUN_ID. No Mail, D1, sending policy or Cloudflare state is accessed.
The contents:read token checks public publication state, not draft inventory.
"""

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def github(path, allow_missing=False):
    """Read a fixed API route; explicit 404 means no token-visible resource.

    In particular, a Release 404 does not prove absence of an internal draft.
    The candidate contract excludes public tags/published Releases, not drafts.
    """
    request = Request(
        f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/{path}",
        headers={
            "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        if allow_missing and error.code == 404:
            return None
        raise ValueError("GitHub preflight request rejected") from None
    except (URLError, OSError, ValueError):
        raise ValueError("GitHub preflight request unavailable") from None


def check_run(run, workflow_id, sha):
    """Require completed successful CI for this exact main or trusted push source."""
    if (
        run.get("workflow_id") != workflow_id
        or run.get("head_sha") != sha
        or run.get("head_branch") not in ("main", "codex/amail-v0.1.0")
        or run.get("event") not in ("push", "workflow_dispatch")
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
    ):
        raise ValueError("exact-source successful hosted CI run required")


def check_release(release):
    """Reject published Release state, without claiming internal drafts are absent."""
    if release is None:
        return
    if not isinstance(release, dict) or not isinstance(release.get("draft"), bool):
        raise ValueError("GitHub Release publication metadata invalid")
    if not release["draft"]:
        raise ValueError("v0.1.0 published Release exists; candidate deployment forbidden")


def main():
    """Reject public tag/published Release and unverified source with read access."""
    try:
        if os.environ.get("GITHUB_REF") != "refs/heads/main":
            raise ValueError("production candidate deploy requires main")
        sha = os.environ.get("GITHUB_SHA", "")
        run_id = os.environ.get("SOURCE_CI_RUN_ID", "")
        if not re.fullmatch(r"[0-9a-f]{40}", sha) or not re.fullmatch(r"[1-9][0-9]*", run_id):
            raise ValueError("full source SHA and numeric source CI run ID required")
        workflow = github("actions/workflows/ci.yml")
        check_run(github(f"actions/runs/{run_id}"), workflow["id"], sha)
        jobs = github(f"actions/runs/{run_id}/jobs?per_page=100&filter=latest")
        site_jobs = [job for job in jobs["jobs"] if job.get("name") == "Astro release site"]
        if len(site_jobs) != 1 or site_jobs[0].get("conclusion") != "success":
            raise ValueError("exact-source Astro CI job must have passed, not skipped")
        # Any tag blocks a candidate downgrade, including an in-flight release.
        if github("git/ref/tags/v0.1.0", allow_missing=True) is not None:
            raise ValueError("v0.1.0 tag exists; use the gated published-site lane")
        # Read access cannot inventory untagged drafts. A hidden draft is not a
        # published Release and does not make truthful candidate copy incorrect.
        check_release(github("releases/tags/v0.1.0", allow_missing=True))
    except (KeyError, ValueError) as error:
        message = str(error) if isinstance(error, ValueError) else "required GitHub metadata unavailable"
        raise SystemExit(f"candidate_site_gate: {message}") from None
    print("candidate_site_gate=ready source_ci=passed published_release=not_visible tag=absent")


if __name__ == "__main__":
    main()
