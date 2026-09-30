"""Hosted native REST-shape fixtures and safety contracts; no provider operations."""

import json
import os
from pathlib import Path
import sqlite3
import unittest
from unittest import mock

import staging_ten_address_d1_proof as target
import staging_ten_address_escrow as escrow
import staging_ten_address_manifest as manifest
from test_staging_ten_address_manifest import SyntheticAEAD

RUN = "1234567"
SHA = "a" * 40


class NativeShape:
    """SQLite fixture below the actual REST transport/parser, not query injection."""

    def __init__(self):
        """Use only in-memory SQLite on the hosted source-test runner."""
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.calls = []
        self.lost = None

    def request(self, method, path, token, body, *, limit):
        """Encode native D1 success metadata; optionally lose a committed response."""
        if method != "POST" or path != f"/accounts/{'a' * 32}/d1/database/{escrow.DB}/query":
            raise AssertionError("fixture endpoint drift")
        if limit != escrow.MAX_RESPONSE or len(body) >= 100_000:
            raise AssertionError("fixture transport bounds")
        value = json.loads(body)
        sql, params = value["sql"], value["params"]
        self.calls.append((sql, params))
        before = self.db.total_changes
        rows = [dict(row) for row in self.db.execute(sql, params).fetchall()]
        self.db.commit()
        if self.lost == sql:
            self.lost = None
            raise TimeoutError("synthetic private response")
        payload = {"success": True, "errors": [], "messages": [], "result": [
            {"success": True, "results": rows, "meta": {
                "changes": self.db.total_changes - before, "duration": 0.12,
                "rows_read": len(rows), "rows_written": self.db.total_changes - before,
                "served_by": "synthetic-provider", "last_row_id": 0, "changed_db": True}}]}
        raw = json.dumps(payload).encode()
        if len(raw) > limit:
            raise AssertionError("fixture response bound")
        return raw


class ProofTests(unittest.TestCase):
    """Validate bounded migration/mirror roundtrip and fail-closed native acknowledgements."""

    def setUp(self):
        """Install a response fixture, never real transport or production crypto."""
        self.world = NativeShape()
        self.addCleanup(self.world.db.close)
        patch = mock.patch.object(target, "request", side_effect=self.world.request)
        patch.start(); self.addCleanup(patch.stop)
        crypto = mock.patch.object(manifest, "_cipher", SyntheticAEAD)
        crypto.start(); self.addCleanup(crypto.stop)
        self.provider = target.Provider("a" * 32, "synthetic-token")

    def prepare(self):
        """Apply both isolated fixture schemas and arm invented mirror ciphertext."""
        self.provider.apply()
        client = target.SyntheticEscrow(self.provider)
        blob = manifest.seal(target.fixture(RUN, SHA), target.KEY, RUN, target.GENERATION)
        client.put(blob, target.KEY, RUN, target.GENERATION)
        client.attach(RUN, target.KEY, target.GENERATION, RUN, blob)
        client.arm(RUN, target.KEY, target.GENERATION, RUN, blob)
        return client, blob

    def test_native_shape_multichunk_roundtrip_terminal_retained_no_real_rows(self):
        """Exercise request encoding/response parser, complete full chunk and terminal tail."""
        client, blob = self.prepare()
        self.assertGreater(len(blob), escrow.CHUNK)
        self.assertLess(len(blob), 2 * escrow.CHUNK)
        row, actual = client.read(RUN, target.KEY, target.GENERATION)
        self.assertEqual(actual, blob)
        self.assertEqual(row["chunk_count"], 2)
        terminal = client._finalize(RUN, target.KEY, target.GENERATION, "2345678", "b" * 40, blob)
        self.assertEqual(terminal["state"], "cleanup_verified")
        self.assertEqual(client.read(RUN, target.KEY, target.GENERATION)[1], blob)
        self.assertEqual(self.world.db.execute("SELECT COUNT(*) FROM staging_acceptance_escrows").fetchone()[0], 0)
        self.assertFalse(any(sql.startswith("DELETE") for sql, params in self.world.calls))
        with self.assertRaisesRegex(manifest.ContractFailure, "d1_proof_query_unreviewed"):
            client._run("purge")

    def test_migration_noop_exact_schema_and_partial_or_drift_rejects(self):
        """No implicit repair, IF NOT EXISTS, DROP, tenant migration or overwrite."""
        self.provider.apply()
        before = len(self.world.calls)
        self.provider.apply()
        self.assertFalse(any(sql.startswith("CREATE") for sql, params in self.world.calls[before:]))
        self.world.db.execute("CREATE TABLE staging_d1_probe_unexpected(x TEXT)")
        before = len(self.world.calls)
        with self.assertRaisesRegex(manifest.ContractFailure, "d1_proof_schema_partial_or_drift"):
            self.provider.apply()
        self.assertFalse(any(sql.startswith("CREATE") for sql, params in self.world.calls[before:]))

    def test_lost_migration_ack_stops_and_partial_restart_cannot_repair(self):
        """A successful provider commit without ACK is not successful schema admission."""
        first = next(iter(target.schema_objects(target.ORIGINAL).values()))[1]
        self.world.lost = first
        with self.assertRaisesRegex(manifest.ContractFailure, "d1_proof_query_unverified"):
            self.provider.apply()
        self.assertEqual(sum(sql == first for sql, params in self.world.calls), 1)
        with self.assertRaisesRegex(manifest.ContractFailure, "d1_proof_schema_partial_or_drift"):
            self.provider.apply()

    def test_ambiguous_native_arm_and_receipt_never_replayed(self):
        """Committed lost-response state is retained; neither path fabricates a fresh ACK."""
        client, blob = self.prepare()
        self.world.lost = target.PROBE_SQL["receipt"]
        with self.assertRaisesRegex(manifest.ContractFailure, "d1_proof_query_unverified"):
            client._finalize(RUN, target.KEY, target.GENERATION, "2345678", "b" * 40, blob)
        self.assertEqual(client.read(RUN, target.KEY, target.GENERATION)[0]["state"], "cleanup_verified")
        with self.assertRaisesRegex(manifest.ContractFailure, "escrow_receipt_not_available"):
            client._finalize(RUN, target.KEY, target.GENERATION, "2345678", "b" * 40, blob)
        self.assertEqual(sum(sql == target.PROBE_SQL["receipt"] for sql, params in self.world.calls), 1)

    def test_lost_native_arm_response_retains_without_a_permit(self):
        """A provider-shaped committed arm cannot be replayed from its later row."""
        self.provider.apply()
        client = target.SyntheticEscrow(self.provider)
        blob = manifest.seal(target.fixture(RUN, SHA), target.KEY, RUN, target.GENERATION)
        client.put(blob, target.KEY, RUN, target.GENERATION)
        client.attach(RUN, target.KEY, target.GENERATION, RUN, blob)
        self.world.lost = target.PROBE_SQL["arm"]
        with self.assertRaisesRegex(manifest.ContractFailure, "d1_proof_query_unverified"):
            client.arm(RUN, target.KEY, target.GENERATION, RUN, blob)
        self.assertEqual(client.read(RUN, target.KEY, target.GENERATION)[0]["state"], "armed")
        with self.assertRaisesRegex(manifest.ContractFailure, "escrow_arm_not_available"):
            client.arm(RUN, target.KEY, target.GENERATION, RUN, blob)
        self.assertEqual(sum(sql == target.PROBE_SQL["arm"] for sql, params in self.world.calls), 1)

    def test_native_response_rejects_batch_drift_failed_envelope_and_bad_rows(self):
        """The shared parser admits only one successful typed native query result."""
        batch = {"success": True, "results": [], "meta": {"changes": 1}}
        for payload in ({"success": False, "result": [batch]},
                        {"success": True, "result": [batch, batch]},
                        {"success": True, "result": [{**batch, "success": False}]},
                        {"success": True, "result": [{**batch, "results": [None]}]},
                        {"success": True, "result": [{**batch, "meta": {"changes": True}}]},
                        {"success": True, "result": [{**batch, "meta": {}}]}):
            with self.subTest(payload=payload):
                with self.assertRaises(manifest.ContractFailure):
                    escrow.query_result(payload)

    def test_cross_dispatch_executes_original_fixture_validation_and_retained_terminal(self):
        """Exercise both controller phases through native JSON, not a fake escrow success."""
        self.provider.apply()
        completed = {"status": "completed"}
        def metadata(path, token):
            """Provide independently read source/run relations; no real GitHub access."""
            run = path.split("/runs/", 1)[1].split("/", 1)[0]
            return {"id": int(run), "run_attempt": 1, "event": "workflow_dispatch",
                    "head_branch": manifest.BRANCH.removeprefix("refs/heads/"),
                    "path": target.WORKFLOW, "repository": {"full_name": manifest.REPOSITORY},
                    "head_sha": SHA if run == RUN else current_sha[0],
                    "status": completed["status"] if run == RUN and current[0] != RUN else "in_progress"}
        current = [RUN]
        current_sha = [SHA]
        def environment(mode, run):
            """Construct hosted manual capabilities afresh; execute consumes them."""
            return {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
                    "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REPOSITORY": manifest.REPOSITORY,
                    "GITHUB_REF": manifest.BRANCH, "GITHUB_RUN_ATTEMPT": "1", "GITHUB_RUN_ID": run,
                    "AMAIL_D1_PROOF_ENVIRONMENT": "staging", "AMAIL_D1_PROOF_CONFIRM": target.CONFIRMS[mode],
                    "AMAIL_D1_PROOF_SOURCE_RUN": "3456789", "AMAIL_D1_PROOF_PRIOR_RUN": RUN if mode == "read-terminal" else "",
                    "CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "synthetic-token",
                    "GITHUB_TOKEN": "synthetic-github-token"}
        with mock.patch.object(target, "checkout", side_effect=lambda: current_sha[0]), \
             mock.patch.object(target, "successful_source") as source, \
             mock.patch.object(target, "github_json", side_effect=metadata), \
             mock.patch.object(target.Provider, "provenance", return_value=("d", "v")):
            with mock.patch.dict(os.environ, environment("write-synthetic", RUN), clear=True):
                written = target.execute("write-synthetic")
            current[0] = "2345678"
            current_sha[0] = "b" * 40
            completed["status"] = "in_progress"
            with mock.patch.dict(os.environ, environment("read-terminal", current[0]), clear=True):
                with self.assertRaisesRegex(manifest.ContractFailure, "d1_proof_original_not_completed"):
                    target.execute("read-terminal")
            self.assertFalse(any(sql == target.PROBE_SQL["receipt"] for sql, params in self.world.calls))
            completed["status"] = "completed"
            with mock.patch.dict(os.environ, environment("read-terminal", current[0]), clear=True):
                terminal = target.execute("read-terminal")
        self.assertEqual(written["envelope_sha256"], terminal["envelope_sha256"])
        self.assertEqual(terminal["mirror_state"], "cleanup_verified")
        self.assertEqual(terminal["original_sha"], SHA)
        self.assertEqual(terminal["source_sha"], "b" * 40)
        self.assertFalse(terminal["real_cleanup_attested"])
        source.assert_called_with("3456789", "b" * 40, "synthetic-github-token")

    def test_fixed_capability_rejects_real_writes_and_generic_select(self):
        """The proof cannot write actual escrow or select mail, keys, users, aliases."""
        for sql in (escrow.SQL["create"], escrow.SQL["receipt"], escrow.SQL["purge"], "SELECT * FROM addresses"):
            with self.assertRaisesRegex(manifest.ContractFailure, "d1_proof_query_unreviewed"):
                self.provider.query(sql)
        self.assertEqual(self.world.calls, [])

    def test_exact_native_database_binding_and_deployment_relation(self):
        """Require independently read DB UUID/name, one D1 binding and stable deployment."""
        deployment = "00000000-0000-0000-0000-000000000004"
        version = "00000000-0000-0000-0000-000000000005"
        serving = {"deployments": [{"id": deployment, "strategy": "percentage",
                                    "versions": [{"version_id": version, "percentage": 100}]}]}
        # The existing serving parser requires the provider's real deployments shape.
        state = {"uuid": escrow.DB, "name": "moesegfault-mail-staging", "binding": escrow.DB}
        def metadata(method, path, token, data=None, limit=65_536):
            """Encode only fixed native metadata observations and a held singleton."""
            if method == "POST":
                self.assertEqual(json.loads(data)["sql"], target.HELD_SQL)
                return json.dumps({"success": True, "result": [
                    {"success": True, "results": [{"state": "held"}], "meta": {"changes": 0}}]}).encode()
            if path.endswith("/d1/database/" + escrow.DB):
                result = {"uuid": state["uuid"], "name": state["name"]}
            elif path.endswith("/deployments?per_page=1&page=1"):
                result = serving
            elif path.endswith("/versions/" + version):
                result = {"id": version, "resources": {"bindings": [
                    {"type": "d1", "name": "MAIL_DB", "id": state["binding"]}]}}
            else:
                raise AssertionError("unreviewed metadata path")
            return json.dumps({"success": True, "result": result}).encode()
        with mock.patch.object(target, "request", side_effect=metadata):
            self.assertEqual(self.provider.provenance(), (deployment, version))
            for key, wrong in (("uuid", "ad06f7f3-8897-4150-b9a9-7a46a8e55b30"),
                               ("name", "moesegfault-mail-production"), ("binding", "foreign-db")):
                old = state[key]
                state[key] = wrong
                with self.assertRaises(manifest.ContractFailure):
                    self.provider.provenance()
                state[key] = old

    def test_guard_rejects_local_retry_wrong_confirmation_and_foreign_prior(self):
        """Dispatch validation precedes capability reads and all provider requests."""
        valid = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
                 "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REPOSITORY": manifest.REPOSITORY,
                 "GITHUB_REF": manifest.BRANCH, "GITHUB_RUN_ATTEMPT": "1", "GITHUB_RUN_ID": RUN,
                 "AMAIL_D1_PROOF_ENVIRONMENT": "staging", "AMAIL_D1_PROOF_CONFIRM": target.CONFIRMS["write-synthetic"]}
        for change in ({"GITHUB_ACTIONS": "false"}, {"GITHUB_RUN_ATTEMPT": "2"},
                       {"AMAIL_D1_PROOF_CONFIRM": "true"}, {"AMAIL_D1_PROOF_PRIOR_RUN": RUN}):
            with mock.patch.dict(os.environ, {**valid, **change}, clear=True):
                with self.assertRaises(manifest.ContractFailure):
                    target.guard("write-synthetic")
        with mock.patch.dict(os.environ, valid, clear=True):
            target.guard("write-synthetic")
        self.assertEqual(self.world.calls, [])

    def test_workflow_manual_staging_secret_boundary_and_no_mail_permissions(self):
        """Source-only workflow inspection; no workflow dispatch or provider access."""
        path = Path(__file__).resolve().parents[2] / target.WORKFLOW
        source = path.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", source)
        self.assertNotRegex(source, r"(?m)^  (push|schedule|pull_request|workflow_call):")
        for required in ("environment: staging", "github.run_attempt == 1",
                         "group: staging-native-mail-acceptance", "cancel-in-progress: false",
                         "github.ref == 'refs/heads/codex/amail-v0.1.0'"):
            self.assertIn(required, source)
        self.assertLess(source.index("p.guard("), source.index("secrets.CLOUDFLARE_API_TOKEN"))
        for forbidden in ("RECOVERY_KEY", "CF_EMAIL_ROUTING_TOKEN", "STAGING_E2E_PASSWORD",
                          "issues: write", "wrangler deploy", "upload-artifact", "send_email"):
            self.assertNotIn(forbidden, source)

    def test_dependency_command_uses_literal_yaml_scalar(self):
        """Keep colon-space shell text out of a plain YAML run scalar.

        This source contract needs no extra parser dependency in the proof job.
        Whole-workflow parsing remains a separate hosted syntax-lint gate.
        """
        source = (Path(__file__).resolve().parents[2] / target.WORKFLOW).read_text(encoding="utf-8")
        command = "python -m pip install --only-binary=:all: -r infra/tests/ten_address_requirements.txt"
        self.assertIn("        run: |\n          " + command + "\n", source)
        self.assertNotIn("        run: " + command, source)


if __name__ == "__main__":
    unittest.main()
