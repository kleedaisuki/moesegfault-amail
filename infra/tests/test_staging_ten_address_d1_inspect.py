"""Hosted-only read-only incident diagnosis contracts; no real provider requests."""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

import staging_ten_address_d1_inspect as inspect
import staging_ten_address_d1_proof as proof
import staging_ten_address_escrow as escrow
import staging_ten_address_manifest as manifest
from test_staging_ten_address_d1_proof import NativeShape
from historical_containment_fixture import VERSION, historical_version

RUN = "1234567"
SHA = "a" * 40
DEPLOYMENT = "00000000-0000-0000-0000-000000000004"


def environment() -> dict:
    """Build explicitly confirmed hosted inspect capabilities for isolated fixtures."""
    return {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REPOSITORY": manifest.REPOSITORY,
            "GITHUB_REF": manifest.BRANCH, "GITHUB_RUN_ATTEMPT": "1", "GITHUB_RUN_ID": RUN,
            "AMAIL_D1_PROOF_ENVIRONMENT": "staging", "AMAIL_D1_PROOF_CONFIRM": proof.CONFIRMS["inspect"],
            "AMAIL_D1_PROOF_PRIOR_RUN": inspect.FAILED_RUN, "AMAIL_D1_PROOF_SOURCE_RUN": "3456789",
            "CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "synthetic-private-token",
            "GITHUB_TOKEN": "synthetic-github-token"}


class InspectionTests(unittest.TestCase):
    """Exercise the real SELECT encoder/parser and incident-bound stage controller."""

    def setUp(self):
        """Prepare in-memory policy and native metadata, without hosted/provider access."""
        self.world = NativeShape()
        self.addCleanup(self.world.db.close)
        self.world.db.execute("CREATE TABLE send_policy(scope TEXT,owner_iss TEXT,owner_sub TEXT,state TEXT)")
        self.world.db.execute("INSERT INTO send_policy VALUES('global','*','*','held')")
        self.serving = {"deployments": [{"id": DEPLOYMENT, "strategy": "percentage",
                                       "versions": [{"version_id": VERSION, "percentage": 100}]}]}
        self.database = {"uuid": escrow.DB, "name": "moesegfault-mail-staging"}
        self.version = historical_version()
        self.github = {"id": int(inspect.FAILED_RUN), "run_attempt": 1, "event": "workflow_dispatch",
                       "head_branch": manifest.BRANCH.removeprefix("refs/heads/"), "path": proof.WORKFLOW,
                       "repository": {"full_name": manifest.REPOSITORY}, "head_sha": inspect.FAILED_SHA,
                       "status": "completed", "conclusion": "failure"}
        self.current = {**self.github, "id": int(RUN), "head_sha": SHA, "status": "in_progress", "conclusion": None}
        self.fail_path = None
        self.gets = []

    def transport(self, method, path, token, body=None, *, limit=65_536):
        """Route fixed read-only endpoints to native fixtures; leak sentinel must stay private."""
        if self.fail_path and self.fail_path in path:
            raise TimeoutError("synthetic-private-provider-response")
        if method == "POST":
            return self.world.request(method, path, token, body, limit=limit)
        self.assertEqual(method, "GET")
        self.gets.append(path)
        if path.endswith(f"d1/database/{escrow.DB}"):
            result = self.database
        elif path.endswith(inspect.DEPLOYMENTS):
            result = self.serving
        elif path.endswith(inspect.WORKER + "versions/" + VERSION):
            result = self.version
        else:
            raise AssertionError("fixture endpoint drift")
        return json.dumps({"success": True, "result": result}).encode()

    def github_read(self, path, token):
        """Bind original failure and current invocation through the real dispatch validator."""
        if path.endswith(f"/runs/{inspect.FAILED_RUN}/attempts/1"):
            return self.github
        self.assertTrue(path.endswith(f"/runs/{RUN}/attempts/1"))
        return self.current

    def populate(self, prefix: str, state: str):
        """Seed schemas as setup only; measured inspect never applies or repairs them."""
        objects = list(proof.schema_objects(prefix).values())
        if state == "partial_or_drift":
            objects = objects[:1]
        for kind, sql in objects if state != "absent" else []:
            self.world.db.execute(sql)
        self.world.db.commit()

    def execute(self, changes=None, **patches):
        """Run source orchestration against fixtures while forbidding every mutation seam."""
        with mock.patch.dict(os.environ, {**environment(), **(changes or {})}, clear=True), \
             mock.patch.object(proof, "request", side_effect=self.transport), \
             mock.patch.object(proof, "github_json", side_effect=self.github_read), \
             mock.patch.object(proof, "checkout", return_value=SHA), \
             mock.patch.object(proof, "successful_source", **patches) as source, \
             mock.patch.object(proof.Provider, "apply", side_effect=AssertionError("DDL forbidden")) as apply, \
             mock.patch.object(proof, "SyntheticEscrow", side_effect=AssertionError("mirror write forbidden")) as mirror:
            before = list(self.world.db.iterdump())
            result = proof.execute("inspect")
            self.assertEqual(list(self.world.db.iterdump()), before)
            apply.assert_not_called()
            mirror.assert_not_called()
        return result, source

    def test_absent_and_exact_are_readonly_observations_not_mutation_authority(self):
        """All absent/exact combinations retain DB and independently classify both namespaces."""
        for formal, mirror in (("absent", "absent"), ("exact", "absent"), ("exact", "exact")):
            with self.subTest(formal=formal, mirror=mirror):
                if formal == "exact" and not self.world.db.execute(
                        "SELECT name FROM sqlite_master WHERE name='staging_acceptance_escrows'").fetchall():
                    self.populate(proof.ORIGINAL, formal)
                if mirror == "exact":
                    self.populate(proof.PREFIX, mirror)
                result, source = self.execute()
                self.assertEqual(result["stages"]["formal_schema"], formal)
                self.assertEqual(result["stages"]["mirror_schema"], mirror)
                self.assertEqual(result["result"], "d1_proof_inspect_readonly_complete_no_mutation_authority")
                self.assertFalse(result["mutation_authority"])
                self.assertTrue(result["read_only"])
                source.assert_called_once_with("3456789", SHA, "synthetic-github-token")
        self.assertTrue(all(sql in (proof.HELD_SQL, proof.SCHEMA_SQL) for sql, params in self.world.calls))

    def test_partial_schema_classifies_other_namespace_without_repair(self):
        """A lost CREATE ACK's partial formal schema never becomes safe by inspection."""
        self.populate(proof.ORIGINAL, "partial_or_drift")
        result, source = self.execute()
        self.assertEqual(result["stages"]["formal_schema"], "partial_or_drift")
        self.assertEqual(result["stages"]["mirror_schema"], "absent")
        self.assertEqual(result["result"], "d1_proof_inspect_partial_or_drift_no_mutation_authority")
        self.assertFalse(any(sql.startswith("CREATE") for sql, params in self.world.calls))

    def test_exact_formal_partial_mirror_and_extra_or_changed_ddl_are_not_exact(self):
        """Mirror and formal drift are classified separately, not merged into schema success."""
        self.populate(proof.ORIGINAL, "exact")
        self.populate(proof.PREFIX, "partial_or_drift")
        result, _ = self.execute()
        self.assertEqual(result["stages"]["formal_schema"], "exact")
        self.assertEqual(result["stages"]["mirror_schema"], "partial_or_drift")
        self.world.db.execute("CREATE TABLE staging_acceptance_unexpected(x TEXT)")
        result, _ = self.execute()
        self.assertEqual(result["stages"]["formal_schema"], "partial_or_drift")
        self.assertEqual(inspect.classify_schema({"unexpected": ("table", "changed")}, proof.ORIGINAL),
                         "partial_or_drift")

    def test_guard_rejects_retry_wrong_ref_confirmation_prior_and_invalid_source(self):
        """Pre-secret guard failures do not make any GitHub/provider requests."""
        for changes in ({"GITHUB_RUN_ATTEMPT": "2"}, {"GITHUB_REF": "refs/heads/main"},
                        {"AMAIL_D1_PROOF_CONFIRM": proof.CONFIRMS["apply-schema"]},
                        {"AMAIL_D1_PROOF_PRIOR_RUN": ""}, {"AMAIL_D1_PROOF_PRIOR_RUN": "4567890"},
                        {"AMAIL_D1_PROOF_SOURCE_RUN": "not-a-run"}):
            with self.subTest(changes=changes):
                result, source = self.execute(changes)
                self.assertEqual(result["stages"]["guard"], "unverified")
                source.assert_not_called()
                self.assertEqual(self.gets, [])
                self.assertEqual(self.world.calls, [])

    def test_github_failure_relation_and_source_gate_precede_provider(self):
        """Exact original attempt/SHA/failure and exact new source are independent gates."""
        for changes in ({"head_sha": "b" * 40}, {"status": "in_progress"}, {"conclusion": "success"},
                        {"run_attempt": 2}, {"path": ".github/workflows/ci.yml"}):
            with self.subTest(changes=changes):
                old = self.github
                self.github = {**old, **changes}
                result, source = self.execute()
                self.github = old
                self.assertEqual(result["stages"]["github_failed_apply"], "unverified")
                source.assert_not_called()
        result, _ = self.execute(side_effect=RuntimeError("synthetic-private-source"))
        self.assertEqual(result["stages"]["source"], "unverified")
        self.assertEqual(self.gets, [])
        self.assertEqual(self.world.calls, [])

    def test_database_worker_binding_and_hold_are_distinct_stops(self):
        """Bad identity or containment cannot query schemas or expose private values."""
        cases = ((self.database, "uuid", "foreign-db", "database"),
                 (self.serving, "deployments", [], "worker"),
                 (self.version, "id", "foreign-version", "binding"))
        for target, field, wrong, phase in cases:
            old = target[field]
            target[field] = wrong
            result, _ = self.execute()
            target[field] = old
            self.assertEqual(result["stages"][phase], "unverified")
            self.assertEqual(result["stages"]["formal_schema"], "not_checked")
        self.world.db.execute("UPDATE send_policy SET state='enabled'")
        result, _ = self.execute()
        self.assertEqual(result["stages"]["held"], "unverified")
        self.assertEqual(result["stages"]["formal_schema"], "not_checked")

    def test_exact_c3f_contract_has_no_other_version_or_binding_fallback(self):
        """Reject direct-only, wrong/extra/missing/duplicate resources before held/schema."""
        mutations = (
            lambda value: value["resources"]["bindings"].pop(1),
            lambda value: value["resources"]["bindings"][1].update(database_id="wrong-role"),
            lambda value: value["resources"]["bindings"][0].update(database_id="wrong-mail"),
            lambda value: value["resources"]["bindings"].append(value["resources"]["bindings"][0].copy()),
            lambda value: value["resources"]["bindings"].append({"name": "TRACE_EVENTS", "type": "queue"}),
        )
        for mutate in mutations:
            self.version = historical_version()
            mutate(self.version)
            with self.subTest(mutate=mutate):
                result, _ = self.execute()
            self.assertEqual(result["stages"]["binding"], "unverified")
            self.assertEqual(result["stages"]["held"], "not_checked")
            self.assertEqual(self.world.calls, [])
        provider = inspect.ReadOnlyProvider("a" * 32, "synthetic-private-token")
        other = "00000000-0000-0000-0000-000000000005"
        value = historical_version()
        value["id"] = other
        with mock.patch.object(provider, "metadata", return_value=value):
            with self.assertRaises(manifest.ContractFailure):
                provider.binding((DEPLOYMENT, other))

    def test_readonly_facade_rejects_all_write_and_arbitrary_read_paths(self):
        """No migration flag or synthetic/real data query can escape the two SELECTs."""
        provider = inspect.ReadOnlyProvider("a" * 32, "synthetic-private-token")
        with mock.patch.object(proof, "request") as transport:
            for sql in (*proof.PROBE_SQL.values(), *escrow.SQL.values(), "SELECT * FROM addresses"):
                if sql == proof.SCHEMA_SQL:
                    continue
                with self.assertRaises(manifest.ContractFailure):
                    provider.query(sql)
            for sql in (value[1] for value in proof.schema_objects(proof.ORIGINAL).values()):
                with self.assertRaises(manifest.ContractFailure):
                    provider.query(sql)
            with self.assertRaises(manifest.ContractFailure):
                provider.query(proof.SCHEMA_SQL, (1, "other"))
            with self.assertRaises(manifest.ContractFailure):
                provider.metadata("workers/scripts/production/settings")
            transport.assert_not_called()
        self.assertFalse(hasattr(provider, "apply"))

    def test_private_transport_failure_and_main_partial_have_fixed_output_and_nonzero(self):
        """Private provider exceptions never leak; partial diagnosis does not pass workflow."""
        self.fail_path = "/d1/database/"
        result, _ = self.execute()
        self.assertEqual(result["stages"]["database"], "unverified")
        self.assertNotIn("synthetic-private", json.dumps(result))
        self.fail_path = None
        self.populate(proof.PREFIX, "partial_or_drift")
        result, _ = self.execute()
        output = io.StringIO()
        with mock.patch.object(proof, "execute", return_value=result), \
             mock.patch.object(sys, "argv", ["proof", "inspect"]), contextlib.redirect_stdout(output):
            self.assertEqual(proof.main(), 1)
        self.assertEqual(json.loads(output.getvalue()), result)

    def test_integer_params_rejected_numeric_string_probe_remains_readonly(self):
        """Test the native string-params hypothesis without replaying a DDL attempt."""
        original = self.transport
        def strings_only(method, path, token, body=None, *, limit=65_536):
            """Reject integer schema parameters with a synthetic private API error."""
            if method == "POST" and json.loads(body)["sql"] == proof.SCHEMA_SQL:
                if type(json.loads(body)["params"][0]) is int:
                    raise ValueError("synthetic-private-params-type-error")
            return original(method, path, token, body, limit=limit)
        with mock.patch.object(self, "transport", side_effect=strings_only):
            result, _ = self.execute()
        for phase in ("formal_schema", "mirror_schema"):
            self.assertEqual(result["stages"][phase], "absent")
            self.assertEqual(result["stages"][phase + "_integer"], "unverified")
            self.assertEqual(result["stages"][phase + "_numeric_string"], "verified")
            self.assertEqual(result["schema_parameter_shapes"][phase], "numeric_string_only")
        self.assertFalse(result["mutation_authority"])
        self.assertNotIn("synthetic-private", json.dumps(result))

    def test_readonly_query_rejects_nonzero_changes_and_schema_response_drift(self):
        """A nominal SELECT cannot admit changed-row metadata or malformed schema rows."""
        provider = inspect.ReadOnlyProvider("a" * 32, "synthetic-private-token")
        bad = {"success": True, "result": [{"success": True, "results": [], "meta": {"changes": 1}}]}
        with mock.patch.object(proof, "request", return_value=json.dumps(bad).encode()):
            with self.assertRaises(manifest.ContractFailure):
                provider.query(proof.HELD_SQL)
        for rows in ([{"name": "foreign", "type": "table", "sql": "x"}],
                     [{"name": proof.ORIGINAL + "x", "type": "table", "sql": None}]):
            with self.assertRaises(manifest.ContractFailure):
                proof.schema_observation(rows, proof.ORIGINAL)

    def test_rechecks_reject_worker_hold_and_schema_changes(self):
        """Later changes cannot turn an earlier schema snapshot into diagnostic success."""
        original = self.transport
        for phase in ("worker_recheck", "held_recheck", "schema_recheck"):
            counts = {"worker": 0, "held": 0, "schema": 0}
            def changing(method, path, token, body=None, *, limit=65_536):
                """Change only the later response without mutating inspected SQLite state."""
                if method == "GET" and path.endswith(inspect.DEPLOYMENTS):
                    counts["worker"] += 1
                    if phase == "worker_recheck" and counts["worker"] == 2:
                        return json.dumps({"success": True, "result": {"deployments": []}}).encode()
                if method == "POST":
                    sql = json.loads(body)["sql"]
                    kind = "held" if sql == proof.HELD_SQL else "schema"
                    counts[kind] += 1
                    if phase == "held_recheck" and kind == "held" and counts[kind] == 2:
                        return json.dumps({"success": True, "result": [{"success": True,
                            "results": [{"state": "enabled"}], "meta": {"changes": 0}}]}).encode()
                    if phase == "schema_recheck" and kind == "schema" and counts[kind] == 5:
                        return json.dumps({"success": True, "result": [{"success": True,
                            "results": [{"name": proof.ORIGINAL + "unexpected", "type": "table",
                                         "sql": "CREATE TABLE staging_acceptance_unexpected(x TEXT)"}],
                            "meta": {"changes": 0}}]}).encode()
                return original(method, path, token, body, limit=limit)
            with self.subTest(phase=phase), mock.patch.object(self, "transport", side_effect=changing):
                result, _ = self.execute()
            self.assertEqual(result["stages"][phase], "unverified")
            self.assertEqual(result["result"], "d1_proof_inspect_failed_no_mutation_authority")

    def test_disagreeing_schema_shapes_and_both_failed_shapes_never_mean_absent(self):
        """Independent successful shapes must agree; response failure is not emptiness."""
        original = self.transport
        for failure in ("disagree", "both_fail"):
            def inconsistent(method, path, token, body=None, *, limit=65_536):
                """Supply protocol disagreement only for formal schema, leaving mirror readable."""
                if method == "POST":
                    value = json.loads(body)
                    if value["sql"] == proof.SCHEMA_SQL and value["params"][1] == proof.ORIGINAL:
                        if failure == "both_fail":
                            raise ValueError("synthetic-private-unavailable")
                        if type(value["params"][0]) is str:
                            return json.dumps({"success": True, "result": [{"success": True,
                                "results": [{"name": proof.ORIGINAL + "unexpected", "type": "table",
                                             "sql": "CREATE TABLE staging_acceptance_unexpected(x TEXT)"}],
                                "meta": {"changes": 0}}]}).encode()
                return original(method, path, token, body, limit=limit)
            with self.subTest(failure=failure), mock.patch.object(self, "transport", side_effect=inconsistent):
                result, _ = self.execute()
            self.assertEqual(result["stages"]["formal_schema"], "unverified")
            self.assertEqual(result["stages"]["mirror_schema"], "absent")
            self.assertEqual(result["stages"]["schema_recheck"], "not_checked")
            self.assertEqual(result["result"], "d1_proof_inspect_failed_no_mutation_authority")

    def test_workflow_registered_path_new_mode_preserves_secret_and_staging_boundary(self):
        """Inspect stays in the existing manual registered path and before-secret gate."""
        source = (Path(__file__).resolve().parents[2] / proof.WORKFLOW).read_text(encoding="utf-8")
        self.assertIn("options: [inspect, apply-schema, write-synthetic, read-terminal]", source)
        self.assertIn("36787173756 for inspect", source)
        self.assertLess(source.index("p.guard("), source.index("secrets.CLOUDFLARE_API_TOKEN"))
        self.assertIn("environment: staging", source)
        self.assertIn("cancel-in-progress: false", source)


if __name__ == "__main__":
    unittest.main()
