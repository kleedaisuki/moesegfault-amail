"""Hosted synthetic native quota capabilities; never run a CLI/browser/provider."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

import staging_ten_address_native as target
import staging_ten_address_manifest as manifest
from test_staging_ten_address_manifest import KEY, RUN, OWNER, plan


def completed(value=None, *, code=0, stderr=b"", stdout=None):
    """Represent bounded captured subprocess bytes without executing anything."""
    return SimpleNamespace(returncode=code, stdout=json.dumps(value).encode() if stdout is None else stdout,
                           stderr=stderr)


class NativeTests(unittest.TestCase):
    """Use repository .temp only; every CLI/provider/browser capability is mocked."""

    def setUp(self):
        """Create synthetic path fixtures under the project, never outside it."""
        target.TEMP.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="quota-native-unit-", dir=target.TEMP)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / "amail.exe"
        self.binary.write_bytes(b"synthetic non-executable fixture")
        self.home = self.root / "home"
        self.home.mkdir()
        self.allowed = tuple(plan()["allowed"])

    def cli(self, runner):
        """Return a source-restricted adapter with no real subprocess capability."""
        return target.Cli(self.binary, self.home, self.allowed, runner=runner)

    def test_exact_add_delete_once_and_no_secret_inherited(self):
        """Capture allowlisted argv/env; no shell, retries, output or provider tokens."""
        runner = mock.Mock(side_effect=[completed({"address": self.allowed[0], "state": "active"}),
                                        completed({"state": "deleting"})])
        with mock.patch.dict(os.environ, {"CF_EMAIL_ROUTING_TOKEN": "private", "GITHUB_TOKEN": "private",
                                          "STAGING_E2E_PASSWORD": "private"}):
            cli = self.cli(runner)
            cli.add(self.allowed[0].split("@")[0])
            cli.delete(self.allowed[0])
        self.assertEqual(runner.call_count, 2)
        for call in runner.call_args_list:
            self.assertNotIn("shell", call.kwargs)
            self.assertEqual(call.kwargs["stdin"], subprocess.DEVNULL)
            self.assertFalse(call.kwargs["check"])
            self.assertEqual(call.kwargs["env"]["AMAIL_TELEMETRY"], "off")
            self.assertNotIn("CF_EMAIL_ROUTING_TOKEN", call.kwargs["env"])
            self.assertNotIn("GITHUB_TOKEN", call.kwargs["env"])
            self.assertNotIn("STAGING_E2E_PASSWORD", call.kwargs["env"])
        self.assertEqual(runner.call_args_list[0].args[0][1:3], ["address", "add"])
        self.assertEqual(runner.call_args_list[1].args[0][1:3], ["address", "delete"])

    def test_unowned_submissions_never_reach_process(self):
        """Commands cannot broaden the encrypted manifest's candidate vocabulary."""
        runner = mock.Mock()
        cli = self.cli(runner)
        with self.assertRaisesRegex(manifest.ContractFailure, "native_submission_unowned"):
            cli.add("unrelated")
        with self.assertRaisesRegex(manifest.ContractFailure, "native_submission_unowned"):
            cli.delete("unrelated@" + manifest.DOMAIN)
        runner.assert_not_called()

    def test_ambiguous_process_outcome_is_fixed_and_never_replayed(self):
        """Timeout/OS/provider text does not escape as a successful denial."""
        for error in (TimeoutError("private raw text"), OSError("private raw text")):
            runner = mock.Mock(side_effect=error)
            with self.assertRaisesRegex(manifest.ContractFailure, "^native_cli_outcome_ambiguous$"):
                self.cli(runner).add("admin")
            self.assertEqual(runner.call_count, 1)

    def test_complete_jsonl_owner_list(self):
        """Empty output is valid; duplicate/retired/cursor rows are not aliases."""
        for output, expected in ((b"", set()),
                                 (json.dumps({"address": self.allowed[0], "state": "active"}).encode(),
                                  {self.allowed[0]})):
            self.assertEqual(self.cli(mock.Mock(return_value=completed(stdout=output))).owned(), expected)
        row = json.dumps({"address": self.allowed[0], "state": "active"}).encode()
        for output in (row + b"\n" + row, b'{"next_cursor":"opaque"}',
                       row.replace(b"active", b"retired"), b"private non-json"):
            with self.assertRaisesRegex(manifest.ContractFailure, "native_owner_list_unverified"):
                self.cli(mock.Mock(return_value=completed(stdout=output))).owned()

    def test_config_and_auth_must_be_staging(self):
        """A genuine authenticated production home cannot satisfy this scope."""
        config = {"api_base": "https://mail-staging.moesegfault.dev", "issuer": manifest.ISSUER,
                  "client_id": "amail-cli-staging", "redirect_uri": "http://127.0.0.1/callback",
                  "telemetry_enabled": False}
        self.cli(mock.Mock(side_effect=[completed(config), completed({"authenticated": True})])).session()
        for change in ({"api_base": "https://mail.moesegfault.dev"}, {"telemetry_enabled": True}):
            with self.assertRaisesRegex(manifest.ContractFailure, "native_staging_config_unverified"):
                self.cli(mock.Mock(return_value=completed(dict(config, **change)))).session()
        with self.assertRaisesRegex(manifest.ContractFailure, "native_session_unverified"):
            self.cli(mock.Mock(side_effect=[completed(config), completed({"authenticated": False})])).session()

    def test_logout_checks_local_session_removed_without_claiming_remote_revoke(self):
        """Supported logout followed by new-process status is the local oracle."""
        runner = mock.Mock(side_effect=[completed({"authenticated": False}), completed({"authenticated": False})])
        self.cli(runner).logout()
        self.assertEqual([call.args[0][1:] for call in runner.call_args_list],
                         [["auth", "logout"], ["auth", "status"]])

    def test_owner_readback_needs_only_selected_verified_synthetic_contact(self):
        """No B account or earlier cross-owner isolation supplies this proof."""
        from staging_second_principal import FIRST, ADDRESS
        record = ("synthetic-principal", OWNER, "verified", "synthetic_username")
        self.assertEqual(target.selected_owner({FIRST: record}, "synthetic_username"), OWNER)
        self.assertEqual(target.selected_owner({FIRST: record, ADDRESS: ("b", "other", "pending", "other")},
                                               "synthetic_username"), OWNER)
        for contacts in ({}, {FIRST: ("bad",)}, {FIRST: tuple(record[:2]) + ("pending", record[3])},
                         {FIRST: record}):
            username = "wrong_username" if contacts == {FIRST: record} else "synthetic_username"
            with self.assertRaisesRegex(manifest.ContractFailure, "native_account_unverified"):
                target.selected_owner(contacts, username)

    def test_native_scope_cleanups_partial_persisted_login(self):
        """A failure after token persistence still attempts logout for that exact home."""
        identity = ModuleType("staging_identity_cdp")
        created = []
        def login(run_dir, binary, expected_address):
            created.append(run_dir)
            (run_dir / "amail-home-synthetic").mkdir()
            raise RuntimeError("synthetic browser teardown failure")
        identity.native_login = login
        identity.store_credential = mock.Mock()
        from staging_second_principal import FIRST
        fake_cli = mock.Mock()
        contacts = {FIRST: ("synthetic-principal", OWNER, "verified", "synthetic_username")}
        with mock.patch.object(target, "os", SimpleNamespace(name="nt")), mock.patch.dict(sys.modules, {"staging_identity_cdp": identity}), \
                mock.patch("staging_second_principal.identity_contacts", return_value=contacts), \
                mock.patch.object(target, "Cli", return_value=fake_cli):
            with self.assertRaisesRegex(RuntimeError, "synthetic browser teardown failure"):
                with target.native_account(self.binary, "synthetic_username", "synthetic-password-12345",
                                           "a" * 32, "private-token", self.allowed):
                    self.fail("partial login must not yield campaign capability")
        fake_cli.logout.assert_called_once()
        self.assertEqual(len(created), 1)
        self.assertFalse(created[0].exists())
