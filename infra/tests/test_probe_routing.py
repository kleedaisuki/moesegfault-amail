"""Exercise bounded Cloudflare routing-token diagnostics without network calls.

中文：验证令牌状态分类与日志脱敏；不调用真实 Cloudflare API。
English: Check token-state classification and log redaction without Cloudflare.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import pathlib
import sys
import unittest
from unittest.mock import patch

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "provider" / "probe_routing.py"
SPEC = importlib.util.spec_from_file_location("probe_routing", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

ENV = {
    "CF_ZONE_ID": "a" * 32,
    "CLOUDFLARE_ACCOUNT_ID": "b" * 32,
    "CF_EMAIL_ROUTING_TOKEN": "secret-never-log",
}


class ProbeRoutingTest(unittest.TestCase):
    """保留诊断价值，但绝不输出凭据或规则。 / Diagnose without leaking secrets."""

    def test_valid_rules_read_skips_token_verification(self) -> None:
        """成功时不多请求令牌接口。 / Avoid extra token calls on success."""

        with patch.dict("os.environ", ENV), patch.object(MODULE, "_request", return_value=(200, {"success": True, "result": []})) as request:
            self.assertEqual(MODULE.main(), 0)
        request.assert_called_once_with(f"/zones/{ENV['CF_ZONE_ID']}/email/routing/rules?per_page=5", ENV["CF_EMAIL_ROUTING_TOKEN"])

    def test_active_token_with_denied_rules_is_classified_without_leak(self) -> None:
        """有效凭据与规则权限不足可区分。 / Distinguish active token from denied rules."""

        replies = [
            (403, {"errors": [{"code": 10000, "message": "secret-never-log"}]}),
            (200, {"success": True, "result": {"id": "private-token-id", "status": "active"}}),
        ]
        output = io.StringIO()
        with patch.dict("os.environ", ENV), patch.object(MODULE, "_request", side_effect=replies), contextlib.redirect_stderr(output):
            self.assertEqual(MODULE.main(), 1)
        report = output.getvalue()
        self.assertIn("HTTP403, codes=10000, token=user:active", report)
        self.assertNotIn("secret-never-log", report)
        self.assertNotIn("private-token-id", report)

    def test_account_token_expiry_is_reported_safely(self) -> None:
        """兼容账户令牌验证接口。 / Fall back to account-token verification."""

        replies = [
            (403, {"errors": [{"code": 10000}]}),
            (403, {"errors": [{"code": 10000}]}),
            (200, {"success": True, "result": {"status": "expired"}}),
        ]
        output = io.StringIO()
        with patch.dict("os.environ", ENV), patch.object(MODULE, "_request", side_effect=replies), contextlib.redirect_stderr(output):
            self.assertEqual(MODULE.main(), 1)
        self.assertIn("token=account:expired", output.getvalue())

    def test_error_codes_are_numeric_and_bounded(self) -> None:
        """错误消息、布尔值与任意对象不得进入日志。 / Log numeric codes only."""

        self.assertEqual(
            MODULE._codes({"errors": [{"code": 1000}, {"code": True}, {"code": "secret"}, {"code": 2000}]}),
            "1000",
        )


if __name__ == "__main__":
    unittest.main()
