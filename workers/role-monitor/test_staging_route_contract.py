"""Independently exercise exact-route lifecycle invariants. / 独立验证精确路由生命周期不变量。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import staging_route as route


def owned_rule() -> dict:
    """Build one provider-shaped owned route. / 构造一条供应商形状的自有规则。"""

    return {
        "id": "synthetic-id",
        "name": route.NAME,
        "enabled": True,
        "source": "api",
        "matchers": [{"type": "literal", "field": "to", "value": route.ALIAS}],
        "actions": [{"type": "worker", "value": [route.WORKER]}],
    }


class RouteLifecycleContractTests(unittest.TestCase):
    """Mutations must affect only one exact synthetic route. / 变更只能影响一条精确合成路由。"""

    def test_apply_creates_once_then_is_idempotent(self) -> None:
        """A retry must not create a duplicate rule. / 重试不得创建重复规则。"""

        inventory = []
        calls = []

        def provider(method: str, path: str, _token: str, body: dict | None = None):
            """Model a minimal successful provider write. / 模拟最小成功的供应商写入。"""

            calls.append((method, path, body))
            self.assertEqual(method, "POST")
            self.assertEqual(body["matchers"], owned_rule()["matchers"])
            self.assertEqual(body["actions"], owned_rule()["actions"])
            inventory.append(owned_rule())
            return 201, {"success": True}

        with patch.object(route, "rules", side_effect=lambda *_: list(inventory)), patch.object(
            route, "call", side_effect=provider
        ):
            self.assertEqual(route.reconcile("zone", "token", "apply"), "created")
            self.assertEqual(route.reconcile("zone", "token", "apply"), "enabled")
        self.assertEqual(len(calls), 1)

    def test_remove_refuses_duplicate_alias_before_write(self) -> None:
        """Two matching rules are a conflict, not a cleanup target. / 两条匹配规则是冲突而非清理目标。"""

        with patch.object(route, "rules", return_value=[owned_rule(), owned_rule()]), patch.object(
            route, "call"
        ) as provider:
            with self.assertRaisesRegex(RuntimeError, "conflict"):
                route.reconcile("zone", "token", "remove")
            provider.assert_not_called()

    def test_remove_requires_readback_absence(self) -> None:
        """Provider success alone cannot prove an exact route is gone. / 供应商成功响应不能单独证明路由消失。"""

        with patch.object(route, "rules", side_effect=[[owned_rule()], [owned_rule()]]), patch.object(
            route, "call", return_value=(204, {})
        ) as provider:
            with self.assertRaisesRegex(RuntimeError, "readback"):
                route.reconcile("zone", "token", "remove")
            self.assertEqual(provider.call_count, 1)

    def test_inventory_rejects_truncated_page(self) -> None:
        """A partial provider page must not hide a conflicting rule. / 部分供应商页面不得隐藏冲突规则。"""

        page = {
            "success": True,
            "result": [owned_rule()],
            "result_info": {
                "page": 1,
                "per_page": 50,
                "count": 1,
                "total_count": 51,
                "total_pages": 2,
            },
        }
        with patch.object(route, "call", return_value=(200, page)):
            with self.assertRaisesRegex(RuntimeError, "pagination"):
                route.rules("zone", "token")

    def test_unknown_action_cannot_delete_owned_route(self) -> None:
        """A typo must fail rather than select the destructive branch. / 拼写错误必须失败，不能进入删除分支。"""

        with patch.object(route, "rules", return_value=[owned_rule()]), patch.object(
            route, "call"
        ) as provider:
            with self.assertRaises((RuntimeError, ValueError)):
                route.reconcile("zone", "token", "audti")
            provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()
