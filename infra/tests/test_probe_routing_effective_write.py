"""Synthetic state-machine tests for the one-rule staging Write probe."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import pathlib
import sys
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch


SOURCE = pathlib.Path(__file__).resolve().parents[1] / "provider" / "probe_routing_effective_write.py"
SPEC = importlib.util.spec_from_file_location("probe_routing_effective_write", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
RUN, ATTEMPT = "123456", "1"
SECRET, TOKEN = "synthetic-private-password", "synthetic-private-token"
ALIAS, NAME = MODULE.identity(SECRET, RUN, ATTEMPT)
RULE = {
    "id": "a" * 32, "name": NAME, "enabled": False, "source": "api",
    "matchers": [{"type": "literal", "field": "to", "value": ALIAS}],
    "actions": [{"type": "worker", "value": [MODULE.WORKER]}],
}
ENV = {
    "STAGING_E2E_PASSWORD": SECRET, "CF_EMAIL_ROUTING_TOKEN": TOKEN,
    "GITHUB_RUN_ID": RUN, "GITHUB_RUN_ATTEMPT": ATTEMPT,
    "CF_ZONE_ID": MODULE.ZONE,
}


class EffectiveWriteProbeTest(unittest.TestCase):
    """Pin no-foreign-delete, no-second-POST, and recovery privacy invariants."""

    def _run(self, mode: str, calls: list[tuple[int, dict]], *, run: str = RUN) -> tuple[int, str, list]:
        """Drive the command with mocked Cloudflare HTTP responses."""

        output = io.StringIO()
        confirm = {"probe": MODULE.PROBE_CONFIRM, "recover": MODULE.RECOVER_CONFIRM, "audit": MODULE.AUDIT_CONFIRM}[mode]
        with patch.dict("os.environ", ENV), patch.object(MODULE, "call", side_effect=calls) as request, contextlib.redirect_stdout(output):
            result = MODULE.main(["probe", mode, confirm, run, ATTEMPT])
        return result, output.getvalue(), request.call_args_list

    @staticmethod
    def listing(rows: list[dict]) -> tuple[int, dict]:
        """Provide exact one-page Cloudflare pagination metadata."""

        return 200, {
            "success": True, "result": rows,
            "result_info": {"page": 1, "per_page": 50, "count": len(rows), "total_count": len(rows), "total_pages": 1},
        }

    def test_probe_success_creates_disabled_rule_then_deletes_exact_id(self) -> None:
        """A valid Write result requires create/readback/GET/delete/absence."""

        calls = [
            self.listing([]), (201, {"success": True, "result": RULE}), self.listing([RULE]),
            self.listing([RULE]), (200, {"success": True, "result": RULE}),
            (204, {}), self.listing([]),
        ]
        code, output, requests = self._run("probe", calls)
        self.assertEqual(code, 0)
        self.assertEqual(output, "routing_write_probe=created\nrouting_write_cleanup=removed\nrouting_write_audit=pending\n")
        self.assertEqual([call.args[0] for call in requests].count("POST"), 1)
        self.assertEqual([call.args[0] for call in requests].count("DELETE"), 1)
        self.assertEqual(requests[1].args[3]["enabled"], False)
        self.assertNotIn(ALIAS, output)
        self.assertNotIn(RULE["id"], output)
        self.assertNotIn(TOKEN, output)

    def test_403_is_numeric_and_no_delete(self) -> None:
        """An explicit provider denial is not a Write grant."""

        calls = [self.listing([]), (403, {"errors": [{"code": 10000, "message": ALIAS + TOKEN}]}), self.listing([])]
        code, output, requests = self._run("probe", calls)
        self.assertEqual(code, 1)
        self.assertEqual(output, "routing_write_probe=rejected_http_403_codes_10000\nrouting_write_cleanup=absent_after_denial\nrouting_write_audit=pending\n")
        self.assertNotIn(ALIAS, output)
        self.assertNotIn(TOKEN, output)
        self.assertFalse(any(call.args[0] == "DELETE" for call in requests))

    def test_timeout_after_commit_still_removes_but_fails(self) -> None:
        """Ambiguous POST is never retried even if its rule appears later."""

        calls = [self.listing([]), (0, {}), self.listing([RULE]), self.listing([RULE]),
                 (200, {"success": True, "result": RULE}), (204, {}), self.listing([])]
        code, output, requests = self._run("probe", calls)
        self.assertEqual(code, 1)
        self.assertIn("routing_write_probe=create_outcome_uncertain", output)
        self.assertIn("routing_write_cleanup=removed", output)
        self.assertEqual([call.args[0] for call in requests].count("POST"), 1)

    def test_existing_foreign_alias_blocks_probe_and_recovery(self) -> None:
        """Neither mode takes over an unrelated rule with the same address."""

        foreign = {**RULE, "actions": [{"type": "drop"}]}
        for mode in ("probe", "recover"):
            code, output, requests = self._run(mode, [self.listing([foreign])])
            self.assertEqual(code, 1)
            self.assertIn("probe_failed=", output)
            self.assertFalse(any(call.args[0] in ("POST", "DELETE") for call in requests))

    def test_recover_exact_rule_and_absent_rule(self) -> None:
        """Recovery can run independently for a killed probe's coordinates."""

        calls = [self.listing([RULE]), (200, {"success": True, "result": RULE}), (204, {}), self.listing([])]
        code, output, requests = self._run("recover", calls)
        self.assertEqual((code, output), (0, "routing_write_recovery=removed\n"))
        self.assertFalse(any(call.args[0] == "POST" for call in requests))
        self.assertEqual(self._run("recover", [self.listing([])])[:2], (0, "routing_write_recovery=absent\n"))

    def test_delayed_audit_is_read_only(self) -> None:
        """The independently dispatched audit only checks exact absence."""

        code, output, requests = self._run("audit", [self.listing([])])
        self.assertEqual((code, output), (0, "routing_write_audit=absent\n"))
        self.assertEqual([call.args[0] for call in requests], ["GET"])
        code, output, requests = self._run("audit", [self.listing([RULE])])
        self.assertEqual((code, output), (1, "routing_write_audit=present\n"))
        self.assertEqual([call.args[0] for call in requests], ["GET"])

    def test_get_mismatch_never_deletes(self) -> None:
        """A changed rule between inventory and GET cannot be removed."""

        changed = {**RULE, "enabled": True}
        code, output, requests = self._run("recover", [self.listing([RULE]), (200, {"success": True, "result": changed})])
        self.assertEqual(code, 1)
        self.assertIn("recovery_get_http_200", output)
        self.assertFalse(any(call.args[0] == "DELETE" for call in requests))

    def test_get_id_mismatch_never_deletes(self) -> None:
        """Shape equality cannot substitute for the exact fetched rule ID."""

        other_id = {**RULE, "id": "b" * 32}
        code, output, requests = self._run("recover", [self.listing([RULE]), (200, {"success": True, "result": other_id})])
        self.assertEqual(code, 1)
        self.assertIn("recovery_get_http_200", output)
        self.assertFalse(any(call.args[0] == "DELETE" for call in requests))

    def test_created_response_id_must_match_list_id(self) -> None:
        """A different exact-shape list ID cannot prove this POST created it."""

        different = {**RULE, "id": "b" * 32}
        calls = [self.listing([]), (201, {"success": True, "result": different}), self.listing([RULE])]
        code, output, requests = self._run("probe", calls)
        self.assertEqual(code, 1)
        self.assertIn("routing_write_probe=create_id_mismatch", output)
        self.assertIn("routing_write_cleanup=frozen_ownership", output)
        self.assertEqual([call.args[0] for call in requests].count("POST"), 1)
        self.assertFalse(any(call.args[0] == "DELETE" for call in requests))

    def test_denial_with_matching_rule_freezes_ownership(self) -> None:
        """A 403 cannot authorize deleting an apparently matching foreign rule."""

        calls = [self.listing([]), (403, {"success": False}), self.listing([RULE])]
        code, output, requests = self._run("probe", calls)
        self.assertEqual(code, 1)
        self.assertIn("routing_write_probe=create_denial_conflict", output)
        self.assertIn("routing_write_cleanup=frozen_after_denial", output)
        self.assertFalse(any(call.args[0] == "DELETE" for call in requests))

    def test_denial_readback_failure_cannot_delete_later_candidate(self) -> None:
        """Even a transient read failure after 403 cannot unlock cleanup."""

        calls = [self.listing([]), (403, {"success": False}), (503, {})]
        code, output, requests = self._run("probe", calls)
        self.assertEqual(code, 1)
        self.assertIn("routing_write_cleanup=frozen_after_denial", output)
        self.assertFalse(any(call.args[0] == "DELETE" for call in requests))

    def test_failed_first_readback_cannot_delete_different_id_later(self) -> None:
        """The POST ID remains an ownership constraint through finally cleanup."""

        post_rule = {**RULE, "id": "b" * 32}
        calls = [self.listing([]), (201, {"success": True, "result": post_rule}),
                 (503, {}), self.listing([RULE])]
        code, output, requests = self._run("probe", calls)
        self.assertEqual(code, 1)
        self.assertIn("routing_write_probe=create_readback_unverified", output)
        self.assertIn("routing_write_cleanup=frozen_ownership", output)
        self.assertFalse(any(call.args[0] == "DELETE" for call in requests))

    def test_ambiguous_delete_reconciles_without_replay(self) -> None:
        """A timed-out DELETE with complete absence is not sent again."""

        calls = [self.listing([RULE]), (200, {"success": True, "result": RULE}),
                 (0, {}), self.listing([])]
        code, output, requests = self._run("recover", calls)
        self.assertEqual((code, output), (0, "routing_write_recovery=absent_after_ambiguous_delete\n"))
        self.assertEqual([call.args[0] for call in requests].count("DELETE"), 1)

    def test_name_collision_and_malformed_foreign_action_block_create(self) -> None:
        """Complete inventory validates non-candidate action shapes too."""

        collision = {**RULE, "matchers": [{"type": "literal", "field": "to", "value": "other@" + MODULE.DOMAIN}]}
        malformed = {**RULE, "name": "other", "actions": [{"type": "worker", "value": "not-an-array"}]}
        for rule in (collision, malformed):
            code, _, requests = self._run("probe", [self.listing([rule])])
            self.assertEqual(code, 1)
            self.assertFalse(any(call.args[0] == "POST" for call in requests))

    def test_capacity_counts_rules_not_matchers(self) -> None:
        """Multiple staging literals in one foreign rule consume one rule slot."""

        foreign = {**RULE, "name": "other", "matchers": [
            {"type": "literal", "field": "to", "value": "one@" + MODULE.DOMAIN},
            {"type": "literal", "field": "to", "value": "two@" + MODULE.DOMAIN},
        ]}
        matched, count = MODULE.target_rules([foreign], ALIAS, NAME)
        self.assertEqual((matched, count), ([], 1))

    def test_incomplete_inventory_blocks_mutation(self) -> None:
        """Page metadata contradictions fail before POST or DELETE."""

        bad = self.listing([])
        bad[1]["result_info"]["total_count"] = 1
        code, output, requests = self._run("probe", [bad])
        self.assertEqual(code, 1)
        self.assertIn("inventory_invalid", output)
        self.assertEqual(len(requests), 1)

    def test_later_page_candidate_blocks_create(self) -> None:
        """Preflight must scan all pages, not just a convenient first page."""

        foreign = {"id": "b" * 32, "name": "other", "enabled": True, "source": "api",
                   "matchers": [{"type": "literal", "field": "to", "value": "other@example.com"}],
                   "actions": [{"type": "drop"}]}
        page_one = (200, {"success": True, "result": [{**foreign, "id": f"{index:032x}"} for index in range(50)],
                          "result_info": {"page": 1, "per_page": 50, "count": 50, "total_count": 51, "total_pages": 2}})
        page_two = (200, {"success": True, "result": [RULE],
                          "result_info": {"page": 2, "per_page": 50, "count": 1, "total_count": 51, "total_pages": 2}})
        code, output, requests = self._run("probe", [page_one, page_two])
        self.assertEqual(code, 1)
        self.assertIn("probe_alias_not_absent", output)
        self.assertEqual([call.args[0] for call in requests], ["GET", "GET"])
        drift = (200, {**page_two[1], "result_info": {**page_two[1]["result_info"], "total_count": 52}})
        code, output, requests = self._run("probe", [page_one, drift])
        self.assertEqual(code, 1)
        self.assertIn("inventory_invalid", output)
        self.assertEqual([call.args[0] for call in requests], ["GET", "GET"])

    def test_duplicate_rule_id_across_pages_blocks_create(self) -> None:
        """A stable total count does not hide pagination reorder or omission."""

        foreign = {"id": "b" * 32, "name": "other", "enabled": True, "source": "api",
                   "matchers": [{"type": "literal", "field": "to", "value": "other@example.com"}],
                   "actions": [{"type": "drop"}]}
        first = (200, {"success": True, "result": [{**foreign, "id": f"{index:032x}"} for index in range(50)],
                       "result_info": {"page": 1, "per_page": 50, "count": 50, "total_count": 51, "total_pages": 2}})
        second = (200, {"success": True, "result": [{**foreign, "id": f"{0:032x}"}],
                        "result_info": {"page": 2, "per_page": 50, "count": 1, "total_count": 51, "total_pages": 2}})
        code, output, requests = self._run("probe", [first, second])
        self.assertEqual(code, 1)
        self.assertIn("inventory_invalid", output)
        self.assertFalse(any(call.args[0] == "POST" for call in requests))

    def test_timeout_and_malformed_2xx_are_uncertain_even_when_absent(self) -> None:
        """An initially absent readback does not prove an uncertain POST failed."""

        for reply in ((0, {}), (200, {"success": True, "result": {}})):
            calls = [self.listing([]), reply, self.listing([]), self.listing([])]
            code, output, requests = self._run("probe", calls)
            self.assertEqual(code, 1)
            self.assertIn("routing_write_probe=create_outcome_uncertain_http_", output)
            self.assertEqual([call.args[0] for call in requests].count("POST"), 1)

    def test_credentials_loaded_only_after_confirmation(self) -> None:
        """A wrong confirmation neither loads secrets nor makes a network call."""

        with patch.object(MODULE, "call") as request, patch.dict("os.environ", ENV), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(MODULE.main(["probe", "probe", "wrong", RUN, ATTEMPT]), 1)
        request.assert_not_called()

    def test_redirect_is_not_followed_with_bearer(self) -> None:
        """A provider 30x response cannot redirect the scoped bearer elsewhere."""

        request = urllib.request.Request("https://api.cloudflare.com/client/v4/test")
        self.assertIsNone(MODULE.NoRedirect().redirect_request(request, None, 302, "redirect", {}, "https://other.example/"))
        error = urllib.error.HTTPError(request.full_url, 302, "redirect", {}, io.BytesIO(b"{}"))
        with patch.object(MODULE._NO_REDIRECT, "open", side_effect=error) as opener:
            self.assertEqual(MODULE.call("GET", "/zones/x/email/routing/rules", TOKEN), (302, {}))
        self.assertEqual(opener.call_count, 1)


if __name__ == "__main__":
    unittest.main()
