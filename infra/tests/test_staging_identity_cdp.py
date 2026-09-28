"""Mock-only safety checks for the staging CDP harness; no browser or network.

中文：仅使用模拟对象验证预发布 CDP 工具安全边界，不启动浏览器或网络。
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode


# CI's infrastructure job need not install websocket-client just to import
# these pure/mock checks. The real harness requires the installed package.
# CI 基础设施任务无需为纯模拟测试安装 websocket-client；实际工具仍要求已安装。
sys.modules.setdefault("websocket", types.ModuleType("websocket"))
SPEC = importlib.util.spec_from_file_location(
    "staging_identity_cdp", Path(__file__).with_name("staging_identity_cdp.py")
)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class HarnessSafetyTests(unittest.TestCase):
    """Exercise secret isolation and route-finally semantics. / 验证秘密隔离与路由 finally 语义。"""

    def test_browser_environment_is_allowlisted(self) -> None:
        """An unrecognized credential-like value never reaches Chrome or CLI.

        中文：未识别的敏感环境变量不能传入 Chrome 或 CLI。
        """

        environment = {
            "SystemRoot": r"C:\Windows",
            "PATH": r"C:\Windows\System32",
            "ROLE_FORWARD_DESTINATION": "private-address",
            "UNEXPECTED_SESSION_NOTE": "sensitive-note",
            "CF_EMAIL_ROUTING_TOKEN": "sensitive-token",
        }
        with patch.dict(os.environ, environment, clear=True):
            passed = probe.browser_environment()
        self.assertEqual(set(passed), {"SystemRoot", "PATH"})

    def test_route_closes_even_if_browser_close_raises(self) -> None:
        """A teardown exception cannot leave the OTP route open.

        中文：浏览器关闭异常也不能跳过验证码路由清理。
        """

        states = iter(["enabled", "enabled", "enabled", "absent"])
        actions: list[str | None] = []

        def fake_route(action: str | None = None) -> str:
            """Simulate the exact helper without contacting Cloudflare. / 模拟精确助手而不联系 Cloudflare。"""

            actions.append(action)
            return "removed" if action == "--remove" else next(states)

        browser = Mock()
        browser.navigate.side_effect = probe.ProbeError("synthetic_registration_failure")
        browser.close.side_effect = OSError("synthetic local teardown")
        with (
            patch.object(probe, "route", side_effect=fake_route),
            patch.object(probe, "Browser", return_value=browser),
            patch.object(probe, "generate_credential", return_value=("amail_e2e_synthetic", "safe-password-123456789")),
            patch.object(probe, "store_credential"),
            patch.object(probe.time, "sleep"),
        ):
            with self.assertRaisesRegex(
                probe.ProbeError, "synthetic_registration_failure\\+browser_teardown_failed"
            ):
                probe.registration(Path(".temp/mock-run"))
        self.assertIn("--remove", actions)
        self.assertEqual(actions[-1], None)

    def test_native_url_requires_state_nonce_and_pkce_challenge(self) -> None:
        """A syntactically plausible URL without fresh proof fields is refused.

        中文：缺少 state、nonce 或 PKCE challenge 的授权 URL 必须被拒绝。
        """

        fields = {
            "client_id": probe.CLIENT,
            "response_type": "code",
            "code_challenge_method": "S256",
            "code_challenge": "a" * 43,
            "state": "b" * 43,
            "nonce": "c" * 43,
            "scope": "openid profile offline_access",
            "redirect_uri": "http://127.0.0.1:49152/callback",
        }
        url = lambda values: f"{probe.ISSUER}/oauth/authorize?{urlencode(values)}"
        self.assertTrue(probe.valid_authorization_url(url(fields)))
        for key in ("state", "nonce", "code_challenge"):
            broken = {name: value for name, value in fields.items() if name != key}
            with self.subTest(key=key):
                self.assertFalse(probe.valid_authorization_url(url(broken)))
        self.assertFalse(probe.valid_authorization_url(url({**fields, "redirect_uri": "https://foreign.example/callback"})))


if __name__ == "__main__":
    unittest.main()
