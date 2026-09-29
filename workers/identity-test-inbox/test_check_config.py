"""Protect the private, staging-only Wrangler contract.

中文：保护 Wrangler 配置的私有和预发布隔离约束。
English: These tests do not deploy or contact Cloudflare.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import tomllib
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("check_test_inbox_config", Path(__file__).with_name("check_config.py"))
assert SPEC and SPEC.loader
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


class ConfigTests(unittest.TestCase):
    """Source-level deployment boundary checks. / 源码级部署边界检查。"""

    def setUp(self) -> None:
        """Load the tracked config only. / 只读取受版本控制的配置。"""

        with Path(__file__).with_name("wrangler.toml").open("rb") as stream:
            self.config = tomllib.load(stream)

    def test_tracked_config_is_private(self) -> None:
        """The intended config is admissible. / 预期配置可通过检查。"""

        self.assertTrue(check.valid(self.config))

    def test_http_route_is_rejected(self) -> None:
        """No custom domain, workers.dev, or preview may publish this Worker.

        中文：不可通过自定义域名、workers.dev 或预览发布此 Worker。
        """

        for field, value in (("routes", ["test.example.com"]), ("workers_dev", True), ("preview_urls", True)):
            candidate = copy.deepcopy(self.config)
            candidate[field] = value
            with self.subTest(field=field):
                self.assertFalse(check.valid(candidate))

    def test_other_bucket_is_rejected(self) -> None:
        """Never bind the user or operator mail buckets. / 不绑定用户或运营邮件存储桶。"""

        candidate = copy.deepcopy(self.config)
        candidate["r2_buckets"][0]["bucket_name"] = "moesegfault-mail-raw-staging"
        self.assertFalse(check.valid(candidate))

    def test_only_reviewed_apex_recipients_are_allowed(self) -> None:
        """Do not turn the private inbox into a broad contact or user-mail sink."""

        self.assertEqual(check.recipients(self.config), frozenset({
            "amail-e2e@moesegfault.dev", "amail-e2e-isolation@moesegfault.dev",
        }))
        for value in (
            "amail-e2e@moesegfault.dev,other@moesegfault.dev",
            "amail-e2e@moesegfault.dev,amail-e2e@mail.moesegfault.dev",
            "amail-e2e@moesegfault.dev,amail-e2e@moesegfault.dev",
            "amail-e2e@moesegfault.dev,amail-e2e-next@moesegfault.dev,",
        ):
            candidate = copy.deepcopy(self.config)
            candidate["vars"]["TEST_RECIPIENTS"] = value
            with self.subTest(value=value):
                self.assertFalse(check.valid(candidate))

    def test_live_bucket_requires_private_surfaces_and_retention(self) -> None:
        """No public domain may remain and the expiry rule must be active.

        中文：不得残留公开域名，并且必须启用过期规则。
        """

        private = [
            (200, {"success": True, "result": {"enabled": False}}),
            (200, {"success": True, "result": {"domains": []}}),
            (200, {"success": True, "result": {"rules": [{
                "id": "amail-test-expire",
                "enabled": True,
                "conditions": {"prefix": "verification/"},
                "deleteObjectsTransition": {"condition": {"type": "Age", "maxAge": 86_400}},
            }]}}),
        ]
        with patch.object(check, "fetch_json", side_effect=private) as fetch:
            check.private_bucket("a" * 32, "token")
            self.assertTrue(fetch.call_args_list[0].args[0].endswith("/domains/managed"))
            self.assertTrue(fetch.call_args_list[1].args[0].endswith("/domains/custom"))
            self.assertTrue(fetch.call_args_list[2].args[0].endswith("/lifecycle"))

    def test_live_bucket_fails_closed_on_public_or_unreadable_state(self) -> None:
        """A 403 or public surface is a deployment stop, never a warning.

        中文：403 或公开入口必须阻断部署，不能仅告警。
        """

        cases = [
            [(403, {})],
            [(200, {"success": True, "result": {"enabled": True}})],
            [(200, {"success": True, "result": {"enabled": False}}), (403, {})],
            [(200, {"success": True, "result": {"enabled": False}}), (200, {"success": True, "result": {"domains": [{"domain": "public.example"}]}})],
            [(200, {"success": True, "result": {"enabled": False}}), (200, {"success": True, "result": {"domains": []}}), (403, {})],
            [(200, {"success": True, "result": {"enabled": False}}), (200, {"success": True, "result": {"domains": []}}), (200, {"success": True, "result": {"rules": [{
                "id": "amail-test-expire",
                "enabled": True,
                "conditions": {"prefix": "verification/"},
                "deleteObjectsTransition": {"condition": {"type": "Age", "maxAge": 172_800}},
            }]}})],
        ]
        for responses in cases:
            with self.subTest(responses=responses), patch.object(check, "fetch_json", side_effect=responses):
                with self.assertRaises(RuntimeError):
                    check.private_bucket("a" * 32, "token")


if __name__ == "__main__":
    unittest.main()
