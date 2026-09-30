"""Hosted synthetic historical-versus-target binding regression contracts."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
import pin_staging_mail as pin
from historical_containment_fixture import BINDINGS, VERSION, historical_version

QUEUE = "a" * 32


class HistoricalBindingTests(unittest.TestCase):
    """The old capability is exact provenance, never an optional target binding."""

    def test_literal_provenance_and_config_independence(self):
        """Every frozen field matches the literal fixture even when TOML is unavailable."""
        fields = {"d1": "database_id", "r2_bucket": "bucket_name", "plain_text": "text"}
        literal = {item["name"]: (item["type"], item.get(fields.get(item["type"], "")))
                   for item in BINDINGS}
        with patch.object(pin, "CONFIG", Path("missing-config-for-historical-fixture")):
            self.assertEqual(pin.containment_predecessor_bindings(), literal)
            self.assertTrue(pin.containment_bindings_match(historical_version(), VERSION))
        contract = pin.containment_predecessor_bindings()
        contract.clear()
        self.assertEqual(pin.containment_predecessor_bindings(), literal)

    def test_current_and_historical_do_not_fall_back(self):
        """Current direct-only and queue-api accept their own set and reject the role."""
        old = historical_version()
        direct = historical_version()
        direct["resources"]["bindings"] = [item for item in direct["resources"]["bindings"]
                                             if item["name"] != "ROLE_MONITOR"]
        self.assertTrue(pin.bindings_match(direct, VERSION))
        self.assertFalse(pin.bindings_match(old, VERSION))
        self.assertFalse(pin.containment_bindings_match(direct, VERSION))
        queue = historical_version()
        queue["resources"]["bindings"] = direct["resources"]["bindings"] + [
            {"name": "TRACE_EVENTS", "type": "queue", "queue_id": QUEUE}]
        self.assertTrue(pin.bindings_match(queue, VERSION, phase="queue-api", queue_id=QUEUE))
        self.assertFalse(pin.containment_bindings_match(queue, VERSION))
        queue["resources"]["bindings"].append(BINDINGS[1].copy())
        self.assertFalse(pin.bindings_match(queue, VERSION, phase="queue-api", queue_id=QUEUE))
        self.assertFalse(pin.bindings_match(old, VERSION, realm="production"))

    def test_wrong_missing_extra_duplicate_and_targets(self):
        """No historical unknown capability, wrong target or secret substitution passes."""
        mutations = [
            lambda items: items.pop(1),
            lambda items: items.append(items[1].copy()),
            lambda items: items[1].update(name="RENAMED_ROLE"),
            lambda items: items[1].update(database_id="wrong-role"),
            lambda items: items[0].update(database_id="wrong-mail"),
            lambda items: items[2].update(bucket_name="moesegfault-mail-raw"),
            lambda items: items[8].update(text="https://identity.moesegfault.dev"),
            lambda items: items[4].update(type="plain_text"),
            lambda items: items.append({"name": "TRACE_EVENTS", "type": "queue", "queue_id": QUEUE}),
            lambda items: items.append({"name": "OFFICIAL_EMAIL", "type": "send_email"}),
            lambda items: items.append({"name": "UNKNOWN", "type": "secret_text"}),
            lambda items: items.__setitem__(1, None),
        ]
        for index, mutate in enumerate(mutations):
            value = historical_version()
            mutate(value["resources"]["bindings"])
            with self.subTest(index=index):
                self.assertFalse(pin.containment_bindings_match(value, VERSION))
        value = historical_version()
        value["id"] = "11111111-1111-1111-1111-111111111111"
        self.assertFalse(pin.containment_bindings_match(value, VERSION))
        self.assertFalse(pin.containment_bindings_match(value, value["id"]))

    def test_shapes_are_shared_and_fail_closed(self):
        """Only the already-reviewed exact result wrapper is accepted."""
        value = historical_version()
        value["resources"]["bindings"] = {"result": value["resources"]["bindings"]}
        self.assertTrue(pin.containment_bindings_match(value, VERSION))
        for actual in ({}, {"result": BINDINGS, "unknown": True}, [None] * 14, None):
            value = historical_version()
            value["resources"]["bindings"] = actual
            self.assertFalse(pin.containment_bindings_match(value, VERSION))


if __name__ == "__main__":
    unittest.main()
