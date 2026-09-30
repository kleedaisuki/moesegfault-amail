"""Hosted-only synthetic quota controller contracts; no live services or CLI."""

from dataclasses import replace
import copy
import json
import unittest
from unittest import mock

import staging_ten_address_hosted as target
import staging_ten_address_manifest as manifest
from test_staging_ten_address_manifest import KEY, RUN, GEN, OWNER, plan, row, rule, SyntheticAEAD

VERSION = "00000000-0000-0000-0000-000000000001"


def evidence():
    """Construct explicit synthetic reviewed-wrapper observations."""
    return target.Evidence("workflow_dispatch", manifest.BRANCH, manifest.REPOSITORY,
                           "staging", "RUN_STAGING_TEN_ADDRESSES", RUN, "1", "a" * 40,
                           "a" * 40, "success", "b" * 40, "success", "synthetic-a", OWNER,
                           "synthetic-username", "synthetic-username", OWNER, VERSION, VERSION,
                           "synthetic-identity", "synthetic-login",
                           ("amail-mail-staging", "amail-inbound-staging", manifest.DOMAIN,
                            manifest.ISSUER), "held")


def rejected(code="reserved_or_invalid_name", status=409):
    """Match actual CLI diagnostic format without provider data."""
    return target.CliResult(1, b"", (f"amail: mail API addresses.add failed: HTTP {status}, "
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
        """Missing evidence, same subject and retried campaigns never reach add."""
        changes = [dict(event="push"), dict(branch="refs/heads/main"), dict(attempt="2"),
                   dict(environment="production"), dict(confirm=""),
                   dict(source_ci_sha="b" * 40), dict(source_ci_conclusion="failure"),
                   dict(isolation_sha=""), dict(isolation_conclusion="failure"),
                   dict(isolation_mail_version="foreign"), dict(owner_a=OWNER),
                   dict(pkce_owner="foreign"), dict(verified_b_username="foreign"),
                   dict(identity_revision=""), dict(bindings=()), dict(sending_state="open")]
        for change in changes:
            with self.subTest(change=change):
                world = World()
                with self.assertRaises(manifest.ContractFailure):
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
            for identifier, downloaded in [("", blob), ("123", blob[:-1] + b"x")]:
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
