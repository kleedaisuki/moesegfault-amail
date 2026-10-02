"""Focused staging adapter contracts, fail-closed provisioning and submit safety."""
from copy import deepcopy
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import check_staging_adapters as check
import inspect_staging as inspector
import deploy_staging_adapter as deploy
import ensure_email_events as events

VERSION = "12345678-1234-1234-1234-123456789abc"
ACCOUNT = "07109e406d4e1ab7a0997dd399db6fd5"
QUEUE_ID, DLQ_ID = "b" * 32, "c" * 32
ENV = {"CLOUDFLARE_ACCOUNT_ID": ACCOUNT, "CLOUDFLARE_API_TOKEN": "private-token"}


def lifecycle():
    """Return a complete queue inventory, exact reader and one domain subscription."""
    catalog = [{"queue_id": QUEUE_ID, "queue_name": check.QUEUE},
               {"queue_id": DLQ_ID, "queue_name": check.DLQ}]
    consumer = {"type": "worker", "script_name": check.EVENTS_WORKER,
                "dead_letter_queue": check.DLQ, "settings": {"batch_size": 10,
                    "max_wait_time_ms": 5000, "max_retries": 5, "retry_delay": 120}}
    details = {QUEUE_ID: {**catalog[0], "consumers": [consumer], "consumers_total_count": 1,
                         "producers": [], "producers_total_count": 0},
               DLQ_ID: {**catalog[1], "consumers": [], "consumers_total_count": 0,
                        "producers": [], "producers_total_count": 0}}
    subscriptions = [{"id": VERSION, "name": "amail-sending-lifecycle-staging", "enabled": True,
        "source": {"type": "email.sending", "zone_id": check.ZONE, "domain": check.DOMAIN},
        "destination": {"type": "queues.queue", "queue_id": QUEUE_ID},
        "events": events.EVENTS.split(",")}]
    return catalog, details, subscriptions


class ProvisioningTests(unittest.TestCase):
    """A failed read cannot authorize queue creation in either realm."""

    @patch.dict(os.environ, ENV)
    def test_failed_inventory_never_creates(self):
        with patch.object(events.queues, "inventory", side_effect=ValueError("unavailable")), patch.object(events, "run") as run:
            with self.assertRaises(ValueError):
                events.ensure_queue(check.QUEUE)
            run.assert_not_called()

    @patch.dict(os.environ, ENV)
    def test_exact_name_presence_and_absence(self):
        catalog, _, _ = lifecycle()
        with patch.object(events.queues, "inventory", return_value=catalog), patch.object(events, "run") as run:
            events.ensure_queue(check.QUEUE)
            run.assert_not_called()
        with patch.object(events.queues, "inventory", return_value=[]), patch.object(events, "run") as run:
            events.ensure_queue(check.QUEUE)
            run.assert_called_once_with("create", check.QUEUE)


class AdapterTests(unittest.TestCase):
    """Exact capabilities, topology and serving brackets reject tempting shortcuts."""

    def test_current_source_and_exact_service(self):
        configs = check.source_configs()
        expected = check.expected_bindings(configs, check.INGRESS)
        rows = [{"name": key, "type": kind, **({"text": value} if kind == "plain_text" else
                {"service": value} if kind == "service" else {})} for key, (kind, value) in expected.items()]
        value = {"id": VERSION, "resources": {"bindings": rows}}
        self.assertTrue(check.bindings_match(value, VERSION, expected))
        rows[1]["service"] = "amail-mail"
        self.assertFalse(check.bindings_match(value, VERSION, expected))
        rows[1]["service"] = "amail-mail-staging"
        rows.append({"name": "EXTRA", "type": "secret_text"})
        self.assertFalse(check.bindings_match(value, VERSION, expected))

    def test_inspector_preserves_exact_observed_adapter_pins_and_safe_failure(self):
        """Diagnosing a live failure neither adopts resources nor relaxes verification."""
        snapshot = {"scripts": {check.INGRESS: {"version": VERSION}, check.EVENTS_WORKER: {"version": VERSION}}}
        with patch.object(check, "verify", side_effect=ValueError("adapter_consumer_unverified")) as verify, \
             patch.object(check, "diagnostic_facts", return_value={"sourceaccount_match": True}):
            result = inspector.adapter_diagnostic(snapshot)
        verify.assert_called_once_with(VERSION, VERSION)
        self.assertEqual(result, {"exact_graph": False, "reason": "adapter_consumer_unverified",
                                  "facts": {"sourceaccount_match": True}})

    def snapshot(self, details=None, subscriptions=None):
        """Exercise real topology predicates with fixture provider reads only."""
        catalog, initial, initial_subscriptions = lifecycle()
        details = initial if details is None else details
        subscriptions = initial_subscriptions if subscriptions is None else subscriptions
        with patch.object(check.queues, "inventory", return_value=catalog), \
             patch.object(check.queues, "request", side_effect=lambda account, token, path: {"result": details[path.split("/")[-1]]}), \
             patch.object(check.forwarding, "pages", return_value=subscriptions):
            return check.lifecycle_snapshot(ACCOUNT, "private-token")

    def test_exact_lifecycle_graph(self):
        self.assertEqual(len(self.snapshot()["queues"]), 2)

    def test_consumer_cross_realm_count_and_settings_drift(self):
        for change in ("script", "count", "settings", "producer", "dlq"):
            _, details, _ = lifecycle()
            consumer = details[QUEUE_ID]["consumers"][0]
            if change == "script":
                consumer["script_name"] = "amail-events"
            elif change == "count":
                details[QUEUE_ID]["consumers_total_count"] = 2
            elif change == "settings":
                consumer["settings"]["retry_delay"] = 30
            elif change == "producer":
                details[QUEUE_ID].update(producers=[{"script": "unexpected"}], producers_total_count=1)
            else:
                details[DLQ_ID].update(consumers=[deepcopy(consumer)], consumers_total_count=1)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.snapshot(details=details)

    def test_duplicate_domain_path_wrong_domain_and_failed_read(self):
        _, _, subscriptions = lifecycle()
        for change in ("duplicate", "domain", "disabled", "events", "destination"):
            rows = deepcopy(subscriptions)
            if change == "duplicate":
                rows.append({**rows[0], "id": "second", "name": "extra"})
            elif change == "domain":
                rows[0]["source"]["domain"] = "mail.moesegfault.dev"
            elif change == "disabled":
                rows[0]["enabled"] = False
            elif change == "events":
                rows[0]["events"].append(rows[0]["events"][0])
            else:
                rows[0]["destination"]["queue_id"] = DLQ_ID
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.snapshot(subscriptions=rows)
        with patch.object(check.queues, "inventory", side_effect=ValueError("unavailable")):
            with self.assertRaises(ValueError):
                check.lifecycle_snapshot(ACCOUNT, "token")

    @patch.dict(os.environ, ENV)
    def test_serving_change_rejected(self):
        before = {check.INGRESS: (VERSION, VERSION), check.EVENTS_WORKER: (VERSION, VERSION)}
        with patch.object(check, "serving", side_effect=[before, {}]), \
             patch.object(check, "lifecycle_snapshot", return_value={}), \
             patch.object(check, "private_surfaces"), patch.object(check, "bindings_match", return_value=True), \
             patch.object(check, "entry_surface_match", return_value=True), \
             patch.object(check.capture, "effective_api_settings", return_value=True), \
             patch.object(check.capture, "worker_readback", return_value={}), \
             patch.object(check.capture, "readback", side_effect=lambda account, token, script, suffix:
                          {"enabled": False, "previews_enabled": False} if suffix == "subdomain" else
                          {"schedules": []} if suffix == "schedules" else {}):
            with self.assertRaisesRegex(ValueError, "adapter_graph_changed"):
                check.verify(VERSION, VERSION)

    def test_private_custom_domain_rejected(self):
        with patch.object(check.isolation, "worker_domains", return_value=[{"service": check.EVENTS_WORKER}]), \
             self.assertRaises(ValueError):
            check.private_surfaces(ACCOUNT, "token")


class DeployTests(unittest.TestCase):
    """The wrapper selects tested staging bytes and never retries a submission."""

    @patch.dict(os.environ, {**ENV, "GITHUB_ACTIONS": "true",
        "GITHUB_REF": "refs/heads/codex/v0.1.2-agent-first-performance",
        "AMAIL_STAGING_DEPLOY_CONFIRM": "RUN_STAGING_V012"})
    def test_events_exact_staging_and_failure_no_retry(self):
        with patch.object(deploy, "require_artifact") as artifact, patch.object(deploy, "submit", return_value=VERSION) as submit:
            self.assertEqual(deploy.deploy("events"), VERSION)
            artifact.assert_called_once_with("mail_events")
            self.assertEqual(submit.call_args.args[0], ["wrangler", "deploy", "--env", "staging"])
        with patch.object(deploy, "require_artifact"), patch.object(deploy, "submit", side_effect=subprocess.TimeoutExpired("private", 600)) as submit:
            with self.assertRaises(subprocess.TimeoutExpired):
                deploy.deploy("events")
            submit.assert_called_once()

    @patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}, clear=True)
    def test_wrong_context_never_submits(self):
        with patch.object(deploy, "submit") as submit, self.assertRaises(ValueError):
            deploy.deploy("events")
        submit.assert_not_called()


class DiagnosticTests(unittest.TestCase):
    """Infrastructure diagnostics cannot disclose arbitrary provider content."""

    def test_closed_failure_reason(self):
        self.assertEqual(check.failure_reason(ValueError("adapter_consumer_unverified")), "adapter_consumer_unverified")
        for error in (ValueError("PRIVATE provider recipient"), RuntimeError("adapter_consumer_unverified"),
                      KeyError("secret"), ValueError({"secret": "private"})):
            self.assertEqual(check.failure_reason(error), "adapter_readback_unverified")

    def test_sanitized_lifecycle_projection(self):
        catalog, details, subscriptions = lifecycle()
        consumer = details[QUEUE_ID]["consumers"][0]
        consumer.pop("type")
        consumer.update(subject="PRIVATE subject", recipient="PRIVATE address", script_name="PRIVATE script")
        consumer["settings"].update(max_concurrency=7, retry_delay="PRIVATE response", batch_size=True)
        subscriptions[0].update(name="PRIVATE subscription", events=["PRIVATE event"])
        details[QUEUE_ID].update(producers=[{"type": "PRIVATE kind", "script": "PRIVATE producer"}], producers_total_count=1)
        with patch.object(check.queues, "inventory", return_value=catalog), \
             patch.object(check.queues, "request", side_effect=lambda account, token, path: {"result": details[path.split("/")[-1]]}), \
             patch.object(check.forwarding, "pages", return_value=subscriptions):
            facts = check.diagnostic_facts(ACCOUNT, "PRIVATE token")
        self.assertNotIn("PRIVATE", json.dumps(facts))
        self.assertTrue(facts["sourceaccount_match"])
        self.assertTrue(facts["main_queue"]["identity_match"])
        self.assertTrue(facts["main_queue"]["producers"]["count_complete"])
        self.assertEqual(facts["main_queue"]["producers"]["itemtypes"]["unknown"], 1)
        self.assertEqual(facts["main_queue"]["consumers"]["itemtypes"]["missing"], 1)
        self.assertEqual(facts["main_queue"]["mainconsumer"]["settings"]["max_concurrency"], 7)
        self.assertEqual(facts["main_queue"]["mainconsumer"]["settings"]["retry_delay"], "invalid")
        self.assertEqual(facts["main_queue"]["mainconsumer"]["settings"]["batch_size"], "invalid")
        self.assertFalse(facts["main_queue"]["mainconsumer"]["script_match"])
        self.assertEqual(facts["subscription"]["related_count"], 1)
        self.assertFalse(facts["subscription"]["name_match"])

    def test_failed_inventory_is_not_absence(self):
        with patch.object(check.queues, "inventory", side_effect=ValueError("PRIVATE provider prose")):
            facts = check.diagnostic_facts(ACCOUNT, "token")
        self.assertNotIn("main_queue", facts)
        self.assertNotIn("queue_inventory_complete", facts)
        self.assertEqual(facts["read_failure"], "adapter_readback_unverified")

    def test_default_failure_output_unchanged(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["checker", "--source-only"]), \
             patch.object(check, "source_configs", side_effect=ValueError("PRIVATE provider prose")), \
             patch.object(check, "diagnostic_facts") as diagnostic, contextlib.redirect_stdout(output):
            self.assertEqual(check.main(), 1)
        self.assertEqual(output.getvalue(), "staging_adapters=UNVERIFIED\n")
        diagnostic.assert_not_called()


if __name__ == "__main__":
    unittest.main()
