"""Hosted safeguards for the disposable staging role route. / 可撤销预发布角色路由的托管测试。"""

from __future__ import annotations

import unittest
from io import BytesIO
import urllib.error
import urllib.request
from unittest.mock import patch

import staging_route as route


def rule() -> dict:
    """Return the exact owned test rule. / 返回精确归属的测试规则。"""

    return {
        "id": "owned-id",
        "name": route.NAME,
        "enabled": True,
        "source": "api",
        "matchers": [{"type": "literal", "field": "to", "value": route.ALIAS}],
        "actions": [{"type": "worker", "value": [route.WORKER]}],
    }


class StagingRouteTests(unittest.TestCase):
    """Refuse conflicts and never touch production roles. / 拒绝冲突，绝不更改生产角色。"""

    def test_exact_ownership(self) -> None:
        """A second action or a redirect voids ownership. / 第二个动作或重定向使归属无效。"""

        item = rule()
        self.assertTrue(route.owned(item))
        item["actions"].append({"type": "forward", "value": ["another@example.test"]})
        self.assertFalse(route.owned(item))

    def test_conflict_fails_before_mutation(self) -> None:
        """Unowned alias never gets deleted or replaced. / 不删除或替换不属于自己的别名。"""

        item = rule()
        item["source"] = "wrangler"
        with patch.object(route, "rules", return_value=[item]), patch.object(route, "call") as call:
            with self.assertRaisesRegex(RuntimeError, "conflict"):
                route.reconcile("zone", "token", "remove")
            call.assert_not_called()

    def test_other_roles_are_untouched(self) -> None:
        """The staging manager never matches the four public role aliases. / 预发布管理器从不匹配四个公开角色。"""

        for address in (
            "abuse@moesegfault.dev",
            "postmaster@moesegfault.dev",
            "abuse@mail.moesegfault.dev",
            "postmaster@mail.moesegfault.dev",
        ):
            item = rule()
            item["matchers"][0]["value"] = address
            self.assertFalse(route.touches_alias(item))

    def test_provider_redirect_never_replays_routing_bearer(self) -> None:
        """A redirected read or write returns only a status and no provider body."""

        request = urllib.request.Request(route.API + "/test")
        self.assertIsNone(route.RejectRedirect().redirect_request(
            request, None, 302, "Found", {}, "https://other.example/"))
        redirect = urllib.error.HTTPError(request.full_url, 302, "Found",
                                            {"Location": "https://other.example/"}, BytesIO(b'{"private":true}'))
        with patch.object(route._NO_REDIRECT, "open", side_effect=redirect) as opener:
            self.assertEqual(route.call("GET", "/zones/x/email/routing/rules", "secret"), (302, {}))
            self.assertEqual(route.call("POST", "/zones/x/email/routing/rules", "secret", {}), (302, {}))
        self.assertEqual(opener.call_count, 2)


if __name__ == "__main__":
    unittest.main()
