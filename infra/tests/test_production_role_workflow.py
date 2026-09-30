"""Direct-only orchestration and historical privacy guards; hosted tests only."""
from pathlib import Path
import os
import re
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import require_production_role_phase1 as evidence
from workflow_source import job_block

class WorkflowTests(unittest.TestCase):
    """Shared writer exclusion and explicit phase prevent unsafe dispatch regressions."""
    def test_workflow_lock_and_dispatch_limit(self):
        """The lock is workflow-level; dependent jobs must not wait on their own lock."""
        source = (ROOT/'.github/workflows/ci.yml').read_text(encoding='utf-8-sig')
        self.assertIn('amail-production-graph-writer',source.split('jobs:')[0])
        inputs = source.split('permissions:')[0]
        self.assertLessEqual(len(re.findall(r'^      [a-z0-9_]+:$',inputs,re.M)),25)
        self.assertNotIn('production_graph_phase:',inputs)
        self.assertIn('production-api-only-maintenance',inputs)
        self.assertNotIn('production-api-role-maintenance', source)
        self.assertNotIn('staging-role-queue-rollout', source)
        self.assertNotIn('trace_sink_canary_run:', inputs)
        self.assertFalse((ROOT/'.github/workflows/deploy-role-monitor-production.yml').exists())
        self.assertNotIn('cancel-in-progress: true', source.split('jobs:')[0])

    def test_active_workflows_cannot_attach_dormant_role_producer(self):
        """Historical role code must not remain an executable v0.1 deploy choice."""
        for path in (ROOT/'.github/workflows').glob('*.y*ml'):
            source = path.read_text(encoding='utf-8-sig')
            with self.subTest(workflow=path.name):
                for forbidden in ('deploy_production_role_monitor.py', 'deploy_staging_role_monitor.py',
                                  'migrate_production_role.py', 'wrangler d1 migrations apply ROLE_MONITOR',
                                  'AMAIL_TRACE_TOPOLOGY: api-role'):
                    self.assertNotIn(forbidden, source)

    def test_maintenance_has_no_queue_provision_replay(self):
        """Maintenance preserves exact API-only Queue IDs; only bootstrap provisions."""
        source = (ROOT/'.github/workflows/ci.yml').read_text(encoding='utf-8-sig')
        block = job_block(source, 'deploy-trace-sink')
        self.assertIn('--phase readback --topology api-only',block)
        self.assertIn('--phase queues --topology api-only',block)
        self.assertIn('prepare_production_graph.py',block)
        self.assertIn("'api-only-maintenance' || 'bootstrap'",block)
        self.assertIn('printf \'queue_id=%s\\ndlq_id=%s\\n\' "$AMAIL_TRACE_QUEUE_ID" "$AMAIL_TRACE_DLQ_ID"', block)
        self.assertLess(block.index('prepare_production_graph.py'),block.index('ensure_trace_queues.py'))
        maintenance = block.split('        run: |\n          if [ ',1)[1].split('          else\n',1)[0]
        self.assertNotIn('--phase queues',maintenance)
        self.assertNotIn('--phase recover',block)

    def test_all_production_graph_checks_use_one_api_only_contract(self):
        """Both lifecycles recheck immutable API/sink pins without a role prerequisite."""
        source = (ROOT/'.github/workflows/ci.yml').read_text(encoding='utf-8-sig')
        for name, checks in (('deploy-trace-sink', 2), ('deploy-worker', 3)):
            block = job_block(source, name)
            with self.subTest(job=name):
                self.assertIn('AMAIL_TRACE_TOPOLOGY: api-only',block)
                self.assertNotIn('AMAIL_EXPECTED_ROLE_WORKER_VERSION',block)
                self.assertNotIn('AMAIL_ROLE_ROUTED_COUNT',block)
                self.assertNotIn('--phase maintenance',block)
                self.assertNotIn('--phase before',block)
                self.assertNotIn('--lifecycle',block)
                self.assertNotIn('api-role',block)
                self.assertNotIn('ensure_role_forwarding.py',block)
                self.assertEqual(block.count('check_production_role_graph.py --phase api-only'),checks)
        api = job_block(source, 'deploy-worker')
        marker = 'production_trace_graph_attestation=api-only-v1'
        post = api.split('      - name: Verify exact graph phase, serving bindings, capture and held sending',1)[1]
        self.assertLess(post.index('--phase api-only'),post.index(marker))
        self.assertIn('AMAIL_EXPECTED_WORKER_VERSION: ${{ steps.api.outputs.version }}',post)
        self.assertIn('AMAIL_EXPECTED_TRACE_SINK_VERSION: ${{ needs.deploy-trace-sink.outputs.sink_version }}',api)
        self.assertIn('AMAIL_EXPECTED_TRACE_SINK_VERSION: ${{ steps.sink.outputs.version }}',job_block(source, 'deploy-trace-sink'))

    def test_staging_promotion_uses_exact_api_only_queue_contract(self):
        """Pin the same held staging deployment, with no contact adoption or role fallback."""
        source = (ROOT/'.github/workflows/ci.yml').read_text(encoding='utf-8-sig')
        api = job_block(source, 'staging-worker')
        sink = job_block(source, 'staging-trace-sink')
        self.assertIn('--target staging --phase readback --topology api-only',api)
        self.assertIn('--target staging --phase queues --topology api-only',sink)
        for block in (api, sink):
            self.assertIn('AMAIL_TRACE_TOPOLOGY: api-only',block)
            self.assertNotIn('AMAIL_EXPECTED_ROLE_WORKER_VERSION',block)
            self.assertNotIn('ROLE_MONITOR',block)
            self.assertNotIn('ensure_role_forwarding.py',block)
            self.assertNotIn('send_control.py',block)
            self.assertNotIn('attest_gate.py',block)
        self.assertIn('check_observability.py --realm staging',api)
        self.assertIn('check_observability.py --realm staging --mode sink',api)
        self.assertIn('check_observability.py --realm staging --mode sink',sink)
        self.assertEqual(api.count('check_send_hold.py --target staging'),3)
        self.assertEqual(sink.count('check_send_hold.py --target staging'),2)
        self.assertLess(api.index('check_send_hold.py'),api.index('configure_sending_privacy.py'))
        self.assertLess(sink.index('check_send_hold.py'),sink.index('ensure_trace_queues.py'))
        deploy = 'deploy_production_mail.py --target staging'
        pin = 'pin_staging_mail.py --phase queue-api'
        self.assertIn('AMAIL_STAGING_MAIL_DEPLOY_CONFIRM: ${{ inputs.confirm }}',api)
        self.assertIn('AMAIL_EXPECTED_WORKER_VERSION: ${{ steps.api.outputs.version }}',api)
        self.assertIn('AMAIL_EXPECTED_TRACE_QUEUE_ID: ${{ needs.staging-trace-sink.outputs.queue_id }}',api)
        self.assertIn('AMAIL_EXPECTED_TRACE_SINK_VERSION: ${{ needs.staging-trace-sink.outputs.sink_version }}',api)
        self.assertNotIn('wrangler deploy',api)
        self.assertLess(api.index(deploy),api.index(pin))
        self.assertLess(api.index(pin),api.rindex('check_send_hold.py'))
        self.assertLess(sink.index('--mode sink'),sink.rindex('check_send_hold.py'))
        self.assertLess(api.rindex('check_send_hold.py'),api.index('Smoke test staging API'))
        serving = job_block(source, 'staging-serving-pin')
        self.assertIn(pin, serving)
        self.assertIn('AMAIL_EXPECTED_TRACE_QUEUE_ID: ${{ vars.AMAIL_TRACE_QUEUE_ID_STAGING }}',serving)

    def test_evidence_gate_rejects_missing_actual_privacy_harness(self):
        """Configuration or staged markers are not production retained-record evidence."""
        with patch.dict(os.environ, {}, clear=True), patch.object(evidence,'log') as log, self.assertRaises(ValueError):
            evidence.verify()
        log.assert_not_called()

if __name__ == '__main__':
    unittest.main()
