"""Mock-only safety checks for the staging CDP harness; no browser or network.

中文：仅使用模拟对象验证预发布 CDP 工具安全边界，不启动浏览器或网络。
"""

from __future__ import annotations

import importlib.util
import json
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
        # Windows normalizes environment key casing, unlike Linux CI.
        # Windows 会规范化环境变量键的大小写，Linux CI 则保留原样。
        self.assertEqual({key.upper() for key in passed}, {"SYSTEMROOT", "PATH"})

    def test_route_closes_even_if_browser_close_raises(self) -> None:
        """A teardown exception cannot leave the OTP route open.

        中文：浏览器关闭异常也不能跳过验证码路由清理。
        """

        states = iter(["enabled", "enabled", "enabled", "absent"])
        actions: list[str | None] = []

        def fake_route(action: str | None = None, address: str = probe.ALIAS) -> str:
            """Simulate the exact helper without contacting Cloudflare. / 模拟精确助手而不联系 Cloudflare。"""

            actions.append(action)
            self.assertEqual(address, probe.ALIAS)
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

    def test_registration_passes_selected_alias_to_every_route_operation(self) -> None:
        """A second test contact cannot silently open or close the first route."""

        second = "amail-e2e-isolation@moesegfault.dev"
        observed: list[tuple[str | None, str]] = []
        states = iter(["enabled", "enabled", "enabled", "absent"])
        def fake_route(action: str | None = None, address: str = probe.ALIAS) -> str:
            """Record only local mock calls."""
            observed.append((action, address))
            return "removed" if action == "--remove" else next(states)
        browser = Mock()
        browser.navigate.side_effect = probe.ProbeError("synthetic_registration_failure")
        with (
            patch.object(probe, "route", side_effect=fake_route),
            patch.object(probe, "Browser", return_value=browser),
            patch.object(probe, "generate_credential", return_value=("amail_e2e_synthetic", "safe-password-123456789")),
            patch.object(probe, "store_credential") as store,
            patch.object(probe.time, "sleep"),
        ):
            with self.assertRaisesRegex(probe.ProbeError, "synthetic_registration_failure"):
                probe.registration(Path(".temp/mock-run"), second)
        self.assertEqual(store.call_args.args[3], second)
        self.assertTrue(observed)
        self.assertTrue(all(address == second for _, address in observed))

    def test_encrypted_payload_supports_existing_first_principal_only(self) -> None:
        """Legacy A blobs remain usable; B never silently falls back to A."""

        payload = {"username": "amail_e2e_synthetic", "password": "safe-password-123456789"}
        self.assertEqual(probe.decoded_credential(payload)[2], probe.ALIAS)
        second = "amail-e2e-isolation@moesegfault.dev"
        self.assertEqual(probe.decoded_credential({**payload, "address": second})[2], second)
        with self.assertRaisesRegex(probe.ProbeError, "dpapi_credential_invalid"):
            probe.decoded_credential({**payload, "address": "mail@moesegfault.dev"})

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

    def test_identity_responses_ignore_preflight_for_every_post_stage(self) -> None:
        """OPTIONS 204 cannot masquerade as any successful Identity POST.

        中文：三类验证端点都不能将 OPTIONS 204 误判为真实 POST 响应。
        """

        paths = (
            probe.REGISTRATION,
            "/v1/me/contacts/contact-1/verification-transactions",
            "/v1/me/contacts/contact-1/verification-transactions/tx-1/completion",
        )
        for path in paths:
            with self.subTest(path=path):
                browser = object.__new__(probe.Browser)
                browser.request_methods = {}
                browser.responses = {}
                browser.finished = set()
                events = [
                    {"method": "Network.requestWillBeSent", "params": {
                        "requestId": "preflight", "request": {"method": "OPTIONS"}}},
                    {"method": "Network.responseReceived", "params": {
                        "requestId": "preflight", "response": {
                            "url": probe.ISSUER + path, "status": 204}}},
                    {"method": "Network.loadingFinished", "params": {"requestId": "preflight"}},
                    {"method": "Network.requestWillBeSent", "params": {
                        "requestId": "actual", "request": {"method": "POST"}}},
                    {"method": "Network.responseReceived", "params": {
                        "requestId": "actual", "response": {
                            "url": probe.ISSUER + path, "status": 201}}},
                ]
                browser.ws = Mock()
                browser.ws.recv.side_effect = [json.dumps(event) for event in events]
                for _ in range(3):
                    browser._receive(1)
                self.assertEqual(browser.responses, {})
                for _ in range(2):
                    browser._receive(1)
                self.assertEqual(browser.response(lambda observed: observed == path, timeout=0.01), (201, "actual"))

    def test_redirect_reuses_request_id_without_inheriting_post_method(self) -> None:
        """A redirected GET must not inherit the original POST method.

        中文：重定向复用请求 ID 时，新 GET 不得继承旧 POST 的语义。
        """

        browser = object.__new__(probe.Browser)
        browser.request_methods = {}
        browser.responses = {}
        browser.finished = set()
        events = [
            {"method": "Network.requestWillBeSent", "params": {
                "requestId": "reused", "request": {"method": "POST"}}},
            {"method": "Network.requestWillBeSent", "params": {
                "requestId": "reused", "request": {"method": "GET"},
                "redirectResponse": {"status": 303}}},
            {"method": "Network.responseReceived", "params": {
                "requestId": "reused", "response": {
                    "url": probe.ISSUER + probe.REGISTRATION, "status": 200}}},
        ]
        browser.ws = Mock()
        browser.ws.recv.side_effect = [json.dumps(event) for event in events]
        for _ in events:
            browser._receive(1)
        self.assertEqual(browser.responses, {})


if __name__ == "__main__":
    unittest.main()
