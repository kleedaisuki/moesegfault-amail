"""A persistent synthetic baseline is one guarded account-stable create intent."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT: Path = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/tests"))
import staging_semantic_e2e as semantic


class BaselineBootstrapTests(unittest.TestCase):
    def test_creation_requires_explicit_authority_and_no_existing_permanent_intent(self) -> None:
        local: str = semantic.managed_baseline_local("synthetic", "synthetic-password-not-a-real-secret")
        with patch.dict(os.environ, {}, clear=True), patch.object(semantic, "one") as create:
            with self.assertRaisesRegex(semantic.mail.ProbeFailure, "^semantic_baseline_alias_missing$"):
                semantic.bootstrap_managed_alias(Path("amail.exe"), {}, local, [])
            create.assert_not_called()
        for state in ("active", "pending", "provisioning", "deleting"):
            with self.subTest(state=state), \
                 patch.dict(os.environ, {"AMAIL_SEMANTIC_BASELINE_BOOTSTRAP": semantic.BASELINE_BOOTSTRAP}), \
                 patch.object(semantic, "one") as create:
                with self.assertRaisesRegex(semantic.mail.ProbeFailure, "^semantic_baseline_existing_alias_unavailable$"):
                    semantic.bootstrap_managed_alias(Path("amail.exe"), {}, local,
                        [{"address": "another@mail-staging.moesegfault.dev", "kind": "mail", "state": state}])
                create.assert_not_called()

    def test_unknown_create_inspects_same_stable_alias_once_and_cleanup_keeps_it(self) -> None:
        username: str = "synthetic"
        password: str = "synthetic-password-not-a-real-secret"
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123"}):
            local: str = semantic.managed_baseline_local(username, password)
        self.assertGreaterEqual(len(local), 3)
        self.assertLessEqual(len(local), 32)
        self.assertRegex(local, r"semantic-[a-f0-9]{16}\Z")
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "456"}):
            self.assertEqual(semantic.managed_baseline_local(username, password), local)
        address: str = local + "@mail-staging.moesegfault.dev"
        environment: dict[str, str] = {"AMAIL_SEMANTIC_BASELINE_BOOTSTRAP": semantic.BASELINE_BOOTSTRAP,
            "CLOUDFLARE_ZONE_ID": "synthetic-zone", "CF_EMAIL_ROUTING_TOKEN": "synthetic-token"}
        with patch.dict(os.environ, environment), \
             patch.object(semantic, "one", side_effect=semantic.mail.ProbeFailure("semantic_cli_failed")) as create, \
             patch.object(semantic.mail, "amail", return_value=[{"address": address, "kind": "mail", "state": "pending"}]) as cli, \
             patch.object(semantic, "await_address") as active, \
             patch.object(semantic.mail, "assert_route") as route, patch.object(semantic.time, "sleep") as settle:
            self.assertEqual(semantic.bootstrap_managed_alias(Path("amail.exe"), {}, local, []), address)
            create.assert_called_once_with(Path("amail.exe"), {}, "address", "add", local)
            cli.assert_called_once_with(Path("amail.exe"), {}, "address", "list",
                                        failure="semantic_baseline_create_inspection_failed")
            self.assertEqual(active.call_count, 2)
            self.assertEqual(route.call_count, 2)
            self.assertTrue(all(call.args[-1] is True for call in route.call_args_list))
            settle.assert_called_once_with(120)
            cli.reset_mock()
            semantic.cleanup_fixture(Path("amail.exe"), {}, address, "known-current-fixture", False,
                                     lambda action: action())
            cli.assert_called_once_with(Path("amail.exe"), {}, "delete", "known-current-fixture",
                                        failure="semantic_fixture_delete_failed")
            self.assertEqual(route.call_count, 2, "cleanup never deletes or re-creates this managed route")


if __name__ == "__main__":
    unittest.main()
