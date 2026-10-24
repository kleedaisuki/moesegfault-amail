"""Measure bounded offline CLI workloads using hosted release binaries.

All fixture setup, cleanup, and reports stay under the repository .temp directory.
Compare candidate and baseline on one runner; no timing threshold gates CI.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / ".temp" / "performance"
MANIFEST = "version=1\nfrom='a@mail.example.test'\nto=['b@example.test']\nsubject='Synthetic benchmark'\n"


def summary(samples: list[float]) -> dict[str, Any]:
    """Retain raw milliseconds and robust summaries for later fair comparisons."""
    median = statistics.median(samples)
    return {
        "samples_ms": samples,
        "median_ms": median,
        "p95_ms": sorted(samples)[math.ceil(len(samples) * 0.95) - 1],
        "mad_ms": statistics.median(abs(value - median) for value in samples),
    }


def fixture(directory: Path, size: int) -> Path:
    """Create a valid draft and inbound-compatible ZIP with owned synthetic data."""
    directory.mkdir()
    (directory / "manifest.toml").write_text(MANIFEST, encoding="utf-8")
    (directory / "body.txt").write_text("Synthetic body.\n" * (size // 16), encoding="utf-8")
    archive = directory.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        for path in directory.iterdir():
            output.write(path, path.name)
    return archive


def stop_daemon(binary: Path, home: Path, env: dict[str, str]) -> None:
    """Never remove a fixture home while its daemon can still write to it."""
    if not (home / "daemon.json").exists():
        return
    result: subprocess.CompletedProcess[bytes] = subprocess.run(
        [str(binary), "daemon", "stop"], env=env, cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=35, check=False)
    if result.returncode != 0:
        raise RuntimeError("benchmark daemon did not stop; fixture retained")


def run_case(binary: Path, args: list[str], home: Path, telemetry: bool,
             count: int, fresh: bool = False,
             prepare: Callable[[], object] | None = None) -> dict[str, Any]:
    """Time actual processes, excluding fixture setup and directory cleanup.

    Fresh means first-use application state, not a forced cold OS page cache.
    stdout/stderr are drained and discarded: artifacts never contain payloads.
    Pipes make timeout waiting event-driven instead of quantizing tiny process
    timings through POSIX wait(timeout)'s exponential polling sleeps.
    """
    env: dict[str, str] = os.environ.copy()
    env.update(AMAIL_HOME=str(home), AMAIL_API_BASE="https://mail.example.test",
               AMAIL_ISSUER="https://identity.example.test", AMAIL_CLIENT_ID="synthetic",
               AMAIL_TERMINAL_ID="amail-synthetic-benchmark")
    if telemetry:
        env.pop("AMAIL_TELEMETRY", None)
    else:
        env["AMAIL_TELEMETRY"] = "off"
    samples: list[float] = []
    codes: list[int] = []
    for iteration in range(count + 3):
        if fresh and home.exists():
            stop_daemon(binary, home, env)
            if not home.resolve().is_relative_to(SCRATCH.resolve()):
                raise ValueError("benchmark home must stay under repository scratch")
            shutil.rmtree(home)
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Explicit synthetic opt-in: benchmarking must not open hundreds of
        # consent pages or change the real user's authorization configuration.
        (home / "config.toml").write_text("yolo = true\n", encoding="utf-8")
        if prepare:
            prepare()
        started = time.perf_counter_ns()
        completed = subprocess.run([str(binary), *args], env=env, cwd=ROOT,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=10, check=False)
        elapsed = (time.perf_counter_ns() - started) / 1e6
        if iteration >= 3:
            samples.append(elapsed)
            codes.append(completed.returncode)
    success = all(code == 0 for code in codes)
    return {**summary(samples), "exit_codes": sorted(set(codes)),
            "status": "ok" if success else "unavailable_or_failed",
            "comparable": success,
            "telemetry": telemetry, "state": "fresh" if fresh else "warm"}


def measure(binary: Path, directory: Path) -> dict[str, Any]:
    """Use representative startup, journal, credential-status and ZIP workloads."""
    directory.mkdir()
    home = directory / "home"
    small = directory / "small"
    large = directory / "long-tail"
    small_zip = fixture(small, 4096)
    large_zip = fixture(large, 2 * 1024 * 1024)
    env: dict[str, str] = os.environ.copy()
    env.update(AMAIL_HOME=str(home), AMAIL_TERMINAL_ID="amail-synthetic-benchmark")
    cases: dict[str, Any] = {}
    try:
        for name, args in [("help", ["--help"]), ("version", ["--version"]),
                           ("config", ["config"]), ("auth_status", ["auth", "status"]),
                           ("discover", ["discover"])]:
            cases[name] = run_case(binary, args, home, False, 25)
        cases["config_telemetry_warm"] = run_case(binary, ["config"], home, True, 25)
        cases["config_telemetry_first_use"] = run_case(binary, ["config"], home, True, 9, fresh=True)
        for label, draft, archive in [("small", small, small_zip), ("long_tail", large, large_zip)]:
            packed = directory / "packed.zip"
            cases[f"pack_{label}"] = run_case(
                binary, ["pack", str(draft), "-o", str(packed)], home, False, 15,
                prepare=lambda: packed.unlink(missing_ok=True))
            unpacked = directory / "unpacked"
            cases[f"unpack_{label}"] = run_case(
                binary, ["unpack", str(archive), "-o", str(unpacked)], home, False, 15,
                prepare=lambda: shutil.rmtree(unpacked) if unpacked.exists() else None)
        return {"binary_bytes": binary.stat().st_size, "cases": cases,
                "approval": "explicit_synthetic_yolo"}
    finally:
        stop_daemon(binary, home, env)


def main() -> None:
    """Write one inspectable report; optionally pair the old binary on this host."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / ".temp"):
        parser.error("--output must stay under repository .temp")
    SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cli-", dir=SCRATCH) as temporary:
        temp = Path(temporary)
        report = {
            "schema": 1, "scope": "offline_process_elapsed", "warmup": 3,
            "environment": {"os": platform.system(), "release": platform.release(),
                            "arch": platform.machine(), "python": platform.python_version(),
                            "cpu_count": os.cpu_count(), "commit": os.environ.get("GITHUB_SHA")},
            "candidate": measure(args.binary.resolve(), temp / "candidate"),
        }
        if args.baseline:
            report["baseline"] = measure(args.baseline.resolve(), temp / "baseline")
            report["comparisons"] = {}
            for name, candidate in report["candidate"]["cases"].items():
                baseline = report["baseline"]["cases"][name]
                comparable = candidate["comparable"] and baseline["comparable"]
                report["comparisons"][name] = {
                    "comparable": comparable,
                    "candidate_over_baseline": candidate["median_ms"] / baseline["median_ms"]
                    if comparable else None,
                }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Offline performance report: {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
