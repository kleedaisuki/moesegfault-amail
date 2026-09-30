"""Fingerprint the Worker check build contract, never unrelated dispatch jobs.

The supported layout is intentionally narrow. Unsupported inherited settings or
dynamic build inputs disable project-cache reuse, not source tests. Run this on
a clean hosted checkout: ``python infra/ci/worker_cache_key.py`` emits only
GitHub-output assignments. Deployment jobs do not consume this cache.
"""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/tests"))
from workflow_source import job_block  # noqa: E402


# Git object identities cover project code, external boundary inputs and the
# fingerprint implementation itself. Optional root build config is absence-bound.
REQUIRED = (
    "Cargo.toml", "Cargo.lock", "crates", "workers",
    "infra/tests/worker-boundary", "infra/ci/worker_cache_key.py",
    "infra/tests/workflow_source.py",
)
OPTIONAL = (".cargo", "rust-toolchain", "rust-toolchain.toml")
TOP_LEVEL = {"name", "run-name", "on", "permissions", "concurrency", "jobs"}
# Only these existing cache/tool steps may depend on execution state. New
# conditional build/setup steps must disable reuse until explicitly reviewed.
STEP_GUARDS = {
    "Install workers-rs bundler": "steps.worker-bundler-cache.outputs.cache-hit != 'true'",
    "Save trusted exact Worker check build cache": (
        "github.event_name == 'push' && (github.ref == 'refs/heads/main' || "
        "github.ref == 'refs/heads/codex/amail-v0.1.0') && "
        "steps.worker-cache-key.outputs.cacheable == 'true' && "
        "steps.worker-check-cache.outputs.cache-hit != 'true'"
    ),
    "Save trusted pinned check bundler": (
        "github.event_name == 'push' && (github.ref == 'refs/heads/main' || "
        "github.ref == 'refs/heads/codex/amail-v0.1.0') && "
        "steps.worker-bundler-cache.outputs.cache-hit != 'true'"
    ),
}
STEP_OPERATIONS = {
    "Install workers-rs bundler": '        run: cargo install worker-build --version 0.8.5 --locked --root "$GITHUB_WORKSPACE/.cache/worker-build-check"',
    "Save trusted exact Worker check build cache": "        uses: actions/cache/save@v4",
    "Save trusted pinned check bundler": "        uses: actions/cache/save@v4",
}


def execution_without_cache_guards(source: str) -> str:
    """Remove only exact existing cache guards; reject all other conditions."""
    result = []
    for block in re.split(r"(?m)(?=^      - )", source):
        lines = block.splitlines()
        # Support only the current name/uses-first layout. In particular,
        # ``- if: expression`` is a real GitHub condition, not literal text.
        if block.startswith("      - ") and not re.match(r"      - (?:name|uses): \S", block):
            raise ValueError("unsupported step-first layout")
        conditions = [line for line in lines if re.match(r"^ +(?:- +)?(?:if|\"if\"|'if')[ \t]*:", line)]
        if conditions:
            step = lines[0].removeprefix("      - name: ")
            guard = STEP_GUARDS.get(step)
            if guard is None or conditions != ["        if: " + guard] or STEP_OPERATIONS[step] not in lines:
                raise ValueError("unsupported conditional build step")
        result.extend(line for line in lines if line not in conditions)
    return "\n".join(result)


def workflow_contract(source: str) -> str:
    """Return the whole Worker job and supported inherited permissions.

    Global env/defaults or unknown top-level fields require a future explicit
    contract extension; until then they produce a fresh miss for every run.
    Anchors/aliases and dynamic build metadata are likewise unsupported because
    their meaning can originate outside the isolated Worker block.
    """
    source = source.replace("\r\n", "\n")
    sections = {}
    current = None
    for line in source.splitlines(keepends=True):
        if not line.strip() or line.lstrip().startswith("#"):
            if current:
                sections[current] += line
            continue
        if "\t" in line[:len(line) - len(line.lstrip())]:
            raise ValueError("unsupported indentation")
        if not line.startswith(" "):
            match = re.fullmatch(r"([a-z][a-z-]*):[^\n]*\n?", line)
            if not match or match.group(1) not in TOP_LEVEL:
                raise ValueError("unsupported inherited field")
            current = match.group(1)
            if current in sections:
                raise ValueError("duplicate top-level field")
            sections[current] = line
        elif current:
            sections[current] += line
        else:
            raise ValueError("unsupported header")
    worker = job_block(source, "worker").rstrip()
    inherited = sections.get("permissions", "permissions: absent").rstrip()
    # Do not resolve YAML indirection or expressions whose runtime values are
    # absent from the source key. Existing cache/guard expressions are static
    # orchestration; runtime build metadata must remain literal.
    for block in (worker, inherited):
        if re.search(r"(?:^|\s)[&*][A-Za-z_]|(?:^|\s)<<:", block):
            raise ValueError("unsupported YAML indirection")
    if "${{" in inherited:
        raise ValueError("dynamic permissions")
    # An input reference is allowed in the job predicate only. Other runtime
    # dispatch-dependent build commands cannot share a source-only key.
    without_guard = re.sub(r"(?m)^    if:.*\n(?:      .*\n)*", "", worker + "\n", count=1)
    if re.search(r"\binputs\.", without_guard):
        raise ValueError("dynamic dispatch build inputs")
    execution = execution_without_cache_guards(without_guard)
    expressions = re.findall(r"\$\{\{(.*?)\}\}", execution)
    allowed = re.compile(r"(?:steps\.worker-(?:cache-key|check-cache|bundler-cache)\.outputs\.[a-z-]+|runner\.(?:os|arch))")
    if any(not allowed.fullmatch(item.strip()) for item in expressions):
        raise ValueError("dynamic execution expression")
    if re.search(r"\b(?:GITHUB_(?:SHA|REF|EVENT|RUN|HEAD_REF|BASE_REF)|INPUT_)[A-Z_]*\b", execution):
        raise ValueError("dynamic execution context")
    return inherited + "\nworker:\n" + worker


def git_text(args: list[str]) -> str:
    """Read committed identities/source without exposing Git error messages."""
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=15,
        check=False,
    )
    if result.returncode:
        raise ValueError("committed inputs unavailable")
    return result.stdout


def source_key(contract: str, identities: dict[str, str]) -> str:
    """Hash an unambiguous ordered representation of every declared input."""
    if set(identities) != set(REQUIRED + OPTIONAL):
        raise ValueError("source identities incomplete")
    if any(not re.fullmatch(r"[0-9a-f]{40,64}", identities[name]) for name in REQUIRED):
        raise ValueError("required source identity invalid")
    if any(identities[name] != "absent" and not re.fullmatch(r"[0-9a-f]{40,64}", identities[name]) for name in OPTIONAL):
        raise ValueError("optional source identity invalid")
    payload = json.dumps([contract, identities], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def committed_key() -> str:
    """Project only committed Worker layout and exact input object identities."""
    contract = workflow_contract(git_text(["show", "HEAD:.github/workflows/ci.yml"]))
    records = git_text(["ls-tree", "-z", "HEAD", "--", *REQUIRED, *OPTIONAL])
    identities = {name: "absent" for name in OPTIONAL}
    for record in records.split("\0"):
        if not record:
            continue
        metadata, name = record.split("\t", 1)
        mode, kind, identity = metadata.split(" ")
        if name not in REQUIRED + OPTIONAL or mode not in ("100644", "100755", "040000") or kind not in ("blob", "tree"):
            raise ValueError("unsupported committed input")
        identities[name] = identity
    # ls-tree's path arguments are root-limited; retrieve nested blobs/trees
    # explicitly instead of treating their absence in its root output as valid.
    for name in REQUIRED:
        if name not in identities:
            identities[name] = git_text(["rev-parse", f"HEAD:{name}"]).strip()
    return source_key(contract, identities)


def output_key() -> tuple[str, bool]:
    """Unsupported layouts miss uniquely and are never written back to cache."""
    try:
        return committed_key(), True
    except (ValueError, OSError, subprocess.SubprocessError):
        return "uncacheable-" + uuid.uuid4().hex, False


def main() -> None:
    """Emit bounded cache outputs; never print source or exception contents."""
    key, cacheable = output_key()
    print(f"source={key}")
    print(f"cacheable={'true' if cacheable else 'false'}")


if __name__ == "__main__":
    main()
