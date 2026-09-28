"""Pure contract checks for operator route ownership and staging isolation.

中文：纯逻辑测试；部署和 SMTP 验证必须在托管环境中另行执行。
English: Pure logic tests; hosted deployment and SMTP proof are separate.
"""

import importlib.util
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location(
    "ensure_ops_routes", Path(__file__).resolve().parents[1] / "ensure_routes.py"
)
assert SPEC and SPEC.loader
routes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(routes)


class RouteContract(unittest.TestCase):
    """Keep system addresses separate and refuse a conflicting destination.

    中文：系统地址独立管理，绝不接管冲突路由。
    """

    def test_production_and_staging_are_distinct(self):
        """Staging never owns apex or production mail-domain roles.

        中文：预发布不占用根域名和生产子域名角色。
        """

        prod_worker, prod = routes.roles("production")
        stage_worker, stage = routes.roles("staging")
        self.assertEqual(prod_worker, "amail-ops")
        self.assertEqual(stage_worker, "amail-ops-staging")
        self.assertEqual(len(prod), 4)
        self.assertEqual(len(stage), 2)
        self.assertFalse(set(prod) & set(stage))

    def test_only_enabled_exact_worker_rule_matches(self):
        """Wrong Worker and disabled role routes cannot be silently reused.

        中文：错误 Worker 或停用的角色路由不能被静默沿用。
        """

        address = "postmaster@mail.moesegfault.dev"
        rule = {
            "enabled": True,
            "matchers": [{"type": "literal", "field": "to", "value": address}],
            "actions": [{"type": "worker", "value": ["amail-ops"]}],
        }
        self.assertTrue(routes.matches(rule, "amail-ops", address))
        self.assertFalse(routes.matches(rule, "amail-inbound", address))
        rule["enabled"] = False
        self.assertFalse(routes.matches(rule, "amail-ops", address))


if __name__ == "__main__":
    unittest.main()
