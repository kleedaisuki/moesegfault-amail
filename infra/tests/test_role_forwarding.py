"""Exercise private-destination role forwarding without calling Cloudflare.

中文：验证分页、冲突拒绝、幂等和保密输出的离线契约。
English: Cover pagination, conflict refusal, idempotence, and non-disclosure.
"""

from __future__ import annotations

import importlib.util
import io
import os
import pathlib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch


PATH = pathlib.Path(__file__).resolve().parents[1] / "provider" / "ensure_role_forwarding.py"
SPEC = importlib.util.spec_from_file_location("ensure_role_forwarding", PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
import sys

sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
DESTINATION = "private@example.invalid"


def rule(role: str, destination: str = DESTINATION, *, enabled: bool = True) -> dict:
    """Build one canonical synthetic routing rule. / 构造测试规则。"""

    return {
        "enabled": enabled,
        "source": "api",
        "matchers": [{"type": "literal", "field": "to", "value": role}],
        "actions": [{"type": "forward", "value": [destination]}],
    }


class FakeClient:
    """Simulate Cloudflare account destinations and zone rules. / 模拟控制面。"""

    account = "a" * 32

    def __init__(self, *, verified: bool = False, current: list[dict] | None = None) -> None:
        """Create an isolated inventory. / 创建隔离清单。"""

        self.verified = verified
        self.destination_exists = verified
        self.current = current or []
        self.posts: list[str] = []

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        """Return paged fixtures and record mutations. / 返回分页清单。"""

        if method == "GET":
            if "/addresses" in path:
                entries = (
                    [{"email": DESTINATION, "verified": "2026-09-28T00:00:00Z" if self.verified else None}]
                    if self.destination_exists
                    else []
                )
            else:
                entries = self.current
            return {
                "success": True,
                "result": entries,
                "result_info": {"page": 1, "per_page": 50, "count": len(entries), "total_count": len(entries)},
            }
        assert method == "POST" and body is not None
        if "/addresses" in path:
            self.destination_exists = True
            self.posts.append("address")
        else:
            self.current.append(body)
            self.posts.append("rule")
        return {"success": True, "result": body}


class RoleForwardTests(unittest.TestCase):
    """Reject unsafe alias states before mutation. / 在变更前拒绝不安全状态。"""

    def test_request_verification_is_idempotent(self) -> None:
        """A pending destination is not created twice. / 待验证地址不会重复创建。"""

        client = FakeClient()
        MODULE.execute(client, "request-verification", DESTINATION)
        MODULE.execute(client, "request-verification", DESTINATION)
        self.assertEqual(client.posts, ["address"])
        self.assertEqual(client.current, [])

    def test_apply_requires_verified_destination(self) -> None:
        """Unverified addresses cannot receive role rules. / 未验证不能建规则。"""

        client = FakeClient()
        with self.assertRaises(MODULE.ProvisionError):
            MODULE.execute(client, "apply", DESTINATION)
        self.assertEqual(client.posts, [])

    def test_apply_creates_exact_four_once(self) -> None:
        """Applying twice is safe and readback is exact. / 两次执行仍只有四条。"""

        client = FakeClient(verified=True)
        MODULE.execute(client, "apply", DESTINATION)
        MODULE.execute(client, "apply", DESTINATION)
        self.assertEqual(client.posts, ["rule"] * 4)
        self.assertEqual(MODULE.audit(client.current, DESTINATION), set(MODULE.ROLES))

    def test_catch_all_fallback_can_coexist_with_exact_roles(self) -> None:
        """Cloudflare matches literal rules before catch-all fallback. / 精确规则先于兜底。"""

        catch_all = {
            "enabled": True,
            "source": "api",
            "matchers": [{"type": "all"}],
            "actions": [{"type": "forward", "value": ["fallback@example.invalid"]}],
        }
        client = FakeClient(verified=True, current=[catch_all])
        MODULE.execute(client, "apply", DESTINATION)
        self.assertEqual(client.posts, ["rule"] * 4)
        self.assertEqual(MODULE.audit(client.current, DESTINATION), set(MODULE.ROLES))

    def test_conflicting_or_duplicate_rule_blocks_all_writes(self) -> None:
        """Never take over existing routes. / 不接管已有路由。"""

        role = MODULE.ROLES[0]
        conflicts = [
            [rule(role, "wrong@example.invalid")],
            [rule(role, enabled=False)],
            [rule(role), rule(role)],
            [rule(role.upper())],
            [{key: value for key, value in rule(role).items() if key != "source"}],
            [{**rule(role), "actions": [{"type": "worker", "value": ["other"]}]}],
            [{**rule(role), "matchers": rule(role)["matchers"] + rule(MODULE.ROLES[1])["matchers"]}],
            [{**rule(role), "matchers": rule(role)["matchers"] + [None]}],
        ]
        for existing in conflicts:
            with self.subTest(existing=existing):
                client = FakeClient(verified=True, current=existing)
                with self.assertRaises(MODULE.ProvisionError):
                    MODULE.execute(client, "apply", DESTINATION)
                self.assertEqual(client.posts, [])

    def test_missing_pagination_fails_closed(self) -> None:
        """A truncated inventory must not be treated as complete. / 清单缺页拒绝写入。"""

        class Broken(FakeClient):
            """Return an inventory without metadata. / 返回缺失分页元数据。"""

            def request(self, method: str, path: str, body: dict | None = None) -> dict:
                """Remove pagination metadata. / 移除分页字段。"""

                value = super().request(method, path, body)
                value.pop("result_info", None)
                return value

        client = Broken(verified=True)
        with self.assertRaises(MODULE.ProvisionError):
            MODULE.execute(client, "apply", DESTINATION)
        self.assertEqual(client.posts, [])

    def test_all_pages_are_read_before_audit(self) -> None:
        """A conflict hidden on page two is still rejected. / 第二页冲突亦被拒绝。"""

        class Paged(FakeClient):
            """Serve two rule pages and one destination page. / 两页规则。"""

            def request(self, method: str, path: str, body: dict | None = None) -> dict:
                """Move the conflicting rule to the second page. / 冲突在第二页。"""

                if method == "GET" and "/rules" in path:
                    page = 2 if "page=2" in path else 1
                    result = [rule(MODULE.ROLES[0], "wrong@example.invalid")] if page == 2 else [
                        rule(f"unrelated{i}@example.invalid") for i in range(50)
                    ]
                    return {
                        "success": True,
                        "result": result,
                        "result_info": {"page": page, "per_page": 50, "count": len(result), "total_count": 51},
                    }
                return super().request(method, path, body)

        client = Paged(verified=True)
        with self.assertRaises(MODULE.ProvisionError):
            MODULE.execute(client, "apply", DESTINATION)
        self.assertEqual(client.posts, [])

    def test_provider_count_shape_empty_and_nonempty(self) -> None:
        """The live API omits total_pages; count metadata is sufficient. / 适配真实返回。"""

        empty = FakeClient()
        self.assertEqual(MODULE.pages(empty, "/accounts/" + empty.account + "/email/routing/addresses"), [])
        populated = FakeClient(verified=True)
        self.assertEqual(len(MODULE.pages(populated, "/accounts/" + populated.account + "/email/routing/addresses")), 1)

    def test_truncated_count_fails_closed(self) -> None:
        """A misleading total must not skip hidden rules. / 拒绝不一致计数。"""

        class Broken(FakeClient):
            """Lie about the number of available rules. / 模拟错误总数。"""

            def request(self, method: str, path: str, body: dict | None = None) -> dict:
                """Report one unreturned item. / 少返回一项。"""

                value = super().request(method, path, body)
                if method == "GET" and "/rules" in path:
                    value["result_info"]["total_count"] += 1
                return value

        client = Broken(verified=True)
        with self.assertRaises(MODULE.ProvisionError):
            MODULE.execute(client, "apply", DESTINATION)
        self.assertEqual(client.posts, [])

    def test_status_does_not_expose_destination(self) -> None:
        """A successful audit log never prints private data. / 成功日志不泄露地址。"""

        env = {
            "ROLE_FORWARD_PHASE": "audit",
            "ROLE_FORWARD_DESTINATION": DESTINATION,
            "CF_EMAIL_ROUTING_TOKEN": "synthetic-secret",
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
        }
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, env), patch.object(MODULE, "Client", return_value=FakeClient(verified=True)):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(MODULE.main(), 0)
        self.assertNotIn(DESTINATION, stdout.getvalue() + stderr.getvalue())
        self.assertNotIn("synthetic-secret", stdout.getvalue() + stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
