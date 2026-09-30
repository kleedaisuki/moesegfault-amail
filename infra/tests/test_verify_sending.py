"""不连接 Cloudflare 或 DNS 即可测试生产门禁。 / Test the gate without network calls."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "dns" / "verify_sending.py"
SPEC = importlib.util.spec_from_file_location("verify_sending", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class VerifySendingTest(unittest.TestCase):
    """测试区域边界、提供商查询和传播重试。 / Test scope, lookup, and retries."""

    def test_relative_name_is_scoped_to_mail(self) -> None:
        """接受邮件子域内的相对名称。 / Accept a mail-scoped relative name."""

        self.assertEqual(MODULE.fqdn("cf-bounce.mail"), "cf-bounce.mail.moesegfault.dev")

    def test_apex_and_sibling_are_rejected(self) -> None:
        """提供商记录不能扩大到根域。 / Never expand scope to the apex."""

        for name in ("@", "moesegfault.dev", "login.moesegfault.dev"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                MODULE.fqdn(name)

    def test_staging_name_cannot_escape_into_production_mail(self) -> None:
        """预发记录不得落入生产邮件子域。 / Keep staging DNS out of production mail."""

        with patch.object(MODULE, "DOMAIN", "mail-staging.moesegfault.dev"):
            self.assertEqual(MODULE.fqdn("cf-bounce.mail-staging"), "cf-bounce.mail-staging.moesegfault.dev")
            with self.assertRaises(ValueError):
                MODULE.fqdn("cf-bounce.mail.moesegfault.dev")

    def test_mx_normalization_keeps_priority(self) -> None:
        """MX 大小写与末尾点仅是表示差异。 / Ignore MX presentation differences."""

        result = MODULE.normalize(
            {"name": "cf-bounce.mail", "type": "MX", "content": "ROUTE1.MX.CLOUDFLARE.NET.", "priority": 10}
        )
        self.assertEqual(result.content, "route1.mx.cloudflare.net")
        self.assertEqual(result.priority, 10)

    def test_provider_lookup_uses_exact_enabled_subdomain(self) -> None:
        """即使 API 返回根域，也只选目标域。 / Select only the target domain."""

        def fake_get(path: str, _token: str) -> list[dict]:
            if path.endswith("/dns"):
                return [{"name": "_dmarc.mail", "type": "TXT", "content": "v=DMARC1; p=reject"}]
            return [
                {"name": "moesegfault.dev", "enabled": True, "tag": "apex"},
                {"name": "mail.moesegfault.dev", "enabled": True, "tag": "mail-id"},
            ]

        with patch.object(MODULE, "api_get", side_effect=fake_get) as api:
            result = MODULE.expected_records("a" * 32, "token")
        self.assertEqual(len(result), 1)
        self.assertTrue(api.call_args.args[0].endswith("/mail-id/dns"))

    def test_propagation_retry_requires_every_nameserver(self) -> None:
        """权威服务器未同步时阻止部署。 / Block until lagging servers catch up."""

        wanted = {MODULE.Record("_dmarc.mail.moesegfault.dev", "TXT", "v=DMARC1; p=reject")}
        observed = [set(), wanted]

        def answers(address: str, _wanted: set) -> set:
            return wanted if address == "192.0.2.1" else observed.pop(0)

        with (
            patch.object(MODULE, "expected_records", return_value=wanted),
            patch.object(MODULE, "nameserver_addresses", return_value={"ns1": ["192.0.2.1"], "ns2": ["192.0.2.2"]}),
            patch.object(MODULE, "authoritative_records", side_effect=answers),
            patch.object(MODULE.time, "sleep") as sleep,
        ):
            MODULE.verify("a" * 32, "token", retries=2, delay=1)
        sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
