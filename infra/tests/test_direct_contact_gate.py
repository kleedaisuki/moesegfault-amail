"""Hosted synthetic tests of direct-only contact SQL and provider admission.

No test contacts Cloudflare, reads secrets, accesses a mailbox, or sends email.
Run this suite on the existing hosted infra test lane, not a local deployment.
"""

from __future__ import annotations

import copy
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/operator"))
import direct_contact_health as health
import direct_contact_policy as adoption
import attest_gate
import send_control
import check_send_hold
import direct_contact_invalidate as invalidation

CONTRACT = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
DESTINATION = "synthetic@example.invalid"
NOW = 1_800_000_000


def policy() -> dict:
    """Build public synthetic identifiers, never the confidential destination."""
    row = {"id": 1, "version": 1, "contract_id": CONTRACT, "destination_id": "destination", "observed_at": NOW}
    row.update({column: f"rule_{index}" for index, column in enumerate(health.PIN_COLUMNS)})
    return row


def database() -> sqlite3.Connection:
    """Apply real migration SQL with a deterministic database clock."""
    db = sqlite3.connect(":memory:")
    db.create_function("unixepoch", 0, lambda: NOW)
    for migration in ("0001_initial.sql", "0002_reservation_lease.sql", "0006_outbound_abuse.sql", "0009_direct_role_contact.sql"):
        db.executescript((ROOT / "crates/mail-worker/migrations" / migration).read_text(encoding="utf-8"))
    return db


def adopt(db: sqlite3.Connection, contract: str = CONTRACT, expected: str | None = None) -> int:
    """Use the actual operator adoption SQL to install synthetic pins."""
    row = policy()
    current = db.execute("SELECT contract_id FROM role_contact_policy WHERE id=1").fetchone()
    expected = expected if expected is not None else current[0] if current else "NONE"
    return db.execute(adoption.ADOPT_SQL, [contract, row["destination_id"], *(row[key] for key in health.PIN_COLUMNS), "operator", "CASE_1", expected]).rowcount


def ready(db: sqlite3.Connection) -> None:
    """Explicitly simulate accepted coverage and a current machine check."""
    adopt(db)
    db.execute(health.WRITE_SQL, [CONTRACT, "healthy", NOW, "1:1:direct-v1"])
    db.execute("UPDATE send_release_gates SET feedback_verified=1,abuse_contact_verified=1,abuse_contact_contract_id=?,delivery_canary_verified=1,preview_reviewed=1 WHERE id=1", [CONTRACT])
    sql, params = send_control.statement("global", "allowed", "", "", "launch_verified", "operator", "CASE_1")
    assert db.execute(sql, params).rowcount == 1


def admit(db: sqlite3.Connection, key: str) -> None:
    """Exercise actual send-request trigger admission, not just the SQL view."""
    db.execute("INSERT INTO send_requests(owner_iss,owner_sub,idem_key,payload_hash,state,created_at) VALUES('issuer','owner',?,'hash','preparing',1)", [key])


class DirectContactSqlTest(unittest.TestCase):
    """Keep human adoption, freshness and held canaries separate."""

    def test_migration_is_held_and_has_no_inferred_contract(self):
        """The old boolean/lease cannot manufacture a direct contact contract."""
        db = database()
        self.assertEqual(db.execute("SELECT state FROM send_policy WHERE scope='global'").fetchone()[0], "held")
        self.assertEqual(db.execute("SELECT count(*) FROM role_contact_policy").fetchone()[0], 0)
        self.assertEqual(db.execute("SELECT abuse_contact_verified,abuse_contact_contract_id FROM send_release_gates").fetchone(), (0, None))
        with self.assertRaises(sqlite3.IntegrityError):
            admit(db, "held")

    def test_raw_global_unhold_is_guarded_for_insert_update_and_reassertion(self):
        """Neither privileged raw SQL nor allowed-to-allowed edits skip readiness."""
        db = database()
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE send_policy SET state='allowed' WHERE scope='global'")
        db.execute("DELETE FROM send_policy WHERE scope='global'")
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO send_policy(scope,owner_iss,owner_sub,state,reason_code,actor,updated_at) VALUES('global','*','*','allowed','review','operator',unixepoch())")
        db.execute("INSERT INTO send_policy(scope,owner_iss,owner_sub,state,reason_code,actor,updated_at) VALUES('global','*','*','held','review','operator',unixepoch())")
        ready(db)
        self.assertEqual(db.execute("UPDATE send_policy SET state='allowed',actor='other' WHERE scope='global'").rowcount, 1)
        db.execute("UPDATE send_release_gates SET preview_reviewed=0 WHERE id=1")
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE send_policy SET state='allowed' WHERE scope='global'")
        db.execute("UPDATE send_release_gates SET preview_reviewed=1 WHERE id=1")
        db.execute("UPDATE send_policy SET state='allowed' WHERE scope='global'")
        db.create_function("unixepoch", 0, lambda: NOW + 21600)
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE send_policy SET state='allowed',actor='other' WHERE scope='global'")
        # An emergency hold and account-local policy change do not depend on
        # contact freshness or any human release attestation.
        db.execute("UPDATE send_policy SET state='held' WHERE scope='global'")
        db.execute("INSERT INTO send_policy(scope,owner_iss,owner_sub,state,reason_code,actor,updated_at) VALUES('account','issuer','owner','allowed','review','operator',unixepoch())")

    def test_hold_readback_works_before_direct_migration_and_denies_missing_state(self):
        """Deployment hold evidence neither requires nor adopts a role contract."""
        db = sqlite3.connect(":memory:")
        for migration in ("0001_initial.sql", "0002_reservation_lease.sql", "0006_outbound_abuse.sql"):
            db.executescript((ROOT / "crates/mail-worker/migrations" / migration).read_text(encoding="utf-8"))
        db.row_factory = sqlite3.Row
        self.assertTrue(check_send_hold.held(dict(db.execute(check_send_hold.HOLD_SQL).fetchone())))
        db.execute("UPDATE send_policy SET state='allowed' WHERE scope='global'")
        self.assertFalse(check_send_hold.held(dict(db.execute(check_send_hold.HOLD_SQL).fetchone())))
        db.execute("DELETE FROM send_policy WHERE scope='global'")
        self.assertFalse(check_send_hold.held(dict(db.execute(check_send_hold.HOLD_SQL).fetchone())))
        self.assertFalse(check_send_hold.held({"global_rows": True, "global_held": True}))

    def test_public_admission_requires_current_contract_and_exclusive_expiry(self):
        """Exact expiry, future observations and missing health deny admission."""
        for checked in (NOW - 21600, NOW - 21601):
            db = database()
            ready(db)
            db.execute("DELETE FROM role_contact_health")
            db.execute(health.WRITE_SQL, [CONTRACT, "healthy", checked, "2:1:direct-v1"])
            with self.assertRaises(sqlite3.IntegrityError):
                admit(db, "expired")
            sql, params = send_control.statement("global", "allowed", "", "", "launch_verified", "operator", "CASE_1")
            self.assertEqual(db.execute(sql, params).rowcount, 0)
        db = database()
        ready(db)
        admit(db, "valid")
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute(health.WRITE_SQL, [CONTRACT, "healthy", NOW + 1, "2:1:direct-v1"])
        db.execute("DELETE FROM role_contact_health")
        with self.assertRaises(sqlite3.IntegrityError):
            admit(db, "missing")

    def test_failure_holds_recovery_never_allows_and_stale_run_never_renews(self):
        """Same-second failure wins; older and equal success cannot override it."""
        db = database()
        ready(db)
        db.execute(health.WRITE_SQL, [CONTRACT, "unverified", NOW, "2:1:direct-v1"])
        self.assertEqual(db.execute("SELECT state FROM send_policy WHERE scope='global'").fetchone()[0], "held")
        for checked in (NOW - 1, NOW):
            self.assertEqual(db.execute(health.WRITE_SQL, [CONTRACT, "healthy", checked, "3:1:direct-v1"]).rowcount, 0)
        db.create_function("unixepoch", 0, lambda: NOW + 1)
        db.execute(health.WRITE_SQL, [CONTRACT, "healthy", NOW + 1, "4:1:direct-v1"])
        self.assertEqual(db.execute("SELECT state FROM send_policy WHERE scope='global'").fetchone()[0], "held")

    def test_replacement_revokes_and_obsolete_checker_cannot_commit(self):
        """A replaced/revoked contract is permanently non-reusable."""
        db = database()
        ready(db)
        adopt(db, OTHER)
        self.assertEqual(db.execute("SELECT state FROM send_policy WHERE scope='global'").fetchone()[0], "held")
        self.assertEqual(db.execute("SELECT abuse_contact_verified,abuse_contact_contract_id FROM send_release_gates").fetchone(), (0, None))
        self.assertEqual(db.execute(health.WRITE_SQL, [CONTRACT, "healthy", NOW, "2:1:direct-v1"]).rowcount, 0)
        with self.assertRaises(sqlite3.IntegrityError):
            adopt(db, CONTRACT)
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE send_release_gates SET abuse_contact_verified=1,abuse_contact_contract_id=?", [CONTRACT])

    def test_adoption_compares_expected_absence_or_current_contract_atomically(self):
        """Stale manual runs cannot replace a contract selected after dispatch."""
        db = database()
        self.assertEqual(adopt(db, expected=OTHER), 0)
        self.assertEqual(adopt(db, expected="NONE"), 1)
        self.assertEqual(adopt(db, OTHER, expected="NONE"), 0)
        self.assertEqual(adopt(db, OTHER, expected=CONTRACT), 1)
        self.assertEqual(adopt(db, "33333333-3333-4333-8333-333333333333", expected=CONTRACT), 0)

    def test_explicit_repeated_contact_revoke_clears_health_without_other_gate_effects(self):
        """Flag-zero revocation still invalidates routes before provider mutation."""
        db = FakeDatabase()
        db.db.execute(health.WRITE_SQL, [CONTRACT, "healthy", NOW, "1:1:direct-v1"])
        db.db.execute("UPDATE send_release_gates SET preview_reviewed=0 WHERE id=1")
        self.assertEqual(db.db.execute("SELECT count(*) FROM role_contact_health").fetchone()[0], 1)
        invalidation.invalidate(db, "github:operator", "CASE_2")
        self.assertEqual(db.db.execute("SELECT count(*) FROM role_contact_health").fetchone()[0], 0)
        db.db.execute(health.WRITE_SQL, [CONTRACT, "healthy", NOW, "2:1:direct-v1"])
        invalidation.invalidate(db, "github:operator", "CASE_3")
        self.assertEqual(db.db.execute("SELECT count(*) FROM role_contact_health").fetchone()[0], 0)
        self.assertEqual(db.db.execute("SELECT state FROM send_policy WHERE scope='global'").fetchone()[0], "held")

    def test_ambiguous_invalidation_never_authorizes_a_provider_mutation(self):
        """A committed-but-unacknowledged revoke still blocks the caller's write."""
        db = FakeDatabase()
        query = db.query
        provider_calls = []

        def ambiguous(sql, params=None):
            """Model a successful D1 commit whose response was lost."""
            result = query(sql, params)
            if sql == invalidation.INVALIDATE_SQL:
                raise health.HealthError("database_unavailable")
            return result

        with patch.object(db, "query", side_effect=ambiguous):
            with self.assertRaises(health.HealthError):
                invalidation.invalidate(db, "github:operator", "CASE_2")
                provider_calls.append("mutation")
        self.assertEqual(provider_calls, [])
        self.assertEqual(db.db.execute("SELECT count(*) FROM role_contact_health").fetchone()[0], 0)

    def test_held_canary_does_not_depend_on_contact_health(self):
        """One held key is allowed without any adopted contract; second is denied."""
        db = database()
        db.execute("UPDATE send_release_gates SET canary_owner_iss='issuer',canary_owner_sub='owner',canary_recipient_sha256='synthetic',canary_expires_at=unixepoch()+900 WHERE id=1")
        admit(db, "first")
        with self.assertRaises(sqlite3.IntegrityError):
            admit(db, "second")
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE send_policy SET state='allowed' WHERE scope='global'")
        db.execute("DELETE FROM send_requests")
        # Force the stored state after removing only the unhold guard to
        # independently test admission's fail-closed defense, not its order.
        db.execute("DROP TRIGGER send_policy_direct_allow_update")
        db.execute("UPDATE send_policy SET state='allowed' WHERE scope='global'")
        with self.assertRaises(sqlite3.IntegrityError):
            admit(db, "first")


class FakeRouting:
    """Return complete one-page synthetic inventories to the real paginator."""

    def __init__(self):
        """Create the exact versioned four-route contract."""
        self.addresses = [{"id": "destination", "email": DESTINATION, "verified": "2026-10-01"}]
        self.rules = [{"id": f"rule_{index}", "enabled": True, "source": "api",
            "matchers": [{"type": "literal", "field": "to", "value": role}],
            "actions": [{"type": "forward", "value": [DESTINATION]}]} for index, role in enumerate(health.forwarding.ROLES)]

    def request(self, method, path, body=None):
        """Require GET and simulate stable complete pagination metadata."""
        assert method == "GET" and body is None
        rows = self.addresses if "/addresses?" in path else self.rules
        return {"success": True, "result": rows, "result_info": {"page": 1, "per_page": 50, "count": len(rows), "total_count": len(rows), "total_pages": 1}}


class FakeDatabase:
    """Execute fixed checker SQL against the same real synthetic migrations."""

    def __init__(self, *, fail_write=False, adopted=True):
        """Adopt a held contract without manufacturing human acceptance."""
        self.db = database()
        if adopted:
            adopt(self.db)
        self.db.row_factory = sqlite3.Row
        self.fail_write = fail_write
        self.writes = 0

    def query(self, sql, params=None):
        """Expose D1's singleton result/meta shape, or one ambiguous write."""
        if sql == health.WRITE_SQL:
            self.writes += 1
            if self.fail_write:
                raise health.HealthError("database_unavailable")
        cursor = self.db.execute(sql, params or [])
        rows = [dict(row) for row in cursor.fetchall()] if cursor.description else []
        return {"success": True, "results": rows, "meta": {"changes": max(0, cursor.rowcount)}}


class DirectContactProviderTest(unittest.TestCase):
    """A new identity or malformed route never silently re-adopts the contract."""

    def test_exact_snapshot_and_drift(self):
        """Destination, shape, rule identity and duplicate matches are checked."""
        self.assertEqual(health.snapshot(FakeRouting(), "a" * 32, policy(), DESTINATION)[0], "destination")
        for mutation in ("destination", "verified", "rule_id", "disabled", "duplicate", "mixed"):
            client = FakeRouting()
            if mutation == "destination":
                client.addresses[0]["id"] = "other"
            elif mutation == "verified":
                client.addresses[0]["verified"] = None
            elif mutation == "rule_id":
                client.rules[0]["id"] = "replacement"
            elif mutation == "disabled":
                client.rules[0]["enabled"] = False
            elif mutation == "duplicate":
                client.rules.append(copy.deepcopy(client.rules[0]))
            else:
                client.rules[0]["matchers"].append({"type": "all"})
            with self.subTest(mutation=mutation), self.assertRaises(Exception):
                health.snapshot(client, "a" * 32, policy(), DESTINATION)

    def test_old_generic_attestation_cannot_claim_coverage(self):
        """Without explicit Inbox/Junk/24h acceptance no provider call occurs."""
        env = {"INPUT_TARGET": "staging", "INPUT_GATE": "abuse_contact_verified", "INPUT_VERIFIED": "true",
            "INPUT_CASE_REF": "CASE_1", "GITHUB_ACTOR": "operator", "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
            "CLOUDFLARE_API_TOKEN": "synthetic"}
        with patch.dict("os.environ", env, clear=True), patch.object(attest_gate.urllib.request, "urlopen") as request:
            self.assertEqual(attest_gate.main(), 2)
            request.assert_not_called()

    def test_routing_client_cannot_mutate_or_redirect(self):
        """The health helper has a fixed GET-only surface and rejects redirects."""
        client = health.RoutingClient("synthetic", "a" * 32)
        with self.assertRaises(health.HealthError):
            client.request("POST", "/zones/anything/email/routing/rules", {})
        self.assertIsNone(health.RejectRedirect().redirect_request(None, None, 302, None, None, "https://example.invalid"))

    def test_checker_failure_invalidates_but_health_success_does_not_attest(self):
        """Provider denial/malformed inventory writes unverified and stays held."""
        for failure in (health.HealthError("provider_unavailable"), ValueError("synthetic malformed inventory")):
            db = FakeDatabase()
            with patch.object(health, "snapshot", side_effect=failure):
                self.assertFalse(health.refresh(db, FakeRouting(), "a" * 32, DESTINATION, "1:1:direct-v1"))
            self.assertEqual(db.db.execute("SELECT state,expires_at FROM role_contact_health").fetchone()[0], "unverified")
        db = FakeDatabase()
        self.assertTrue(health.refresh(db, FakeRouting(), "a" * 32, DESTINATION, "1:1:direct-v1"))
        self.assertEqual(db.db.execute("SELECT state FROM send_policy WHERE scope='global'").fetchone()[0], "held")
        self.assertEqual(db.db.execute("SELECT abuse_contact_verified FROM send_release_gates").fetchone()[0], 0)
        self.assertEqual(db.db.execute("SELECT count(*) FROM direct_role_contact_ready").fetchone()[0], 0)

    def test_snapshot_drift_denies_and_ambiguous_write_is_not_retried(self):
        """Read bracketing detects drift; D1 failure cannot announce renewal."""
        db = FakeDatabase()
        with patch.object(health, "snapshot", side_effect=[("first",), ("changed",)]):
            self.assertFalse(health.refresh(db, FakeRouting(), "a" * 32, DESTINATION, "1:1:direct-v1"))
        db = FakeDatabase(fail_write=True)
        with self.assertRaises(health.HealthError):
            health.refresh(db, FakeRouting(), "a" * 32, DESTINATION, "1:1:direct-v1")
        self.assertEqual(db.writes, 1)

    def test_optional_no_adoption_skip_requires_explicit_held_readback(self):
        """Only real absence plus a proven legacy hold can yield a safe skip."""
        db = FakeDatabase(adopted=False)
        self.assertIsNone(health.refresh(db, FakeRouting(), "a" * 32, DESTINATION, "1:1:direct-v1", skip_unadopted_held=True))
        self.assertEqual(db.writes, 0)
        db.db.execute("DROP TRIGGER send_policy_direct_allow_update")
        db.db.execute("UPDATE send_policy SET state='allowed' WHERE scope='global'")
        with self.assertRaises(health.HealthError):
            health.optional_held_policy(db)
        db.db.execute("UPDATE send_policy SET state='held' WHERE scope='global'")
        db.db.execute("DROP VIEW direct_role_contact_ready")
        with self.assertRaises(health.HealthError):
            health.optional_held_policy(db)

    def test_optional_idle_schema_executes_actual_view_and_health_columns(self):
        """Matching catalog names cannot disguise unusable or nonempty readiness."""
        for malformed in ("nonzero_view", "broken_view", "broken_health"):
            db = FakeDatabase(adopted=False)
            if malformed == "nonzero_view":
                db.db.execute("DROP VIEW direct_role_contact_ready")
                db.db.execute("CREATE VIEW direct_role_contact_ready AS SELECT 1 AS contract_id")
                expected_error = health.HealthError
            elif malformed == "broken_view":
                db.db.execute("DROP VIEW direct_role_contact_ready")
                db.db.execute("CREATE VIEW direct_role_contact_ready AS SELECT contract_id FROM absent_synthetic_table")
                expected_error = sqlite3.OperationalError
            else:
                db.db.execute("DROP TABLE role_contact_health")
                db.db.execute("CREATE TABLE role_contact_health(id INTEGER PRIMARY KEY)")
                expected_error = sqlite3.OperationalError
            with self.subTest(malformed=malformed), self.assertRaises(expected_error):
                health.optional_held_policy(db)
    def test_optional_pre_migration_skip_never_treats_provider_errors_as_absence(self):
        """Catalog absence is queried positively; all errors still fail closed."""
        db = FakeDatabase(adopted=False)
        db.db = sqlite3.connect(":memory:")
        db.db.row_factory = sqlite3.Row
        for migration in ("0001_initial.sql", "0002_reservation_lease.sql", "0006_outbound_abuse.sql"):
            db.db.executescript((ROOT / "crates/mail-worker/migrations" / migration).read_text(encoding="utf-8"))
        self.assertIsNone(health.optional_held_policy(db))
        with patch.object(db, "query", side_effect=health.HealthError("database_unavailable")):
            with self.assertRaises(health.HealthError):
                health.optional_held_policy(db)

    def test_optional_held_main_needs_no_routing_secret_before_adoption(self):
        """No-adoption held readback never touches the routing client or mailbox."""
        env = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "1",
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "synthetic", "INPUT_SKIP_UNADOPTED_HELD": "true"}
        with patch.dict("os.environ", env, clear=True), patch.object(health, "DatabaseClient", return_value=FakeDatabase(adopted=False)), patch.object(health, "RoutingClient") as client:
            self.assertEqual(health.main(), 0)
            client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
