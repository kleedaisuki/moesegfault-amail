"""Synthetic contracts for historical-only Worker R2 delivery classification."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
import os
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

from infra.tests import staging_worker_r2_delivery_history as history


START = datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc)
END = START + timedelta(minutes=12)
WINDOW = (START, END)


def workflow_job(source: str, name: str) -> str:
    """Extract exactly one top-level job independent of neighboring job names."""
    pattern = rf"^  {re.escape(name)}:\n(.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)"
    matches = re.findall(pattern, source, re.MULTILINE | re.DOTALL)
    if len(matches) != 1:
        raise ValueError("workflow job missing or duplicated")
    return matches[0]


def send(status: str = "sent", cause: str | None = None,
         identity: str | None = "provider-private", final: int = 1) -> dict:
    """Construct one exact synthetic Sending row without printing its fields."""

    return {"datetime": "2026-10-01T01:04:00Z", "from": history.SENDER,
            "to": history.FIRST,
            "subject": history.TEMPLATE + history.marker(history.RUN, history.ATTEMPT),
            "messageId": identity, "status": status,
            "errorCause": cause, "isLastEvent": final}


def route(identity: str | None = "provider-private") -> dict:
    """Construct a matching Routing row without asserting Worker ownership."""

    return {"datetime": "2026-10-01T01:05:00Z", "from": history.SENDER,
            "to": history.FIRST,
            "subject": history.TEMPLATE + history.marker(history.RUN, history.ATTEMPT),
            "messageId": identity, "status": "handled", "action": "worker",
            "ruleMatched": "rule-private"}


def envelope(sending: list[dict], routing: list[dict]) -> dict:
    """Wrap only the two selected zone-level event datasets."""

    return {"data": {"viewer": {"zones": [{
        "emailSendingAdaptive": sending, "emailRoutingAdaptive": routing,
    }]}}}


class DeliveryHistoryTests(unittest.TestCase):
    """Keep positive observations narrow and sampled absence inconclusive."""

    def test_unknown_address_requires_positive_exact_terminal_event(self) -> None:
        """Classify only a unique matched provider failure cause."""

        result = history.classify(envelope([
            send("deliveryFailed", "routing_unknown_address")], []), WINDOW)
        self.assertEqual(result, ("sending_routing_unknown_address_observed", "one", "zero"))

    def test_correlated_routing_does_not_claim_intended_worker_or_r2(self) -> None:
        """A shared message ID is evidence of Routing, not R2 persistence."""

        result = history.classify(envelope([send()], [route()]), WINDOW)
        self.assertEqual(result, ("routing_correlated_observed_worker_unverified", "one", "one"))

    def test_missing_or_unjoined_events_do_not_become_negative_evidence(self) -> None:
        """Sampling and missing cross-dataset IDs prevent causal claims."""

        self.assertEqual(history.classify(envelope([], []), WINDOW)[0],
                         "historical_events_inconclusive")
        self.assertEqual(history.classify(envelope([send()], [route("different")]), WINDOW)[0],
                         "routing_id_unjoined")
        self.assertEqual(history.classify(envelope([send(identity=None)], []), WINDOW)[0],
                         "historical_events_inconclusive")

    def test_exact_subject_and_recipient_are_not_prefix_matches(self) -> None:
        """A lookalike or other-recipient event is not this probe's event."""

        wrong = send()
        wrong["subject"] += "-other"
        wrong_recipient = send()
        wrong_recipient["to"] = "foreign@example.invalid"
        self.assertEqual(history.classify(envelope([wrong, wrong_recipient], []), WINDOW)[0],
                         "historical_events_inconclusive")

    def test_lifecycle_rows_and_full_pages_are_not_duplicate_send_proof(self) -> None:
        """One message can have multiple statuses; full page is incomplete."""

        earlier = send("sent", final=0)
        later = send("deliveryFailed", "routing_unknown_address")
        self.assertEqual(history.classify(envelope([earlier, later], []), WINDOW)[0],
                         "sending_routing_unknown_address_observed")
        with self.assertRaisesRegex(history.HistoryError, "limit"):
            history.classify(envelope([send()] * history.LIMIT, []), WINDOW)
        with self.assertRaisesRegex(history.HistoryError, "scope"):
            out = send()
            out["datetime"] = "2026-10-02T01:04:00Z"
            history.classify(envelope([out], []), WINDOW)

    def test_missing_final_or_multiple_ids_remain_inconclusive(self) -> None:
        """Contradictory lifecycle evidence cannot establish terminal cause."""

        self.assertEqual(history.classify(envelope([send(final=0), send(final=0)], []),
                                          WINDOW)[0], "historical_events_inconclusive")
        self.assertEqual(history.classify(envelope([send(), send(identity="other")], []),
                                          WINDOW)[0], "historical_events_inconclusive")
        self.assertEqual(history.classify(envelope([
            send("deliveryFailed", "routing_unknown_address", final=0)], []),
            WINDOW)[0], "sending_event_observed_status_unverified")

    def test_one_graphql_read_has_no_marker_or_address_in_query(self) -> None:
        """Only a fixed time-scoped analytics request reaches the provider."""

        class Reply:
            """Return a bounded synthetic provider reply without network use."""

            status = 200

            def __enter__(self):
                """Model urllib's response context."""

                return self

            def __exit__(self, *_args):
                """Close the synthetic response."""

                return None

            def read(self, _limit):
                """Return only an empty pair of event datasets."""

                return json.dumps(envelope([], [])).encode()

        with patch.object(history.OPENER, "open", return_value=Reply()) as opening:
            self.assertEqual(history.fetch("a" * 32, "token-private", WINDOW),
                             envelope([], []))
        self.assertEqual(opening.call_count, 1)
        request = opening.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.full_url, history.API)
        self.assertNotIn(history.marker(history.RUN, history.ATTEMPT), request.data.decode())
        self.assertNotIn(history.FIRST, request.data.decode())
        self.assertNotIn(history.SENDER, request.data.decode())

    def test_historical_step_provenance_and_fixed_window(self) -> None:
        """Derive the UTC interval only from the reviewed original probe step."""

        run = {"id": int(history.RUN), "run_attempt": 1, "event": "workflow_dispatch",
               "status": "completed", "conclusion": "failure", "head_sha": history.SHA,
               "head_branch": history.BRANCH, "path": history.WORKFLOW,
               "created_at": "2026-10-01T00:58:00Z", "updated_at": "2026-10-01T01:11:00Z"}
        step = {"name": history.PROBE_STEP_NAME, "status": "completed",
                "conclusion": "failure", "started_at": "2026-10-01T01:00:00Z",
                "completed_at": "2026-10-01T01:10:00Z"}
        job = {"name": history.JOB_NAME, "run_id": int(history.RUN),
               "head_sha": history.SHA, "status": "completed", "conclusion": "failure",
               "started_at": "2026-10-01T00:59:00Z",
               "completed_at": "2026-10-01T01:10:30Z", "steps": [step]}
        jobs = {"total_count": 1, "jobs": [job]}
        with patch.object(history, "github_json", side_effect=[run, jobs]), \
                patch.object(history, "datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime(2026, 10, 1, 2, tzinfo=timezone.utc)
            self.assertEqual(history.historical_window("token-private"),
                             (datetime(2026, 10, 1, 0, 58, tzinfo=timezone.utc),
                              datetime(2026, 10, 1, 1, 20, tzinfo=timezone.utc)))
        bad = dict(jobs)
        bad["jobs"] = [dict(job, steps=[dict(step, name="other")])]
        with patch.object(history, "github_json", side_effect=[run, bad]), \
                self.assertRaisesRegex(history.HistoryError, "provenance"):
            history.historical_window("token-private")

    def test_no_private_values_reach_output_or_stderr(self) -> None:
        """Even an unexpected provider failure prints only a fixed label."""

        stdout, stderr = StringIO(), StringIO()
        env = {"CF_ZONE_ID": "a" * 32, "CF_OBSERVABILITY_TOKEN": "token-private",
               "GITHUB_TOKEN": "github-private", "GITHUB_REPOSITORY": history.REPOSITORY}
        with patch.dict(os.environ, env), patch.object(sys, "argv", ["probe", history.CONFIRM,
                                                                     history.RUN]), \
                patch.object(history, "historical_window", return_value=WINDOW), \
                patch.object(history, "fetch", side_effect=ValueError("raw-private")), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(history.main(), 1)
        self.assertEqual(stdout.getvalue(), "worker_r2_history=UNVERIFIED reason=internal\n")
        self.assertEqual(stderr.getvalue(), "")
        self.assertNotIn("private", stdout.getvalue() + stderr.getvalue())

    def test_workflow_job_boundary_ignores_inserted_neighbor(self) -> None:
        """A newly adjacent credential-bearing job cannot pollute per-job checks."""
        name = "staging-worker-r2-delivery-history"
        owned = "    steps:\n      - env:\n          CF_OBSERVABILITY_TOKEN: owned\n"
        source = "jobs:\n  " + name + ":\n" + owned + (
            "  arbitrary-inserted-job:\n    steps:\n      - env:\n"
            "          CF_OBSERVABILITY_TOKEN: unrelated\n"
            "  staging-second-principal-preflight:\n    steps: []\n")
        self.assertEqual(workflow_job(source, name), owned)
        self.assertEqual(workflow_job(source, name).count("CF_OBSERVABILITY_TOKEN"), 1)
        self.assertEqual(workflow_job("jobs:\n  " + name + ":\n" + owned, name), owned)
        for invalid in ("jobs:\n", source + "  " + name + ":\n" + owned):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    workflow_job(invalid, name)

    def test_workflow_is_manual_staging_and_tests_before_secrets(self) -> None:
        """Keep the historical read separate from every mutating probe target."""

        workflow = (Path(__file__).resolve().parents[2] / ".github" / "workflows" /
                    "ci.yml").read_text(encoding="utf-8")
        block = workflow_job(workflow, "staging-worker-r2-delivery-history")
        self.assertIn("github.event_name == 'workflow_dispatch'", block)
        self.assertIn("github.ref == 'refs/heads/codex/amail-v0.1.0'", block)
        self.assertIn("environment: staging", block)
        self.assertIn("actions: read", block)
        self.assertIn(history.CONFIRM, block)
        self.assertLess(block.index("Test fixed historical event and privacy contracts"),
                        block.index("CF_OBSERVABILITY_TOKEN: ${{ secrets.CF_OBSERVABILITY_TOKEN }}"))
        self.assertEqual(block.count("CF_OBSERVABILITY_TOKEN: ${{ secrets.CF_OBSERVABILITY_TOKEN }}"), 1)
        self.assertNotIn("CLOUDFLARE_API_TOKEN", block)
        self.assertNotIn("CF_EMAIL_ROUTING_TOKEN", block)
        self.assertNotIn("staging_worker_created_r2.py", block)


if __name__ == "__main__":
    unittest.main()
