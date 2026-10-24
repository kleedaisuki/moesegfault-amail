"""Exercise the hosted native daemon/profile journey without credentials or network.

Homes remain private under repository .temp and are removed after daemon shutdown.
Only fixed case labels are printed; endpoint capabilities are never artifacts.
"""

from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any
import uuid

ROOT: Path = Path(__file__).resolve().parents[1]


class Journey:
    def __init__(self, binary: Path, home: Path) -> None:
        self.binary: Path = binary
        self.home: Path = home
        self.terminals: dict[str, str] = {name: str(uuid.uuid4()) for name in ("a", "b")}

    def environment(self, terminal: str) -> dict[str, str]:
        env: dict[str, str] = os.environ.copy()
        env.update(AMAIL_HOME=str(self.home), AMAIL_TELEMETRY="off",
                   AMAIL_TERMINAL_ID=self.terminals[terminal],
                   AMAIL_API_BASE="https://mail.example.test",
                   AMAIL_ISSUER="https://identity.example.test", AMAIL_CLIENT_ID="synthetic")
        return env

    def command(self, terminal: str, *args: str, success: bool = True) -> dict[str, Any]:
        completed: subprocess.CompletedProcess[str] = subprocess.run(
            [str(self.binary), *args], cwd=ROOT, env=self.environment(terminal), capture_output=True,
            text=True, timeout=35, check=False)
        if (completed.returncode == 0) != success:
            raise AssertionError(f"{' '.join(args[:2])}: unexpected exit {completed.returncode}")
        if not success:
            return {}
        value: Any = json.loads(completed.stdout)
        if not isinstance(value, dict):
            raise AssertionError("CLI command must return one JSON object")
        return value

    def profiles(self, terminal: str) -> dict[str, dict[str, Any]]:
        value: dict[str, Any] = self.command(terminal, "profile", "list")
        rows: Any = value["profiles"]
        if not isinstance(rows, list):
            raise AssertionError("profile list must contain profiles array")
        return {row["name"]: row for row in rows}

    def profile(self, terminal: str) -> dict[str, Any] | None:
        value: Any = self.command(terminal, "profile", "status")["profile"]
        if value is not None and not isinstance(value, dict):
            raise AssertionError("profile status must contain object or null")
        return value

    def run(self) -> None:
        # Race first-use clients, not merely repeated requests to an existing daemon.
        with ThreadPoolExecutor(max_workers=6) as pool:
            starts: list[dict[str, Any]] = list(pool.map(
                lambda _: self.command("a", "profile", "list"), range(6)))
        assert all("profiles" in result for result in starts)
        daemon: dict[str, Any] = self.command("a", "daemon", "status")
        assert daemon["running"] is True
        first_pid: int = int(daemon["pid"])
        assert first_pid > 0
        print("PASS concurrent-first-use")

        self.command("a", "profile", "activate", "user")
        user: dict[str, Any] | None = self.profile("a")
        assert user is not None and user["name"] == "user"
        durable: dict[str, Any] = self.command("a", "profile", "create", "journey-worker")["profile"]
        assert durable["durable"] is True
        self.command("a", "profile", "activate", "journey-worker", success=False)
        self.command("a", "profile", "deactivate")
        self.command("a", "profile", "activate", "journey-worker")
        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses: list[dict[str, Any] | None] = list(pool.map(lambda _: self.profile("a"), range(4)))
        assert all(row is not None and row["id"] == durable["id"] for row in statuses)
        assert self.command("a", "daemon", "status")["pid"] == first_pid
        print("PASS same-terminal-processes-share-profile")

        self.command("b", "profile", "activate", "journey-worker", success=False)
        self.command("a", "profile", "deactivate")
        assert self.profile("a") is None
        self.command("b", "profile", "activate", "journey-worker", success=False)
        self.command("a", "profile", "activate", "journey-worker")
        recovered: dict[str, Any] | None = self.profile("a")
        assert recovered is not None and recovered["id"] == durable["id"]
        print("PASS deactivate-reserves-and-recovers")

        self.command("a", "profile", "release")
        assert self.profiles("a")["journey-worker"]["id"] == durable["id"]
        self.command("b", "profile", "activate", "journey-worker")
        ephemeral: dict[str, Any] = self.command("b", "profile", "create", "journey-temporary")["profile"]
        assert ephemeral["durable"] is False
        self.command("b", "profile", "deactivate")
        self.command("b", "profile", "activate", "journey-temporary")
        self.command("b", "profile", "release")
        assert "journey-temporary" not in self.profiles("b")
        self.command("b", "profile", "activate", "journey-worker")
        replacement: dict[str, Any] = self.command("b", "profile", "create", "journey-temporary")["profile"]
        assert replacement["id"] != ephemeral["id"]
        assert replacement["durable"] is False
        print("PASS durable-release-and-ephemeral-name-reuse")

        self.command("b", "daemon", "stop")
        resumed: dict[str, Any] | None = self.profile("b")
        assert resumed is not None and resumed["id"] == durable["id"]
        assert self.command("b", "daemon", "status")["running"] is True
        print("PASS daemon-restart-preserves-terminal-session")

        draft: Path = self.home / "draft"
        draft.mkdir()
        (draft / "manifest.toml").write_text(
            "version=1\nfrom='a@mail.example.test'\nto=['b@example.test']\nsubject='Synthetic journey'\n",
            encoding="utf-8")
        body: str = "Synthetic profile archive.\n" * 160
        (draft / "body.txt").write_text(body, encoding="utf-8")
        archive: Path = self.home / "draft.zip"
        unpacked: Path = self.home / "unpacked"
        assert self.command("b", "pack", str(draft), "-o", str(archive))["packed"] is True
        assert self.command("b", "unpack", str(archive), "-o", str(unpacked))["unpacked"] is True
        assert (unpacked / "body.txt").read_text(encoding="utf-8") == body
        print("PASS daemon-archive-roundtrip")


def nested_capture_eof(binary: Path, scratch: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="capture-", dir=scratch) as directory:
        home: Path = Path(directory)
        (home / "config.toml").write_text("yolo = true\n", encoding="utf-8")
        journey: Journey = Journey(binary, home)
        intermediate: str = (
            "import subprocess, sys\n"
            "command: list[str] = [sys.argv[1], 'profile', 'list']\n"
            "result: subprocess.CompletedProcess[bytes] = subprocess.run(\n"
            "    command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,\n"
            "    close_fds=False, timeout=10, check=False)\n"
            "sys.exit(result.returncode)\n"
        )
        # On Windows an inherited ancestor pipe is not necessarily a standard
        # handle. close_fds=False deliberately carries that extra handle to the
        # CLI, whose detached daemon must inherit no handles at all.
        pool: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)
        try:
            outer: Future[subprocess.CompletedProcess[str]] = pool.submit(
                subprocess.run,
                [sys.executable, "-c", intermediate, str(binary)],
                cwd=ROOT, env=journey.environment("a"), capture_output=True,
                text=True, timeout=12, check=False)
            result: subprocess.CompletedProcess[str] = outer.result(timeout=15)
            assert result.returncode == 0, "nested startup must exit successfully"
            assert result.stdout == "", "nested startup must not leak daemon output"
            assert journey.command("a", "daemon", "status")["running"] is True
            print("PASS nested-capture-eof-with-live-daemon")
        finally:
            # subprocess.run's timeout recovery can itself wait for EOF on
            # Windows. Stopping only this owned daemon unblocks that path
            # before the executor joins, including against a broken binary.
            try:
                stopped: subprocess.CompletedProcess[bytes] = subprocess.run(
                    [str(binary), "daemon", "stop"], cwd=ROOT,
                    env=journey.environment("a"), stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=10, check=False)
                assert stopped.returncode == 0, "owned capture daemon must stop"
            finally:
                pool.shutdown(wait=True)


def main() -> None:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    args: argparse.Namespace = parser.parse_args()
    binary: Path = args.binary.resolve(strict=True)
    scratch: Path = ROOT / ".temp" / "v030-profile-journey"
    scratch.mkdir(parents=True, exist_ok=True)
    nested_capture_eof(binary, scratch)
    with tempfile.TemporaryDirectory(prefix="native-", dir=scratch) as directory:
        home: Path = Path(directory)
        (home / "config.toml").write_text(
            "yolo = true\n[daemon]\nmax_concurrency = 4\nstart_timeout_seconds = 15\n",
            encoding="utf-8")
        journey: Journey = Journey(binary, home)
        try:
            journey.run()
        finally:
            journey.command("a", "daemon", "stop")


if __name__ == "__main__":
    main()
