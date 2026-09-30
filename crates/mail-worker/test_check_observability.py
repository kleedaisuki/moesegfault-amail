"""Static and mocked readback tests for the mail observability privacy gate."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import check_observability as gate


class ObservabilityGateTests(unittest.TestCase):
    """Require independent explicit settings in every mail API realm."""

    def test_both_local_realms_are_explicitly_safe(self) -> None:
        """Production and staging must not depend on inherited defaults."""

        for realm in gate.SCRIPT:
            with self.subTest(realm=realm):
                self.assertTrue(gate.safe_observability(gate.local_settings(realm)["observability"]))

    def test_each_capture_and_export_path_fails_closed(self) -> None:
        """No missing or contradictory readback field may be treated as safe."""

        safe = gate.local_settings("production")
        self.assertTrue(gate.safe_settings(safe))
        cloudflare_sink = {"observability": {**safe["observability"]}}
        cloudflare_sink["observability"]["logs"] = {
            **safe["observability"]["logs"], "destinations": ["cloudflare"]
        }
        cloudflare_sink["observability"]["traces"] = {
            **safe["observability"]["traces"], "destinations": ["cloudflare"]
        }
        self.assertTrue(gate.safe_settings(cloudflare_sink))
        for field, value in (("redact_query_string", False), ("enabled", True), ("head_sampling_rate", 0.1)):
            changed = {"observability": {**safe["observability"], field: value}}
            self.assertFalse(gate.safe_settings(changed))
        for section, field, value in (
            ("logs", "enabled", True),
            ("logs", "invocation_logs", True),
            ("logs", "persist", False),
            ("logs", "head_sampling_rate", 0.1),
            ("logs", "destinations", ["export"]),
            ("traces", "enabled", True),
            ("traces", "destinations", ["export"]),
        ):
            observation = {**safe["observability"]}
            observation[section] = {**observation[section], field: value}
            self.assertFalse(gate.safe_settings({"observability": observation}))
        self.assertFalse(gate.safe_settings({**safe, "logpush": True}))
        self.assertFalse(gate.safe_settings({**safe, "tail_consumers": [{"service": "other"}]}))

    def test_both_readbacks_are_required(self) -> None:
        """A safe script setting cannot mask an unsafe deployed version."""

        safe = gate.local_settings("staging")
        unsafe = {"observability": {**safe["observability"], "redact_query_string": False}}
        with patch.object(gate, "readback", side_effect=[unsafe, safe]) as fetch:
            self.assertFalse(gate.verify("staging", "account", "token"))
            self.assertEqual(fetch.call_count, 1)
        with patch.object(gate, "readback", side_effect=[safe, unsafe]) as fetch:
            self.assertFalse(gate.verify("staging", "account", "token"))
            self.assertEqual(fetch.call_count, 2)


if __name__ == "__main__":
    unittest.main()
