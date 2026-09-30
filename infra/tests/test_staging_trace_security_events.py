"""Synthetic privacy and schema tests for the one-shot Security Events probe."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "provider"))
import probe_staging_trace_security_events as probe  # noqa: E402


def event(*, at: str = probe.START, host: str = probe.HOST,
          action: str = "block", source: str = "botfight",
          description: str | None = "Bot Fight Mode") -> dict:
    """Construct a fake selected fieldset without real request details."""

    return {"datetime": at, "clientRequestHTTPHost": host, "action": action,
            "source": source, "description": description}


def payload(rows: list[dict]) -> dict:
    """Wrap synthetic rows in the zone-scoped GraphQL shape."""

    return {"data": {"viewer": {"zones": [{"firewallEventsAdaptive": rows}]}},
            "errors": None}


class SecurityEventTests(unittest.TestCase):
    """Fail closed on scope, page, and provider-controlled output ambiguity."""

    def test_query_is_zone_host_time_scoped_and_minimal(self) -> None:
        """The query must not request identifiers or sensitive request details."""

        for part in ("zoneTag: $zoneTag", "datetime_geq: $start", "datetime_leq: $end",
                     "clientRequestHTTPHost: $host", "limit: 100", "description"):
            self.assertIn(part, probe.QUERY)
        for forbidden in ("clientIP", "clientRequestPath", "clientRequestQuery", "rayName",
                          "userAgent", "ruleId", "requestSource"):
            self.assertNotIn(forbidden, probe.QUERY)

    def test_mitigation_is_only_candidate_not_attributed(self) -> None:
        """A same-host sampled block is only a candidate in the two-minute window."""

        self.assertEqual(probe.classify(payload([event()])), [
            "security_events_count=1",
            "security_events_bucket=action:block,source:botfight,rule:bot_fight_mode,count:1",
            "security_events_result=sampled_edge_candidate",
        ])

    def test_empty_and_nonmitigating_event_never_exonerate(self) -> None:
        """Sampling or ordinary log action cannot prove the request crossed the edge."""

        self.assertEqual(probe.classify(payload([])), [
            "security_events_count=0", "security_events_result=no_sample_or_non_edge",
        ])
        self.assertEqual(probe.classify(payload([event(action="log")])), [
            "security_events_count=1",
            "security_events_bucket=action:log,source:botfight,rule:bot_fight_mode,count:1",
            "security_events_result=no_sample_or_non_edge",
        ])

    def test_unknown_provider_text_is_never_emitted(self) -> None:
        """Free-form descriptions, sources, and actions collapse to fixed labels."""

        lines = probe.classify(payload([event(action="PRIVATE-ACTION", source="PRIVATE-SOURCE",
                                              description="PRIVATE-RULE-URL-IP")]))
        self.assertEqual(lines[1], "security_events_bucket=action:other,source:other,rule:other,count:1")
        self.assertNotIn("PRIVATE", "\n".join(lines))

    def test_bad_shape_scope_and_full_page_fail_closed(self) -> None:
        """No partial result is printed from malformed, out-of-scope, or full pages."""

        bad = [
            {}, {**payload([]), "errors": [{"message": "PRIVATE"}]},
            payload([event(host="other.example")]),
            payload([event(at="2026-09-30T04:58:41Z")]),
            payload([event(at="2026-09-30T05:00:43Z")]),
            payload([event(at="2026-09-30T04:59:42+00:00")]),
            payload([event(description=42)]),
            payload([event()] * probe.LIMIT),
            {"data": {"viewer": {"zones": []}}, "errors": None},
            {"data": {"viewer": {"zones": [{"firewallEventsAdaptive": []},
                                          {"firewallEventsAdaptive": []}]}}, "errors": None},
            payload([{**event(), "clientIP": "PRIVATE"}]),
        ]
        for value in bad:
            with self.subTest(case=type(value).__name__), self.assertRaises(probe.Unverified):
                probe.classify(value)

    def test_duplicate_keys_rejected(self) -> None:
        """A duplicate GraphQL field cannot shadow the checked host or error key."""

        with self.assertRaises(probe.Unverified):
            json.loads('{"data":{},"data":{"private":"SECRET"}}',
                       object_pairs_hook=probe._unique_object)

    def test_confirmation_and_exact_run_gate_network(self) -> None:
        """A changed confirmation or incident ID never spends the credential."""

        with patch.object(probe, "fetch") as fetch:
            for confirm, run_id in (("bad", probe.RUN_ID), (probe.CONFIRM, "other")):
                with self.assertRaises(probe.Unverified):
                    probe.run(confirm, run_id, "a" * 32, "secret")
            fetch.assert_not_called()

    def test_main_suppresses_raw_failures(self) -> None:
        """Provider exceptions and schema messages cannot enter stdout."""

        output = StringIO()
        with patch.object(probe, "fetch", side_effect=RuntimeError("PRIVATE path token")), \
             patch.dict("os.environ", {"CF_ZONE_ID": "a" * 32,
                                       "CLOUDFLARE_API_TOKEN": "PRIVATE"}), \
             patch.object(sys, "argv", ["probe", probe.CONFIRM, probe.RUN_ID]), \
             redirect_stdout(output):
            code = probe.main()
        self.assertEqual(code, 1)
        self.assertEqual(output.getvalue(), "security_events_result=unverified reason=internal\n")


if __name__ == "__main__":
    unittest.main()
