"""One-shot staging-only issuer repair preserves tested artifacts and graph brackets."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'infra/deploy'))
import repair_staging_billing_issuer as repair

class IssuerRepairTests(unittest.TestCase):
    """No unchecked source, alternative realm or retry can reach the writer."""
    def environment(self):
        """Construct synthetic credentials-free hosted admission metadata."""
        return dict(repair.PINS,AMAIL_STAGING_ISSUER_REPAIR_CONFIRM=repair.CONFIRM,
                    GITHUB_REF='refs/heads/codex/v0.2.0-billing',GITHUB_ACTIONS='true',
                    GITHUB_SHA='a'*40,GITHUB_RUN_ID='123')

    def snapshot(self):
        """Return only the infrastructure pins checked across the mutation."""
        return {'pins':{'amail-mail-staging':('api-deploy',repair.PINS['AMAIL_EXPECTED_WORKER_VERSION']),
                        'amail-trace-sink-staging':('sink-deploy',repair.PINS['AMAIL_EXPECTED_TRACE_SINK_VERSION'])}}

    def test_bad_admission_never_reads_or_writes(self):
        """Wrong branch, confirmation or predecessor stops before provider access."""
        for name,value in (('GITHUB_REF','refs/heads/main'),
                           ('AMAIL_STAGING_ISSUER_REPAIR_CONFIRM',''),
                           ('AMAIL_EXPECTED_MAINTENANCE_VERSION','newer')):
            with patch.dict(os.environ,dict(self.environment(),**{name:value}),clear=True), \
                 patch.object(repair.graph,'verify') as verify,patch.object(repair,'deploy_maintenance') as deploy:
                with self.assertRaises(ValueError): repair.execute()
                verify.assert_not_called()
                deploy.assert_not_called()

    def test_success_brackets_one_submit_and_retains_safe_evidence(self):
        """Only exact missing-issuer predecessor is exceptional; postcondition is strict."""
        snapshot=self.snapshot()
        with patch.dict(os.environ,self.environment(),clear=True), \
             patch.object(repair.graph,'verify',side_effect=[snapshot,snapshot]) as verify, \
             patch.object(repair,'deploy_maintenance',return_value='new-version') as deploy, \
             patch.object(Path,'write_text') as write,redirect_stdout(io.StringIO()):
            repair.execute()
        deploy.assert_called_once_with(True)
        self.assertEqual(verify.call_args_list[0].kwargs,{'allow_missing_issuer_predecessor':True})
        self.assertEqual(verify.call_args_list[1].kwargs,{})
        self.assertIn('new-version',write.call_args.args[0])

    def test_failed_submit_never_replays(self):
        """Ambiguous provider result cannot trigger a second writer."""
        with patch.dict(os.environ,self.environment(),clear=True), \
             patch.object(repair.graph,'verify',return_value=self.snapshot()) as verify, \
             patch.object(repair,'deploy_maintenance',side_effect=RuntimeError('synthetic')) as deploy:
            with self.assertRaises(RuntimeError): repair.execute()
        deploy.assert_called_once_with(True)
        self.assertEqual(verify.call_count,1)

    def test_non_target_drift_fails_after_exactly_one_submit(self):
        """Serving API/sink deployment identity, not just version, must remain stable."""
        before,after=self.snapshot(),self.snapshot()
        after['pins']['amail-mail-staging']=('different-deployment',repair.PINS['AMAIL_EXPECTED_WORKER_VERSION'])
        with patch.dict(os.environ,self.environment(),clear=True), \
             patch.object(repair.graph,'verify',side_effect=[before,after]), \
             patch.object(repair,'deploy_maintenance',return_value='new-version') as deploy:
            with self.assertRaisesRegex(ValueError,'non_target_changed'): repair.execute()
        deploy.assert_called_once_with(True)

if __name__=='__main__': unittest.main()
