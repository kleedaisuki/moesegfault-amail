"""Synthetic privacy and correlation checks for one historical Cron log oracle."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from infra.tests import staging_role_phase_logs as probe


def row(label: str, request: str = "request-12345678", trigger: str = "scheduled",
        version: str = probe.VERSION, kind: str = "cf-worker-log") -> dict:
    """Construct a synthetic Cloudflare application-log envelope."""

    return {
        "timestamp": probe.START + 1,
        "$metadata": {"service": probe.SERVICE, "requestId": request, "type": kind,
                      "message": {"message": label}},
        "$workers": {"eventType": trigger, "scriptName": probe.SERVICE,
                     "requestId": request,
                     "scriptVersion": {"id": version}},
        "source": {"message": label},
    }


class RolePhaseLogTests(unittest.TestCase):
    """Reject cross-run, unreviewed, truncated, and false phase evidence."""

    def test_same_invocation_failure(self) -> None:
        """Correlate digest and destination failure using only an opaque key."""

        records = [row("role alert digest accepted groups=1"),
                   row("role monitor phase=destination failed"),
                   row("role monitor health check failed")]
        self.assertEqual(probe.classify(records), "same_invocation_destination_failed")

    def test_failure_in_other_invocation_is_not_attributed(self) -> None:
        """A later Cron failure cannot explain an earlier accepted digest."""

        records = [row("role alert digest accepted groups=1"),
                   row("role monitor phase=routes failed", "request-87654321")]
        self.assertEqual(probe.classify(records), "digest_only_inconclusive")

    def test_failed_phase_and_healthy_are_contradictory(self) -> None:
        """Never publish a root cause from an impossible control-flow pairing."""

        records = [row("role alert digest accepted groups=1"),
                   row("role monitor phase=destination failed"),
                   row("role monitor healthy pending=0")]
        with self.assertRaisesRegex(probe.ProbeError, "invocation_phase_ambiguous"):
            probe.classify(records)

    def test_accepted_digest_and_failed_digest_are_contradictory(self) -> None:
        """The accepted marker is flush_alerts' last action before success."""

        records = [row("role alert digest accepted groups=1"),
                   row("role monitor phase=digest failed")]
        with self.assertRaisesRegex(probe.ProbeError, "invocation_phase_ambiguous"):
            probe.classify(records)

    def test_email_arrival_is_not_parsed_as_cron(self) -> None:
        """Skip dynamic Email Handler references without displaying them."""

        records = [row("role arrival accepted role=staging_probe ref=secret", trigger="email"),
                   row("role alert digest accepted groups=1")]
        self.assertEqual(probe.classify(records), "digest_only_inconclusive")

    def test_unknown_scheduled_text_fails_closed(self) -> None:
        """Never silently treat an unreviewed Cron payload as harmless."""

        with self.assertRaisesRegex(probe.ProbeError, "scheduled_text_unreviewed"):
            probe.classify([row("private destination: do not print")])

    def test_provider_invocation_event_is_not_an_app_log(self) -> None:
        """Skip only Cloudflare's typed Cron invocation summary."""

        records = [row("opaque provider Cron summary", kind="cf-worker-event"),
                   row("role alert digest accepted groups=1")]
        self.assertEqual(probe.classify(records), "digest_only_inconclusive")
        unknown = row("opaque provider Cron summary")
        unknown["$metadata"].pop("type")
        with self.assertRaisesRegex(probe.ProbeError, "scheduled_kind_unverified"):
            probe.classify([unknown])

    def test_wrapper_shape_and_unknown_text_have_distinct_safe_codes(self) -> None:
        """Do not print a payload when the provider wrapper differs."""

        bad_source = row("role monitor healthy pending=0")
        bad_source["source"] = {"unreviewed": "private text"}
        with self.assertRaisesRegex(probe.ProbeError, "scheduled_source_shape_unreviewed"):
            probe.classify([bad_source])
        bad_message = row("role monitor healthy pending=0")
        bad_message["$metadata"]["message"] = {"unreviewed": "private text"}
        with self.assertRaisesRegex(probe.ProbeError, "scheduled_message_shape_unreviewed"):
            probe.classify([bad_message])

    def test_version_and_scope_fail_closed(self) -> None:
        """A log from another revision or service cannot be attributed."""

        with self.assertRaisesRegex(probe.ProbeError, "historical_version_unverified"):
            probe.classify([row("role monitor healthy pending=0", version="other")])
        outside = row("role monitor healthy pending=0")
        outside["$metadata"]["service"] = "another-worker"
        with self.assertRaisesRegex(probe.ProbeError, "service_scope_unverified"):
            probe.classify([outside])
        wrong_script = row("role monitor healthy pending=0")
        wrong_script["$workers"]["scriptName"] = "another-worker"
        with self.assertRaisesRegex(probe.ProbeError, "worker_scope_unverified"):
            probe.classify([wrong_script])
        missing_script = row("role monitor healthy pending=0")
        del missing_script["$workers"]["scriptName"]
        with self.assertRaisesRegex(probe.ProbeError, "worker_scope_unverified"):
            probe.classify([missing_script])

    def test_query_echo_and_pagination_fail_closed(self) -> None:
        """A changed time window or incomplete page is never absence proof."""

        good_run = {"status": "COMPLETED", "dry": True,
                    "timeframe": {"from": probe.START, "to": probe.END},
                    "query": {"parameters": {"datasets": [], "filterCombination": "and",
                                             "filters": [{"key": "$metadata.service",
                                                          "operation": "eq", "type": "string",
                                                          "value": probe.SERVICE}]}}}
        envelope = {"success": True, "result": {"run": good_run,
                                                 "events": {"count": 1, "events": [row("role monitor healthy pending=0")]}}}
        with patch.object(probe, "read_json", return_value=envelope):
            self.assertEqual(len(probe.retained_events("a" * 32, "opaque")), 1)
        shifted = {**envelope, "result": {**envelope["result"], "run": {
            **good_run, "timeframe": {"from": probe.START - 1, "to": probe.END}}}}
        with patch.object(probe, "read_json", return_value=shifted):
            with self.assertRaisesRegex(probe.ProbeError, "query_incomplete_or_echo_unverified"):
                probe.retained_events("a" * 32, "opaque")
        complete_row = row("role monitor healthy pending=0")
        complete_row["$metadata"]["id"] = "event-1"
        partial = {**envelope, "result": {**envelope["result"],
                                           "events": {"count": 2, "events": [complete_row]}}}
        with patch.object(probe, "read_json", return_value=partial):
            with self.assertRaisesRegex(probe.ProbeError, "events_page_incomplete"):
                probe.retained_events("a" * 32, "opaque")
        missing_cursor = {**partial, "result": {**partial["result"],
                                                 "events": {"count": 2,
                                                            "events": [row("role monitor healthy pending=0")]}}}
        with patch.object(probe, "read_json", return_value=missing_cursor):
            with self.assertRaisesRegex(probe.ProbeError, "events_cursor_unverified"):
                probe.retained_events("a" * 32, "opaque")

    def test_historical_run_pin(self) -> None:
        """Only the original failed Actions run can authorize the query."""

        run = {"id": int(probe.RUN), "head_sha": probe.SHA, "conclusion": "failure",
               "status": "completed", "event": "workflow_dispatch",
               "head_branch": "codex/amail-v0.1.0", "path": ".github/workflows/ci.yml@main"}
        with patch.object(probe, "read_json", return_value=run):
            probe.historical_run("opaque")
        with patch.object(probe, "read_json", return_value={**run, "head_sha": "other"}):
            with self.assertRaisesRegex(probe.ProbeError, "historical_run_unverified"):
                probe.historical_run("opaque")


if __name__ == "__main__":
    unittest.main()
