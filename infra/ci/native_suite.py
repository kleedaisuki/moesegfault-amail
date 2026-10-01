"""Execute one fixed native suite on its own GitHub-hosted runner.

GitHub's matrix owns concurrency and cancellation. This helper selects the
existing package command, preserves TAP diagnostics and records timing/counts.
It does not build Rust, contact providers, classify mail or authorize deployment.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
BOUNDARY = ROOT / "infra/tests/worker-boundary"
SUITES = {"core": ("test", 102), "entry": ("test:entry-split", 7),
          "liveness": ("test:maintenance-liveness", 6), "accepted": ("test:accepted-stage", 9),
          "routing": ("test:routing-deadline", 7), "embedding": ("test:embedding-deadline", 6),
          "diagnostics": ("test:maintenance-diagnostics", 13), "budget": ("test:outbound-budget", 1)}


def command(suite: str) -> list[str]:
    """Reuse the package's test files without arbitrary shell execution or flags."""
    script, _ = SUITES[suite]
    value = json.loads((BOUNDARY / "package.json").read_text(encoding="utf-8"))["scripts"][script].split()
    if (value[:2] != ["node", "--test"] or len(value) < 3 or len(value) != len(set(value))
            or any(not re.fullmatch(r"[a-z0-9-]+\.test\.mjs", name) for name in value[2:])):
        raise ValueError("suite_command_invalid")
    return value


def counts(output: str, minimum: int) -> dict[str, int]:
    """An exit code alone cannot silently accept missing, skipped or cancelled tests."""
    result = {}
    for field in ("tests", "pass", "fail", "cancelled", "skipped", "todo"):
        values = re.findall(r"^# " + field + r" ([0-9]+)$", output, re.MULTILINE)
        if len(values) != 1:
            raise ValueError(f"suite_summary_missing: {field}")
        result[field] = int(values[0])
    if (result["tests"] < minimum or result["pass"] != result["tests"]
            or any(result[name] for name in ("fail", "cancelled", "skipped", "todo"))):
        raise ValueError("suite_incomplete: " + json.dumps(result, sort_keys=True))
    return result


def main() -> int:
    """Emit a source/run-bound suite receipt and preserve normal Node diagnostics."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=SUITES)
    suite = parser.parse_args().suite
    if os.getenv("GITHUB_ACTIONS") != "true":
        raise SystemExit("Native project tests belong on GitHub-hosted runners.")
    started = time.monotonic()
    receipt = {"schema": "native-suite/v1", "suite": suite, "source_sha": os.getenv("GITHUB_SHA"),
               "run_id": os.getenv("GITHUB_RUN_ID"), "result": "failed"}
    try:
        result = subprocess.run(command(suite), cwd=BOUNDARY, capture_output=True, text=True,
                                timeout=900, check=False)
        print(result.stdout, end="")
        print(result.stderr, end="")
        receipt["exit_code"] = result.returncode
        receipt.update(counts(result.stdout, SUITES[suite][1]))
        if result.returncode:
            raise ValueError("suite_failed")
        receipt["result"] = "passed"
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        receipt["error_type"] = type(error).__name__
        # Suite commands/results contain synthetic tests and public source only,
        # not mail/user/provider inputs. Preserve their useful debugging context.
        receipt["message"] = str(error)
    receipt["duration_ms"] = int((time.monotonic() - started) * 1000)
    folder = ROOT / ".temp/ci"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"native-{suite}.json").write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as file:
            file.write(f"## Native suite: {suite}\n\n"
                       f"Result: **{receipt['result']}**, duration: **{receipt['duration_ms']} ms**.\n\n"
                       f"Tests: {receipt.get('tests', 'unreported')}; passed: {receipt.get('pass', 'unreported')}.\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
