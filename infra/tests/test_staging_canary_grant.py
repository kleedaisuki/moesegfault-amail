"""Atomic, staging-only owned-self canary grants with no provider operations."""
import os
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/operator"))
import grant_canary as grant
import direct_contact_health as health
import ensure_role_forwarding as forwarding


class StagingCanaryTests(unittest.TestCase):
    """A current owned route cannot steal a live grant or widen the recipient."""

    def setUp(self):
        """Use the actual parameterized guarded UPDATE against in-memory SQLite."""
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)
        self.connection.executescript("""
          CREATE TABLE send_policy(scope,owner_iss,owner_sub,state);
          INSERT INTO send_policy VALUES('global','*','*','held');
          CREATE TABLE addresses(address,owner_iss,owner_sub,state,needs_reconcile,cf_rule_id);
          CREATE TABLE send_release_gates(id INTEGER,canary_owner_iss,canary_owner_sub,
            canary_recipient_sha256,canary_expires_at INTEGER,canary_used_by,actor,case_ref,updated_at);
          INSERT INTO send_release_gates(id,canary_expires_at) VALUES(1,0);
        """)
        self.address = "send-" + "a" * 16 + "@mail-staging.moesegfault.dev"
        self.connection.execute("INSERT INTO addresses VALUES(?,?,?,?,?,?)",
            [self.address, grant.DATABASES["staging"][1], "synthetic-sub", "active", 0, "b" * 32])
        self.rule = {"tag": "b" * 32, "enabled": True, "source": "api",
                     "matchers": [{"type": "literal", "field": "to", "value": self.address}],
                     "actions": [{"type": "worker", "value": ["amail-inbound-staging"]}]}
        self.environment = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/codex/v0.1.2-agent-first-performance",
            "GITHUB_ACTOR": "synthetic-actor", "AMAIL_TEST_RUN_NONCE": "a" * 16,
            "AMAIL_STAGING_CANARY_CONFIRM": "RUN_STAGING_OWNED_SEND_V012", "CF_EMAIL_ROUTING_TOKEN": "synthetic"}
        self.writes = 0

    def query(self, sql: str, params=None) -> dict:
        """Return D1's single statement batch shape without network IO."""
        cursor = self.connection.execute(sql, params or [])
        if sql.startswith("UPDATE"):
            self.writes += 1
            return {"meta": {"changes": cursor.rowcount}, "results": []}
        return {"results": [dict(row) for row in cursor.fetchall()]}

    def invoke(self):
        """Run only the new guarded mode; original operator main is untouched."""
        with patch.dict(os.environ, self.environment, clear=True), \
             patch.object(health, "DatabaseClient") as client, \
             patch.object(forwarding, "rules", return_value=[self.rule]):
            client.return_value.query.side_effect = self.query
            return grant.grant_staging_owned("c" * 32, "synthetic-token", self.address, "synthetic-sub", "staging-123")

    def test_own_self_recipient_preserves_global_hold(self):
        """Exact ownership/routing produces one short-lived pinned grant."""
        result = self.invoke()
        self.assertEqual((result["held"], result["live"]), (1, 1))
        self.assertIsNone(result["canary_used_by"])
        self.assertEqual(self.writes, 1)

    def test_live_slot_is_atomically_refused_without_overwrite(self):
        """Even the same owner cannot reset a still-live one-use grant."""
        self.invoke()
        self.connection.execute("UPDATE send_release_gates SET canary_used_by='original-intent'")
        with self.assertRaisesRegex(ValueError, "live_slot_or_hold_changed"):
            self.invoke()
        self.assertEqual(self.connection.execute("SELECT canary_used_by FROM send_release_gates").fetchone()[0], "original-intent")

    def test_wrong_branch_or_unowned_route_blocks_before_write(self):
        """No production context or service-target substitution reaches UPDATE."""
        self.environment["GITHUB_REF"] = "refs/heads/main"
        with self.assertRaisesRegex(ValueError, "context_unverified"):
            self.invoke()
        self.environment["GITHUB_REF"] = "refs/heads/codex/v0.1.2-agent-first-performance"
        self.rule["actions"] = [{"type": "worker", "value": ["amail-inbound"]}]
        with self.assertRaisesRegex(ValueError, "route_unverified"):
            self.invoke()
        self.assertEqual(self.writes, 0)

    def test_changed_hold_cannot_authorize_the_conditional_write(self):
        """Read-before-write cannot bypass the authoritative SQL held predicate."""
        self.connection.execute("UPDATE send_policy SET state='allowed'")
        with self.assertRaisesRegex(ValueError, "live_slot_or_hold_changed"):
            self.invoke()
        self.assertEqual(self.connection.execute("SELECT canary_expires_at FROM send_release_gates").fetchone()[0], 0)

    def test_ambiguous_update_is_not_replayed(self):
        """A committed-but-unobserved grant remains reserved until ordinary expiry."""
        def ambiguous(sql, params=None):
            result = self.query(sql, params)
            if sql.startswith("UPDATE"):
                raise TimeoutError("synthetic ambiguous write")
            return result
        with patch.dict(os.environ, self.environment, clear=True), \
             patch.object(health, "DatabaseClient") as client, patch.object(forwarding, "rules", return_value=[self.rule]):
            client.return_value.query.side_effect = ambiguous
            with self.assertRaises(TimeoutError):
                grant.grant_staging_owned("c" * 32, "synthetic", self.address, "synthetic-sub", "staging-123")
        self.assertEqual(self.writes, 1)
        self.assertGreater(self.connection.execute("SELECT canary_expires_at FROM send_release_gates").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
