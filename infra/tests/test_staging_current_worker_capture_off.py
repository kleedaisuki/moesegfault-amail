"""Synthetic one-shot current-resource PATCH contracts; no provider requests."""
import contextlib
import copy
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
import apply_staging_current_worker_capture_off as subject
from test_staging_capture_off import deployment, version
from apply_staging_capture_off import POLICY


def worker(issues=None):
    """Make writable and response-only fields distinguishable in private fixtures."""
    policy = copy.deepcopy(POLICY)
    if issues is None:
        del policy["issues"]
    else:
        policy["issues"]["enabled"] = issues
    return {"id": "synthetic-worker-id", "name": subject.SCRIPT,
            "logpush": False, "tail_consumers": [], "tags": ["PRIVATE_TAG"],
            "subdomain": {"enabled": True, "previews_enabled": False,
                          "url": "https://private.invalid", "preview_url_suffix": "PRIVATE"},
            "observability": policy, "created_on": "PRIVATE_TIMESTAMP",
            "updated_on": "before", "references": {"PRIVATE": []},
            "previews_base_config": {"env": {"PRIVATE_BINDING": {"type": "secret_text"}}}}


class CurrentWorkerTests(unittest.TestCase):
    """Reject ambiguous projection, write, readback or concurrency evidence."""

    def execute(self, prior=None, current=None, reads=None, response=None, error=None):
        """Inject every transport boundary and retain one-shot call evidence."""
        prior = worker() if prior is None else prior
        current = worker(False) if current is None else current
        reads = [deployment(), version(), deployment(), version(), deployment()] if reads is None else reads
        phases = dict.fromkeys(subject.PHASES, "skipped")
        with patch.object(subject, "fetch", side_effect=reads), patch.object(
                subject, "worker_readback", side_effect=[prior, current]), patch.object(
                subject, "patch_worker", return_value=response or {
                    "id": prior["id"], "name": subject.SCRIPT}, side_effect=error) as writer:
            result = subject.apply("a" * 32, "PRIVATE_TOKEN", subject.VERSION, phases)
        return result, writer, phases

    def test_one_patch_and_distinct_positive_get(self):
        """Six-field projection excludes all response-only and preview data."""
        result, writer, phases = self.execute()
        self.assertEqual(result, "applied")
        self.assertEqual(writer.call_count, 1)
        self.assertEqual(writer.call_args.args[2], "synthetic-worker-id")
        body = writer.call_args.args[3]
        self.assertEqual(set(body), {"name", "logpush", "observability", "subdomain", "tags", "tail_consumers"})
        self.assertEqual(body["subdomain"], {"enabled": True, "previews_enabled": False})
        self.assertEqual(phases["readback"], "explicit_off")
        self.assertEqual(phases["serving_pin"], "match")

    def test_already_explicit_off_never_writes(self):
        """Positive state reconciliation remains bracketed and independently read."""
        result, writer, _ = self.execute(prior=worker(False))
        self.assertEqual(result, "unchanged")
        writer.assert_not_called()

    def test_missing_required_projection_rejects(self):
        """Missing or mistyped required writable fields never get defaults."""
        for field in ("subdomain", "tags", "id", "logpush", "tail_consumers"):
            prior = worker()
            del prior[field]
            with self.subTest(field=field), self.assertRaises((ValueError, KeyError)):
                self.execute(prior=prior)
        for field, value in (("tags", None), ("tags", [False]), ("logpush", True),
                             ("id", "../bad"), ("tail_consumers", [{"name": "private"}]),
                             ("subdomain", {"enabled": True}),
                             ("subdomain", {"enabled": True, "previews_enabled": 0})):
            prior = worker()
            prior[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.execute(prior=prior)

    def test_unknown_or_active_capture_rejects(self):
        """Only the independent Issues switch may differ from capture-off."""
        for update in ({"unknown": False}, {"enabled": True}, {"logs": {"enabled": True}},
                       {"issues": {"enabled": "false"}}, {"issues": {"other": False}}):
            prior = worker()
            prior["observability"].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.execute(prior=prior)

    def test_preserve_optional_preferences(self):
        """Recognized inactive sampling/export preferences are never round-trip loss."""
        prior = worker(True)
        prior["observability"]["logs"]["destinations"] = ["cloudflare"]
        prior["observability"]["traces"]["propagation_policy"] = None
        current = copy.deepcopy(prior)
        current["observability"]["issues"]["enabled"] = False
        _, writer, _ = self.execute(prior=prior, current=current)
        self.assertEqual(writer.call_args.args[3]["observability"], current["observability"])
        del current["observability"]["traces"]["propagation_policy"]
        with self.assertRaises(ValueError):
            self.execute(prior=prior, current=current)

    def test_patch_identity_and_missing_readback_fail_closed(self):
        """An accepted write alone or provider omission is never an attestation."""
        for response in ({"id": "other", "name": subject.SCRIPT}, {"id": "synthetic-worker-id"}):
            with self.assertRaises(ValueError):
                self.execute(response=response)
        for issues in (None, True):
            with self.assertRaises(ValueError):
                self.execute(current=worker(issues))

    def test_unaffected_preview_references_and_subdomain_drift(self):
        """Private response-only settings must remain present and equal."""
        for field in ("tags", "subdomain", "references", "previews_base_config", "created_on"):
            current = worker(False)
            del current[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.execute(current=current)
        current = worker(False)
        current["updated_on"] = "after"
        self.assertEqual(self.execute(current=current)[0], "applied")

    def test_serving_binding_and_ambiguous_patch_fail_closed(self):
        """No drift, extra Queue, retry or fallback is admitted."""
        for reads in ([deployment(version="a" * 36)],
                      [deployment(), version(), deployment(identifier=subject.VERSION)],
                      [deployment(), version(), deployment(), version(), deployment(identifier=subject.VERSION)]):
            with self.assertRaises(ValueError):
                self.execute(reads=reads)
        extra = version()
        extra["resources"]["bindings"].append({"name": "TRACE_EVENTS", "type": "queue"})
        with self.assertRaises(ValueError):
            self.execute(reads=[deployment(), extra])
        with patch.object(subject, "patch_worker", side_effect=ValueError("PRIVATE")) as writer:
            # exercise the real transaction with the outer write mock only
            with patch.object(subject, "fetch", side_effect=[deployment(), version(), deployment()]), patch.object(
                    subject, "worker_readback", return_value=worker()), self.assertRaises(ValueError):
                subject.apply("a" * 32, "PRIVATE", subject.VERSION, {})
            self.assertEqual(writer.call_count, 1)

    def test_patch_transport_method_and_no_redirect_reader(self):
        """Use PATCH at validated current ID, not PUT or legacy scripts path."""
        with patch.object(subject, "request_result", return_value={}) as reader:
            subject.patch_worker("a" * 32, "PRIVATE", "fixed-id", subject.projection(worker()))
        request = reader.call_args.args[0]
        self.assertEqual(request.method, "PATCH")
        self.assertTrue(request.full_url.endswith("/workers/workers/fixed-id"))
        self.assertNotIn("previews_base_config", json.loads(request.data))

    def test_bounded_strict_success_decoder(self):
        """Reject duplicate fields, nonfinite JSON, overlimit and non-200 replies."""
        from urllib.request import Request
        for raw, status in ((b'{"success":true,"result":{"enabled":true,"enabled":false}}', 200),
                            (b'{"success":true,"result":{"rate":NaN}}', 200),
                            (b'{"success":false,"result":{}}', 200),
                            (b'{"success":true,"result":{}}', 201),
                            (b' ' * (subject.LIMIT + 1), 200)):
            response = MagicMock()
            response.__enter__.return_value = response
            response.status = status
            response.read.return_value = raw
            opener = MagicMock()
            opener.open.return_value = response
            with patch.object(subject, "build_opener", return_value=opener), self.assertRaises(ValueError):
                subject.request_result(Request("https://synthetic.invalid"))
            self.assertEqual(opener.open.call_count, 1)
            response.read.assert_called_once_with(subject.LIMIT + 1)

    def test_main_guards_and_private_failures(self):
        """Fixed bins hide arbitrary exception text, private identities and tokens."""
        env = {"CLOUDFLARE_ACCOUNT_ID": "a" * 32, "CLOUDFLARE_API_TOKEN": "PRIVATE_TOKEN",
               "GITHUB_SHA": "b" * 40, "GITHUB_REF": "refs/heads/codex/amail-v0.1.0",
               "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_RUN_ATTEMPT": "1",
               "AMAIL_CURRENT_WORKER_CONFIRM": subject.CONFIRM,
               "AMAIL_CURRENT_WORKER_FREEZE": subject.FREEZE,
               "AMAIL_EXPECTED_WORKER_VERSION": subject.VERSION}
        for field in ("GITHUB_RUN_ATTEMPT", "GITHUB_REF", "AMAIL_CURRENT_WORKER_FREEZE"):
            bad = dict(env, **{field: "bad"})
            with patch.dict(os.environ, bad, clear=True), patch.object(subject, "apply") as runner, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(subject.main(), 1)
                runner.assert_not_called()
        output = io.StringIO()
        with patch.dict(os.environ, env, clear=True), patch.object(subject, "apply", side_effect=RuntimeError("PRIVATE_TOKEN PRIVATE_URL")), contextlib.redirect_stdout(output):
            self.assertEqual(subject.main(), 1)
        self.assertNotIn("PRIVATE", output.getvalue())
        self.assertNotIn("attestation", output.getvalue())


if __name__ == "__main__":
    unittest.main()
