"""Hosted-only synthetic quota controller contracts; no live services or CLI."""

from dataclasses import replace
import copy
import json
import unittest
from unittest import mock

import staging_ten_address_hosted as target
import staging_ten_address_manifest as manifest
from test_staging_ten_address_manifest import KEY, RUN, GEN, OWNER, plan, row, rule, SyntheticAEAD, provenance

VERSION = "00000000-0000-0000-0000-000000000001"


def evidence():
    """Construct explicit synthetic reviewed-wrapper observations."""
    return target.Evidence("workflow_dispatch", manifest.BRANCH, manifest.REPOSITORY,
                           "staging", "RUN_STAGING_TEN_ADDRESSES", RUN, "1", "a" * 40,
                           "a" * 40, "success", OWNER, "synthetic_username",
                           "synthetic_username", OWNER, VERSION,
                           provenance()["identity_revision"], provenance()["login_revision"],
                           ("amail-mail-staging", "amail-inbound-staging", manifest.DOMAIN,
                            manifest.ISSUER), "held")


def rejected(code="reserved_or_invalid_name", status=409):
    """Match actual CLI diagnostic format without provider data."""
    reason = {409: "Conflict", 403: "Forbidden", 500: "Internal Server Error"}.get(status, "Unknown")
    return target.CliResult(1, b"", (f"amail: mail API addresses.add failed: HTTP {status} {reason}, "
                                  f"code={code}, correlation_id=none\n").encode())


class World:
    """In-memory synthetic adapter with bounded exact tombstone retirement."""

    def __init__(self):
        """Use no credentials, provider requests, files or subprocesses."""
        self.snapshot = manifest.Snapshot({}, [], 0)
        self.calls = []
        self.deletes = []
        self.version = VERSION
        self.behavior = None
        self.empty = True

    def read(self):
        """Return isolated snapshots so count-preserving comparisons are useful."""
        return copy.deepcopy(self.snapshot)

    def owned(self):
        """Include all live synthetic B rows."""
        return {a for a, r in self.snapshot.rows.items()
                if r["owner_sub"] == OWNER and r["state"] != "retired"}

    def create(self, part):
        """Materialize one exact row/rule as the real add might have done."""
        address = f"{part.lower()}@{manifest.DOMAIN}"
        identity = f"synthetic-{len(self.calls)}"
        self.snapshot.rows[address] = row(saved=identity, local_part=part.lower(),
                                          slot=min(len(self.owned()), 9))
        self.snapshot.rules.append(rule(address, identity))
        self.snapshot = manifest.Snapshot(self.snapshot.rows, self.snapshot.rules,
                                           self.snapshot.global_count + 1)
        return target.CliResult(0, json.dumps({"address": address, "state": "active"}).encode(), b"")

    def add(self, part):
        """Record every submission before the possible side effect/exception."""
        self.calls.append(part)
        if self.behavior is not None:
            result = self.behavior(part)
            if result is not None:
                return result
        if part.lower() in manifest.RESERVED:
            return rejected()
        if len(self.owned()) == 10:
            return rejected("address_limit")
        return self.create(part)

    def delete(self, address):
        """Retire the exact owner row once; never delete preexisting baselines."""
        self.deletes.append(address)
        saved = self.snapshot.rows[address]
        saved.update(state="retired", cf_rule_id=None, needs_reconcile=0)
        rules = [r for r in self.snapshot.rules if r["address"] != address]
        self.snapshot = manifest.Snapshot(self.snapshot.rows, rules, self.snapshot.global_count - 1)

    def adapter(self):
        """Expose only the explicitly declared synthetic capabilities."""
        return target.Adapter(self.read, self.owned, self.add, self.delete, self.read,
                              lambda: self.version, lambda resources: self.empty)


class HostedTests(unittest.TestCase):
    """Exercise campaign safety and privacy, not deployment acceptance."""

    def run_campaign(self, world, **changes):
        """Authenticate a synthetic envelope before exercising the controller."""
        value = plan()
        with mock.patch.object(manifest, "_cipher", SyntheticAEAD):
            blob = manifest.seal(value, KEY, RUN, GEN)
            return target.campaign(replace(evidence(), **changes), blob, blob, "123", KEY,
                                   GEN, 1001, world.adapter())

    def test_escrow_attach_arm_order_follows_complete_admission_before_first_add(self):
        """Real synthetic SQL ACK is required; no purge/finalize occurs in campaign."""
        from test_staging_ten_address_escrow import Database
        database = Database()
        self.addCleanup(database.db.close)
        world = World()
        events = []
        with mock.patch.object(manifest, "_cipher", SyntheticAEAD):
            blob = manifest.seal(plan(), KEY, RUN, GEN)
            client = target.escrow.Escrow("a"*32, "synthetic", query=database.query)
            client.put(blob, KEY, RUN, GEN)
            attach, arm, add = client.attach, client.arm, world.add
            def attached(*args):
                self.assertEqual(world.calls, [])
                events.append("attach")
                return attach(*args)
            def armed(*args):
                self.assertEqual(events, ["attach"])
                self.assertEqual(world.calls, [])
                events.append("arm")
                return arm(*args)
            def added(part):
                self.assertEqual(events[:2], ["attach", "arm"])
                self.assertEqual(client.parent(RUN)["state"], "armed")
                events.append("add")
                return add(part)
            client.attach, client.arm, world.add = attached, armed, added
            adapter = world.adapter()
            with mock.patch.object(client, "_purge") as purge, mock.patch.object(client, "_finalize") as finalize:
                labels = target.campaign_escrow(evidence(), blob, blob, "123", KEY, GEN,
                                                1001, adapter, client)
                purge.assert_not_called(); finalize.assert_not_called()
            self.assertEqual(labels[-1], "ten_address_cleanup_verified")
            self.assertEqual(events[:3], ["attach", "arm", "add"])
            self.assertEqual(client.read(RUN, KEY, GEN)[1], blob)

    def test_escrow_admission_or_attachment_failure_never_arms_or_cleans_addresses(self):
        """Neither missing durable evidence nor artifact attach ambiguity grants finally."""
        for failure in ("read", "attach"):
            with self.subTest(failure=failure), mock.patch.object(manifest, "_cipher", SyntheticAEAD):
                blob = manifest.seal(plan(), KEY, RUN, GEN)
                world = World()
                client = mock.Mock()
                client.read.return_value = ({"state":"sealed", "armed_at":None,
                                            "cleanup_receipt_sha":None}, blob)
                getattr(client, failure).side_effect = manifest.ContractFailure("synthetic_failure")
                with self.assertRaises(manifest.ContractFailure):
                    target.campaign_escrow(evidence(), blob, blob, "123", KEY, GEN,
                                           1001, world.adapter(), client)
                client.arm.assert_not_called()
                self.assertEqual(world.calls, [])
                self.assertEqual(world.deletes, [])

    def test_escrow_attachment_drift_rechecks_all_admission_before_arm(self):
        """Attach success cannot mask changed global, owner, serving or storage evidence."""
        from test_staging_ten_address_escrow import Database
        for drift in ("global", "owner", "serving", "storage"):
            with self.subTest(drift=drift), mock.patch.object(manifest, "_cipher", SyntheticAEAD):
                database = Database()
                self.addCleanup(database.db.close)
                world = World()
                blob = manifest.seal(plan(), KEY, RUN, GEN)
                client = target.escrow.Escrow("a"*32, "synthetic", query=database.query)
                client.put(blob, KEY, RUN, GEN)
                attach = client.attach
                adapter = world.adapter()
                def attached_then_drifted(*args):
                    attach(*args)
                    if drift == "global":
                        world.snapshot = manifest.Snapshot({"foreign@example.test": row(owner="foreign",
                            saved="foreign-rule", local_part="foreign", created=1)},
                            [rule("foreign@example.test", "foreign-rule")], 1)
                    elif drift == "owner":
                        adapter.list_owned = lambda: {"foreign@example.test"}
                    elif drift == "serving":
                        world.version = "00000000-0000-0000-0000-000000000099"
                    else:
                        world.empty = False
                client.attach = attached_then_drifted
                with mock.patch.object(client, "arm", wraps=client.arm) as arm:
                    with self.assertRaises(manifest.ContractFailure):
                        target.campaign_escrow(evidence(), blob, blob, "123", KEY, GEN,
                                               1001, adapter, client)
                    arm.assert_not_called()
                self.assertEqual(world.calls, [])
                self.assertEqual(world.deletes, [])
                retained, actual = client.read(RUN, KEY, GEN)
                self.assertEqual(retained["state"], "sealed")
                self.assertEqual(retained["artifact_id"], "123")
                self.assertIsNone(retained["armed_at"])
                self.assertEqual(actual, blob)

    def test_escrow_arm_zero_change_never_grants_controller_mutation_or_cleanup(self):
        """Even an armed readback cannot repair a zero-change current-invocation ACK."""
        from test_staging_ten_address_escrow import Database
        for committed in (False, True):
            with self.subTest(committed=committed), mock.patch.object(manifest, "_cipher", SyntheticAEAD):
                database = Database()
                self.addCleanup(database.db.close)
                world = World()
                blob = manifest.seal(plan(), KEY, RUN, GEN)
                arm_calls = []
                def zero_arm(sql, params):
                    if sql == target.escrow.SQL["arm"]:
                        arm_calls.append(params)
                        if committed:
                            database.query(sql, params)
                        return target.escrow.Result([], 0)
                    return database.query(sql, params)
                client = target.escrow.Escrow("a"*32, "synthetic", query=zero_arm)
                client.put(blob, KEY, RUN, GEN)
                with self.assertRaisesRegex(manifest.ContractFailure, "escrow_arm_ack_unverified"):
                    target.campaign_escrow(evidence(), blob, blob, "123", KEY, GEN,
                                           1001, world.adapter(), client)
                self.assertEqual(len(arm_calls), 1)
                self.assertEqual(world.calls, [])
                self.assertEqual(world.deletes, [])
                retained, actual = client.read(RUN, KEY, GEN)
                self.assertEqual(retained["state"], "armed" if committed else "sealed")
                self.assertIsNone(retained["cleanup_receipt_sha"])
                self.assertEqual(actual, blob)

    def test_ten_serial_reserved_and_exact_cleanup(self):
        """Ten simultaneous active routes and exact quota denial precede cleanup."""
        world = World()
        labels = self.run_campaign(world)
        self.assertEqual(labels, ("ten_address_reserved_verified", "ten_address_limit_verified",
                                  "ten_address_cleanup_verified"))
        self.assertEqual(world.calls[:28], manifest.submissions())
        self.assertEqual(len(world.calls), 39)
        self.assertEqual(len(set(world.deletes)), 10)
        self.assertEqual(world.snapshot.global_count, 0)
        self.assertTrue(all(r["state"] == "retired" for r in world.snapshot.rows.values()))

    def test_execution_and_provenance_gates_no_mutation(self):
        """Missing evidence, wrong subject and retried campaigns never reach add."""
        changes = [dict(event="push"), dict(branch="refs/heads/main"), dict(attempt="2"),
                   dict(environment="production"), dict(confirm=""),
                   dict(source_ci_sha="b" * 40), dict(source_ci_conclusion="failure"),
                   dict(owner=""), dict(pkce_owner="foreign"), dict(verified_username="foreign"),
                   dict(identity_revision=""), dict(bindings=()), dict(sending_state="open")]
        for change in changes:
            with self.subTest(change=change):
                world = World()
                with self.assertRaises(manifest.ContractFailure):
                    self.run_campaign(world, **change)
                self.assertEqual(world.calls, [])

    def test_single_account_needs_no_second_owner_or_isolation_run(self):
        """Quota and reserved boundaries cannot be mistaken for isolation proof."""
        value = evidence()
        value.validate()
        self.assertNotIn("isolation_sha", vars(value))
        self.assertNotIn("owner_b", vars(value))
        self.assertEqual(value.provenance(), provenance())

    def test_changed_authenticated_username_or_revisions_prevents_mutation(self):
        """Even individually valid observations must match uploaded ciphertext."""
        for change in (dict(identity_revision="00000000-0000-0000-0000-000000000009"),
                       dict(login_revision="00000000-0000-0000-0000-000000000009"),
                       dict(verified_username="another_username", expected_username="another_username")):
            world = World()
            with self.assertRaisesRegex(manifest.ContractFailure, "campaign_manifest_mismatch"):
                self.run_campaign(world, **change)
            self.assertEqual(world.calls, [])

    def test_exact_negative_oracle(self):
        """Status, stdout, typed code, and one diagnostic line are all material."""
        target.negative(rejected(), "reserved_or_invalid_name")
        for value in [rejected(status=403), rejected("http_error"), rejected("address_limit"),
                      target.CliResult(0, b"", rejected().stderr),
                      target.CliResult(1, b"{}", rejected().stderr),
                      target.CliResult(1, b"", b"HTTP 409 code=reserved_or_invalid_name"),
                      target.CliResult(1, b"", rejected().stderr + b"secret\n")]:
            with self.assertRaisesRegex(manifest.ContractFailure, "negative_cli_mismatch"):
                target.negative(value, "reserved_or_invalid_name")

    def test_real_cli_reason_phrase_and_diagnostics(self):
        """Accept actual reqwest status display and source-owned diagnostic grammar."""
        for code in ("address_limit", "reserved_or_invalid_name"):
            result = rejected(code)
            self.assertIn(b"HTTP 409 Conflict,", result.stderr)
            target.negative(result, code)
            target.negative(target.CliResult(1, b"", result.stderr.replace(
                b"409 Conflict,", b"409,")), code)
            with_diag = result.stderr.replace(b"correlation_id=none\n",
                b"correlation_id=00000000-0000-0000-0000-000000000001, diag=v1:input:none:0:0\r\n")
            target.negative(target.CliResult(1, b"", with_diag), code)

    def test_error_bodies_and_other_statuses_never_pass(self):
        """No provider body, invalid reason or duplicated status/code is an oracle."""
        good = rejected().stderr
        bodies = [rejected(status=500).stderr, rejected(status=403).stderr,
                  good.replace(b"409 Conflict", b"409 Forbidden"),
                  good.replace(b"409 Conflict", b"4090 Conflict"),
                  good.replace(b"reserved_or_invalid_name", b"reserved_or_invalid_name_extra"),
                  good.rstrip() + b', response={"status":409,"secret":"private"}\n',
                  good + b'<html>HTTP 409 Conflict private</html>\n',
                  good.rstrip() + b', cf_error=1101\n',
                  good.rstrip() + b', diag=v1:input:none:099:0\n',
                  b'{"code":"reserved_or_invalid_name","status":409}\n',
                  good + good]
        for body in bodies:
            with self.assertRaisesRegex(manifest.ContractFailure, "^negative_cli_mismatch$"):
                target.negative(target.CliResult(1, b"", body), "reserved_or_invalid_name")

    def test_reserved_success_reconciles_entire_manifest(self):
        """Unexpected successful ADMIN is deleted only when exactly owned."""
        world = World()
        world.behavior = lambda part: world.create(part) if part == "admin" else None
        with self.assertRaisesRegex(manifest.ContractFailure, "ten_address_mutation_ambiguous"):
            self.run_campaign(world)
        self.assertEqual(world.calls, ["admin"])
        self.assertEqual(len(world.deletes), 1)
        self.assertEqual(world.snapshot.global_count, 0)

    def test_rejected_reserved_with_side_effect_is_not_pass(self):
        """Matching 409 cannot hide a newly created reserved resource."""
        world = World()
        def bad(part):
            """Simulate a server regression returning denial after allocation."""
            world.create(part)
            return rejected()
        world.behavior = bad
        with self.assertRaisesRegex(manifest.ContractFailure, "ten_address_mutation_ambiguous"):
            self.run_campaign(world)
        self.assertEqual(len(world.calls), 1)
        self.assertEqual(len(world.deletes), 1)

    def test_timeout_after_create_never_replays_add(self):
        """An ambiguous first accepted add is cleaned from complete intent."""
        world = World()
        def timeout(part):
            """Create once before a synthetic lost response."""
            if part.startswith("qt0-"):
                world.create(part)
                raise TimeoutError("private synthetic secret")
            return None
        world.behavior = timeout
        with self.assertRaisesRegex(manifest.ContractFailure, "^ten_address_mutation_ambiguous$"):
            self.run_campaign(world)
        self.assertEqual(len(world.calls), 29)
        self.assertEqual(len(world.deletes), 1)

    def test_eleventh_success_is_cleaned_not_quota_pass(self):
        """Full manifest includes the rejected-request candidate before add."""
        world = World()
        world.behavior = lambda part: world.create(part) if part.startswith("qt10-") else None
        with self.assertRaisesRegex(manifest.ContractFailure, "ten_address_mutation_ambiguous"):
            self.run_campaign(world)
        self.assertEqual(len(world.deletes), 11)

    def test_capacity_exhausted_is_not_owner_quota(self):
        """Global capacity denial never masquerades as the ten-slot oracle."""
        world = World()
        world.behavior = lambda part: rejected("capacity_exhausted") if part.startswith("qt10-") else None
        with self.assertRaisesRegex(manifest.ContractFailure, "ten_address_mutation_ambiguous"):
            self.run_campaign(world)
        self.assertEqual(len(world.deletes), 10)

    def test_cleanup_ambiguity_fails_without_delete_replay(self):
        """Lost delete response stops exact cleanup and leaves recovery required."""
        world = World()
        adapter = world.adapter()
        def broken(address):
            """Simulate uncertain transport with no retry."""
            world.deletes.append(address)
            raise TimeoutError("private")
        adapter.delete = broken
        with mock.patch.object(world, "adapter", return_value=adapter):
            with self.assertRaisesRegex(manifest.ContractFailure, "^ten_address_cleanup_required$"):
                self.run_campaign(world)
        self.assertEqual(len(world.deletes), 1)

    def test_async_delete_202_waits_for_cron_without_replay(self):
        """Realistic retired+needs=1 is polled before the next exact DELETE."""
        world = World()
        pending = {}
        adapter = world.adapter()
        observations = []

        def asynchronous_delete(address):
            """Return as HTTP 202 while route removal awaits synthetic Cron."""
            self.assertEqual(pending, {})
            world.deletes.append(address)
            world.snapshot.rows[address].update(state="retired", cf_rule_id=None,
                                                needs_reconcile=1)
            world.snapshot = manifest.Snapshot(world.snapshot.rows, world.snapshot.rules,
                                               world.snapshot.global_count - 1)
            pending[address] = 3

        def cron_read():
            """Only repeated reads advance the synthetic route retirement."""
            for address in list(pending):
                observations.append(world.snapshot.rows[address]["needs_reconcile"])
                pending[address] -= 1
                if pending[address] == 0:
                    world.snapshot.rows[address]["needs_reconcile"] = 0
                    world.snapshot.rules[:] = [r for r in world.snapshot.rules
                                                if r["address"] != address]
                    del pending[address]
            return world.read()

        adapter.read = cron_read
        adapter.delete = asynchronous_delete
        with mock.patch.object(world, "adapter", return_value=adapter), \
                mock.patch.object(target.time, "sleep") as sleep:
            self.assertEqual(len(self.run_campaign(world)), 3)
        self.assertEqual(len(world.deletes), 10)
        self.assertEqual(len(set(world.deletes)), 10)
        self.assertEqual(len(observations), 30)
        self.assertEqual(sleep.call_count, 20)
        self.assertEqual(pending, {})

    def test_async_retirement_timeout_requires_recovery_no_replay(self):
        """Bounded read-only waiting does not turn a stuck Cron into a pass."""
        world = World()
        adapter = world.adapter()

        def never_settles(address):
            """Retire D1 once but leave provider cleanup pending indefinitely."""
            world.deletes.append(address)
            world.snapshot.rows[address].update(state="retired", cf_rule_id=None,
                                                needs_reconcile=1)
            world.snapshot = manifest.Snapshot(world.snapshot.rows, world.snapshot.rules,
                                               world.snapshot.global_count - 1)

        adapter.delete = never_settles
        with mock.patch.object(world, "adapter", return_value=adapter), \
                mock.patch.object(target.time, "monotonic", side_effect=[0, 361]):
            with self.assertRaisesRegex(manifest.ContractFailure, "^ten_address_cleanup_required$"):
                self.run_campaign(world)
        self.assertEqual(len(world.deletes), 1)

    def test_recovery_of_prior_delete_202_only_polls(self):
        """Interrupted DELETE 202 is settled rather than submitted again."""
        world = World()
        address = plan()["allowed"][0]
        world.snapshot.rows[address] = row(state="retired", reconcile=1,
                                           local_part=address.split("@", 1)[0])
        adapter = world.adapter()
        reads = []

        def settles():
            """Complete previous retirement on the third read-only snapshot."""
            reads.append(True)
            if len(reads) == 3:
                world.snapshot.rows[address]["needs_reconcile"] = 0
            return world.read()

        adapter.read = settles
        with mock.patch.object(target.time, "sleep"):
            target.recover(plan(), KEY, GEN, OWNER, adapter)
        self.assertGreaterEqual(len(reads), 3)
        self.assertEqual(world.deletes, [])

    def test_cross_run_pretransition_crash_never_replays_delete(self):
        """Active/pending rows cannot distinguish unsent from lost DELETEs."""
        for state in ("active", "pending", "provisioning"):
            with self.subTest(state=state):
                world = World()
                address = plan()["allowed"][0]
                world.create(address.split("@", 1)[0])
                world.snapshot.rows[address]["state"] = state
                with self.assertRaisesRegex(manifest.ContractFailure,
                                            "^recovery_manual_intervention_required$"):
                    target.recover(plan(), KEY, GEN, OWNER, world.adapter())
                self.assertEqual(world.deletes, [])
                self.assertEqual(world.calls, [])

    def test_reentered_campaign_does_not_grant_cleanup_permission(self):
        """A failed empty-baseline gate must not enter mutating finally."""
        world = World()
        address = plan()["allowed"][0]
        world.create(address.split("@", 1)[0])
        with self.assertRaises(manifest.ContractFailure):
            self.run_campaign(world)
        self.assertEqual(world.calls, [])
        self.assertEqual(world.deletes, [])

    def test_cross_run_posttransition_crash_settles_read_only(self):
        """A deleting journal transition is owned by Cron, never a second send."""
        world = World()
        address = plan()["allowed"][0]
        world.create(address.split("@", 1)[0])
        world.snapshot.rows[address]["state"] = "deleting"
        adapter = world.adapter()
        reads = []

        def cron_read():
            """Complete the prior D1/provider transition without CLI mutation."""
            reads.append(True)
            if len(reads) == 3:
                world.snapshot.rows[address].update(state="retired", cf_rule_id=None,
                                                    needs_reconcile=0)
                world.snapshot.rules.clear()
                world.snapshot = manifest.Snapshot(world.snapshot.rows, [], 0)
            return world.read()

        adapter.read = cron_read
        with mock.patch.object(target.time, "sleep"):
            target.recover(plan(), KEY, GEN, OWNER, adapter)
        self.assertGreaterEqual(len(reads), 3)
        self.assertEqual(world.deletes, [])

    def test_cross_run_partial_cleanup_settles_then_requires_manual(self):
        """Existing retirement is settled even when another live row is ambiguous."""
        world = World()
        live, pending = plan()["allowed"][:2]
        world.create(live.split("@", 1)[0])
        world.snapshot.rows[pending] = row(state="retired", reconcile=1,
                                           local_part=pending.split("@", 1)[0])
        adapter = world.adapter()
        reads = []

        def cron_read():
            """Settle only the already submitted retirement."""
            reads.append(True)
            if len(reads) == 3:
                world.snapshot.rows[pending]["needs_reconcile"] = 0
            return world.read()

        adapter.read = cron_read
        with mock.patch.object(target.time, "sleep"):
            with self.assertRaisesRegex(manifest.ContractFailure,
                                        "^recovery_manual_intervention_required$"):
                target.recover(plan(), KEY, GEN, OWNER, adapter)
        self.assertEqual(world.snapshot.rows[pending]["needs_reconcile"], 0)
        self.assertEqual(world.deletes, [])

    def test_pin_and_storage_fail_closed(self):
        """Foreign serving state and unexpected mail/storage cannot pass."""
        for kind in ("pin", "storage"):
            world = World()
            if kind == "pin":
                world.version = "foreign"
            else:
                world.empty = False
            with self.assertRaises(manifest.ContractFailure):
                self.run_campaign(world)
            self.assertEqual(world.calls, [])

    def test_missing_or_tampered_artifact_before_mutation(self):
        """Durability confirmation cannot be faked by upload success alone."""
        world = World()
        with mock.patch.object(manifest, "_cipher", SyntheticAEAD):
            blob = manifest.seal(plan(), KEY, RUN, GEN)
            # A constant replacement can equal the random tag byte; XOR always changes it.
            tampered = blob[:-1] + bytes([blob[-1] ^ 1])
            self.assertNotEqual(blob, tampered)
            for identifier, downloaded in [("", blob), ("123", tampered)]:
                with self.assertRaises(manifest.ContractFailure):
                    target.campaign(evidence(), blob, downloaded, identifier, KEY, GEN,
                                    1001, world.adapter())
        self.assertEqual(world.calls, [])

    def test_cancellation_executes_finally_cleanup(self):
        """Cooperative cancellation cleans; hard process kill needs external recovery."""
        world = World()
        def interrupted(part):
            """Interrupt after creating the first allowed route."""
            if part.startswith("qt0-"):
                world.create(part)
                raise KeyboardInterrupt()
            return None
        world.behavior = interrupted
        with self.assertRaises(KeyboardInterrupt):
            self.run_campaign(world)
        self.assertEqual(len(world.deletes), 1)

    def test_prepare_uses_no_mutator(self):
        """Preflight sealing is separate from artifact upload and mutation."""
        world = World()
        with mock.patch.object(manifest, "_cipher", SyntheticAEAD):
            prepared, sealed = target.prepare(evidence(), KEY, GEN, 1000, world.adapter())
            self.assertEqual(manifest.open_manifest(sealed, KEY, RUN, GEN), prepared)
        self.assertEqual(world.calls, [])

    def test_ingress_oracle_matches_staging_configuration(self):
        """Do not repeat the old ingress/inbound name mismatch in fixtures."""
        from pathlib import Path
        import tomllib
        config = tomllib.loads((Path(__file__).resolve().parents[2] /
                               "crates/mail-worker/wrangler.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["env"]["staging"]["vars"]["EMAIL_INGRESS_WORKER_NAME"],
                         rule("synthetic@" + manifest.DOMAIN)["worker"])
