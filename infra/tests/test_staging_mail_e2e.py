"""Synthetic failure-path checks for the deployed-probe harness.

中文：完全模拟 CLI 和 Cloudflare，不发送邮件或调用部署服务。
"""

import importlib.util
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import json
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

    def test_rule_inventory_rejects_duplicate_ids_across_complete_pages(self) -> None:
        """Stable total counts alone cannot prove a paginated inventory is complete."""

        class Response:
            status = 200

            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps(self.payload).encode()

        def page(number, rules):
            return {"success": True, "result": rules,
                    "result_info": {"page": number, "per_page": 50,
                                    "count": len(rules), "total_count": 51, "total_pages": 2}}

        first = [{"id": f"{n:032x}", "matchers": []} for n in range(50)]
        second = [{"id": first[0]["id"], "matchers": []}]
        responses = iter([Response(page(1, first)), Response(page(2, second))])
        with patch.object(HARNESS, "control_open", side_effect=lambda *_args, **_kw: next(responses)):
            with self.assertRaises(HARNESS.ProbeFailure) as caught:
                HARNESS.cf_rules("a" * 32, "private-token")
        self.assertEqual(str(caught.exception), "routing_inventory_id_invalid")

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
                "CLOUDFLARE_ACCOUNT_ID": "b" * 32,
                "CLOUDFLARE_API_TOKEN": "d1-read",
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
            b"amail: mail API addresses.add failed: HTTP 503 Service Unavailable, "
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
        self.assertEqual(HARNESS.cli_failure(unsafe, "address_register_failed"), "address_register_failed_http_503_unknown_code")
        self.assertEqual(
            HARNESS.cli_failure(b"provider says private_mailbox_body", "address_register_failed"),
            "address_register_failed",
        )
        self.assertEqual(
            HARNESS.cli_failure(
                b"amail: mail API messages.search failed: HTTP 503 Service Unavailable, "
                b"code=semantic_index_incomplete, correlation_id=private-identifier\n",
                "semantic_search_failed",
            ),
            "semantic_search_failed_http_503_semantic_index_incomplete",
        )

    def test_cli_failure_classifies_fixed_search_conflicts_without_private_text(self) -> None:
        """Expose only reviewed consistency codes, not opaque request metadata."""

        for code in (b"search_job_stale", b"search_cursor_stale"):
            stderr = (
                b"amail: mail API messages.list failed: HTTP 409 Conflict, code="
                + code + b", correlation_id=private-identifier\n"
            )
            self.assertEqual(
                HARNESS.cli_failure(stderr, "mail_sync_failed"),
                "mail_sync_failed_http_409_" + code.decode("ascii"),
            )
        self.assertEqual(
            HARNESS.cli_failure(
                b"amail: mail API messages.list failed: HTTP 409 Conflict, "
                b"code=private_mailbox_body, correlation_id=private-identifier\n",
                "mail_sync_failed",
            ),
            "mail_sync_failed_http_409_unknown_code",
        )

    def test_address_failure_closed_diagnostic_and_transport_contract(self) -> None:
        """Discard hostile suffixes and accept only fixed CLI diagnostic grammar."""

        base = (b"amail: mail API addresses.add failed: HTTP 503 Service Unavailable, "
                b"code=routing_unavailable, correlation_id=private-id")
        good = base + b", diag=v1:routing_create:provider:403:10000\n"
        self.assertEqual(
            HARNESS.cli_failure(good, "address_register_failed"),
            "address_register_failed_http_503_routing_unavailable_diag_v1_routing_create_provider_403_10000",
        )
        for bad in (b"v1:routing_create:provider:0403:10000",
                    b"v1:routing_create:provider:403:private@example.test",
                    b"v1:unknown:provider:403:10000", b"v1:routing_create:provider:403:10000:secret"):
            self.assertEqual(
                HARNESS.cli_failure(base + b", diag=" + bad + b"\n", "address_register_failed"),
                "address_register_failed_http_503_routing_unavailable",
            )
        fixed = {
            b"amail: mail API addresses.add transport failed: kind=timeout\n": "transport_timeout",
            b"amail: mail API addresses.add transport failed: kind=other\n": "transport_other",
            b"amail: mail API addresses.add body read failed: kind=timeout\n": "body_timeout",
            b"amail: mail API addresses.add body read failed: kind=other\n": "body_other",
            b"amail: mail API addresses.add response invalid: kind=json\n": "success_body_invalid",
            b"amail: not logged in; run `amail login`\n": "auth_before_request",
        }
        for stderr, label in fixed.items():
            self.assertEqual(HARNESS.cli_failure(stderr, "address_register_failed"),
                             "address_register_failed_" + label)
        self.assertEqual(
            HARNESS.cli_failure(
                b"amail: mail API addresses.add failed: HTTP 502 Bad Gateway, "
                b"code=http_error, correlation_id=private-id\n", "address_register_failed"),
            "address_register_failed_http_502_http_error",
        )
        self.assertEqual(
            HARNESS.cli_failure(
                b"amail: mail API addresses.add failed: HTTP 599, "
                b"code=http_error, correlation_id=private-id\n", "address_register_failed"),
            "address_register_failed_http_599_http_error",
        )
        self.assertEqual(HARNESS.cli_failure(b"Error: private@example.test", "address_register_failed"),
                         "address_register_failed")

    def test_address_failure_cloudflare_header_category_is_fixed(self) -> None:
        """The actual CLI response category survives, but no header bytes do."""

        base = (b"amail: mail API addresses.add failed: HTTP 500 Internal Server Error, "
                b"code=http_error, correlation_id=none")
        for category in (b"1101", b"1102", b"other", b"absent"):
            stderr = base + b", cf_error=" + category + b"\n"
            self.assertEqual(
                HARNESS.cli_failure(stderr, "address_register_failed"),
                "address_register_failed_http_500_http_error_cf_" + category.decode("ascii"),
            )
        with_diag = base + b", diag=v1:routing_create:provider:503:0, cf_error=1101\n"
        self.assertEqual(
            HARNESS.cli_failure(with_diag, "address_register_failed"),
            "address_register_failed_http_500_http_error_diag_v1_routing_create_provider_503_0_cf_1101",
        )
        for category in (b"1101private", b"private@example.test"):
            stderr = base + b", cf_error=" + category + b"\n"
            self.assertEqual(HARNESS.cli_failure(stderr, "address_register_failed"),
                             "address_register_failed_http_500_http_error")
        self.assertEqual(
            HARNESS.cli_failure(base + b", cf_error=1101\rleak\n", "address_register_failed"),
            "address_register_failed",
        )
        client_error = base.replace(b"500 Internal Server Error", b"409 Conflict")
        self.assertEqual(
            HARNESS.cli_failure(client_error + b", cf_error=1101\n", "address_register_failed"),
            "address_register_failed_http_409_http_error",
        )

    def test_precleanup_snapshot_is_fixed_and_read_only(self) -> None:
        """Exact route and parameterized row reduce to labels without payload exposure."""

        address = "e2e-private@mail-staging.moesegfault.dev"
        rule = {
            "id": "a" * 32,
            "source": "api", "name": "amail " + address, "enabled": True,
            "actions": [{"type": "worker", "value": [HARNESS.INGRESS]}],
            "matchers": [{"type": "literal", "field": "to", "value": address}],
        }
        with patch.object(HARNESS, "cf_rules", return_value=[rule]):
            self.assertEqual(HARNESS.route_snapshot("zone", "token", address), "one_exact_owned")
        with patch.object(HARNESS, "cf_rules", return_value=[{**rule, "id": "private-id"}]):
            self.assertEqual(HARNESS.route_snapshot("zone", "token", address), "unverified")
        with patch.object(HARNESS, "cf_rules", return_value=[rule, rule]):
            self.assertEqual(HARNESS.route_snapshot("zone", "token", address), "conflict")
        with patch.object(HARNESS, "cf_rules", return_value=[{"matchers": "private"}]):
            self.assertEqual(HARNESS.route_snapshot("zone", "token", address), "unverified")

        row = {"state": "provisioning", "cf_rule_id": None, "needs_reconcile": 1,
               "owner_iss": HARNESS.ISSUER, "owner_sub": "synthetic-sub"}
        payload = {"success": True, "result": [{"success": True, "results": [row]}]}

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps(payload).encode()

        def fetch(req, timeout):
            self.assertEqual(timeout, 25)
            self.assertEqual(req.get_method(), "POST")
            self.assertEqual(json.loads(req.data), {"sql": HARNESS.ADDRESS_ROW_SQL, "params": [address]})
            return Response()

        with patch.object(HARNESS, "control_open", side_effect=fetch):
            self.assertEqual(HARNESS.row_snapshot("a" * 32, "secret", address),
                             ("provisioning", "null", "reconcile_1"))
            payload["result"][0]["results"] = []
            self.assertEqual(HARNESS.row_snapshot("a" * 32, "secret", address),
                             ("row_absent", "absent", "absent"))
            payload["result"][0]["results"] = [{**row, "state": "private@example.test"}]
            self.assertEqual(HARNESS.row_snapshot("a" * 32, "secret", address),
                             ("unverified", "unverified", "unverified"))

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

    def test_failed_add_snapshots_before_cleanup_and_preserves_both_failures(self) -> None:
        """One failed add must read exact state before retiring its same alias."""

        HARNESS.TEMP.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=HARNESS.TEMP) as directory:
            root = Path(directory)
            home = root / "home"
            home.mkdir()
            binary = root / "amail.exe"
            binary.touch()
            order = []

            def fake_amail(_binary, _env, *args, failure):
                if args == ("auth", "status"):
                    return [{"authenticated": True}]
                if args == ("address", "list"):
                    return []
                if args[:2] == ("address", "add"):
                    order.append("add")
                    raise HARNESS.ProbeFailure("address_register_failed_http_503_routing_unavailable")
                raise AssertionError("unexpected CLI operation")

            def snapshot(*_args):
                order.append("snapshot")
                raise RuntimeError("private-address@example.test")

            def cleanup(*_args):
                order.append("cleanup")
                raise HARNESS.ProbeFailure("address_or_route_cleanup_failed")

            env = {
                "CLOUDFLARE_ZONE_ID": "a" * 32,
                "CLOUDFLARE_ACCOUNT_ID": "b" * 32,
                "CLOUDFLARE_API_TOKEN": "d1-read",
                "CF_EMAIL_ROUTING_TOKEN": "routing",
                "AMAIL_TEST_SMTP_TOKEN": "sending",
            }
            argv = ["probe", "--confirm-staging", "--home", str(home), "--amail", str(binary)]
            output = StringIO()
            with patch.dict(os.environ, env), patch.object(sys, "argv", argv), patch.object(
                HARNESS, "amail", side_effect=fake_amail
            ), patch.object(HARNESS, "cf_rules", return_value=[]), patch.object(
                HARNESS, "assert_staging_sender"
            ), patch.object(HARNESS, "print_snapshot", side_effect=snapshot), patch.object(
                HARNESS, "cleanup_run", side_effect=cleanup
            ), redirect_stdout(output):
                with self.assertRaises(HARNESS.ProbeFailure) as caught:
                    HARNESS.main()
        self.assertEqual(order, ["add", "snapshot", "cleanup"])
        self.assertEqual(str(caught.exception),
                         "address_register_failed_http_503_routing_unavailable_cleanup_address_or_route_cleanup_failed")
        self.assertIn("address_add_snapshot_route:unverified", output.getvalue())
        self.assertIn("address_add_primary:address_register_failed_http_503_routing_unavailable", output.getvalue())
        self.assertIn("address_add_cleanup:address_or_route_cleanup_failed", output.getvalue())
        self.assertNotIn("private-address", output.getvalue())

    def test_cli_timeout_has_fixed_label(self) -> None:
        """Hide process payload on a timeout. / 超时不泄露进程负载。"""

        with patch.object(HARNESS.subprocess, "run", side_effect=subprocess.TimeoutExpired("amail", 90)):
            with self.assertRaises(HARNESS.ProbeFailure) as caught:
                HARNESS.amail(Path("amail.exe"), {}, "sync", failure="sync_failed")
        self.assertEqual(str(caught.exception), "sync_failed_subprocess_timeout")

    def test_message_timeout_still_retires_address(self) -> None:
        """Retire even when the complete mailbox inventory fails."""

        calls = []

        def fake_amail(_binary, _env, *args, failure):
            calls.append(args)
            return []

        with patch.object(HARNESS, "amail", side_effect=fake_amail), patch.object(
            HARNESS, "cf_rules", return_value=[]
        ), patch.object(HARNESS, "row_snapshot", return_value=("retired", "null", "reconcile_0")), patch.object(
            HARNESS, "cleanup_messages", side_effect=HARNESS.ProbeFailure("cleanup_search_unverified")):
            with self.assertRaises(HARNESS.ProbeFailure) as caught:
                HARNESS.cleanup_run(Path("amail.exe"), {}, "zone", "token", "test@example.test", "nonce")
        self.assertEqual(str(caught.exception), "message_cleanup_failed")
        self.assertIn(("address", "delete", "test@example.test"), calls)
        self.assertIn(("address", "list"), calls)

    def test_retirement_precedes_slow_message_inventory(self) -> None:
        """A search timeout cannot leave the run's public route enabled."""

        order = []

        def fake_amail(_binary, _env, *args, failure):
            order.append(args)
            return []

        def failed_messages(*_args):
            order.append(("messages",))
            raise HARNESS.ProbeFailure("cleanup_search_transport_unverified")

        with patch.object(HARNESS, "amail", side_effect=fake_amail), patch.object(
            HARNESS, "cf_rules", return_value=[]
        ), patch.object(HARNESS, "row_snapshot", return_value=("retired", "null", "reconcile_0")), patch.object(
            HARNESS, "cleanup_messages", side_effect=failed_messages
        ):
            with self.assertRaises(HARNESS.ProbeFailure):
                HARNESS.cleanup_run(Path("amail"), {}, "zone", "token", "box@example.test", "nonce")
        self.assertLess(order.index(("address", "delete", "box@example.test")), order.index(("messages",)))

    def test_route_and_cli_absence_do_not_override_dirty_d1_row(self) -> None:
        """A provider route gone with D1 reconciliation pending is still live cleanup debt."""

        def fake_amail(_binary, _env, *args, failure):
            return []

        with patch.object(HARNESS, "amail", side_effect=fake_amail), patch.object(
            HARNESS, "cf_rules", return_value=[]
        ), patch.object(HARNESS, "row_snapshot", return_value=("deleting", "null", "reconcile_1")), patch.object(
            HARNESS, "cleanup_messages"
        ) as messages, patch.object(HARNESS.time, "monotonic", side_effect=[0, 1, 421]), patch.object(
            HARNESS.time, "sleep", return_value=None
        ):
            with self.assertRaises(HARNESS.ProbeFailure) as caught:
                HARNESS.cleanup_run(Path("amail"), {}, "zone", "token", "box@example.test", "nonce")
        self.assertEqual(str(caught.exception), "address_or_route_cleanup_failed")
        messages.assert_not_called()

    def test_cleanup_inventory_restarts_after_mid_page_stale(self) -> None:
        """Never combine pages across a generation change."""

        def reply(args):
            if "--cursor" in args and reply.calls == 2:
                return subprocess.CompletedProcess(args, 1, b"", (
                    b"amail: mail API messages.search failed: HTTP 409 Conflict, "
                    b"code=search_cursor_stale\n"))
            if reply.calls == 1:
                return subprocess.CompletedProcess(args, 0,
                    b'{"id":"old","mailbox":"box@example.test","direction":"inbound"}\n'
                    b'{"next_cursor":"first"}\n', b"")
            return subprocess.CompletedProcess(args, 0,
                b'{"id":"new","mailbox":"box@example.test","direction":"inbound"}\n', b"")
        reply.calls = 0

        def run(args, **_kwargs):
            reply.calls += 1
            return reply(args)

        with patch.object(HARNESS.subprocess, "run", side_effect=run), patch.object(
            HARNESS.time, "sleep", return_value=None
        ):
            found = HARNESS.cleanup_inventory(Path("amail"), {}, "box@example.test")
        self.assertEqual(set(found), {"new"})

    def test_cleanup_inventory_rejects_repeated_cursor(self) -> None:
        """A looping cursor is an incomplete inventory, not a deletion target."""

        pages = iter((b'{"id":"one","mailbox":"box@example.test","direction":"inbound"}\n'
                      b'{"next_cursor":"same"}\n',
                      b'{"id":"two","mailbox":"box@example.test","direction":"inbound"}\n'
                      b'{"next_cursor":"same"}\n'))
        with patch.object(HARNESS.subprocess, "run", side_effect=lambda *_args, **_kw:
                          subprocess.CompletedProcess([], 0, next(pages), b"")):
            with self.assertRaises(HARNESS.ProbeFailure) as caught:
                HARNESS.cleanup_inventory(Path("amail"), {}, "box@example.test")
        self.assertEqual(str(caught.exception), "cleanup_search_cursor_unverified")

    def test_cleanup_inventory_obeys_one_outer_deadline(self) -> None:
        """A second page cannot reset the cleanup time budget."""

        first = (b'{"id":"one","mailbox":"box@example.test","direction":"inbound"}\n'
                 b'{"next_cursor":"later"}\n')
        with patch.object(HARNESS.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, first, b"")) as run, patch.object(
            HARNESS.time, "monotonic", side_effect=[0, 0, 121]
        ):
            with self.assertRaises(HARNESS.ProbeFailure) as caught:
                HARNESS.cleanup_inventory(Path("amail"), {}, "box@example.test", 120)
        self.assertEqual(str(caught.exception), "cleanup_search_deadline")
        run.assert_called_once()

    def test_cleanup_verify_rejects_wrong_mailbox_and_message_id(self) -> None:
        """A matching title alone never authorizes deletion."""

        address = "box@example.test"
        subject = "AMAIL-E2E-nonce-Signal"
        oracle = {"subject": subject, "submitted_message_id": "<right@example.test>",
                  "phrase": "private"}
        listed = {"id_1": {"id": "id_1", "subject": subject}}
        detail = {"id": "id_1", "mailbox": address, "direction": "inbound",
                  "subject": subject, "from": HARNESS.SENDER, "to": [address],
                  "metadata": {"message_id": "<wrong@example.test>"}, "has_text": True,
                  "has_html": True, "has_attachments": True, "attachment_count": 2}
        with patch.object(HARNESS, "amail", return_value=[detail]):
            with self.assertRaises(HARNESS.ProbeFailure) as caught:
                HARNESS.cleanup_verify(Path("amail"), {}, address, listed, {subject: oracle})
        self.assertEqual(str(caught.exception), "cleanup_get_mismatch")
        detail["metadata"]["message_id"] = oracle["submitted_message_id"]
        detail["mailbox"] = "other@example.test"
        with patch.object(HARNESS, "amail", return_value=[detail]):
            with self.assertRaises(HARNESS.ProbeFailure) as caught:
                HARNESS.cleanup_verify(Path("amail"), {}, address, listed, {subject: oracle})
        self.assertEqual(str(caught.exception), "cleanup_get_mismatch")

    def test_ambiguous_delete_is_not_repeated(self) -> None:
        """Read back an ambiguous single-ID mutation; never submit it again."""

        subject = "AMAIL-E2E-nonce-Signal"
        oracle = {subject: {"submitted_message_id": "<id>", "phrase": "secret"},
                  "AMAIL-E2E-nonce-Distractor": {"submitted_message_id": "<id2>", "phrase": "secret2"}}
        found = {"id_1": {"id": "id_1", "subject": subject}}
        with patch.object(HARNESS, "cleanup_inventory", return_value=found), patch.object(
            HARNESS, "cleanup_verify"
        ), patch.object(HARNESS, "cleanup_delete_once", return_value=False) as delete, patch.object(
            HARNESS, "amail_not_found"
        ) as readback:
            with self.assertRaises(HARNESS.ProbeFailure) as caught:
                HARNESS.cleanup_messages(Path("amail"), {}, "box@example.test", oracle, True)
        self.assertEqual(str(caught.exception), "cleanup_delete_status_unverified")
        delete.assert_called_once()
        readback.assert_called_once()

    def test_partial_smtp_submission_requires_independent_settled_count(self) -> None:
        """One delivered fixture cannot turn a partial SMTP attempt green."""

        address = "box@example.test"
        oracles = {"Signal": {}, "Distractor": {}}

        def fake_amail(_binary, _env, *args, failure):
            if args == ("address", "list"):
                return []
            return [{"ok": True}]

        with patch.object(HARNESS, "amail", side_effect=fake_amail), patch.object(
            HARNESS, "cf_rules", return_value=[]
        ), patch.object(HARNESS, "row_snapshot", return_value=("retired", "null", "reconcile_0")), patch.object(
            HARNESS, "cleanup_messages"), patch.object(
            HARNESS, "cleanup_d1_counts", return_value=(1, 0)
        ), patch.object(HARNESS.time, "sleep", return_value=None):
            with self.assertRaises(HARNESS.ProbeFailure) as caught:
                HARNESS.cleanup_run(Path("amail"), {}, "zone", "token", address, "nonce",
                                    oracles, True, False, "account", "d1-token")
        self.assertEqual(str(caught.exception), "message_cleanup_unverified")

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
                        "CLOUDFLARE_ACCOUNT_ID": "b" * 32,
                        "CLOUDFLARE_API_TOKEN": "d1-read",
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
                        HARNESS, "print_snapshot", return_value=("route_absent", "row_absent")
                    ), patch.object(
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
