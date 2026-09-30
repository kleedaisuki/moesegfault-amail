"""Synthetic discriminator contracts; no provider, Mail traffic, or external fixtures."""
from __future__ import annotations

import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/provider"))
import staging_issues_create_probe as probe
from workflow_source import job_block

IDENTITY = "00000000000000000000000000000001"
SHA = "a" * 40


def worker() -> dict:
    """Return a code-free raw GET fixture, not an SDK-default-filled object."""
    return {**probe.create_body(), "id": IDENTITY, "created_on": "2026-10-01T00:00:00Z",
            "updated_on": "2026-10-01T00:00:00Z", "deployed_on": None,
            "references": dict.fromkeys(probe.REFERENCES, [])}


def environment() -> dict:
    """Build public immutable hosted coordinates, with no credentials."""
    return {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": probe.REF,
            "GITHUB_REPOSITORY": probe.REPOSITORY, "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_SHA": SHA, "GITHUB_RUN_ID": "123", "ISSUES_REVIEWED_SHA": SHA,
            "ISSUES_APPROVED_SHA": SHA, "ISSUES_CONFIRM": probe.CONFIRM,
            "ISSUES_FREEZE": probe.FREEZE}


def page(items: list, total: int | None = None, number: int = 1) -> dict:
    """Return complete typed pagination metadata; missing fields are not defaults."""
    total = len(items) if total is None else total
    return {"success": True, "errors": [], "result": items,
            "result_info": {"page": number, "per_page": 100, "count": len(items),
                            "total_count": total, "total_pages": max(1, (total + 99) // 100)}}


class FakeClient:
    """Record fixed operations; never inherit the real credentialed transport."""

    def __init__(self, current: dict | None = None):
        """Configure raw readback independently of creation acknowledgement."""
        self.current = worker() if current is None else current
        self.calls = []

    def original(self):
        """Record one privately stable Mail snapshot."""
        self.calls.append("original")
        return ("original-version-bindings-settings",)

    def held_idle(self):
        """Record the content-free hold/grant check."""
        self.calls.append("hold")

    def workers_page(self, number):
        """Return complete absence, not a not-found transport exception."""
        self.calls.append("absence")
        return page([])

    def create(self):
        """Supply a deliberately separate creation acknowledgement."""
        self.calls.append("create")
        return {"id": IDENTITY, "name": probe.NAME}

    def worker(self, identity):
        """Require the exact returned ID for the single independent GET."""
        if identity != IDENTITY:
            raise ValueError("synthetic-secret")
        self.calls.append("readback")
        return self.current

    def no_versions(self, identity):
        """Record the separate uploaded-code absence evidence."""
        if identity != IDENTITY:
            raise ValueError("synthetic-secret")
        self.calls.append("no_versions")


class CreateProbeTests(unittest.TestCase):
    """Protect exact targeting, one-shot semantics, isolation and safe result bins."""

    def test_create_body_has_only_reviewed_six_fields(self):
        """No routes, code, previews template, bindings, URL copy, or triggers exist."""
        body = probe.create_body()
        self.assertEqual(set(body), {"name", "observability", "logpush", "tags", "tail_consumers", "subdomain"})
        self.assertEqual(body["name"], probe.NAME)
        self.assertIs(body["logpush"], False)
        self.assertEqual(body["tags"], [])
        self.assertEqual(body["tail_consumers"], [])
        self.assertEqual(body["subdomain"], {"enabled": False, "previews_enabled": False})
        for name in ("logs", "traces", "issues"):
            self.assertIs(body["observability"][name]["enabled"], False)
        self.assertIs(body["observability"]["enabled"], False)
        self.assertIs(body["observability"]["logs"]["invocation_logs"], False)
        body["observability"]["enabled"] = True
        self.assertIs(probe.create_body()["observability"]["enabled"], False)

    def test_issues_false_omitted_and_true_are_not_conflated(self):
        """Check raw omission of the container and flag separately from null."""
        cases = [({"enabled": False}, "explicit_off"), ({"enabled": True}, "true"), ({}, "omitted")]
        for value, expected in cases:
            with self.subTest(value=value):
                current = worker()
                current["observability"]["issues"] = value
                self.assertEqual(probe.issues_bin(current), expected)
        current = worker()
        del current["observability"]["issues"]
        self.assertEqual(probe.issues_bin(current), "omitted")

    def test_malformed_issues_and_unknown_capture_fail_closed(self):
        """No null, numeric Boolean, external destination, or unknown mechanism passes."""
        for value in (None, False, [], {"enabled": None}, {"enabled": 0}, {"enabled": "false"},
                      {"enabled": False, "new_capture": False}):
            with self.subTest(value=value):
                current = worker()
                current["observability"]["issues"] = value
                with self.assertRaises(ValueError):
                    probe.issues_bin(current)
        for mutate in (
            lambda o: o.update(enabled=True),
            lambda o: o.update(head_sampling_rate=True),
            lambda o: o.update(redact_query_string=False),
            lambda o: o.update(new_capture=False),
            lambda o: o["logs"].update(enabled=True),
            lambda o: o["logs"].update(invocation_logs=True),
            lambda o: o["traces"].update(enabled=True),
            lambda o: o["traces"].update(destinations=["https://synthetic-secret.invalid"]),
        ):
            current = worker()
            mutate(current["observability"])
            with self.assertRaises(ValueError):
                probe.issues_bin(current)

    def test_isolation_requires_positive_flags_references_and_no_deployment(self):
        """Unknown capabilities or absent mandatory off evidence stop progression."""
        probe.isolated(worker())
        for key, value in (("logpush", True), ("tail_consumers", [{"name": "synthetic"}]),
                           ("tags", ["synthetic"]), ("deployed_on", "2026-10-01T00:00:00Z"),
                           ("previews_base_config", {"env": {"secret": {"type": "secret_text"}}}),
                           ("routes", []), ("bindings", []), ("code", "synthetic")):
            current = worker()
            current[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                probe.isolated(current)
        for mutate in (
            lambda w: w.pop("deployed_on"),
            lambda w: w["subdomain"].pop("previews_enabled"),
            lambda w: w["subdomain"].update(enabled=True),
            lambda w: w["subdomain"].update(previews_enabled=True),
            lambda w: w["subdomain"].update(new_url_flag=False),
            lambda w: w["references"].pop("queues"),
            lambda w: w["references"].update(workers=[{"id": "synthetic-secret"}]),
            lambda w: w["references"].update(new_product=[]),
        ):
            current = worker()
            mutate(current)
            with self.assertRaises(ValueError):
                probe.isolated(current)
        current = worker()
        current["subdomain"].update(url="https://not-live.invalid", preview_url_suffix="not-live.invalid")
        probe.isolated(current)

    def test_identity_cannot_adopt_mail_or_renamed_worker(self):
        """The response name and immutable ID must both match independently."""
        self.assertEqual(probe.check_identity(worker(), IDENTITY), IDENTITY)
        for value in (None, "", probe.NAME, probe.SCRIPT, "amail-mail", "../secret", "x" * 129):
            current = worker()
            current["id"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                probe.check_identity(current)
        current = worker()
        current["name"] = probe.SCRIPT
        with self.assertRaises(ValueError):
            probe.check_identity(current)
        with self.assertRaises(ValueError):
            probe.check_identity(worker(), "other-id")

    def test_complete_bounded_namespace_absence(self):
        """Read all advertised pages rather than guessing absence from an error."""
        client = Mock()
        items = [{"id": f"id-{n}", "name": f"worker-{n:03}"} for n in range(101)]
        client.workers_page.side_effect = [page(items[:100], 101), page(items[100:], 101, 2)]
        self.assertTrue(probe.name_absent(client))
        self.assertEqual(client.workers_page.call_count, 2)
        client.workers_page.side_effect = None
        client.workers_page.return_value = page([])
        self.assertTrue(probe.name_absent(client))
        client.workers_page.return_value = page([{"id": IDENTITY, "name": probe.NAME}])
        self.assertFalse(probe.name_absent(client))

    def test_incomplete_or_changed_namespace_fails_closed(self):
        """Reject absent metadata, excessive pages, duplicates and changing totals."""
        good = page([{"id": "id-one", "name": "worker-one"}])
        bad = []
        for key in good["result_info"]:
            current = copy.deepcopy(good)
            del current["result_info"][key]
            bad.append(current)
            current = copy.deepcopy(good)
            current["result_info"][key] = True
            bad.append(current)
        current = copy.deepcopy(good)
        current["result_info"]["total_count"] = 501
        current["result_info"]["total_pages"] = 6
        bad.extend([current, page([{}]), page([{"id": "../unsafe", "name": "worker-one"}]),
                    page([{"id": "id-one", "name": "worker-one"}] * 2)])
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                probe.name_absent(Mock(workers_page=Mock(return_value=value)))
        items = [{"id": f"id-{n}", "name": f"worker-{n}"} for n in range(100)]
        client = Mock(workers_page=Mock(side_effect=[page(items, 101), page([], 100, 2)]))
        with self.assertRaises(ValueError):
            probe.name_absent(client)

    def test_transport_failures_never_create_or_retry(self):
        """403, arbitrary 404 and unavailable evidence are not name absence."""
        for error in (PermissionError("secret-403"), ValueError("404 raw-body"), TimeoutError("secret-url")):
            client = FakeClient()
            client.workers_page = Mock(side_effect=error)
            with self.assertRaises(Exception):
                probe.probe(client, Mock(), dict.fromkeys(probe.FIELDS, "skipped"))
            self.assertNotIn("create", client.calls)

    def test_happy_path_and_omission_are_independent_get_evidence(self):
        """Creation acknowledgement deliberately contains no observability at all."""
        for omitted in (False, True):
            current = worker()
            if omitted:
                del current["observability"]["issues"]
            client, recovery = FakeClient(current), Mock()
            phases = dict.fromkeys(probe.FIELDS, "skipped")
            self.assertEqual(probe.probe(client, recovery, phases), "omitted" if omitted else "explicit_off")
            self.assertEqual(client.calls, ["original", "hold", "absence", "create", "readback",
                                            "no_versions", "original", "hold"])
            recovery.save.assert_called_once_with(IDENTITY)
            self.assertEqual(phases["original_pin"], "match")
            self.assertEqual(phases["hold"], "match")

    def test_occupied_name_does_not_adopt_or_mutate(self):
        """Preexisting exact resource means stop, not read-and-patch or delete."""
        client, recovery = FakeClient(), Mock()
        client.workers_page = Mock(return_value=page([{"id": IDENTITY, "name": probe.NAME}]))
        phases = dict.fromkeys(probe.FIELDS, "skipped")
        self.assertEqual(probe.probe(client, recovery, phases), "UNVERIFIED")
        self.assertEqual(phases["absence"], "name_occupied")
        self.assertNotIn("create", client.calls)
        recovery.save.assert_not_called()

    def test_ambiguous_post_never_adopts_or_replays(self):
        """No finally deletion can erase the only recovery identity of a partial write."""
        client, recovery = FakeClient(), Mock()
        client.create = Mock(side_effect=TimeoutError("Bearer synthetic-secret"))
        phases = dict.fromkeys(probe.FIELDS, "skipped")
        with self.assertRaises(TimeoutError):
            probe.probe(client, recovery, phases)
        client.create.assert_called_once()
        recovery.save.assert_not_called()
        self.assertEqual(phases["create"], "attempted")

    def test_failed_independent_readback_keeps_exact_resource_pin(self):
        """No cleanup follows a missing/changed identity, isolation failure or transport failure."""
        client, recovery = FakeClient(), Mock()
        client.worker = Mock(side_effect=ValueError("synthetic-provider-body"))
        phases = dict.fromkeys(probe.FIELDS, "skipped")
        with self.assertRaises(ValueError):
            probe.probe(client, recovery, phases)
        recovery.save.assert_called_once_with(IDENTITY)
        self.assertEqual(client.calls.count("create"), 1)
        self.assertEqual(phases["recovery"], "identity_saved")

    def test_original_pin_or_hold_change_invalidates_probe(self):
        """Shadow success is discarded when the original bracket is unstable."""
        client = FakeClient()
        client.original = Mock(side_effect=[("before",), ("after",)])
        with self.assertRaises(ValueError):
            probe.probe(client, Mock(), dict.fromkeys(probe.FIELDS, "skipped"))
        client = FakeClient()
        client.held_idle = Mock(side_effect=[None, ValueError("canary-active")])
        with self.assertRaises(ValueError):
            probe.probe(client, Mock(), dict.fromkeys(probe.FIELDS, "skipped"))

    def test_guard_needs_independent_approval_and_exact_first_attempt(self):
        """Missing approvals, debug, wrong ref/repo and reruns fail before credentials."""
        self.assertEqual(probe.guard(environment())["source_sha"], SHA)
        for key in environment():
            current = environment()
            current[key] = "unexpected"
            with self.subTest(key=key), self.assertRaises(ValueError):
                probe.guard(current)
        for key, value in (("RUNNER_DEBUG", "1"), ("ACTIONS_RUNNER_DEBUG", "TRUE"),
                           ("ACTIONS_STEP_DEBUG", "true")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                probe.guard({**environment(), key: value})

    def test_decoder_rejects_ambiguous_and_oversized_envelopes(self):
        """Reject duplicate keys, nonfinite values, errors and malformed raw JSON."""
        self.assertEqual(probe.decode(b'{"success":true,"errors":[],"result":{}}')["result"], {})
        for raw in (b'{"success":true,"success":false,"errors":[]}',
                    b'{"success":true,"errors":[],"result":{"enabled":false,"enabled":true}}',
                    b'{"success":true,"errors":[],"result":NaN}', b'{"success":1,"errors":[]}',
                    b'{"success":true,"errors":[{"message":"synthetic-secret"}]}',
                    b'{"success":true}', b"invalid", b"x" * (probe.LIMIT + 1)):
            with self.subTest(raw=raw[:40]), self.assertRaises(ValueError):
                probe.decode(raw)

    def test_transport_does_not_redirect_or_retry_and_is_bounded(self):
        """A fake response verifies exact POST body, authorization and byte cap."""
        response = Mock(status=200)
        response.read.return_value = b'{"success":true,"errors":[],"result":{"id":"synthetic"}}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock(open=Mock(return_value=response))
        with patch.object(probe, "build_opener", return_value=opener):
            probe.Client("a" * 32, "synthetic-token").create()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertTrue(request.full_url.endswith("/workers/workers"))
        self.assertEqual(json.loads(request.data), probe.create_body())
        response.read.assert_called_once_with(probe.LIMIT + 1)
        opener.open.assert_called_once()
        self.assertIsNone(probe.NoRedirect().redirect_request(None, None, 302, "secret", {}, "https://secret.invalid"))

    def test_no_versions_requires_complete_empty_metadata(self):
        """No deployment timestamp is insufficient: uploaded versions must also be absent."""
        empty = {"result": [], "result_info": {"count": 0, "total_count": 0,
                 "page": 1, "per_page": 1, "total_pages": 0}}
        client = probe.Client("a" * 32, "synthetic")
        with patch.object(client, "_request", return_value=empty):
            client.no_versions(IDENTITY)
        for key in empty["result_info"]:
            current = copy.deepcopy(empty)
            del current["result_info"][key]
            with patch.object(client, "_request", return_value=current), self.assertRaises(ValueError):
                client.no_versions(IDENTITY)
        with patch.object(client, "_request", return_value={**empty, "result": [{"id": "synthetic"}]}), self.assertRaises(ValueError):
            client.no_versions(IDENTITY)

    def test_hold_requires_literal_aggregate_counts_and_no_usable_canary(self):
        """Global hold alone cannot authorize this probe while a one-use grant is active."""
        row = dict.fromkeys(("global_rows", "global_held", "gate_rows", "idle_rows"), 1)
        client = probe.Client("a" * 32, "synthetic")
        good = {"result": [{"success": True, "results": [row]}]}
        with patch.object(client, "_request", return_value=good) as request:
            client.held_idle()
        self.assertEqual(request.call_args.args[0], f"d1/database/{probe.DATABASE}/query")
        self.assertEqual(request.call_args.args[1], {"sql": probe.HOLD_SQL, "params": []})
        for key in row:
            for invalid in (0, 2, True, "1", None):
                current = copy.deepcopy(good)
                current["result"][0]["results"][0][key] = invalid
                with self.subTest(key=key, invalid=invalid), \
                     patch.object(client, "_request", return_value=current), self.assertRaises(ValueError):
                    client.held_idle()

    def test_main_never_prints_provider_errors_or_resource_ids(self):
        """Every attempted phase remains categorical when provider errors contain secrets."""
        output = io.StringIO()
        with patch.dict(os.environ, environment(), clear=True), patch.object(sys, "argv", ["probe"]), \
             patch.object(probe, "Recovery"), patch.object(probe, "Client"), \
             patch.object(probe, "probe", side_effect=ValueError("Bearer SECRET https://private.invalid " + IDENTITY)), \
             patch("sys.stdout", output):
            self.assertEqual(probe.main(), 1)
        self.assertIn("staging_issues_create_probe=UNVERIFIED", output.getvalue())
        for private in ("SECRET", "private.invalid", IDENTITY, "Traceback"):
            self.assertNotIn(private, output.getvalue())

    def test_recovery_persists_only_non_secret_allowlisted_pins_under_workspace(self):
        """Resource pins cannot contain bodies, account ID, configuration, or arbitrary values."""
        base = ROOT / ".temp"
        base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as directory, patch.object(probe, "ROOT", Path(directory)):
            recovery = probe.Recovery(probe.guard(environment()))
            recovery.save(IDENTITY)
            record = json.loads((Path(directory) / ".temp/issues-create-probe/resource.json").read_bytes())
            self.assertEqual(set(record), {"name", "utc", "repository", "workflow", "source_sha", "run", "attempt", "worker_id"})
            self.assertEqual(record["worker_id"], IDENTITY)
            with self.assertRaises(ValueError):
                probe.Recovery(probe.guard(environment()))

    def test_workflow_is_manual_presecret_guarded_and_no_delete(self):
        """Protected provider job depends on credential-free tests and shared writer exclusion."""
        source = (ROOT / ".github/workflows/staging-issues-create-probe.yml").read_text(encoding="utf-8")
        guard, live = job_block(source, "guard"), job_block(source, "probe")
        self.assertIn("  workflow_dispatch:", source)
        self.assertNotIn("  push:", source)
        self.assertNotIn("  schedule:", source)
        self.assertNotIn("secrets.", guard)
        self.assertNotIn("environment: staging", guard)
        self.assertIn("--guard", guard)
        self.assertIn("test_staging_issues_create_probe.py", guard)
        self.assertIn("    needs: guard", live)
        self.assertIn("    environment: staging", live)
        self.assertIn("group: staging-native-mail-acceptance", live)
        self.assertIn("cancel-in-progress: false", live)
        self.assertIn("if: always()", live)
        self.assertIn("path: .temp/issues-create-probe/resource.json", live)
        self.assertIn("include-hidden-files: true", live)
        self.assertIn("overwrite: false", live)
        self.assertNotIn("CF_EMAIL_ROUTING_TOKEN", source)
        self.assertNotIn("GITHUB_TOKEN:", source)
        self.assertEqual(live.count("run: python infra/provider/staging_issues_create_probe.py\n"), 1)
        helper = Path(probe.__file__).read_text(encoding="utf-8")
        self.assertNotIn('method="DELETE"', helper)
        self.assertNotIn('method="PATCH"', helper)
        self.assertNotIn("time.sleep", helper)


if __name__ == "__main__":
    unittest.main()
