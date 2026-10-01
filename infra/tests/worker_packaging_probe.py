"""Inspect pinned Wrangler output without deploying or qualifying a release.

Reuse only a successful full CI artifact at the exact PR base SHA, then prove
that the checkout differs solely in this diagnostic's public source/docs. The
original manifest context is retained; no ordinary admission rule is extended.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
from native_fixture import api
from validated_worker_build import identity
import worker_artifact as artifact

FOLDER = ROOT / ".temp/ci/packaging-probe"
STATE = FOLDER / "source.json"
DIAGNOSTIC = {".github/workflows/worker-packaging-probe.yml", "infra/tests/worker_packaging_probe.py",
              "infra/tests/worker-packaging-probe.mjs", "infra/tests/test_worker_packaging_probe.py"}
PRODUCTS = {"mail_api": "crates/mail-worker", "trace_sink": "workers/trace-sink",
            "mail_ingress": "workers/mail-ingress", "mail_events": "workers/mail-events",
            "identity_inbox": "workers/identity-test-inbox", "role_monitor": "workers/role-monitor"}


def changed_inputs(paths: list[str]) -> list[str]:
    """Only this probe and public Markdown may differ from original source evidence."""
    return [path for path in paths if not (path in DIAGNOSTIC or path == "README.md"
            or path.startswith(("docs/", ".agents/skills/")) and path.endswith(".md"))]


def prepare(sha: str) -> None:
    """Choose immutable bytes from exact-base full main CI, never merely a green producer."""
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("exact_pr_base_sha_required")
    diff = subprocess.run(["git", "diff", "--name-only", "-z", sha, "HEAD", "--"],
                          cwd=ROOT, capture_output=True, check=True, timeout=30).stdout
    if (len(diff) > 8 * 1024 * 1024 or diff and not diff.endswith(b"\0")
            or changed_inputs(diff.decode("utf-8").split("\0")[:-1])):
        raise ValueError("diagnostic_changed_compilation_or_unknown_input")
    runs = api(f"workflows/ci.yml/runs?branch=main&event=push&status=success&head_sha={sha}&per_page=100")
    if runs.get("total_count") != len(runs.get("workflow_runs", [])):
        raise ValueError("complete_original_run_inventory_required")
    matches = [run for run in runs["workflow_runs"] if run.get("head_sha") == sha]
    if len(matches) != 1:
        raise ValueError("unique_successful_exact_base_run_required")
    run = matches[0]
    value = identity(run, api(f"runs/{run['id']}/attempts/{run['run_attempt']}/jobs?per_page=100"),
                     api(f"runs/{run['id']}/artifacts?per_page=100"), sha)
    value["probe_sha"] = os.environ["GITHUB_SHA"]
    FOLDER.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(value), encoding="utf-8")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"artifact_id={value['artifact_id']}\nbuild_run_id={value['run_id']}\n")
    print(json.dumps({"event": "packaging_probe_source_selected", **value}, sort_keys=True))


def restore() -> None:
    """Verify the original compiler/run/source and file hashes without inventing a new build."""
    value = json.loads(STATE.read_text(encoding="utf-8"))
    if value["probe_sha"] != os.environ["GITHUB_SHA"]:
        raise ValueError("probe_source_changed")
    env = {**os.environ, "GITHUB_SHA": value["source_sha"], "GITHUB_RUN_ID": value["run_id"],
           "GITHUB_RUN_ATTEMPT": str(value["run_attempt"])}
    subprocess.run([sys.executable, str(ROOT / "infra/ci/worker_artifact.py"), "restore"],
                   cwd=ROOT, env=env, check=True, timeout=60)


def command(config: Path, destination: Path, realm: str) -> list[str]:
    """Always request credential-free packaging, never a deployment submission."""
    result = ["wrangler", "deploy", "--dry-run", "--config", str(config),
              "--outdir", str(destination), "--metafile", str(destination / "meta.json")]
    return result + (["--env", "staging"] if realm == "staging" else [])


def packaged(folder: Path, expected_wasm: str) -> dict:
    """Require a complete single bundled JS/Wasm graph; unknown layouts fail visibly."""
    files = sorted(path for path in folder.rglob("*") if path.is_file())
    if any(path.is_symlink() for path in folder.rglob("*")) or sum(path.stat().st_size for path in files) > artifact.LIMIT:
        raise ValueError("packaged_tree_invalid")
    wasm = [path for path in files if path.suffix == ".wasm"]
    entries = [path for path in files if path.suffix in (".js", ".mjs")]
    if len(wasm) != 1 or len(entries) != 1 or hashlib.sha256(wasm[0].read_bytes()).hexdigest() != expected_wasm:
        raise ValueError("packaged_wasm_or_entry_graph_mismatch")
    return {"entry": entries[0].relative_to(ROOT).as_posix(),
            "wasm": wasm[0].relative_to(ROOT).as_posix(), "wasm_sha256": expected_wasm,
            "files": {path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in files}}


def package() -> None:
    """Compare real dry-run output with verified inputs and retain timing/transform facts."""
    if any(value for name, value in os.environ.items() if name.startswith(("CLOUDFLARE_", "CF_"))):
        raise ValueError("provider_capability_refused")
    original = artifact.files(artifact.FOLDER)
    if artifact.files(ROOT) != original:
        raise ValueError("restored_generated_inputs_changed")
    version = subprocess.run(["wrangler", "--version"], capture_output=True, text=True, check=True, timeout=30)
    if not re.search(r"\b4\.142\.0\b", version.stdout):
        raise ValueError("pinned_wrangler_required")
    receipt = {"schema": "worker-packaging-probe/v1", **json.loads(STATE.read_text()),
               "wrangler": "4.142.0", "diagnostic_only": True, "packages": []}
    for component, product in PRODUCTS.items():
        config = ROOT / product / "wrangler.toml"
        value = tomllib.loads(config.read_text(encoding="utf-8"))
        if "build" in value or any("build" in env for env in value.get("env", {}).values()):
            raise ValueError("custom_build_refused")
        expected = [digest for name, digest in original.items() if name.startswith(product + "/build/") and name.endswith(".wasm")]
        if len(expected) != 1:
            raise ValueError("unique_original_wasm_required")
        # Default is production for Mail products but staging-only for the inbox;
        # keep the actual config selection rather than inventing a production realm.
        for realm in ("default", "staging") if "staging" in value.get("env", {}) else ("default",):
            destination = FOLDER / f"{component}-{realm}"
            destination.mkdir(exist_ok=False)
            started = time.monotonic()
            result = subprocess.run(command(config, destination, realm), cwd=config.parent,
                                    capture_output=True, text=True, timeout=120, check=False)
            if result.returncode:
                # Source-only configuration/bundler diagnostics, never provider credentials.
                print(result.stdout[-8192:])
                print(result.stderr[-8192:])
                raise ValueError(f"dry_run_failed: {component}/{realm}/exit={result.returncode}")
            entry = packaged(destination, expected[0])
            entry.update(component=component, realm=realm, duration_ms=int((time.monotonic() - started) * 1000),
                         config_sha256=hashlib.sha256(config.read_bytes()).hexdigest(),
                         tested_generated_js_identical=any(digest == entry["files"][Path(entry["entry"]).name]
                                                          for name, digest in original.items() if name.endswith((".js", ".mjs"))))
            receipt["packages"].append(entry)
    if artifact.files(ROOT) != original:
        raise ValueError("packaging_modified_original_generated_inputs")
    (FOLDER / "packages.json").write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))


def main() -> None:
    """Hosted diagnostics only; no Rust compile, provider capability or release verdict."""
    if os.getenv("GITHUB_ACTIONS") != "true":
        raise SystemExit("Packaging probes belong on GitHub-hosted runners.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "restore", "package"))
    parser.add_argument("--base-sha", default="")
    args = parser.parse_args()
    prepare(args.base_sha) if args.operation == "prepare" else restore() if args.operation == "restore" else package()


if __name__ == "__main__":
    main()
