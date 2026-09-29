"""Synthetic failure-path checks for the deployed-probe harness.

中文：完全模拟 CLI 和 Cloudflare，不发送邮件或调用部署服务。
"""

import importlib.util
from contextlib import redirect_stdout
from io import StringIO
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

    def test_address_creation_preflight_rejects_known_account_conflicts(self) -> None:
        """A candidate already owned or a full account must not enter add."""

        address = "e2e-test@" + HARNESS.DOMAIN
        owned = [{"address": address, "state": "pending"}]
        with self.assertRaises(HARNESS.ProbeFailure) as caught:
            HARNESS.assert_address_creation_preflight(owned, [], address)
        self.assertEqual(str(caught.exception), "address_preflight_candidate_owned")

        owned = [
            {"address": f"owned-{n}@{HARNESS.DOMAIN}", "state": "active"}
            for n in range(10)
        ]
        with self.assertRaises(HARNESS.ProbeFailure) as caught:
            HARNESS.assert_address_creation_preflight(owned, [], address)
        self.assertEqual(str(caught.exception), "address_preflight_account_full")
        with self.assertRaises(HARNESS.ProbeFailure) as caught:
            HARNESS.assert_address_creation_preflight(
                [{"address": "duplicate@example.test", "state": "active"}] * 2,
                [], address,
            )
        self.assertEqual(str(caught.exception), "address_preflight_shape")

    def test_address_creation_preflight_checks_domain_inventory(self) -> None:
        """Count one rule per staging-domain literal matcher, not apex routes."""

        address = "e2e-test@" + HARNESS.DOMAIN

        def literal(n: int, domain: str) -> dict:
            return {"name": f"rule-{n}", "matchers": [
                {"type": "literal", "field": "to", "value": f"test-{n}@{domain}"}
            ]}

        staging = [literal(n, HARNESS.DOMAIN) for n in range(200)]
        apex = literal(201, "moesegfault.dev")
        HARNESS.assert_address_creation_preflight([], staging[:199] + [apex], address)
        with self.assertRaises(HARNESS.ProbeFailure) as caught:
            HARNESS.assert_address_creation_preflight([], staging + [apex], address)
        self.assertEqual(str(caught.exception), "address_preflight_domain_full")
        with self.assertRaises(HARNESS.ProbeFailure) as caught:
            HARNESS.assert_address_creation_preflight([], [literal(1, HARNESS.DOMAIN), {
                "name": "amail " + address,
                "matchers": [{"type": "literal", "field": "to", "value": "other@example.test"}],
            }], address)
        self.assertEqual(str(caught.exception), "address_preflight_candidate_routed")
        with self.assertRaises(HARNESS.ProbeFailure) as caught:
            HARNESS.assert_address_creation_preflight([], [{"matchers": "private"}], address)
        self.assertEqual(str(caught.exception), "routing_inventory_shape")

    def test_rule_inventory_rejects_truncated_or_inconsistent_pages(self) -> None:
        """Missing total_pages is allowed; missing rows despite total_count is not."""

        complete = {
            "success": True, "result": [{"matchers": []}],
            "result_info": {"page": 1, "per_page": 50, "count": 1, "total_count": 1},
        }
        self.assertEqual(HARNESS.validated_rule_page(complete, 1, None)[1:], (1, 1))
        truncated = {**complete, "result_info": {**complete["result_info"], "total_count": 2}}
        with self.assertRaises(HARNESS.ProbeFailure) as caught:
            HARNESS.validated_rule_page(truncated, 1, None)
        self.assertEqual(str(caught.exception), "routing_pages_invalid")
        contradictory = {**complete, "result_info": {**complete["result_info"], "total_pages": 2}}
        with self.assertRaises(HARNESS.ProbeFailure) as caught:
            HARNESS.validated_rule_page(contradictory, 1, None)
        self.assertEqual(str(caught.exception), "routing_pages_invalid")
        with self.assertRaises(HARNESS.ProbeFailure) as caught:
            HARNESS.validated_rule_page(complete, 1, 2)
        self.assertEqual(str(caught.exception), "routing_pages_invalid")

    def test_address_preflight_stops_before_add_and_cleanup(self) -> None:
        """A known full account cannot cause any mutation or cleanup call."""

        HARNESS.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=HARNESS.TEMP) as directory:
            root = Path(directory)
            home = root / "home"
            home.mkdir()
            binary = root / "amail.exe"
            binary.touch()
            calls = []

            def fake_amail(_binary, _env, *args, failure):
                calls.append(args)
                if args == ("auth", "status"):
                    return [{"authenticated": True}]
                if args == ("address", "list"):
                    return [
                        {"address": f"owned-{n}@{HARNESS.DOMAIN}", "state": "active"}
                        for n in range(10)
                    ]
                raise AssertionError("unexpected CLI mutation")

            env = {
                "CLOUDFLARE_ZONE_ID": "a" * 32,
                "CF_EMAIL_ROUTING_TOKEN": "routing",
                "AMAIL_TEST_SMTP_TOKEN": "sending",
            }
            argv = ["probe", "--confirm-staging", "--home", str(home), "--amail", str(binary)]
            with patch.dict(os.environ, env), patch.object(sys, "argv", argv), patch.object(
                HARNESS, "amail", side_effect=fake_amail
            ), patch.object(HARNESS, "cf_rules", return_value=[]), patch.object(
                HARNESS, "assert_staging_sender"
            ), patch.object(HARNESS, "cleanup_run") as cleanup:
                with self.assertRaises(HARNESS.ProbeFailure) as caught:
                    HARNESS.main()
            self.assertEqual(str(caught.exception), "address_preflight_account_full")
            self.assertEqual(calls, [("auth", "status"), ("address", "list")])
            cleanup.assert_not_called()

    def test_cli_failure_keeps_only_allowlisted_public_code(self) -> None:
        """Preserve a useful status while dropping correlation and private text."""

        stderr = (
            b"Error: mail API addresses.add failed: HTTP 503 Service Unavailable, "
            b"code=routing_unavailable, correlation_id=private-identifier\n"
        )
        self.assertEqual(
            HARNESS.cli_failure(stderr, "address_register_failed"),
            "address_register_failed_http_503_routing_unavailable",
        )
        self.assertEqual(
            HARNESS.cli_failure(
                stderr.replace(b"routing_unavailable", b"service_unavailable"),
                "address_register_failed",
            ),
            "address_register_failed_http_503_service_unavailable",
        )
        unsafe = stderr.replace(b"routing_unavailable", b"private_mailbox_body")
        self.assertEqual(HARNESS.cli_failure(unsafe, "address_register_failed"), "address_register_failed")
        self.assertEqual(
            HARNESS.cli_failure(b"provider says private_mailbox_body", "address_register_failed"),
            "address_register_failed",
        )
        self.assertEqual(
            HARNESS.cli_failure(
                b"Error: mail API messages.search failed: HTTP 503 Service Unavailable, "
                b"code=semantic_index_incomplete, correlation_id=private-identifier\n",
                "semantic_search_failed",
            ),
            "semantic_search_failed_http_503_semantic_index_incomplete",
        )

    def test_semantic_gate_reuses_delivered_rows_and_retries_only_index_lag(self) -> None:
        """One timed index miss may recover without another SMTP send or mutation."""

        nonce = "0123456789abcdef"
        signal = {"id": "one", "received_at": "2026-09-29T00:00:01Z", "read": False, "score": 0.8}
        distractor = {"id": "two", "received_at": "2026-09-29T00:00:00Z", "read": False, "score": 0.7}
        calls = []

        def fake_amail(_binary, _env, *args, failure):
            calls.append(args)
            if len(calls) == 1:
                raise HARNESS.ProbeFailure("semantic_search_failed_http_503_semantic_index_incomplete")
            if "--read" in args or "signal-private-absent" in args:
                return []
            if "--body" in args:
                return [signal]
            return [signal, distractor]

        output = StringIO()
        with patch.object(HARNESS, "amail", side_effect=fake_amail), patch.object(
            HARNESS.time, "monotonic", side_effect=[0, 0]
        ), patch.object(HARNESS.time, "sleep") as sleep, redirect_stdout(output):
            HARNESS.semantic_cases(
                Path("amail.exe"), {}, "fixture@mail-staging.moesegfault.dev", nonce,
                signal, {"phrase": "signal-private"}, distractor,
            )
        self.assertEqual(output.getvalue().strip(), "semantic_two_message_search_verified")
        self.assertEqual(len(calls), 5)
        self.assertTrue(all(args[0] == "search" for args in calls))
        sleep.assert_called_once_with(30)

    def test_semantic_gate_fails_closed_after_bounded_index_wait(self) -> None:
        """An incomplete index cannot become a false semantic-search pass."""

        nonce = "0123456789abcdef"
        row = {"id": "one", "received_at": "2026-09-29T00:00:01Z"}
        other = {"id": "two", "received_at": "2026-09-29T00:00:00Z"}
        with patch.object(
            HARNESS, "amail", side_effect=HARNESS.ProbeFailure(
                "semantic_search_failed_http_503_semantic_index_incomplete"
            )
        ), patch.object(HARNESS.time, "monotonic", side_effect=[0, 390]), patch.object(
            HARNESS.time, "sleep"
        ) as sleep:
            with self.assertRaises(HARNESS.ProbeFailure) as caught:
                HARNESS.semantic_cases(
                    Path("amail.exe"), {}, "fixture@mail-staging.moesegfault.dev", nonce,
                    row, {"phrase": "signal-private"}, other,
                )
        self.assertEqual(str(caught.exception), "semantic_index_timeout")
        sleep.assert_not_called()

    def test_hosted_nonce_is_validated_without_changing_local_default(self) -> None:
        """Reject malformed recovery suffixes; retain random local behavior."""

        with patch.dict(os.environ, {"AMAIL_TEST_RUN_NONCE": "a" * 16}):
            self.assertEqual(HARNESS.run_nonce(), "a" * 16)
        with patch.dict(os.environ, {"AMAIL_TEST_RUN_NONCE": "../unsafe"}):
            with self.assertRaises(HARNESS.ProbeFailure) as caught:
                HARNESS.run_nonce()
        self.assertEqual(str(caught.exception), "run_nonce_invalid")
        with patch.dict(os.environ, {"AMAIL_TEST_RUN_NONCE": ""}), patch.object(
            HARNESS.secrets, "token_hex", return_value="b" * 16
        ):
            self.assertEqual(HARNESS.run_nonce(), "b" * 16)

    def test_primary_and_cleanup_failures_remain_visible(self) -> None:
        """Cleanup failure must not erase the first deployed-probe failure."""

        primary = HARNESS.ProbeFailure("smtp_submission_failed")
        cleanup = HARNESS.ProbeFailure("address_or_route_cleanup_failed")
        combined = HARNESS.acceptance_failure(primary, cleanup)
        self.assertEqual(
            str(combined),
            "smtp_submission_failed_cleanup_address_or_route_cleanup_failed",
        )
        self.assertIs(HARNESS.acceptance_failure(primary, None), primary)
        self.assertIs(HARNESS.acceptance_failure(None, cleanup), cleanup)

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

        clock = iter((0, 1, 421))
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
        """Finally runs and reports both primary and cleanup failures.

        中文：地址创建后发生意外超时，即使清理也失败仍保留两种错误。
        """

        HARNESS.TEMP.mkdir(exist_ok=True)
        for cleanup_failure in (None, HARNESS.ProbeFailure("address_or_route_cleanup_failed")):
            with self.subTest(cleanup_failed=cleanup_failure is not None):
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
                    ), patch.object(HARNESS, "cleanup_run", side_effect=cleanup_failure) as cleanup, patch.object(
                        HARNESS.time, "sleep", return_value=None
                    ):
                        with self.assertRaises(HARNESS.ProbeFailure) as caught:
                            HARNESS.main()
                    expected = "probe_unexpected_failure"
                    if cleanup_failure:
                        expected += "_cleanup_address_or_route_cleanup_failed"
                    self.assertEqual(str(caught.exception), expected)
                    cleanup.assert_called_once()
                    self.assertEqual(cleanup.call_args.args[4], created["address"])


if __name__ == "__main__":
    unittest.main()
