"""Synthetic failure-path checks for the deployed-probe harness.

中文：完全模拟 CLI 和 Cloudflare，不发送邮件或调用部署服务。
"""

import importlib.util
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "staging_mail_e2e", Path(__file__).with_name("staging_mail_e2e.py")
)
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARNESS)


class CleanupTests(unittest.TestCase):
    """Guarantee timeout does not skip alias retirement. / 保证超时不跳过别名退役。"""

    def test_cli_timeout_has_fixed_label(self) -> None:
        """Hide process payload on a timeout. / 超时不泄露进程负载。"""

        with patch.object(HARNESS.subprocess, "run", side_effect=subprocess.TimeoutExpired("amail", 90)):
            with self.assertRaises(HARNESS.ProbeFailure) as caught:
                HARNESS.amail(Path("amail.exe"), {}, "sync", failure="sync_failed")
        self.assertEqual(str(caught.exception), "sync_failed")

    def test_message_timeout_still_retires_address(self) -> None:
        """Retire even when cleanup sync times out. / 清理同步超时仍需注销地址。"""

        calls = []

        def fake_amail(_binary, _env, *args, failure):
            calls.append(args)
            if args[:1] == ("sync",):
                raise HARNESS.ProbeFailure("cleanup_sync_failed")
            return []

        with patch.object(HARNESS, "amail", side_effect=fake_amail), patch.object(
            HARNESS, "cf_rules", return_value=[]
        ):
            with self.assertRaises(HARNESS.ProbeFailure) as caught:
                HARNESS.cleanup_run(Path("amail.exe"), {}, "zone", "token", "test@example.test", "nonce")
        self.assertEqual(str(caught.exception), "message_cleanup_failed")
        self.assertIn(("address", "delete", "test@example.test"), calls)
        self.assertIn(("address", "list"), calls)

    def test_address_list_failure_does_not_hide_route(self) -> None:
        """Report uncertain cleanup rather than a false pass. / 地址查询失败不得冒充清理成功。"""

        calls = []

        def fake_amail(_binary, _env, *args, failure):
            calls.append(args)
            if args == ("address", "list"):
                raise HARNESS.ProbeFailure("retire_readback_failed")
            return []

        clock = iter((0, 1, 91))
        with patch.object(HARNESS, "amail", side_effect=fake_amail), patch.object(
            HARNESS, "cf_rules", return_value=[]
        ), patch.object(HARNESS.time, "monotonic", side_effect=lambda: next(clock)), patch.object(
            HARNESS.time, "sleep", return_value=None
        ):
            with self.assertRaises(HARNESS.ProbeFailure) as caught:
                HARNESS.cleanup_run(Path("amail.exe"), {}, "zone", "token", "test@example.test", "nonce")
        self.assertEqual(str(caught.exception), "address_or_route_cleanup_failed")
        self.assertIn(("address", "delete", "test@example.test"), calls)

    def test_unexpected_post_creation_timeout_enters_cleanup(self) -> None:
        """The top-level finally owns cleanup even for non-ProbeFailure exceptions.

        中文：地址创建后出现意外超时，顶层 finally 仍必须运行清理。
        """

        HARNESS.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=HARNESS.TEMP) as directory:
            root = Path(directory)
            home = root / "home"
            home.mkdir()
            binary = root / "amail.exe"
            binary.touch()
            created = {"address": None}

            def fake_amail(_binary, _env, *args, failure):
                if args == ("auth", "status"):
                    return [{"authenticated": True}]
                if args[:2] == ("address", "add"):
                    created["address"] = args[2] + "@" + HARNESS.DOMAIN
                    return [{"address": created["address"], "state": "active"}]
                if args == ("address", "list"):
                    return [{"address": created["address"], "state": "active"}] if created["address"] else []
                raise AssertionError("unexpected CLI call")

            env = {
                "CLOUDFLARE_ZONE_ID": "a" * 32,
                "CF_EMAIL_ROUTING_TOKEN": "routing",
                "AMAIL_TEST_SMTP_TOKEN": "sending",
            }
            argv = ["probe", "--confirm-staging", "--home", str(home), "--amail", str(binary)]
            with patch.dict(os.environ, env), patch.object(sys, "argv", argv), patch.object(
                HARNESS, "amail", side_effect=fake_amail
            ), patch.object(HARNESS, "cf_rules", return_value=[]), patch.object(
                HARNESS, "assert_route"
            ), patch.object(HARNESS, "assert_staging_sender"), patch.object(
                HARNESS, "smtp_send", side_effect=subprocess.TimeoutExpired("smtp", 30)
            ), patch.object(HARNESS, "cleanup_run") as cleanup, patch.object(
                HARNESS.time, "sleep", return_value=None
            ):
                with self.assertRaises(HARNESS.ProbeFailure) as caught:
                    HARNESS.main()
            self.assertEqual(str(caught.exception), "probe_unexpected_failure")
            cleanup.assert_called_once()
            self.assertEqual(cleanup.call_args.args[4], created["address"])


if __name__ == "__main__":
    unittest.main()
