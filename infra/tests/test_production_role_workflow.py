"""Production orchestration/privacy-evidence source guards; hosted tests only."""
from pathlib import Path
import os
import re
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import require_production_role_phase1 as evidence

class WorkflowTests(unittest.TestCase):
    """Shared writer exclusion and explicit phase prevent unsafe dispatch regressions."""
    def test_workflow_lock_and_dispatch_limit(self):
        """The lock is workflow-level; dependent jobs must not wait on their own lock."""
        source = (ROOT/'.github/workflows/ci.yml').read_text(encoding='utf-8-sig')
        role = (ROOT/'.github/workflows/deploy-role-monitor-production.yml').read_text(encoding='utf-8-sig')
        self.assertIn('amail-production-graph-writer',source.split('jobs:')[0])
        self.assertIn('amail-production-graph-writer',role.split('jobs:')[0])
        inputs = source.split('permissions:')[0]
        self.assertLessEqual(len(re.findall(r'^      [a-z_]+:$',inputs,re.M)),25)
        self.assertNotIn('production_graph_phase:',inputs)
        self.assertIn('production-api-role-maintenance',inputs)
        self.assertLess(role.index('require_production_role_phase1.py'),role.index('migrate_production_role.py'))
        self.assertLess(role.index('--phase before'),role.index('deploy_production_role_monitor.py'))
        self.assertIn('--phase after',role)
        self.assertNotIn('ensure_role_forwarding.py',role)

    def test_maintenance_has_no_queue_provision_replay(self):
        """Maintained api-role graph requires readback rather than permissive initialization."""
        source = (ROOT/'.github/workflows/ci.yml').read_text(encoding='utf-8-sig')
        block = source.split('  deploy-trace-sink:')[1].split('  staging-trace-sink:')[0]
        self.assertIn('--phase readback --topology api-role',block)
        self.assertIn('--phase queues --topology api-only',block)
        self.assertIn('prepare_production_graph.py',block)
        self.assertIn('--phase maintenance',block)

    def test_evidence_gate_rejects_missing_actual_privacy_harness(self):
        """Configuration or staged markers are not production retained-record evidence."""
        with patch.dict(os.environ, {}, clear=True), patch.object(evidence,'log') as log, self.assertRaises(ValueError):
            evidence.verify()
        log.assert_not_called()

if __name__ == '__main__':
    unittest.main()
