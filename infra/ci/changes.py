"""Select affected source checks; accepted runtime bytes are not rebuilt for tooling edits."""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOURCE_TARGETS = frozenset({"checks", "staging", "staging-maintenance-repair", "production",
                            "production-api-only-maintenance", "production-fresh-bootstrap",
                            "production-fresh-online"})
SHARED = ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", ".cargo/")
WORKER_PROJECTS = ("crates/mail-worker", "workers/trace-sink", "workers/mail-ingress",
                   "workers/mail-events", "workers/identity-test-inbox", "workers/role-monitor")
QUEUE_PROJECTS = frozenset({"workers/trace-sink", "workers/mail-ingress", "workers/mail-events"})


@dataclass(frozen=True)
class Plan:
    cli: bool = False
    worker: bool = False
    site: bool = False
    infra: bool = False
    tests: tuple[str, ...] = ()
    python: tuple[str, ...] = ()
    native_static: bool = False
    worker_projects: tuple[str, ...] = ()


def worker_projects(paths: list[str]) -> tuple[str, ...]:
    if any(path in SHARED or path.startswith(".cargo/") for path in paths):
        return WORKER_PROJECTS
    selected = {project for project in WORKER_PROJECTS
                if any(path.startswith(project + "/") for path in paths)}
    if any(path.startswith("crates/trace-schema/") for path in paths):
        selected.update(("crates/mail-worker", "workers/trace-sink", "workers/role-monitor"))
    for path in paths:
        if not path.startswith("infra/tests/worker-boundary/"):
            continue
        if not path.endswith(".test.mjs") or Path(path).name == "trace-sink.test.mjs":
            selected.update(QUEUE_PROJECTS)
        if Path(path).name != "trace-sink.test.mjs":
            selected.add("crates/mail-worker")
    # The existing queue journey exercises the sink and lifecycle consumer together.
    if selected & QUEUE_PROJECTS:
        selected.update(QUEUE_PROJECTS)
    return tuple(project for project in WORKER_PROJECTS if project in selected)


def boundary_tests(projects: tuple[str, ...]) -> tuple[str, ...]:
    folder = ROOT / "infra/tests/worker-boundary"
    return tuple(path.name for path in sorted(folder.glob("*.test.mjs"))
                 if (path.name == "trace-sink.test.mjs" and bool(set(projects) & QUEUE_PROJECTS))
                 or (path.name != "trace-sink.test.mjs" and "crates/mail-worker" in projects))


def classify(paths: list[str], *, event: str, target: str = "", confirm: str = "") -> Plan:
    """Manual promotion consumes admitted evidence; source events examine only their delta."""
    if event == "workflow_dispatch":
        full = target in SOURCE_TARGETS and confirm != "RUN_PRODUCTION_V031"
        native_site = full and target != "staging-maintenance-repair"
        return Plan(cli=native_site, worker=full, site=native_site, infra=full,
                    worker_projects=WORKER_PROJECTS if full else ())
    shared = any(path in SHARED or path.startswith(".cargo/") for path in paths)
    cli = shared or any(path.startswith(("crates/amail/", "crates/trace-schema/")) for path in paths)
    projects = worker_projects(paths)
    site = any(path.startswith("site/") and path != "site/scripts/browser-acceptance.mjs" for path in paths)
    python = tuple(path for path in paths if path.endswith(".py") and (ROOT / path).is_file())
    tests = {path[:-3].replace("/", ".") for path in python
             if path.startswith("infra/tests/test_") and "/" not in path[len("infra/tests/"):]}
    for path in python:
        candidate = ROOT / "infra/tests" / ("test_" + Path(path).name)
        if candidate.is_file():
            tests.add("infra.tests." + candidate.stem)
    if ".github/workflows/ci.yml" in paths or "infra/ci/changes.py" in paths:
        tests.add("infra.tests.test_ci_changes")
    return Plan(cli=cli, worker=bool(projects), site=site, infra=bool(python or tests),
                tests=tuple(sorted(tests)), python=python, worker_projects=projects)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, timeout=30).strip()


def delta(event: dict[str, Any], kind: str, head: str) -> list[str]:
    """Synchronize compares the previous head, not every previously verified PR commit."""
    base = event.get("before")
    if kind == "pull_request" and not base:
        base = event.get("pull_request", {}).get("base", {}).get("sha")
    if not isinstance(base, str) or re.fullmatch(r"[0-9a-f]{40}", base) is None or set(base) == {"0"}:
        return git("ls-files").splitlines()
    return git("diff", "--name-only", base, head).splitlines()


def accepted_base(head: str) -> str | None:
    """A source-owned checkpoint is useful only after its actual source gates are verified."""
    record = ROOT / "infra/release/accepted-candidate.json"
    if not record.is_file():
        return None
    try:
        import accepted_staging_artifact as accepted
    except ImportError:
        return None
    value = json.loads(record.read_text(encoding="utf-8"))
    version = tomllib.loads((ROOT / "crates/amail/Cargo.toml").read_text(encoding="utf-8"))["package"]["version"]
    if value.get("schema") != "amail-accepted-candidate/v1":
        raise ValueError("accepted_checkpoint_invalid")
    if value.get("version") != version:
        return None
    source = accepted.producer(value["source_run"])
    if source["source_sha"] != value.get("source_sha"):
        raise ValueError("accepted_checkpoint_invalid")
    try:
        accepted.runtime_closure(source["source_sha"], head)
    except ValueError as error:
        if str(error) != "accepted_source_runtime_changed":
            raise
        return None
    return source["source_sha"]


def backend_base(head: str) -> str | None:
    """Backend acceptance does not replace the published native release's provenance."""
    path = ROOT / "infra/ci/accepted-backend.json"
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if (set(value) != {"schema", "source_run", "source_sha", "acceptance_run"}
            or value.get("schema") != "amail-accepted-backend/v1"):
        raise ValueError("accepted_backend_checkpoint_invalid")
    if value["source_run"] is None and value["source_sha"] is None and value["acceptance_run"] is None:
        return None
    import mail_backend_artifact as backend
    source = backend.producer(value["source_run"], value["acceptance_run"])
    if source["source_sha"] != value["source_sha"]:
        raise ValueError("accepted_backend_checkpoint_invalid")
    try:
        backend.accepted.runtime_closure(source["source_sha"], head)
    except ValueError as error:
        if str(error) != "accepted_source_runtime_changed":
            raise
        return None
    return source["source_sha"]


def emit(plan: Plan) -> None:
    values = {name: str(getattr(plan, name)).lower() for name in ("cli", "worker", "site", "infra", "native_static")}
    values.update(tests=json.dumps(plan.tests), python=json.dumps(plan.python))
    values.update(worker_projects=json.dumps(plan.worker_projects),
                  boundary_tests=json.dumps(boundary_tests(plan.worker_projects)))
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write("".join(f"{key}={value}\n" for key, value in values.items()))
    print("affected_checks=" + ",".join(name for name in ("cli", "worker", "site", "infra") if getattr(plan, name)))


def focused() -> None:
    for path in json.loads(os.environ.get("CHANGED_PYTHON", "[]")):
        ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)
    modules = json.loads(os.environ.get("AFFECTED_TESTS", "[]"))
    if not all(isinstance(module, str) and re.fullmatch(r"infra\.tests\.test_[a-z_0-9]+", module) for module in modules):
        raise ValueError("affected_test_module_invalid")
    if modules:
        subprocess.run(["python", "-m", "unittest", *modules, "-v"], cwd=ROOT, check=True)


def native_scope(head: str) -> bool:
    sys.path.insert(0, str(ROOT / "infra/release"))
    import native_patch
    try:
        return native_patch.applies(head)
    except ValueError:
        # Later source work at the same package version gets normal coverage,
        # never an error or a waiver from the historical focused release profile.
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "test"))
    args = parser.parse_args()
    if args.action == "test":
        focused()
        return
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    kind, head = os.environ["GITHUB_EVENT_NAME"], os.environ["GITHUB_SHA"]
    paths = [] if kind == "workflow_dispatch" else delta(event, kind, head)
    focused_native: bool = kind != "workflow_dispatch" and native_scope(head)
    base = (backend_base(head) or accepted_base(head)) if kind != "workflow_dispatch" and not focused_native else None
    if focused_native:
        affected: Plan = classify(paths, event=kind)
        # The tagged workflow builds all five changed binaries once, runs only
        # the reviewed patch tests, then gates publication on its native journey.
        plan = replace(affected, cli=False, native_static=True)
    elif base:
        # Exclude the accepted changes when their PR is later merged to main.
        changed = set(git("diff", "--name-only", base, head).splitlines())
        paths = [path for path in paths if path in changed]
        plan = classify(paths, event=kind)
        plan = replace(plan, cli=False)
    else:
        inputs = event.get("inputs", {})
        plan = classify(paths, event=kind, target=inputs.get("target", ""), confirm=inputs.get("confirm", ""))
    emit(plan)


if __name__ == "__main__":
    main()
