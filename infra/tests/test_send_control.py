"""Operator control and Queue provisioning contracts. / 操作员控制与队列配置契约。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


def module(path: str):
    """Load one repository script without installing a local package. / 无需安装本地包即可加载仓库脚本。"""
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(path.replace("/", "_"), root / path)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


control = module("infra/operator/send_control.py")
events = module("infra/deploy/ensure_email_events.py")
privacy = module("infra/provider/configure_sending_privacy.py")


class SendControlContract(unittest.TestCase):
    """Keep operator mutations parameterized and narrowly scoped. / 保持操作员修改参数化且作用域收敛。"""

    def test_account_statement_binds_untrusted_subject(self):
        """An apostrophe in an opaque subject cannot become SQL. / 不透明主体中的引号不能变成 SQL。"""
        sql, params = control.statement("account", "held", "issuer", "x'; DROP TABLE send_policy; --", "review", "operator", "CASE_1")
        self.assertNotIn("DROP TABLE", sql)
        self.assertIn("DROP TABLE", params[1])
        self.assertIn("ON CONFLICT", sql)

    def test_global_allow_requires_explicit_production_confirmation(self):
        """The launch switch cannot be turned on by a typo. / 不能因误输入而打开上线开关。"""
        env = {
            "INPUT_TARGET": "production", "INPUT_SCOPE": "global", "INPUT_STATE": "allowed",
            "INPUT_REASON_CODE": "launch_verified", "INPUT_CASE_REF": "CASE_1",
            "GITHUB_ACTOR": "operator", "CLOUDFLARE_ACCOUNT_ID": "account", "CLOUDFLARE_API_TOKEN": "redacted",
        }
        with patch.dict("os.environ", env, clear=True):
            self.assertEqual(control.main(), 2)


class EmailEventsProvisionContract(unittest.TestCase):
    """Provisioning is idempotent and rejects source drift. / 配置过程幂等且拒绝来源漂移。"""

    def test_matching_subscription_is_not_duplicated(self):
        """A repeated deploy only lists the existing scoped subscription. / 重复部署只检查已有域名订阅。"""
        body = json.dumps({"result": [{"name": "lifecycle", "enabled": True, "events": events.EVENTS.split(","), "source": {"type": "email.sending", "domain": "mail.example.test"}}]})
        with patch.object(events, "run", return_value=subprocess.CompletedProcess([], 0, body, "")) as run:
            events.ensure_subscription("queue", "lifecycle", "mail.example.test")
        run.assert_called_once()

    def test_wrong_domain_subscription_fails_closed(self):
        """A same-name subscription for another domain is not accepted. / 不接受同名但指向其他域名的订阅。"""
        body = json.dumps({"result": [{"name": "lifecycle", "enabled": True, "events": events.EVENTS.split(","), "source": {"type": "email.sending", "domain": "other.example.test"}}]})
        with patch.object(events, "run", return_value=subprocess.CompletedProcess([], 0, body, "")):
            with self.assertRaises(RuntimeError):
                events.ensure_subscription("queue", "lifecycle", "mail.example.test")


class SendingPrivacyContract(unittest.TestCase):
    """Never act on an apex, wildcard or ambiguous sending-domain match. / 绝不误改根域、通配符或含糊匹配。"""

    def test_exact_enabled_domain_only(self):
        """A verified exact user domain is the only editable result. / 仅精确的已启用用户域可修改。"""
        rows = [{"name": "moesegfault.dev", "enabled": True, "tag": "apex"}, {"name": "mail.moesegfault.dev", "enabled": True, "tag": "user"}]
        self.assertEqual(privacy.unique_domain(rows, "mail.moesegfault.dev")["tag"], "user")
        with self.assertRaises(ValueError):
            privacy.unique_domain(rows + [rows[1]], "mail.moesegfault.dev")


if __name__ == "__main__":
    unittest.main()
