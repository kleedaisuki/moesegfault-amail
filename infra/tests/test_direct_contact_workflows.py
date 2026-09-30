"""Hosted source contracts for contact operations; never invoke live helpers.

Workflow syntax is checked independently by the existing hosted YAML guard.
These assertions preserve authorization, privacy and pre-mutation ordering.
"""

from itertools import product
from pathlib import Path
import re
import unittest

from workflow_source import job_block

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
CHECKOUT = "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683"


def source(name: str) -> str:
    """Read only the scoped workflow, preserving expressions and shell text."""
    return (WORKFLOWS / name).read_text(encoding="utf-8-sig")


class DirectContactWorkflowTests(unittest.TestCase):
    """Manual ownership, periodic freshness and provider mutations stay separate."""

    def test_manual_paths_are_protected_main_only_and_held(self):
        """Adoption cannot unhold; coverage never comes from a scheduled job."""
        for name, job in (("direct-contact-adopt.yml", "adopt"),
                          ("direct-contact-attest.yml", "attest")):
            with self.subTest(workflow=name):
                text = source(name)
                head = text.split("permissions:", 1)[0]
                block = job_block(text, job)
                self.assertIn("workflow_dispatch:", head)
                self.assertNotIn("schedule:", head)
                self.assertIn("github.event_name == 'workflow_dispatch'", block)
                self.assertIn("github.ref == 'refs/heads/main'", block)
                self.assertIn("environment: ${{ inputs.target }}", block)
                self.assertIn(CHECKOUT, block)
                self.assertIn("persist-credentials: false", block)
                self.assertNotIn("send_control.py", block)
                self.assertNotIn("ROLE_FORWARD_DESTINATION", block)
                self.assertNotIn("CF_EMAIL_ROUTING_TOKEN", block)

    def test_adoption_pins_exact_current_contract_without_input_shell_expansion(self):
        """A stale manual request must not replace a newer adopted identity."""
        text = source("direct-contact-adopt.yml")
        block = job_block(text, "adopt")
        for suffix, key in (("EXPECTED_CONTACT_CONTRACT_ID", "expected_contact_contract_id"),
                            ("DESTINATION_ID", "destination_id"),
                            ("APEX_ABUSE_RULE_ID", "apex_abuse_rule_id"),
                            ("APEX_POSTMASTER_RULE_ID", "apex_postmaster_rule_id"),
                            ("MAIL_ABUSE_RULE_ID", "mail_abuse_rule_id"),
                            ("MAIL_POSTMASTER_RULE_ID", "mail_postmaster_rule_id"),
                            ("CASE_REF", "case_ref"), ("CONFIRM", "confirm")):
            self.assertIn(f"INPUT_{suffix}: ${{{{ inputs.{key} }}}}", block)
        self.assertIn("ADOPT_DIRECT_CONTACT_HELD", text)
        self.assertIn("run: python infra/operator/direct_contact_policy.py", block)
        self.assertNotRegex(block, r"run:.*\$\{\{")
        self.assertLessEqual(len(re.findall(r"^      [a-z_]+:$", text, re.M)), 25)

    def test_human_attestation_requires_exact_contract_and_explicit_phrase(self):
        """Revocation defaults false and requires no affirmative coverage input."""
        text = source("direct-contact-attest.yml")
        block = job_block(text, "attest")
        self.assertIn("default: 'false'", text)
        self.assertIn("options: ['false', 'true']", text)
        self.assertIn("ACCEPT_INBOX_JUNK_AND_24H_CLOUDFLARE_RESPONSE", text)
        self.assertIn("INPUT_GATE: abuse_contact_verified", block)
        self.assertIn("INPUT_CONTACT_CONTRACT_ID: ${{ inputs.contact_contract_id }}", block)
        self.assertIn("INPUT_CONTACT_COVERAGE: ${{ inputs.contact_coverage }}", block)
        self.assertIn("INPUT_VERIFIED: ${{ inputs.verified }}", block)
        self.assertIn("run: python infra/operator/attest_gate.py", block)
        # The original generic workflow cannot manufacture missing human evidence.
        legacy = source("attest-send-gate.yml")
        self.assertNotIn("INPUT_CONTACT_COVERAGE:", legacy)
        self.assertNotIn("INPUT_CONTACT_CONTRACT_ID:", legacy)

    def test_hourly_refresh_is_production_only_or_explicit_manual_realm(self):
        """No environment approval, fallback grant, upload or hidden write lane."""
        text = source("direct-contact-health.yml")
        block = job_block(text, "refresh")
        self.assertIn("cron: '17 * * * *'", text)
        self.assertIn("github.ref == 'refs/heads/main'", block)
        self.assertIn("github.event_name == 'schedule'", block)
        self.assertIn("github.event_name == 'workflow_dispatch'", block)
        self.assertIn("INPUT_TARGET: ${{ inputs.target || 'production' }}", block)
        self.assertIn("INPUT_SKIP_UNADOPTED_HELD: 'true'", block)
        for secret in ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN",
                       "CF_EMAIL_ROUTING_TOKEN", "ROLE_FORWARD_DESTINATION"):
            self.assertIn(f"{secret}: ${{{{ secrets.{secret} }}}}", block)
        self.assertIn("run: python infra/operator/direct_contact_health.py", block)
        self.assertNotRegex(block, re.compile(r"^    environment:", re.M))
        for forbidden in ("continue-on-error:", "|| true", "always()", "upload-artifact",
                          "attest_gate.py", "send_control.py", "ensure_role_forwarding.py",
                          "direct_contact_policy.py", "GITHUB_STEP_SUMMARY", "wrangler"):
            self.assertNotIn(forbidden, block)

    def test_health_schedule_requires_activation_but_manual_does_not(self):
        """Evaluate the source predicate against synthetic events, never providers.

        The narrow source grammar fixes precedence and job-level placement.
        GitHub compares strings case-insensitively and missing vars are empty.
        This is a contract model, not a replacement for hosted workflow lint.
        """
        block = job_block(source("direct-contact-health.yml"), "refresh")
        guards = re.findall(r"^    if: (.+)$", block, re.M)
        self.assertEqual(len(guards), 1)
        predicate = re.fullmatch(
            r"github\.ref == '([^']+)' && "
            r"\(github\.event_name == '([^']+)' \|\| "
            r"\(github\.event_name == '([^']+)' && "
            r"vars\.AMAIL_CONTACT_HEALTH_ACTIVE == '([^']+)'\)\)",
            guards[0],
        )
        self.assertIsNotNone(predicate)
        main, manual, scheduled, active = predicate.groups()
        self.assertEqual((main, manual, scheduled, active),
                         ("refs/heads/main", "workflow_dispatch", "schedule", "true"))
        cases = product(
            ("refs/heads/main", "refs/heads/candidate", "refs/tags/v1"),
            ("schedule", "workflow_dispatch", "push", "pull_request"),
            (None, "", "false", "1", "yes", " true ", "true", "TRUE"),
        )
        for ref, event, value in cases:
            with self.subTest(ref=ref, event=event, activation=value):
                variable = "" if value is None else value
                observed = ref.casefold() == main.casefold() and (
                    event.casefold() == manual.casefold() or (
                        event.casefold() == scheduled.casefold()
                        and variable.casefold() == active.casefold()
                    )
                )
                expected = ref == "refs/heads/main" and (
                    event == "workflow_dispatch" or (
                        event == "schedule" and value in ("true", "TRUE")
                    )
                )
                self.assertEqual(observed, expected)

    def test_all_contact_mutation_paths_share_a_non_canceling_realm_lock(self):
        """A health job cannot refresh concurrently with provider mutation/unhold."""
        for name in ("direct-contact-adopt.yml", "direct-contact-attest.yml",
                     "direct-contact-health.yml", "send-control.yml",
                     "attest-send-gate.yml", "role-forwarding.yml"):
            with self.subTest(workflow=name):
                head = source(name).split("jobs:", 1)[0]
                self.assertIn("group: amail-direct-contact-", head)
                self.assertIn("cancel-in-progress: false", head)
        self.assertIn("group: amail-direct-contact-production", source("role-forwarding.yml"))

    def test_provider_mutation_invalidates_before_routes_but_audit_is_read_only(self):
        """Missing migration/failed containment denies before any provider side effect."""
        block = job_block(source("role-forwarding.yml"), "reconcile")
        barrier = block.index("name: Invalidate contact acceptance and prove production global hold")
        provider = block.index("name: Reconcile private destination and exact role rules")
        self.assertLess(barrier, provider)
        containment = block[barrier:provider]
        self.assertIn("if: inputs.phase != 'audit'", containment)
        self.assertIn("INPUT_TARGET: production", containment)
        self.assertIn("INPUT_CASE_REF: ${{ inputs.case_ref }}", containment)
        self.assertIn("run: python infra/operator/direct_contact_invalidate.py", containment)
        self.assertNotIn("continue-on-error:", block)
        self.assertNotIn("always()", block)
        self.assertNotIn("|| true", block)


if __name__ == "__main__":
    unittest.main()
