"""Contract tests for fail-closed operator deployment configuration.

中文：验证部署配置默认拒绝以及用户邮箱存储隔离。
English: Verify sentinel denial and isolation from user mailbox storage.
"""

import importlib.util
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_ops_config", ROOT / "check_config.py")
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def prepared() -> dict:
    """Construct synthetic, non-live values for pure config checks.

    中文：使用合成非实值构造纯配置校验输入。
    """

    config = tomllib.loads((ROOT / "wrangler.toml.template").read_text(encoding="utf-8"))
    config["vars"]["TEAM_DOMAIN"] = "https://example.cloudflareaccess.com"
    config["vars"]["ACCESS_AUD"] = "synthetic-production-aud"
    config["d1_databases"][0]["database_id"] = "11111111-1111-4111-8111-111111111111"
    stage = config["env"]["staging"]
    stage["vars"]["TEAM_DOMAIN"] = "https://example.cloudflareaccess.com"
    stage["vars"]["ACCESS_AUD"] = "synthetic-staging-aud"
    stage["d1_databases"][0]["database_id"] = "22222222-2222-4222-8222-222222222222"
    return config


class ConfigContract(unittest.TestCase):
    """Deployment may never depend on default placeholders or user DBs.

    中文：部署绝不依赖模板哨兵或用户数据库。
    """

    def test_template_is_not_deployable(self):
        """Unfilled template denies production and staging.

        中文：未填模板在生产和预发布均拒绝。
        """

        config = tomllib.loads((ROOT / "wrangler.toml.template").read_text(encoding="utf-8"))
        for target in ("production", "staging"):
            with self.assertRaises(ValueError):
                checker.check(config, target)

    def test_isolated_config_passes(self):
        """Synthetic, separate bindings are allowed by pure checks.

        中文：合成且隔离的绑定通过纯逻辑校验。
        """

        config = prepared()
        checker.check(config, "production")
        checker.check(config, "staging")

    def test_user_mail_db_is_rejected(self):
        """A plausible ID cannot point OPS_DB at user MAIL_DB.

        中文：有效格式的 ID 也不能把 OPS_DB 指向用户 MAIL_DB。
        """

        config = prepared()
        config["d1_databases"][0]["database_id"] = "ad06f7f3-8897-4150-b9a9-7a46a8e55b30"
        with self.assertRaises(ValueError):
            checker.check(config, "production")


if __name__ == "__main__":
    unittest.main()
