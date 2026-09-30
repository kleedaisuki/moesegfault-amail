"""Validate production release gating without touching Cloudflare or local Rust.

中文：用纯内存响应验证出站发布门禁的失败关闭行为。
English: Exercise fail-closed outbound release checks with in-memory responses.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "release" / "check_send_gate.py"
SPEC = importlib.util.spec_from_file_location("check_send_gate", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def payload(**overrides: int) -> dict:
    """构造最小 D1 查询结果。 / Build the minimal D1 query response."""

    row = {
        "global_rows": 1,
        "global_allowed": 1,
        "gate_rows": 1,
        "gates_ready": 1,
        "contact_ready": 1,
    }
    row.update(overrides)
    return {"success": True, "result": [{"success": True, "results": [row]}]}


class CheckSendGateTest(unittest.TestCase):
    """任何缺失、重复、未确认或错误都不得发布。 / Deny missing or unready state."""

    def test_only_exact_singleton_allowed_and_all_gates_ready_passes(self) -> None:
        """成功状态必须完整且唯一。 / Require exact singleton readiness."""

        self.assertTrue(MODULE.release_ready(payload()))
        for key in ("global_rows", "global_allowed", "gate_rows", "gates_ready", "contact_ready"):
            with self.subTest(key=key):
                self.assertFalse(MODULE.release_ready(payload(**{key: 0})))
                self.assertFalse(MODULE.release_ready(payload(**{key: 2})))
                self.assertFalse(MODULE.release_ready(payload(**{key: True})))

    def test_malformed_or_failed_query_is_denied(self) -> None:
        """远端错误和非单行结果失败关闭。 / Deny malformed or failed D1 responses."""

        for body in (
            {},
            {"success": False, "result": [{"success": True, "results": [{}]}]},
            {"success": True, "result": []},
            {"success": True, "result": [{"success": False, "results": [payload()]}]},
            {"success": True, "result": [{"success": True, "results": []}]},
        ):
            with self.subTest(body=body):
                self.assertFalse(MODULE.release_ready(body))

    def test_run_reads_health_then_only_fixed_production_database(self) -> None:
        """只读取固定生产库，不把标识符写入输出。 / Query the fixed production DB only."""

        env = {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "secret"}
        with patch.dict("os.environ", env), patch.object(MODULE, "_json_request", side_effect=[{"status": "ok"}, payload()]) as fetch:
            MODULE.run()
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(fetch.call_args_list[0].args[0].full_url, MODULE.MAIL_HEALTH)
        database_request = fetch.call_args_list[1].args[0]
        self.assertIn(MODULE.PRODUCTION_D1_ID, database_request.full_url)
        self.assertEqual(database_request.get_method(), "POST")
        self.assertIn(b"SELECT", database_request.data)

    def test_run_requires_health_and_credentials(self) -> None:
        """无凭据或不健康 API 阻止发布。 / Missing credentials or health deny release."""

        with patch.dict("os.environ", {"CLOUDFLARE_ACCOUNT_ID": "", "CLOUDFLARE_API_TOKEN": ""}):
            with self.assertRaises(MODULE.GateError):
                MODULE.run()
        env = {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "secret"}
        with patch.dict("os.environ", env), patch.object(MODULE, "_json_request", return_value={"status": "down"}):
            with self.assertRaises(MODULE.GateError):
                MODULE.run()


if __name__ == "__main__":
    unittest.main()
