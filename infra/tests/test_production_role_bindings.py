"""Realm-specific binding contracts; hosted tests only, no provider requests."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import pin_staging_mail as pin
import verify_role_monitor_staging as role
QUEUE = "a" * 32
VERSION = "11111111-1111-4111-8111-111111111111"
DATABASE = "06e84adb-fe29-4183-b131-5042a48bcdee"

class ProductionBindingsTests(unittest.TestCase):
    """Production capability expansion is explicit and cannot weaken staging."""
    def api_version(self):
        """Construct synthetic immutable capabilities from reviewed production config."""
        rows = []
        for name, (kind, value) in pin.expected_bindings("queue-api", QUEUE, realm="production").items():
            row = {"name": name, "type": kind}
            field = {"d1":"database_id", "r2_bucket":"bucket_name", "plain_text":"text", "queue":"queue_id"}.get(kind)
            if field:
                row[field] = value
            if name == "OFFICIAL_EMAIL":
                row["allowed_sender_addresses"] = ["mail@moesegfault.dev"]
            rows.append(row)
        return {"id": VERSION, "resources": {"bindings": rows}}

    def test_api_realms_are_disjoint(self):
        """Production accepts its extra official sender, staging rejects it."""
        value = self.api_version()
        self.assertTrue(pin.bindings_match(value, VERSION, phase="queue-api", queue_id=QUEUE, realm="production"))
        self.assertFalse(pin.bindings_match(value, VERSION, phase="queue-api", queue_id=QUEUE))
        for row in value["resources"]["bindings"]:
            if row["name"] == "OFFICIAL_EMAIL":
                del row["allowed_sender_addresses"]
        self.assertFalse(pin.bindings_match(value, VERSION, phase="queue-api", queue_id=QUEUE, realm="production"))

    def test_production_role_rejects_fault_and_wrong_realm(self):
        """Staging fault injection and D1 identities never reach production."""
        value = {"bindings": [
            {"type":"d1", "name":"ROLE_MONITOR", "database_id":DATABASE},
            {"type":"send_email", "name":"ROLE_ALERT", "allowed_sender_addresses":["mail@moesegfault.dev"]},
            {"type":"queue", "name":"ROLE_TRACE_EVENTS", "queue_id":QUEUE},
            {"type":"plain_text", "name":"ROLE_REALM", "text":"production"},
            {"type":"plain_text", "name":"CF_ZONE_ID", "text":role.ZONE}]}
        role.inspect_bindings(value, QUEUE, realm="production", database=DATABASE)
        for extra in ({"type":"secret_text", "name":"ROLE_TEST_FAULT"}, deepcopy(value["bindings"][0])):
            changed = deepcopy(value)
            changed["bindings"].append(extra)
            with self.assertRaises(RuntimeError):
                role.inspect_bindings(changed, QUEUE, realm="production", database=DATABASE)
        with self.assertRaises(RuntimeError):
            role.inspect_bindings(value, QUEUE)

if __name__ == "__main__":
    unittest.main()
