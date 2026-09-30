"""Synthetic contracts for the one-shot staging capture settings correction."""
import contextlib
import copy
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
import apply_staging_capture_off as subject
from pin_staging_mail import expected_bindings

DEPLOYMENT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def deployment(version=subject.VERSION, identifier=DEPLOYMENT):
    """Build exact single100 synthetic serving evidence."""
    return {"deployments": [{"id": identifier, "strategy": "percentage",
        "versions": [{"version_id": version, "percentage": 100}]}]}


def version():
    """Build synthetic binding names/resources matching reviewed source only."""
    values = []
    for name, (kind, value) in expected_bindings().items():
        binding = {"name": name, "type": kind}
        key = {"d1": "database_id", "r2_bucket": "bucket_name", "plain_text": "text"}.get(kind)
        if key:
            binding[key] = value
        values.append(binding)
    return {"id": subject.VERSION, "resources": {"bindings": values}}


def settings(issues=False):
    """Make actual positive Worker evidence plus unsupported legacy shapes."""
    obs = copy.deepcopy(subject.POLICY)
    if issues is None:
        del obs["issues"]
    else:
        obs["issues"]["enabled"] = issues
    return ({"id": "PRIVATE_WORKER_ID", "name": subject.SCRIPT,
             "observability": obs, "logpush": False, "tail_consumers": []},
            {}, {"observability": None, "logpush": False,
                 "tail_consumers": None, "tags": ["PRIVATE_TAG"]})


class CaptureCorrectionTests(unittest.TestCase):
    """Ensure no source, provider, drift or ambiguity can emit false acceptance."""

    def apply_fixture(self, prior=None, current=None, reads=None, patch_error=None):
        """Run only synthetic providers, returning mocks for exact mutation count."""
        reads = reads or [deployment(), version(), deployment(), version(), deployment()]
        with patch.object(subject, "source_policy", return_value=copy.deepcopy(subject.POLICY)), \
             patch.object(subject, "fetch", side_effect=reads) as fetch, \
             patch.object(subject, "settings", side_effect=[prior or settings(None), current or settings()]), \
             patch.object(subject, "patch_policy", side_effect=patch_error) as writer:
            result = subject.apply("a" * 32, "PRIVATE_TOKEN", subject.VERSION)
        return result, fetch, writer

    def test_exact_settings_only_body_and_order(self):
        """Only the reviewed full observability object changes, without a redeploy."""
        result, reader, writer = self.apply_fixture()
        self.assertEqual(result, "applied")
        writer.assert_called_once_with("a" * 32, "PRIVATE_TOKEN", subject.POLICY)
        self.assertEqual([call.args[2] for call in reader.call_args_list],
            ["deployments?per_page=1&page=1", f"versions/{subject.VERSION}",
             "deployments?per_page=1&page=1", f"versions/{subject.VERSION}",
             "deployments?per_page=1&page=1"])

    def test_positive_all_off_recovery_is_read_only(self):
        """A new first-attempt recovery run does not repeat an already applied PATCH."""
        result, _, writer = self.apply_fixture(prior=settings())
        self.assertEqual(result, "unchanged")
        writer.assert_not_called()

    def test_enabled_or_missing_issues_can_be_corrected(self):
        """Independent Issues does not make the preflight claim full containment."""
        for old in (True, None):
            self.assertEqual(self.apply_fixture(prior=settings(old))[0], "applied")

    def test_other_capture_and_identity_fail_before_patch(self):
        """No unrelated unsafe subsystem, export or wrong Worker is admitted."""
        for field, value in [("name", "OTHER"), ("id", None), ("logpush", True),
                             ("tail_consumers", [{}])]:
            prior = settings(None)
            prior[0][field] = value
            with self.assertRaises(ValueError):
                self.apply_fixture(prior=prior)
        for change in ({"enabled": True}, {"logs": {"enabled": True}},
                       {"issues": {"enabled": "false"}}, {"issues": {"other": False}}):
            prior = settings(None)
            prior[0]["observability"].update(change)
            with self.assertRaises(ValueError):
                self.apply_fixture(prior=prior)

    def test_missing_issues_after_patch_never_passes(self):
        """A provider omission remains unverified after an explicit successful write."""
        for issues in (None, True):
            with self.assertRaises(ValueError):
                self.apply_fixture(current=settings(issues))

    def test_identity_or_unaffected_state_drift_rejects(self):
        """Keep private Worker identity, tags, Logpush and tails outside the write."""
        for index, key, value in [(0, "id", "DIFFERENT"), (2, "tags", ["DIFFERENT"]),
                                  (2, "tail_consumers", [])]:
            current = settings()
            current[index][key] = value
            with self.assertRaises(ValueError):
                self.apply_fixture(current=current)

    def test_binding_and_deployment_drift_reject(self):
        """No Queue binding, split traffic or unchanged-version new deployment passes."""
        extra = version()
        extra["resources"]["bindings"].append({"name": "TRACE_EVENTS", "type": "queue"})
        for reads in ([deployment(), extra],
                      [deployment(version=DEPLOYMENT)],
                      [deployment(), version(), deployment(identifier=subject.VERSION)],
                      [deployment(), version(), deployment(), version(), deployment(identifier=subject.VERSION)]):
            with self.assertRaises(ValueError):
                self.apply_fixture(reads=reads)
        split = deployment()
        split["deployments"][0]["versions"][0]["percentage"] = 50
        with self.assertRaises(ValueError):
            self.apply_fixture(reads=[split])

    def test_patch_ambiguity_has_no_retry(self):
        """An ambiguous mutation stops; only a later read-only reconciliation may pass."""
        with patch.object(subject, "source_policy", return_value=subject.POLICY), \
             patch.object(subject, "fetch", side_effect=[deployment(), version(), deployment()]), \
             patch.object(subject, "settings", return_value=settings(None)), \
             patch.object(subject, "patch_policy", side_effect=ValueError("PRIVATE_BODY")) as writer:
            with self.assertRaises(ValueError):
                subject.apply("a" * 32, "PRIVATE_TOKEN", subject.VERSION)
        writer.assert_called_once()

    def test_body_url_bounds_and_no_redirect(self):
        """The writer uses exact JSON endpoint, bounded read and redirect refusal."""
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"success":true,"result":{}}'
        response.__enter__.return_value = response
        opener = MagicMock()
        opener.open.return_value = response
        with patch.object(subject, "build_opener", return_value=opener):
            subject.patch_policy("a" * 32, "PRIVATE_TOKEN", subject.POLICY)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "PATCH")
        self.assertEqual(request.full_url,
            f"{subject.API}/accounts/{'a' * 32}/workers/scripts/{subject.SCRIPT}/script-settings")
        self.assertEqual(json.loads(request.data), {"observability": subject.POLICY})
        response.read.assert_called_once_with(subject.LIMIT + 1)
        self.assertEqual(opener.open.call_args.kwargs, {"timeout": 15})
        self.assertIsNone(subject.NoRedirect().redirect_request(None, None, 302, "", {}, "https://OTHER"))
        for raw in (b"PRIVATE_BODY", b'{"success":false,"result":{}}',
                    b'{"success":true,"result":[]}', b"x" * (subject.LIMIT + 1)):
            response.read.return_value = raw
            with patch.object(subject, "build_opener", return_value=opener), self.assertRaises(ValueError):
                subject.patch_policy("a" * 32, "PRIVATE_TOKEN", subject.POLICY)
        opener.open.side_effect = URLError("PRIVATE_BODY")
        with patch.object(subject, "build_opener", return_value=opener), self.assertRaises(ValueError):
            subject.patch_policy("a" * 32, "PRIVATE_TOKEN", subject.POLICY)

    def test_source_must_equal_reviewed_object(self):
        """A source intent check cannot silently serialize an added configuration field."""
        self.assertEqual(subject.source_policy(), subject.POLICY)
        stage = {"env": {"staging": {"name": subject.SCRIPT,
                                    "observability": {**subject.POLICY, "unknown": False}}}}
        with patch.object(subject.tomllib, "load", return_value=stage), self.assertRaises(ValueError):
            subject.source_policy()

    def test_first_attempt_and_fixed_private_output(self):
        """Only a successful exact dispatch emits one typed marker, never raw errors."""
        env = {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "PRIVATE_TOKEN",
               "AMAIL_EXPECTED_WORKER_VERSION": subject.VERSION,
               "AMAIL_CONTAINMENT_CONFIRM": subject.CONFIRM, "GITHUB_RUN_ATTEMPT": "1",
               "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_SHA": "b" * 40,
               "GITHUB_REF": "refs/heads/codex/amail-v0.1.0"}
        output = io.StringIO()
        with patch.dict(os.environ, env, clear=True), patch.object(subject, "apply", return_value="applied"), \
             contextlib.redirect_stdout(output):
            self.assertEqual(subject.main(), 0)
        self.assertEqual(output.getvalue().splitlines(), ["staging_api_capture_off=applied",
            f"staging_api_capture_off_attestation=settings-v1 version={subject.VERSION}"])
        for key, bad in (("GITHUB_RUN_ATTEMPT", "2"), ("GITHUB_EVENT_NAME", "push"),
                         ("GITHUB_REF", "refs/heads/main"), ("GITHUB_SHA", "bad"),
                         ("AMAIL_CONTAINMENT_CONFIRM", "bad")):
            output = io.StringIO()
            with patch.dict(os.environ, {**env, key: bad}, clear=True), \
                 patch.object(subject, "apply") as run, contextlib.redirect_stdout(output):
                self.assertEqual(subject.main(), 1)
                run.assert_not_called()
            self.assertEqual(output.getvalue(), "staging_api_capture_off=UNVERIFIED\n")
        output = io.StringIO()
        with patch.dict(os.environ, env, clear=True), \
             patch.object(subject, "apply", side_effect=ValueError("PRIVATE_BODY")), \
             contextlib.redirect_stdout(output):
            self.assertEqual(subject.main(), 1)
        self.assertEqual(output.getvalue(), "staging_api_capture_off=UNVERIFIED\n")


if __name__ == "__main__":
    unittest.main()
