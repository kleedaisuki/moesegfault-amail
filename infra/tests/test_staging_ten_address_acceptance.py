"""Hosted synthetic full quota phase composition; no real login, CLI or providers."""

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import staging_ten_address_acceptance as target
import staging_ten_address_manifest as manifest
import staging_ten_address_provenance as provenance
from test_staging_ten_address_manifest import KEY, RUN, GEN, OWNER, plan, provenance as identity_provenance, SyntheticAEAD
from test_staging_ten_address_hosted import World, VERSION
from test_staging_ten_address_escrow import Database

SHA = "a" * 40
PINS = provenance.Pins(VERSION, identity_provenance()["identity_revision"], identity_provenance()["login_revision"])


class PhaseTests(unittest.TestCase):
    """Exercise real controller composition while replacing every external capability."""

    def args(self, mode):
        """Use public original run/artifact IDs, never Secret arguments."""
        return argparse.Namespace(mode=mode, source_run="789", prior_run=RUN, artifact_id="123",
                                  mail_phase="pre-queue", queue_id="")

    def setup_world(self):
        """Keep synthetic path fixtures in a dedicated repository .temp subtree."""
        root = Path(__file__).resolve().parents[2] / ".temp"
        root.mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(prefix="quota-phase-unit-", dir=root)
        self.addCleanup(temp.cleanup)
        patch = mock.patch.object(target, "TEMP", Path(temp.name))
        patch.start(); self.addCleanup(patch.stop)
        world = World()
        reader = mock.Mock()
        reader.read.side_effect = world.read
        reader.sending_state.return_value = "held"
        reader.storage_empty.return_value = True
        services = mock.Mock()
        services.read.return_value = PINS
        cli = mock.Mock()
        cli.add.side_effect = world.add
        cli.delete.side_effect = world.delete
        cli.owned.side_effect = world.owned
        @contextmanager
        def native(*args, **kwargs):
            yield OWNER, cli
        artifacts = mock.Mock()
        def binary(source_run, checkout, destination, now):
            destination.write_bytes(b"synthetic trusted fixture")
            return destination
        artifacts.binary.side_effect = binary
        values = {"GITHUB_TOKEN": "synthetic", "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                  "CLOUDFLARE_ZONE_ID": "b" * 32, "CLOUDFLARE_API_TOKEN": "synthetic",
                  "CF_EMAIL_ROUTING_TOKEN": "synthetic", "STAGING_E2E_USERNAME": "synthetic_username",
                  "STAGING_E2E_PASSWORD": "synthetic-password-long", "AMAIL_TEN_ADDRESS_RECOVERY_KEY": KEY,
                  "AMAIL_TEN_ADDRESS_KEY_GENERATION": GEN}
        return world, reader, services, cli, native, artifacts, values

    def execute(self, mode, *, privacy="match", tampered=False, active_recovery=False,
                terminal=False, teardown_failure=False, scratch_failure=False, post_teardown_drift=False):
        """Run controller with synthetic authenticated envelopes and no environment tools."""
        world, reader, services, cli, native, artifacts, values = self.setup_world()
        with mock.patch.object(manifest, "_cipher", SyntheticAEAD):
            value = plan()
            # Real campaigns require a fresh manifest timestamp from prepare.
            import time
            value["created_at"] = int(time.time() * 1000)
            blob = manifest.seal(value, KEY, RUN, GEN)
            original_create = world.create
            def create(part):
                result = original_create(part)
                world.snapshot.rows[part.lower() + "@" + manifest.DOMAIN]["created_at"] = int(time.time() * 1000)
                return result
            world.create = create
            if mode == "recover" and active_recovery:
                world.create(value["allowed"][0].split("@")[0])
            artifacts.content.return_value = blob
            if mode == "campaign":
                destination = target.prepared_file(RUN)
                destination.parent.mkdir()
                destination.write_bytes(blob + b"tampered" if tampered else blob)
            current = RUN if mode != "recover" else "9999999"
            native_state = {"closed":False}
            @contextmanager
            def observed_native(*args,**kwargs):
                with native(*args,**kwargs) as account:
                    yield account
                native_state["closed"] = True
                if post_teardown_drift:
                    world.create(value["allowed"][0].split("@")[0])
                if teardown_failure:
                    raise manifest.ContractFailure("native_session_cleanup_required")
            database = Database()
            self.addCleanup(database.db.close)
            def query(sql,params):
                if sql in (target.escrow.SQL["receipt"],target.escrow.SQL["purge"]):
                    self.assertTrue(native_state["closed"])
                    self.assertEqual(list(target.TEMP.glob("ten-address-hosted-*")),[])
                return database.query(sql,params)
            escrow_client = target.escrow.Escrow("a"*32,"synthetic",query=query)
            if terminal:
                escrow_client.put(blob,KEY,RUN,GEN)
                escrow_client.attach(RUN,KEY,GEN,"123",blob)
            self.last_terminal = escrow_client,database,native_state
            with mock.patch.object(target, "environment", return_value=values), \
                    mock.patch.object(target, "checkout", return_value=SHA), \
                    mock.patch.dict(target.os.environ, {"GITHUB_RUN_ID": current}), \
                    mock.patch.object(target, "dispatch_record", return_value={"head_sha": SHA}), \
                    mock.patch.object(target.provenance, "successful_source") as source, \
                    mock.patch.object(target.artifact, "Artifacts", return_value=artifacts), \
                    mock.patch.object(target, "Readback", return_value=reader), \
                    mock.patch.object(target.provenance, "Services", return_value=services) as service_factory, \
                    mock.patch.object(target.provenance.mail_pin, "run", return_value=privacy) as private, \
                    mock.patch.object(target.native, "native_account", observed_native), \
                    mock.patch.object(target.escrow,"Escrow",return_value=escrow_client) as escrow_factory:
                if isinstance(privacy,list):
                    private.side_effect = privacy
                if scratch_failure:
                    remove = mock.patch.object(target.shutil,"rmtree",side_effect=OSError("synthetic private error"))
                    remove.start()
                try:
                    result = (target.finalize_recovery(self.args(mode)) if terminal else target.execute(self.args(mode)))
                finally:
                    if scratch_failure:
                        remove.stop()
                    if mode == "recover":
                        cli.add.assert_not_called()
                        cli.delete.assert_not_called()
                    self.assertEqual(escrow_factory.call_count,int(terminal))
            self.assertEqual(source.call_count, 1)
            self.assertIs(service_factory.call_args.args[2], reader.sending_state)
            self.assertEqual(list(target.TEMP.glob("ten-address-hosted-*")), [])
            return result, world, artifacts, private, cli

    def test_prepare_only_seals_durable_upload_file_without_address_mutation(self):
        """Actual prepare controller gets no add/delete capability before artifact upload."""
        result, world, artifacts, privacy, cli = self.execute("prepare")
        self.assertEqual(result, ("ten_address_recovery_prepared",))
        self.assertEqual(world.calls, [])
        cli.add.assert_not_called(); cli.delete.assert_not_called()
        artifacts.content.assert_not_called()
        with mock.patch.object(manifest, "_cipher", SyntheticAEAD):
            value = manifest.open_manifest(target.prepared_file(RUN).read_bytes(), KEY, RUN, GEN)
        self.assertEqual(value["owner_sub"], OWNER)
        self.assertEqual(value["provenance"], identity_provenance())

    def test_campaign_reads_same_ciphertext_then_ten_addresses_and_cleanup(self):
        """Complete synthetic campaign is gated by source/artifact/privacy/hold/pins."""
        result, world, artifacts, privacy, cli = self.execute("campaign")
        self.assertEqual(result[-1], "ten_address_cleanup_verified")
        self.assertEqual(len(world.calls), 39)
        self.assertEqual(len(world.deletes), 10)
        self.assertEqual(world.snapshot.global_count, 0)
        self.assertEqual(privacy.call_count, 2)
        self.assertEqual(artifacts.content.call_args.args[:3], ("123", RUN, SHA))

    def test_recovery_never_grants_add_or_requires_local_prepared_file(self):
        """Original encrypted artifact can be recovered from a later independent run."""
        result, world, artifacts, privacy, cli = self.execute("recover")
        self.assertEqual(result, ("ten_address_recovery_verified",))
        cli.add.assert_not_called()
        self.assertEqual(len(world.deletes), 0)
        self.assertEqual(world.snapshot.global_count, 0)
        self.assertFalse(target.prepared_file(RUN).exists())
        self.assertEqual(artifacts.content.call_args.args[:3], ("123", RUN, SHA))
        self.assertEqual(privacy.call_count, 2)

    def test_active_external_recovery_requires_manual_intervention_without_delete(self):
        """An active row cannot prove whether an earlier invocation attempted DELETE."""
        with self.assertRaisesRegex(manifest.ContractFailure, "recovery_manual_intervention_required"):
            self.execute("recover", active_recovery=True)

    def test_dormant_terminal_coordinator_verifies_recovery_and_teardown_before_sql(self):
        """A real controller recovery, native exit and binary removal precede receipt/purge."""
        result,world,artifacts,privacy,cli = self.execute("recover",terminal=True)
        client,database,native_state = self.last_terminal
        self.assertEqual(result,("ten_address_terminal_receipt_verified",))
        self.assertEqual(client.parent(RUN)["cleanup_verifier_run"],"9999999")
        self.assertEqual(client.parent(RUN)["cleanup_verifier_sha"],SHA)
        self.assertEqual(database.query(target.escrow.SQL["aggregate"],(RUN,)).rows,[{"n":0,"bytes":0}])
        self.assertTrue(native_state["closed"])
        self.assertEqual(privacy.call_count,3)
        cli.add.assert_not_called(); cli.delete.assert_not_called()
        self.assertEqual(world.calls,[])

    def test_terminal_coordinator_native_or_scratch_failure_preserves_ciphertext(self):
        """Incomplete local teardown never emits terminal SQL despite clean remote baseline."""
        for option,code in (("teardown_failure","native_session_cleanup_required"),
                            ("scratch_failure","quota_local_cleanup_required")):
            with self.subTest(option=option):
                with self.assertRaisesRegex(manifest.ContractFailure,code):
                    self.execute("recover",terminal=True,**{option:True})
                client,database,native_state = self.last_terminal
                self.assertEqual(client.parent(RUN)["state"],"sealed")
                self.assertFalse(any(sql in (target.escrow.SQL["receipt"],target.escrow.SQL["purge"])
                                     for sql,params in database.calls))
                self.assertGreater(database.query(target.escrow.SQL["aggregate"],(RUN,)).rows[0]["n"],0)

    def test_terminal_coordinator_active_privacy_or_post_teardown_drift_never_finalizes(self):
        """Clean teardown cannot compensate for a failed independent remote/privacy oracle."""
        for options in ({"active_recovery":True},
                        {"privacy":["match","match","privacy_unverified"]},
                        {"post_teardown_drift":True}):
            with self.subTest(options=options):
                with self.assertRaises(manifest.ContractFailure):
                    self.execute("recover",terminal=True,**options)
                client,database,native_state = self.last_terminal
                self.assertEqual(client.parent(RUN)["state"],"sealed")
                self.assertFalse(any(sql in (target.escrow.SQL["receipt"],target.escrow.SQL["purge"])
                                     for sql,params in database.calls))

    def test_capture_off_failure_or_ciphertext_mismatch_never_mutates(self):
        """Matching bindings do not replace effective capture-off or durable ciphertext proof."""
        with self.assertRaisesRegex(manifest.ContractFailure, "quota_effective_privacy_unverified"):
            self.execute("campaign", privacy="privacy_unverified")
        with self.assertRaisesRegex(manifest.ContractFailure, "artifact_not_durable"):
            self.execute("campaign", tampered=True)

    def test_activation_missing_rows_and_timeout_have_no_add_capability(self):
        """Polling cannot replay an allocation or manufacture successful prefix state."""
        reader = mock.Mock()
        reader.read.return_value = manifest.Snapshot({}, [], 0)
        with self.assertRaisesRegex(manifest.ContractFailure, "quota_activation_allocation_missing"):
            target.activation(reader, tuple(plan()["allowed"]))
        reader.read.assert_called_once()


class EntryTests(unittest.TestCase):
    """No CI wiring or mutable provider resources are accessed by entrypoint tests."""

    def test_local_default_execution_stops_before_secret_read(self):
        """Ordinary CLI use cannot accidentally run the hosted quota harness."""
        with mock.patch.dict(target.os.environ, {}, clear=True):
            with self.assertRaisesRegex(manifest.ContractFailure, "dispatch_unconfirmed"):
                target.environment("prepare")

    def test_terminal_source_seam_rejects_campaign_before_any_capability(self):
        """No campaign-success path or command-line switch can mint a cleanup receipt."""
        with mock.patch.object(target,"environment") as environment:
            with self.assertRaisesRegex(manifest.ContractFailure,"quota_terminal_recovery_only"):
                target.finalize_recovery(argparse.Namespace(mode="campaign"))
            environment.assert_not_called()

    def test_manual_intervention_is_a_fixed_failure_not_a_success_marker(self):
        """No unreviewed opt-in can turn unknown cross-run deletion into a replay."""
        from contextlib import redirect_stderr
        from io import StringIO
        output = StringIO()
        with mock.patch.object(target.sys, "argv", ["quota", "recover", "--source-run", "789"]), \
                mock.patch.object(target, "execute", side_effect=manifest.ContractFailure("recovery_manual_intervention_required")), \
                redirect_stderr(output):
            self.assertEqual(target.main(), 1)
        self.assertEqual(output.getvalue().strip(), "ten_address_recovery_manual_intervention_required")

    def test_actual_manual_run_identity_must_match_exact_workflow(self):
        """A diagnostic/source run cannot authorize this campaign despite matching SHA."""
        value = {"id": int(RUN), "run_attempt": 1, "event": "workflow_dispatch",
                 "head_branch": manifest.BRANCH.removeprefix("refs/heads/"),
                 "path": target.artifact.RECOVERY_WORKFLOW, "repository": {"full_name": manifest.REPOSITORY},
                 "head_sha": SHA, "status": "in_progress"}
        with mock.patch.object(target, "github_json", return_value=value):
            self.assertEqual(target.dispatch_record(RUN, "private", checkout_sha=SHA), value)
        for change in ({"event": "push"}, {"path": ".github/workflows/ci.yml"}, {"status": "completed"},
                       {"head_sha": "b" * 40}, {"run_attempt": 2}):
            with mock.patch.object(target, "github_json", return_value=dict(value, **change)):
                with self.assertRaisesRegex(manifest.ContractFailure, "dispatch_provenance_unverified"):
                    target.dispatch_record(RUN, "private", checkout_sha=SHA)
