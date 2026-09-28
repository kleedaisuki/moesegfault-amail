"""Guard the private role-monitor deployment boundary. / 守护私有角色监控部署边界。"""

from __future__ import annotations

import pathlib
import tomllib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG = ROOT / "workers" / "role-monitor" / "wrangler.toml"


class RoleMonitorConfigTests(unittest.TestCase):
    """Prevent an accidental public endpoint or cross-realm D1 binding. / 防止意外公开入口或跨环境 D1 绑定。"""

    def test_staging_and_production_are_isolated(self) -> None:
        """The monitor has no HTTP route and no Wrangler-owned mail addresses. / 监控器无 HTTP 路由或 Wrangler 管理的邮件地址。"""

        config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertFalse(config["workers_dev"])
        self.assertFalse(config["preview_urls"])
        self.assertNotIn("routes", config)
        self.assertNotIn("addresses", config)
        self.assertFalse(config["env"]["staging"]["workers_dev"])
        self.assertFalse(config["env"]["staging"]["preview_urls"])
        self.assertNotIn("routes", config["env"]["staging"])
        self.assertNotIn("addresses", config["env"]["staging"])
        self.assertNotEqual(
            config["d1_databases"][0]["database_id"],
            config["env"]["staging"]["d1_databases"][0]["database_id"],
        )
        self.assertEqual(config["d1_databases"][0]["binding"], "ROLE_MONITOR")
        self.assertEqual(config["env"]["staging"]["d1_databases"][0]["binding"], "ROLE_MONITOR")

    def test_binding_fixes_official_sender_without_leaking_destination(self) -> None:
        """Only the official sender is committed; destination remains protected. / 只提交官方发件人，目的地保密。"""

        config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
        for binding in (config["send_email"][0], config["env"]["staging"]["send_email"][0]):
            self.assertEqual(binding["name"], "ROLE_ALERT")
            self.assertEqual(binding["allowed_sender_addresses"], ["mail@moesegfault.dev"])
            self.assertNotIn("destination_address", binding)
            self.assertNotIn("allowed_destination_addresses", binding)


if __name__ == "__main__":
    unittest.main()
