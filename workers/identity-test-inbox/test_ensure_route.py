"""Exercise fail-closed behavior of the staging-only exact routing rule.

中文：验证预发布精确路由在冲突与重复规则时保持关闭。
English: No test calls Cloudflare or uses a real token.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("ensure_test_route", Path(__file__).with_name("ensure_route.py"))
assert SPEC and SPEC.loader
route = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(route)


def fixture(worker: str = route.WORKER, enabled: bool = True, address: str = route.ADDRESS) -> dict:
    """Construct one exact provider-style rule. / 构造一条精确规则。"""

    return {
        "id": "opaque-rule",
        "source": "api",
        "enabled": enabled,
        "matchers": [{"type": "literal", "field": "to", "value": address}],
        "actions": [{"type": "worker", "value": [worker]}],
    }


class RouteTests(unittest.TestCase):
    """Rule ownership invariants. / 路由归属不变量。"""

    def test_owned_rule_is_idempotent(self) -> None:
        """Do not create duplicates. / 不创建重复规则。"""

        with patch.object(route, "list_rules", return_value=[fixture()]), patch.object(route, "call") as call:
            self.assertEqual(route.reconcile("zone", "token", "apply"), "enabled")
            call.assert_not_called()

    def test_second_configured_alias_is_exact_and_leaves_primary_untouched(self) -> None:
        """Parameterized route creation does not capture or delete another principal's route."""

        second = "amail-e2e-isolation@moesegfault.dev"
        primary = fixture()
        with patch.object(route, "list_rules", side_effect=[[primary], [primary, fixture(address=second)]]), patch.object(
            route, "call", return_value=(201, {"success": True})
        ) as call:
            self.assertEqual(route.reconcile("zone", "token", "apply", second), "created")
            self.assertEqual(call.call_args.args[3]["matchers"][0]["value"], second)
        with patch.object(route, "list_rules", return_value=[primary]), patch.object(route, "call") as call:
            self.assertEqual(route.reconcile("zone", "token", "remove", second), "absent")
            call.assert_not_called()

    def test_unconfigured_alias_fails_before_inventory_or_mutation(self) -> None:
        """Arbitrary command-line addresses cannot be routed by this helper."""

        with patch.object(route, "list_rules") as listed, patch.object(route, "call") as call:
            with self.assertRaisesRegex(RuntimeError, "allowlist"):
                route.reconcile("zone", "token", "apply", "other@moesegfault.dev")
            listed.assert_not_called()
            call.assert_not_called()

    def test_conflicting_worker_is_not_taken_over(self) -> None:
        """A foreign target is a hard conflict. / 外部目标属于硬冲突。"""

        with patch.object(route, "list_rules", return_value=[fixture(worker="foreign")]):
            with self.assertRaisesRegex(RuntimeError, "conflict"):
                route.reconcile("zone", "token", "apply")

    def test_disabled_or_duplicate_rule_is_not_taken_over(self) -> None:
        """Neither disabled nor duplicate inventory is silently repaired.

        中文：已禁用或重复的规则不能被静默修复。
        """

        for rules in ([fixture(enabled=False)], [fixture(), fixture()]):
            with self.subTest(rules=rules), patch.object(route, "list_rules", return_value=rules):
                with self.assertRaisesRegex(RuntimeError, "conflict"):
                    route.reconcile("zone", "token", "apply")

    def test_remove_requires_owned_rule(self) -> None:
        """Never delete a foreign rule. / 绝不删除外部规则。"""

        with patch.object(route, "list_rules", return_value=[fixture(worker="foreign")]), patch.object(route, "call") as call:
            with self.assertRaisesRegex(RuntimeError, "conflict"):
                route.reconcile("zone", "token", "remove")
            call.assert_not_called()

    def test_remove_requires_explicit_api_source(self) -> None:
        """An omitted source is unknown, not proof of our rule.

        中文：缺失 source 属于未知归属，不能当作自身规则删除。
        """

        unsigned = fixture()
        unsigned.pop("source")
        with patch.object(route, "list_rules", return_value=[unsigned]), patch.object(route, "call") as call:
            with self.assertRaisesRegex(RuntimeError, "conflict"):
                route.reconcile("zone", "token", "remove")
            call.assert_not_called()

    def test_total_pages_overrides_short_batch(self) -> None:
        """A short first page is not proof that another authoritative page is absent.

        中文：第一页不足分页上限，不代表服务端声明的下一页不存在。
        """

        unrelated = {"id": "other", "matchers": [{"type": "literal", "field": "to", "value": "other@example.com"}]}
        pages = [
            (200, {"success": True, "result": [unrelated], "result_info": {"total_pages": 2}}),
            (200, {"success": True, "result": [fixture(worker="foreign")], "result_info": {"total_pages": 2}}),
        ]
        with patch.object(route, "call", side_effect=pages) as call:
            rules = route.list_rules("zone", "token")
        self.assertEqual(len(rules), 2)
        self.assertIn("page=2", call.call_args_list[1].args[1])
        with patch.object(route, "list_rules", return_value=rules), patch.object(route, "call") as mutation:
            with self.assertRaisesRegex(RuntimeError, "conflict"):
                route.reconcile("zone", "token", "apply")
            mutation.assert_not_called()

    def test_zero_total_pages_is_not_a_valid_first_page(self) -> None:
        """Contradictory pagination metadata must not hide a conflicting rule.

        中文：矛盾的分页元数据不得掩盖冲突规则。
        """

        response = (200, {"success": True, "result": [], "result_info": {"total_pages": 0}})
        with patch.object(route, "call", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "pagination"):
                route.list_rules("zone", "token")

    def test_empty_204_delete_is_success_after_absence_readback(self) -> None:
        """Cloudflare may return a valid bodyless 204 for deletion.

        中文：删除可能以有效的无正文 204 响应返回，仍须回读确认消失。
        """

        with patch.object(route, "list_rules", side_effect=[[fixture()], []]), patch.object(
            route, "call", return_value=(204, {})
        ) as call:
            self.assertEqual(route.reconcile("zone", "token", "remove"), "removed")
            self.assertEqual(call.call_args.args[0], "DELETE")

    def test_create_requires_exact_enabled_worker_readback(self) -> None:
        """A successful API response alone cannot establish route ownership.

        中文：API 创建成功响应不足以证明路由归属与目标正确。
        """

        with patch.object(route, "list_rules", side_effect=[[], [fixture(worker="foreign")]]), patch.object(
            route, "call", return_value=(201, {"success": True})
        ):
            with self.assertRaisesRegex(RuntimeError, "readback"):
                route.reconcile("zone", "token", "apply")


if __name__ == "__main__":
    unittest.main()
