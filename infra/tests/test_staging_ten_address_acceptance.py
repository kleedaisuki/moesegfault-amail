"""Hosted synthetic full quota phase composition; no real login, CLI or providers."""

import argparse
import copy
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import staging_ten_address_acceptance as target
import staging_ten_address_manifest as manifest
import staging_ten_address_provenance as provenance
from test_staging_ten_address_manifest import KEY, RUN, GEN, OWNER, plan, row, rule, provenance as identity_provenance, SyntheticAEAD
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
                terminal=False, teardown_failure=False, scratch_failure=False, post_teardown_drift=False,
                tombstones=False, final_drift="", transport="artifact", historical_sha=SHA,
                original_status="completed", original_record_sha=None, same_run=False,
                selected_generation=GEN, selected_key=KEY, corrupt_chunk=False, original_missing=False,
                prior_terminal=False, late_chunk_loss="", durable_prepare=False,
                preparation_failure="", durable_campaign=False, arm_failure=""):
        """Run controller with synthetic authenticated envelopes and no environment tools."""
        world, reader, services, cli, native, artifacts, values = self.setup_world()
        terminal = terminal or transport == "escrow"
        values["AMAIL_TEN_ADDRESS_KEY_GENERATION"] = selected_generation
        values["AMAIL_TEN_ADDRESS_RECOVERY_KEY"] = selected_key
        with mock.patch.object(manifest, "_cipher", SyntheticAEAD):
            baseline = manifest.Snapshot({},[],0)
            if final_drift.startswith("unrelated"):
                baseline = manifest.Snapshot({"foreign@example.test":row(owner="foreign",saved="foreign-rule",local_part="foreign",created=1)},
                                             [rule("foreign@example.test","foreign-rule")],1)
            value = plan(baseline)
            if late_chunk_loss == "partial":
                # Two legal encrypted chunks suffice to expose partial retention;
                # maximum-size transport has its own explicit real-cipher check.
                value["baseline"]["objects"] = {f"synthetic-{index}-" + "x"*900:"a"*64 for index in range(100)}
            value["checkout"] = historical_sha
            world.snapshot = copy.deepcopy(manifest.Snapshot(**value["baseline"]))
            # Real campaigns require a fresh manifest timestamp from prepare.
            import time
            value["created_at"] = int(time.time() * 1000)
            blob = manifest.seal(value, KEY, RUN, GEN)
            if tombstones:
                for index,address in enumerate(value["allowed"][:10]):
                    world.snapshot.rows[address] = row(state="retired",created=value["created_at"]+1,
                            local_part=address.split("@",1)[0],slot=index,next_reconcile_at=123456789)
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
            current = RUN if mode != "recover" or same_run else "9999999"
            native_state = {"closed":False}
            @contextmanager
            def observed_native(*args,**kwargs):
                with native(*args,**kwargs) as account:
                    yield account
                native_state["closed"] = True
                if post_teardown_drift:
                    world.create(value["allowed"][0].split("@")[0])
                if final_drift == "unrelated-row":
                    world.snapshot.rows["foreign@example.test"]["owner_sub"] = "changed-foreign"
                elif final_drift == "unrelated-rule":
                    world.snapshot.rules[0]["raw_digest"] = "c"*64
                elif final_drift == "tombstone-owner":
                    world.snapshot.rows[value["allowed"][0]]["owner_sub"] = "foreign"
                elif final_drift == "tombstone-unsettled":
                    world.snapshot.rows[value["allowed"][0]]["needs_reconcile"] = 1
                if late_chunk_loss and prior_terminal:
                    # Simulate another receipt-authorized storage actor after
                    # initial full escrow readback and native recovery. The
                    # coordinator itself must not send a purge or claim retained.
                    lose_chunks()
                if teardown_failure:
                    raise manifest.ContractFailure("native_session_cleanup_required")
            database = Database()
            self.addCleanup(database.db.close)
            def lose_chunks():
                """Model a separate receipt-gated actor, never a coordinator purge call."""
                sql = f"DELETE FROM {target.escrow.PARTS} WHERE original_run=?"
                if late_chunk_loss == "partial":
                    sql += " AND chunk_index=0"
                database.db.execute(sql,(RUN,))
                database.db.commit()
            def query(sql,params):
                if sql in (target.escrow.SQL["receipt"],target.escrow.SQL["purge"]):
                    self.assertTrue(native_state["closed"])
                    self.assertEqual(list(target.TEMP.glob("ten-address-hosted-*")),[])
                return database.query(sql,params)
            escrow_client = target.escrow.Escrow("a"*32,"synthetic",query=query)
            if terminal or durable_campaign:
                escrow_client.put(blob,KEY,RUN,GEN)
                escrow_client.attach(RUN,KEY,GEN,"123",blob)
            if arm_failure:
                original_arm = escrow_client.arm
                if arm_failure == "lost-ack":
                    def lost_arm(*args):
                        original_arm(*args)
                        raise manifest.ContractFailure("escrow_arm_ack_unverified")
                    escrow_client.arm = lost_arm
                elif arm_failure == "already-armed":
                    escrow_client.arm(RUN, KEY, GEN, "123", blob)
                elif arm_failure == "wrong-permit":
                    escrow_client.arm = mock.Mock(return_value=target.escrow.Arm(RUN, "f"*64, "123", 1))
                else:
                    raise AssertionError("unknown synthetic arm failure")
            if prior_terminal:
                # Seed only synthetic SQL metadata, never real recovery proof.
                seed = target.escrow.Escrow("a"*32,"synthetic",query=database.query)
                self.prior_receipt = seed._finalize(RUN,KEY,GEN,"8888888","b"*40,blob)
            if late_chunk_loss and not prior_terminal:
                original_finalize = escrow_client._finalize
                def finalized_then_lost(*args):
                    receipt = original_finalize(*args)
                    self.prior_receipt = receipt
                    lose_chunks()
                    return receipt
                escrow_client._finalize = finalized_then_lost
            if corrupt_chunk:
                original_query = escrow_client._query
                def corrupt(sql,params):
                    result = original_query(sql,params)
                    if sql == target.escrow.SQL["part"] and result.rows:
                        result.rows[0]["chunk_sha"] = "f"*64
                    return result
                escrow_client._query = corrupt
            self.last_terminal = escrow_client,database,native_state
            if durable_prepare:
                # Narrow prepare must not acquire later campaign/terminal powers.
                for name in ("attach", "arm", "_finalize", "_purge"):
                    setattr(escrow_client, name, mock.Mock(side_effect=AssertionError("forbidden prepare capability")))
                prepare_put, prepare_read = escrow_client.put, escrow_client.read
                def unpublished_put(*args):
                    self.assertFalse(target.prepared_file(RUN).exists())
                    return prepare_put(*args)
                def unpublished_read(*args):
                    self.assertFalse(target.prepared_file(RUN).exists())
                    return prepare_read(*args)
                escrow_client.put, escrow_client.read = unpublished_put, unpublished_read
            if preparation_failure:
                if preparation_failure == "lost-write":
                    original_put = escrow_client.put
                    def lost_put(*args):
                        original_put(*args)
                        raise manifest.ContractFailure("escrow_seal_unverified")
                    escrow_client.put = lost_put
                elif preparation_failure == "readback":
                    original_put = escrow_client.put
                    def sealed_then_changed(*args):
                        sealed = original_put(*args)
                        database.db.execute(f"UPDATE {target.escrow.PARENT} SET artifact_id='321' WHERE original_run=?", (RUN,))
                        database.db.commit()
                        return sealed
                    escrow_client.put = sealed_then_changed
                else:
                    raise AssertionError("unknown synthetic preparation failure")
            def dispatch_record(run,token,*,checkout_sha=None):
                if checkout_sha is None and original_missing:
                    raise manifest.ContractFailure("dispatch_provenance_unverified")
                return ({"head_sha":SHA,"status":"in_progress"} if checkout_sha is not None else
                        {"head_sha":original_record_sha or historical_sha,"status":original_status})
            with mock.patch.object(target, "environment", return_value=values), \
                    mock.patch.object(target, "checkout", return_value=SHA), \
                    mock.patch.dict(target.os.environ, {"GITHUB_RUN_ID": current}), \
                    mock.patch.object(target, "dispatch_record", side_effect=dispatch_record), \
                    mock.patch.object(target.provenance, "successful_source") as source, \
                    mock.patch.object(target.artifact, "Artifacts", return_value=artifacts), \
                    mock.patch.object(target, "Readback", return_value=reader), \
                    mock.patch.object(target.provenance, "Services", return_value=services) as service_factory, \
                    mock.patch.object(target.provenance.mail_pin, "run", return_value=privacy) as private, \
                    mock.patch.object(target.native, "native_account", observed_native), \
                    mock.patch.object(target.escrow,"Escrow",return_value=escrow_client) as escrow_factory, \
                    mock.patch.object(target,"ESCROW_GENERATION",GEN):
                if isinstance(privacy,list):
                    private.side_effect = privacy
                if scratch_failure:
                    remove = mock.patch.object(target.shutil,"rmtree",side_effect=OSError("synthetic private error"))
                    remove.start()
                try:
                    args = self.args(mode)
                    if durable_prepare:
                        args.artifact_id = ""
                        args.prior_run = ""
                        result = target.prepare_escrow(args)
                    elif durable_campaign:
                        args.prior_run = ""
                        result = target.campaign_escrow(args)
                    elif transport == "escrow":
                        args.artifact_id = ""
                        result = target.finalize_escrow_recovery(args)
                    else:
                        result = (target.finalize_recovery(args) if terminal else target.execute(args))
                finally:
                    if scratch_failure:
                        remove.stop()
                    if mode == "recover" or durable_prepare or arm_failure:
                        cli.add.assert_not_called()
                        cli.delete.assert_not_called()
                    self.assertLessEqual(escrow_factory.call_count,int(terminal or durable_prepare or durable_campaign))
                    if durable_prepare:
                        for name in ("attach", "arm", "_finalize", "_purge"):
                            getattr(escrow_client, name).assert_not_called()
                        escrow_client.read = prepare_read
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

    def test_dormant_durable_prepare_seals_exact_bytes_without_arming(self):
        """An upload file is exposed only after complete independent D1 authentication."""
        result, world, artifacts, privacy, cli = self.execute("prepare", durable_prepare=True)
        client, database, native_state = self.last_terminal
        with mock.patch.object(manifest, "_cipher", SyntheticAEAD):
            retained, blob = client.read(RUN, KEY, GEN)
        self.assertEqual(result, ("ten_address_escrow_prepared",))
        self.assertEqual(blob, target.prepared_file(RUN).read_bytes())
        self.assertEqual(retained["state"], "sealed")
        self.assertIsNone(retained["artifact_id"])
        self.assertIsNone(retained["armed_at"])
        self.assertIsNone(retained["cleanup_receipt_sha"])
        self.assertTrue(native_state["closed"])
        self.assertEqual(world.calls, [])
        cli.add.assert_not_called(); cli.delete.assert_not_called()
        artifacts.content.assert_not_called()

    def test_durable_prepare_ambiguous_write_or_drift_never_exposes_upload(self):
        """Retain provider evidence without file-only fallback or alias permissions."""
        for failure in ("lost-write", "readback"):
            with self.subTest(failure=failure):
                with self.assertRaises(manifest.ContractFailure):
                    self.execute("prepare", durable_prepare=True, preparation_failure=failure)
                client, database, native_state = self.last_terminal
                self.assertFalse(target.prepared_file(RUN).exists())
                self.assertEqual(client.parent(RUN)["state"], "sealed")
                self.assertIsNone(client.parent(RUN)["armed_at"])
                self.assertGreater(database.query(target.escrow.SQL["aggregate"], (RUN,)).rows[0]["bytes"], 0)

    def test_durable_prepare_corrupt_chunk_keeps_writing_evidence_without_upload(self):
        """Failed chunk authentication cannot become a seal, upload or mutation grant."""
        with self.assertRaises(manifest.ContractFailure):
            self.execute("prepare", durable_prepare=True, corrupt_chunk=True)
        client, database, native_state = self.last_terminal
        self.assertFalse(target.prepared_file(RUN).exists())
        self.assertEqual(client.parent(RUN)["state"], "writing")
        self.assertIsNone(client.parent(RUN)["armed_at"])

    def test_durable_prepare_rejects_campaign_recovery_and_attached_inputs(self):
        """Wrong phase/coordinates fail before reading private environment capabilities."""
        for mode in ("campaign", "recover", "prepare"):
            with self.subTest(mode=mode), mock.patch.object(target, "environment") as env:
                with self.assertRaisesRegex(manifest.ContractFailure, "quota_escrow_prepare_only"):
                    target.prepare_escrow(self.args(mode))
                env.assert_not_called()

    def test_durable_prepare_rejects_nonretained_generation(self):
        """Generation mismatch is rejected before provider or native account work."""
        with mock.patch.object(target, "environment", return_value={"AMAIL_TEN_ADDRESS_KEY_GENERATION": "other"}), \
                mock.patch.object(target, "checkout") as checkout:
            args = self.args("prepare")
            args.artifact_id = args.prior_run = ""
            with self.assertRaisesRegex(manifest.ContractFailure, "escrow_generation_unsupported"):
                target.prepare_escrow(args)
            checkout.assert_not_called()

    def test_durable_campaign_requires_known_arm_and_retains_complete_ciphertext(self):
        """Serial quota assertions do not substitute for independent terminal receipt."""
        result, world, artifacts, privacy, cli = self.execute("campaign", durable_campaign=True)
        client, database, native_state = self.last_terminal
        with mock.patch.object(manifest, "_cipher", SyntheticAEAD):
            retained, blob = client.read(RUN, KEY, GEN)
        self.assertEqual(result[-1], "ten_address_cleanup_verified")
        self.assertEqual(retained["state"], "armed")
        self.assertEqual(retained["artifact_id"], "123")
        self.assertIsNotNone(retained["armed_at"])
        self.assertIsNone(retained["cleanup_receipt_sha"])
        self.assertEqual(blob, artifacts.content.return_value)
        self.assertEqual(len(world.calls), 39)
        self.assertEqual(len(world.deletes), 10)

    def test_durable_campaign_lost_ack_already_armed_or_wrong_permit_never_mutates(self):
        """Readback and caller tokens cannot repair the current-invocation permission."""
        for failure in ("lost-ack", "already-armed", "wrong-permit"):
            with self.subTest(failure=failure):
                with self.assertRaises(manifest.ContractFailure):
                    self.execute("campaign", durable_campaign=True, arm_failure=failure)
                client, database, native_state = self.last_terminal
                self.assertIsNone(client.parent(RUN)["cleanup_receipt_sha"])
                self.assertGreater(database.query(target.escrow.SQL["aggregate"], (RUN,)).rows[0]["bytes"], 0)

    def test_durable_campaign_rejects_foreign_original_or_wrong_phase_before_credentials(self):
        """Only the present campaign may seek a new known arm acknowledgement."""
        for mode in ("prepare", "recover", "campaign"):
            with self.subTest(mode=mode), mock.patch.object(target, "environment") as env:
                with self.assertRaisesRegex(manifest.ContractFailure, "quota_escrow_campaign_only"):
                    target.campaign_escrow(self.args(mode))
                env.assert_not_called()

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

    def test_terminal_coordinator_accepts_ten_exact_settled_retired_tombstones(self):
        """Production cleanup keeps owner tombstones and old reconciliation scheduling metadata."""
        result,world,artifacts,privacy,cli = self.execute("recover",terminal=True,tombstones=True)
        self.assertEqual(result,("ten_address_terminal_receipt_verified",))
        self.assertEqual(len(world.snapshot.rows),10)
        self.assertEqual(world.snapshot.global_count,0)
        self.assertTrue(all(record["state"] == "retired" and record["next_reconcile_at"] == 123456789
                            for record in world.snapshot.rows.values()))
        self.assertEqual(world.calls,[])
        cli.add.assert_not_called(); cli.delete.assert_not_called()

    def test_post_teardown_unrelated_or_tombstone_drift_retains_ciphertext(self):
        """Read-only cleanup accepts legitimate tombstones but rejects changed baselines/ownership."""
        for kind in ("unrelated-row","unrelated-rule","tombstone-owner","tombstone-unsettled"):
            with self.subTest(kind=kind):
                with self.assertRaises(manifest.ContractFailure):
                    self.execute("recover",terminal=True,tombstones=True,final_drift=kind)
                client,database,native_state = self.last_terminal
                self.assertTrue(native_state["closed"])
                self.assertEqual(client.parent(RUN)["state"],"sealed")
                self.assertFalse(any(sql in (target.escrow.SQL["receipt"],target.escrow.SQL["purge"])
                                     for sql,params in database.calls))

    def test_explicit_d1_recovery_preserves_historical_sha_and_all_ciphertext(self):
        """Expired-artifact transport is deliberately absent; current verifier SHA stays distinct."""
        result,world,artifacts,privacy,cli = self.execute("recover",transport="escrow",
                                                       historical_sha="c"*40,tombstones=True)
        self.assertEqual(result,("ten_address_escrow_receipt_retained",))
        artifacts.content.assert_not_called()
        self.assertEqual(artifacts.binary.call_args.args[:2],("789",SHA))
        client,database,native_state = self.last_terminal
        retained = client.parent(RUN)
        self.assertEqual(retained["source_sha"],"c"*40)
        self.assertEqual(retained["cleanup_verifier_sha"],SHA)
        self.assertEqual(retained["cleanup_verifier_run"],"9999999")
        self.assertEqual(retained["artifact_id"],"123")
        self.assertEqual(retained["state"],"cleanup_verified")
        self.assertEqual(database.query(target.escrow.SQL["aggregate"],(RUN,)).rows[0]["n"],retained["chunk_count"])
        self.assertFalse(any(sql == target.escrow.SQL["purge"] for sql,params in database.calls))
        with mock.patch.object(manifest,"_cipher",SyntheticAEAD):
            self.assertEqual(client.read(RUN,KEY,GEN)[0],retained)
        cli.add.assert_not_called(); cli.delete.assert_not_called()

    def test_d1_transport_rejects_unknown_original_or_generation_and_ciphertext(self):
        """Independent original identity and exact full encrypted content cannot be replaced."""
        for options in ({"original_status":"in_progress"},{"same_run":True},
                        {"original_record_sha":"d"*40},{"selected_generation":"other-generation"},
                        {"selected_key":"cd"*32},{"original_missing":True},
                        {"corrupt_chunk":True},{"active_recovery":True}):
            with self.subTest(options=options):
                with self.assertRaises(manifest.ContractFailure):
                    self.execute("recover",transport="escrow",**options)
                client,database,native_state = self.last_terminal
                self.assertEqual(client.parent(RUN)["state"],"sealed")
                self.assertFalse(any(sql in (target.escrow.SQL["receipt"],target.escrow.SQL["purge"])
                                     for sql,params in database.calls))

    def test_d1_terminal_resume_reauthenticates_full_ciphertext_without_rewriting_receipt(self):
        """Historical terminal metadata still requires fresh recovery and final retained bytes."""
        result,world,artifacts,privacy,cli = self.execute("recover",transport="escrow",prior_terminal=True,tombstones=True)
        client,database,native_state = self.last_terminal
        self.assertEqual(result,("ten_address_escrow_receipt_retained",))
        self.assertEqual(client.parent(RUN),self.prior_receipt)
        self.assertEqual(client.parent(RUN)["cleanup_verifier_run"],"8888888")
        self.assertEqual(sum(sql == target.escrow.SQL["receipt"] for sql,params in database.calls),1)
        self.assertFalse(any(sql == target.escrow.SQL["purge"] for sql,params in database.calls))
        self.assertTrue(native_state["closed"])
        artifacts.content.assert_not_called()
        cli.add.assert_not_called(); cli.delete.assert_not_called()

    def test_d1_terminal_late_zero_or_partial_loss_cannot_claim_ciphertext_retained(self):
        """Receipt-gated storage loss after initial readback is rejected at the final boundary."""
        for prior,loss in ((True,"zero"),(True,"partial"),(False,"zero"),(False,"partial")):
            with self.subTest(prior=prior,loss=loss):
                with self.assertRaisesRegex(manifest.ContractFailure,"escrow_chunks_incomplete"):
                    self.execute("recover",transport="escrow",prior_terminal=prior,late_chunk_loss=loss)
                client,database,native_state = self.last_terminal
                self.assertTrue(native_state["closed"])
                self.assertEqual(client.parent(RUN),self.prior_receipt)
                self.assertEqual(sum(sql == target.escrow.SQL["receipt"] for sql,params in database.calls),1)
                self.assertFalse(any(sql == target.escrow.SQL["purge"] for sql,params in database.calls))
                chunks = database.query(target.escrow.SQL["aggregate"],(RUN,)).rows[0]["n"]
                self.assertEqual(chunks,0 if loss == "zero" else self.prior_receipt["chunk_count"]-1)

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

    def test_explicit_escrow_seam_cannot_be_campaign_or_artifact_fallback(self):
        """No existing artifact-ID input or mutation phase can select D1 transport."""
        for args in (argparse.Namespace(mode="campaign",artifact_id=""),
                     argparse.Namespace(mode="recover",artifact_id="123")):
            with mock.patch.object(target,"environment") as environment:
                with self.assertRaisesRegex(manifest.ContractFailure,"quota_escrow_recovery_only"):
                    target.finalize_escrow_recovery(args)
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
