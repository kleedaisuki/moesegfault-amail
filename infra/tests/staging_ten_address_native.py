"""Native one-account quota capabilities without an executable live entry point.

A reviewed hosted wrapper must still establish exact binary/source/service and
immutable artifact provenance before granting this adapter to the campaign.
No direct auth-store/token read, account registration, SMTP or provider rule
mutation is available here. Supported amail add/delete are called once only.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Callable

import staging_ten_address_hosted as hosted
import staging_ten_address_manifest as manifest
from staging_mail_e2e import cli_env

ROOT = Path(__file__).resolve().parents[2]
TEMP = ROOT / ".temp"
require = manifest.require


def contained(path: Path, *, directory: bool) -> Path:
    """Confine a real binary/home to the repository's non-redirected .temp tree."""
    require(TEMP.resolve() == TEMP, "native_temp_redirected")
    try:
        value = path.resolve(strict=True)
    except Exception:
        raise manifest.ContractFailure("native_path_invalid") from None
    require(TEMP in value.parents and (value.is_dir() if directory else value.is_file()),
            "native_path_invalid")
    return value


class Cli:
    """Allow only campaign-local address commands and supported session teardown."""

    def __init__(self, binary: Path, home: Path, allowed: tuple[str, ...],
                 *, runner: Callable | None = None):
        """Validate fresh-run paths and exact candidate submission vocabulary."""
        self.binary = contained(binary, directory=False)
        self.home = contained(home, directory=True)
        require(isinstance(allowed, tuple) and len(allowed) == 11 and len(set(allowed)) == 11
                and all(re.fullmatch(r"qt[0-9]+-[a-z2-7]{26}@" + re.escape(manifest.DOMAIN), value)
                        is not None for value in allowed), "native_candidates_invalid")
        self.allowed = allowed
        self.resources = set(allowed) | {part.lower() + "@" + manifest.DOMAIN for part in manifest.submissions()}
        self._runner = runner or subprocess.run

    def _run(self, args: tuple[str, ...]) -> hosted.CliResult:
        """Capture privately, never shell-evaluate, retry, or inherit provider secrets."""
        try:
            result = self._runner([str(self.binary), *args], env=cli_env(self.home),
                                  stdin=subprocess.DEVNULL, capture_output=True,
                                  timeout=90, check=False)
            value = hosted.CliResult(result.returncode, result.stdout, result.stderr)
            value.validate()
            return value
        except manifest.ContractFailure:
            raise
        except Exception:
            raise manifest.ContractFailure("native_cli_outcome_ambiguous") from None

    def _json(self, args: tuple[str, ...]) -> dict:
        """Require one exact successful JSON result with no auxiliary diagnostic text."""
        result = self._run(args)
        require(result.returncode == 0 and result.stderr == b"", "native_cli_result_unverified")
        try:
            value = json.loads(result.stdout)
        except Exception:
            raise manifest.ContractFailure("native_cli_result_unverified") from None
        require(isinstance(value, dict), "native_cli_result_unverified")
        return value

    def session(self) -> None:
        """Independently confirm pinned staging config and persisted authenticated home."""
        config = self._json(("config",))
        require(all(config.get(key) == value for key, value in {
            "api_base": "https://mail-staging.moesegfault.dev", "issuer": manifest.ISSUER,
            "client_id": "amail-cli-staging", "redirect_uri": "http://127.0.0.1/callback",
            "telemetry_enabled": False,
        }.items()), "native_staging_config_unverified")
        require(self._json(("auth", "status")).get("authenticated") is True,
                "native_session_unverified")

    def owned(self) -> set[str]:
        """Parse complete compact address JSONL, refusing duplicates/retired/cursors."""
        result = self._run(("address", "list"))
        require(result.returncode == 0 and result.stderr == b"", "native_owner_list_unverified")
        try:
            rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        except Exception:
            raise manifest.ContractFailure("native_owner_list_unverified") from None
        require(len(rows) <= 10 and all(isinstance(row, dict)
                and isinstance(row.get("address"), str)
                and row["address"].endswith("@" + manifest.DOMAIN)
                and row.get("state") in ("pending", "provisioning", "active", "deleting") for row in rows),
                "native_owner_list_unverified")
        values = {row["address"] for row in rows}
        require(len(values) == len(rows), "native_owner_list_unverified")
        return values

    def add(self, part: str) -> hosted.CliResult:
        """Submit one exact source-listed reserved probe or derived candidate once."""
        require(part in manifest.submissions() or part + "@" + manifest.DOMAIN in self.allowed,
                "native_submission_unowned")
        return self._run(("address", "add", part))

    def delete(self, address: str) -> None:
        """Submit only a manifest-scoped delete; caller must re-audit row/rule ownership."""
        require(address in self.resources, "native_submission_unowned")
        value = self._json(("address", "delete", address))
        require(value.get("state") == "deleting", "native_delete_outcome_ambiguous")

    def logout(self) -> None:
        """Remove the exact home session and attempt normal refresh revocation.

        CLI logout intentionally cannot prove remote revocation on a provider
        outage; this result proves local authenticated state was removed only.
        """
        require(self._json(("auth", "logout")).get("authenticated") is False,
                "native_session_cleanup_required")
        require(self._json(("auth", "status")).get("authenticated") is False,
                "native_session_cleanup_required")


def selected_owner(contacts: dict, username: str) -> str:
    """Bind only existing synthetic A's verified contact/username/pairwise subject.

    B can be absent, pending or verified: it supplies no evidence for this
    campaign and cannot alter A's required contact binding. This is independent
    Identity D1 evidence, not a token copied from another CLI home.
    """
    from staging_second_principal import FIRST
    require(isinstance(contacts, dict) and FIRST in contacts, "native_account_unverified")
    record = contacts[FIRST]
    require(isinstance(record, (tuple, list)) and len(record) == 4, "native_account_unverified")
    principal, subject, state, observed = record
    require(isinstance(principal, str) and bool(principal)
            and isinstance(subject, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,256}", subject) is not None
            and state == "verified" and observed == username, "native_account_unverified")
    return subject


@contextmanager
def native_account(binary: Path, username: str, password: str, account: str,
                   token: str, allowed: tuple[str, ...]):
    """Use one fresh hosted Windows PKCE home; revoke locally and remove owned files.

    Fresh browser login submits the exact protected synthetic username. Current
    verified-contact readback supplies its pairwise subject before/after that
    supported native flow. There is no fabricated subject, first-party account
    creation, existing user session reuse or local credential decryption.
    Caller must arrange same-manifest remote cleanup before leaving this scope.
    Hard runner cancellation still requires the immutable artifact recovery path.
    """
    require(os.name == "nt" and isinstance(username, str)
            and re.fullmatch(r"[a-z0-9_]{3,32}", username) is not None
            and isinstance(password, str) and 15 <= len(password) <= 128,
            "native_hosted_credentials_invalid")
    contained(binary, directory=False)
    from staging_second_principal import FIRST, identity_contacts
    from staging_hosted_e2e import unique_auth_home
    from staging_identity_cdp import native_login, store_credential
    owner = selected_owner(identity_contacts(account, token), username)
    run_dir = Path(tempfile.mkdtemp(prefix="ten-address-native-", dir=TEMP)).resolve()
    cli = None
    try:
        store_credential(run_dir, username, password, FIRST)
        native_login(run_dir, binary, expected_address=FIRST)
        cli = Cli(binary, unique_auth_home(run_dir), allowed)
        cli.session()
        require(selected_owner(identity_contacts(account, token), username) == owner,
                "native_account_changed")
        yield owner, cli
    finally:
        cleanup_failed = False
        try:
            if cli is None:
                homes = [path for path in run_dir.glob("amail-home-*") if path.is_dir()]
                require(len(homes) <= 1, "native_session_cleanup_required")
                if homes:
                    # Login may persist a token before browser teardown fails.
                    # Remove that same partial home, not only successful sessions.
                    cli = Cli(binary, homes[0], allowed)
            if cli is not None:
                cli.logout()
        except Exception:
            cleanup_failed = True
        require(TEMP in run_dir.parents and run_dir.name.startswith("ten-address-native-"),
                "native_cleanup_path_unverified")
        try:
            shutil.rmtree(run_dir)
        except Exception:
            cleanup_failed = True
        require(not cleanup_failed, "native_session_cleanup_required")
