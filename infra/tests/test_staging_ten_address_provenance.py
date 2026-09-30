"""Hosted synthetic quota source/serving/hold contracts; no live control planes."""

import copy
import unittest
from unittest import mock

import staging_ten_address_provenance as target
import staging_ten_address_manifest as manifest
from test_staging_ten_address_manifest import RUN

SHA = "a" * 40
V = ["00000000-0000-0000-0000-00000000000" + str(i) for i in range(1, 4)]


def run():
    """Represent exact successful source provenance, never a caller pass flag."""
    return {"id": int(RUN), "run_attempt": 1, "event": "push", "status": "completed",
            "conclusion": "success", "head_sha": SHA,
            "head_branch": manifest.BRANCH.removeprefix("refs/heads/"),
            "path": target.SOURCE_WORKFLOW, "repository": {"full_name": manifest.REPOSITORY}}


def jobs():
    """Supply complete six-job metadata including the executed real crypto step."""
    return {"total_count": len(target.JOBS), "jobs": [
        {"name": name, "run_id": int(RUN), "head_sha": SHA, "status": "completed", "conclusion": "success",
         "steps": [{"name": "Test real encrypted quota recovery envelopes", "status": "completed",
                    "conclusion": "success"}] if name == target.JOBS[-1] else []} for name in target.JOBS]}


def identity():
    """Keep protocol-critical and persistent bindings explicitly staging."""
    bindings = [{"name": name, "type": "plain_text", "text": value}
                for name, value in target.IDENTITY_FIXED.items()]
    bindings += [{"name": "DB", "type": "d1", "database_id": target.IDENTITY_DB},
                 {"name": "AUDIT_ARCHIVE", "type": "r2_bucket", "bucket_name": "moesegfault-identity-audit-staging"},
                 {"name": "AVATARS", "type": "r2_bucket", "bucket_name": "moesegfault-avatars-staging"},
                 {"name": "EMAIL", "type": "send_email", "allowed_sender_addresses": ["identity@moesegfault.dev"]},
                 {"name": "OIDC_PRIVATE_KEY_PKCS8", "type": "secret_text"}]
    return {"id": V[1], "resources": {"bindings": bindings}}


def mail():
    """Generate binding fixtures from the existing exact reviewed Mail checker."""
    fields = {"d1": "database_id", "r2_bucket": "bucket_name", "plain_text": "text"}
    return {"id": V[0], "resources": {"bindings": [dict(name=name, type=kind,
             **({fields[kind]: value} if kind in fields else {}))
             for name, (kind, value) in target.mail_pin.expected_bindings().items()]}}


class ProvenanceTests(unittest.TestCase):
    """No test can manufacture a live quota acceptance result."""

    def source(self, result=None, listing=None):
        """Inject raw GitHub observations, not precomputed success booleans."""
        target.successful_source(RUN, SHA, "synthetic-token",
                                 read=mock.Mock(side_effect=[result or run(), listing or jobs()]))

    def test_exact_complete_successful_source(self):
        """All cross-platform, Worker, site and infrastructure jobs must execute."""
        self.source()
        for change in ({"head_sha": "b" * 40}, {"event": "workflow_dispatch"},
                       {"conclusion": "failure"}, {"run_attempt": 2}, {"head_branch": "main"}):
            with self.assertRaises(manifest.ContractFailure):
                self.source(dict(run(), **change))

    def test_incomplete_skipped_duplicate_or_missing_crypto_never_passes(self):
        """A green run alone cannot attest skipped/omitted test capabilities."""
        changes = []
        incomplete = jobs(); incomplete["total_count"] += 1; changes.append(incomplete)
        skipped = jobs(); skipped["jobs"][1]["conclusion"] = "skipped"; changes.append(skipped)
        duplicate = jobs(); duplicate["jobs"].append(copy.deepcopy(duplicate["jobs"][1])); duplicate["total_count"] += 1; changes.append(duplicate)
        missing = jobs(); missing["jobs"][-1]["steps"] = []; changes.append(missing)
        crypto = jobs(); crypto["jobs"][-1]["steps"][0]["conclusion"] = "skipped"; changes.append(crypto)
        for listing in changes:
            with self.assertRaises(manifest.ContractFailure):
                self.source(listing=listing)

    def service(self, *, read=None, hold=None):
        """Return a real validator over injected provider-shaped observations."""
        versions = {target.mail_pin.SCRIPT: mail(), target.IDENTITY: identity(),
                    target.LOGIN: {"id": V[2], "resources": {"bindings": []}}}
        def observed(worker, suffix):
            if suffix.startswith("versions/"):
                return copy.deepcopy(versions[worker])
            return {"deployments": [{"id": V[0], "strategy": "percentage",
                                      "versions": [{"version_id": versions[worker]["id"], "percentage": 100}]}]}
        return target.Services("a" * 32, "synthetic-token", hold or (lambda: "held"), read=read or observed)

    def test_current_serving_relation_and_hold_are_independent_observations(self):
        """Three revisions come from actual version-scoped control-plane inventory."""
        self.assertEqual(self.service().read(), target.Pins(*V))
        reader = mock.Mock()
        with self.assertRaisesRegex(manifest.ContractFailure, "global_sending_not_held"):
            self.service(read=reader, hold=lambda: "allowed").read()
        reader.assert_not_called()
        holds = iter(["held", "allowed"])
        with self.assertRaisesRegex(manifest.ContractFailure, "global_sending_not_held"):
            self.service(hold=lambda: next(holds)).read()

    def test_pin_rechecks_reuse_immutable_binding_admission(self):
        """Per-operation checks fetch current serving IDs/hold, not unchanged version bodies."""
        services = self.service()
        pins = services.read()
        reader = mock.Mock(wraps=services._read)
        services._read = reader
        services.check(pins)
        self.assertEqual(reader.call_count, 3)
        self.assertTrue(all(call.args[1] == "deployments?per_page=1&page=1" for call in reader.call_args_list))
        with self.assertRaisesRegex(manifest.ContractFailure, "service_relation_changed"):
            services.check(target.Pins(V[1], V[1], V[2]))

    def test_split_traffic_or_provider_failure_is_not_a_pin(self):
        """No latest-uploaded version or raw provider failure can substitute serving."""
        invalid = {"deployments": [{"id": V[0], "strategy": "percentage", "versions": [
            {"version_id": V[0], "percentage": 50}, {"version_id": V[1], "percentage": 50}]}]}
        with self.assertRaisesRegex(manifest.ContractFailure, "service_serving_unverified"):
            self.service(read=lambda *args: invalid).read()
        with self.assertRaisesRegex(manifest.ContractFailure, "^service_provenance_unverified$"):
            self.service(read=mock.Mock(side_effect=RuntimeError("private response"))).read()

    def test_identity_foreign_data_and_protocol_origin_are_rejected(self):
        """Unknown service bindings and wrong issuer/store resources fail closed."""
        for name, field, value in (("DB", "database_id", V[0]),
                                   ("ISSUER", "text", "https://identity.moesegfault.dev"),
                                   ("AVATARS", "bucket_name", "production")):
            observed = identity()
            next(binding for binding in observed["resources"]["bindings"] if binding["name"] == name)[field] = value
            with self.assertRaisesRegex(manifest.ContractFailure, "identity_bindings_unverified"):
                target.identity_bindings(observed, V[1])
        observed = identity()
        observed["resources"]["bindings"].append({"name": "FOREIGN_SERVICE", "type": "service", "service": "production"})
        with self.assertRaises(manifest.ContractFailure):
            target.identity_bindings(observed, V[1])

    def test_complete_bindings_need_no_duplicate_or_missing_inventory(self):
        """An omitted bindings list is not equivalent to an empty static Login Worker."""
        for observed in ({"id": V[2], "resources": {}},
                         {"id": V[2], "resources": {"bindings": [{"name": "A"}, {"name": "A"}]}}):
            with self.assertRaises(manifest.ContractFailure):
                target.binding_inventory(observed, V[2])
