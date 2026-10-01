"""Synthetic contracts for the fixed read-only capture preflight discriminator."""
import contextlib
import copy
import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
import diagnose_staging_capture_preflight as subject
import apply_staging_capture_off as mutator
from historical_containment_fixture import historical_version

DEPLOYMENT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def deployment(identifier=DEPLOYMENT, version=subject.VERSION):
    """Build exact single100 synthetic serving evidence."""
    return {"deployments": [{"id": identifier, "strategy": "percentage",
        "versions": [{"version_id": version, "percentage": 100}]}]}


def version():
    """Use the literal historical fixture, independent of current TOML."""
    return historical_version()


def worker():
    """Model reported dormant defaults and missing independent Issues switch."""
    return {"id": "PRIVATE_WORKER_ID", "name": subject.SCRIPT, "logpush": False,
        "tail_consumers": [], "observability": {"enabled": False,
        "redact_query_string": False, "head_sampling_rate": 1,
        "logs": {"enabled": False, "persist": True, "invocation_logs": True,
                 "head_sampling_rate": 1, "destinations": []},
        "traces": {"enabled": False, "persist": True,
                   "head_sampling_rate": 1, "destinations": []}}}


class DiagnosticTests(unittest.TestCase):
    """Resolve preflight blockers without introducing any mutation path."""

    def fixture(self, reads=None, current=None):
        """Use mocked fixed readers and make any PATCH attempt fail the test."""
        with patch.object(subject, "source_policy", return_value=mutator.POLICY), \
             patch.object(subject, "fetch", side_effect=reads or [deployment(), version(),
                 {}, {"observability": None, "tail_consumers": None}, deployment()]) as fetch, \
             patch.object(subject, "worker_readback", return_value=current or worker()) as resource, \
             patch.object(mutator, "patch_policy", side_effect=AssertionError("No PATCH permitted")) as writer:
            result = subject.diagnose("a" * 32, "PRIVATE_TOKEN", subject.VERSION)
        writer.assert_not_called()
        return result, fetch, resource

    def test_reported_bins_pass_effective_default_off_preflight(self):
        """Missing Issues/null old representation cannot alone explain helper failure."""
        original = worker()
        (status, values), fetch, resource = self.fixture(current=original)
        self.assertEqual(status, "diagnosed")
        self.assertEqual(values["preflight"], "pass")
        self.assertEqual([x.args[2] for x in fetch.call_args_list],
            [subject.DEPLOYMENTS, f"versions/{subject.VERSION}", "settings", "script-settings",
             subject.DEPLOYMENTS])
        resource.assert_called_once_with("a" * 32, "PRIVATE_TOKEN")
        self.assertNotIn("issues", original["observability"])
        self.assertTrue(subject.effective_api_settings(original, subject.SCRIPT))

    def test_source_and_input_stop_before_provider_reads(self):
        """No unreviewed version/source can be used for discovery."""
        with patch.object(subject, "fetch") as fetch:
            status, _ = subject.diagnose("a", "t", DEPLOYMENT)
            self.assertEqual(status, "input_unverified")
            fetch.assert_not_called()
        with patch.object(subject, "source_policy", side_effect=ValueError("PRIVATE")), \
             patch.object(subject, "fetch") as fetch:
            status, values = subject.diagnose("a", "t", subject.VERSION)
        self.assertEqual(status, "source_unverified")
        self.assertEqual(values["source"], "unverified")
        fetch.assert_not_called()

    def test_exact_binding_failure_is_refined_not_accepted(self):
        """Separate version binding mismatch from current/legacy policy phases."""
        extra = version()
        extra["resources"]["bindings"].append({"name": "PRIVATE", "type": "queue"})
        (status, values), _, _ = self.fixture(reads=[deployment(), extra, {}, {}, deployment()])
        self.assertEqual(status, "diagnosed")
        self.assertEqual(values["bindings"], "mismatch")
        self.assertEqual(values["binding_cause"], "bindings_count")
        self.assertEqual(values["worker_policy"], "match")
        self.assertEqual(values["preflight"], "blocked")
        actual = version()
        actual["resources"]["bindings"] = {"result": actual["resources"]["bindings"]}
        (status, values), _, _ = self.fixture(reads=[deployment(), actual, {}, {}, deployment()])
        self.assertEqual(values["bindings"], "match")
        self.assertEqual(status, "diagnosed")

    def test_binding_cause_categories_are_closed(self):
        """Never output binding identity/value/count while distinguishing source contracts."""
        cases = [(None, None, "version_identity"),
                 ("id", "PRIVATE", "version_identity"),
                 ("resources", None, "resources_shape")]
        for key, value, reason in cases:
            actual = {} if key is None else {**version(), key: value}
            self.assertEqual(subject.binding_cause(actual), reason)
        for field, value, reason in (("name", "PRIVATE", "binding_names"),
                                     ("type", "PRIVATE", "binding_type"),
                                     ("database_id", "PRIVATE", "d1_resource")):
            actual = version()
            actual["resources"]["bindings"][0][field] = value
            self.assertEqual(subject.binding_cause(actual), reason)

    def test_normalization_policy_and_projection_are_distinct(self):
        """A normalized container can still violate policy; projection can fail independently."""
        current = worker()
        current["observability"]["issues"] = {"enabled": "PRIVATE"}
        (_, values), _, _ = self.fixture(current=current)
        self.assertEqual(values["worker_normalized"], "unverified")
        self.assertEqual(values["worker_policy"], "skipped")
        current = worker()
        current["observability"]["logs"]["enabled"] = True
        (_, values), _, _ = self.fixture(current=current)
        self.assertEqual(values["worker_normalized"], "ok")
        self.assertEqual(values["worker_policy"], "mismatch")
        (_, values), _, _ = self.fixture(reads=[deployment(), version(),
            {"observability": {"enabled": True}}, {"tags": "PRIVATE"}, deployment()])
        self.assertEqual(values["settings_policy"], "mismatch")
        self.assertEqual(values["script_settings_policy"], "match")
        self.assertEqual(values["unaffected_projection"], "unverified")

    def test_transport_is_bounded_and_always_closes_serving_bracket(self):
        """Do not retry a failed read or collapse transport into policy failure."""
        error = ValueError("PRIVATE_PROVIDER_BODY")
        error.__cause__ = URLError("PRIVATE_HOST")
        (status, values), fetch, _ = self.fixture(reads=[deployment(), version(),
            error, {}, deployment()])
        self.assertEqual(status, "incomplete")
        self.assertEqual(values["settings_read"], "transport")
        self.assertEqual(values["preflight"], "unavailable")
        self.assertEqual(values["serving_after"], "match")
        self.assertEqual(fetch.call_count, 5)
        for cause, expected in ((HTTPError("PRIVATE", 403, "PRIVATE", {}, None), "http_denied"),
                                (HTTPError("PRIVATE", 404, "PRIVATE", {}, None), "http_not_found"),
                                (HTTPError("PRIVATE", 503, "PRIVATE", {}, None), "http_5xx"),
                                (TimeoutError("PRIVATE"), "timeout"),
                                (ValueError("PRIVATE"), "provider_unverified")):
            error.__cause__ = cause
            self.assertEqual(subject.failure_category(error), expected)

    def test_changed_deployment_discards_attribution(self):
        """Never print collected resource/policy bins as stable on deployment drift."""
        (status, values), _, _ = self.fixture(reads=[deployment(), version(), {}, {},
            deployment(identifier=subject.VERSION)])
        self.assertEqual(status, "deployment_changed")
        self.assertEqual(values["serving_after"], "changed")
        self.assertEqual(set(values.values()), {"discarded", "changed"})

    def test_output_never_contains_provider_data_or_attestation(self):
        """Read-only success has distinct fixed labels, no rollout marker or identifiers."""
        env = {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "PRIVATE_TOKEN",
            "AMAIL_EXPECTED_WORKER_VERSION": subject.VERSION,
            "AMAIL_CAPTURE_PREFLIGHT_CONFIRM": subject.CONFIRM,
            "GITHUB_RUN_ATTEMPT": "1", "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REF": "refs/heads/codex/amail-v0.1.0", "GITHUB_SHA": "b" * 40}
        output = io.StringIO()
        values = dict.fromkeys(subject.FIELDS, "match")
        with patch.dict(os.environ, env, clear=True), \
             patch.object(subject, "diagnose", return_value=("diagnosed", values)), \
             contextlib.redirect_stdout(output):
            self.assertEqual(subject.main(), 0)
        self.assertEqual(len(output.getvalue().splitlines()), len(subject.FIELDS) + 1)
        for secret in ("PRIVATE", subject.VERSION, DEPLOYMENT, "attestation", "Current Version ID"):
            self.assertNotIn(secret, output.getvalue())
        for key, value in (("GITHUB_RUN_ATTEMPT", "2"), ("GITHUB_EVENT_NAME", "push"),
                           ("AMAIL_EXPECTED_WORKER_VERSION", DEPLOYMENT),
                           ("AMAIL_CAPTURE_PREFLIGHT_CONFIRM", "PRIVATE")):
            with patch.dict(os.environ, {**env, key: value}, clear=True), \
                 patch.object(subject, "diagnose") as probe, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(subject.main(), 1)
                probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
