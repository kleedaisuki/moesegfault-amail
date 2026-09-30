"""Immutable production historical evidence and deploy secrecy, hosted fixtures only."""
from copy import deepcopy
from pathlib import Path
import json
import os
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'infra/deploy'))
import require_production_role_phase1 as evidence
import deploy_production_role_monitor as deploy
SHA='a'*40

class HistoricalEvidenceTests(unittest.TestCase):
    """Exact realm, source, attempt, job uniqueness and separate privacy kinds are mandatory."""
    def fixtures(self):
        """Create independent synthetic first-attempt hosted metadata."""
        run={"id":1,"run_attempt":1,"status":"completed","conclusion":"success","event":"workflow_dispatch","head_branch":"main","head_sha":SHA,"path":".github/workflows/ci.yml","repository":{"full_name":evidence.REPO}}
        job={"id":2,"run_id":1,"run_attempt":1,"head_sha":SHA,"name":"Deploy mail API","status":"completed","conclusion":"success"}
        return run,{"total_count":1,"jobs":[job]}

    def test_exact_historical_first_attempt(self):
        """One successful matched job is the only accepted log source."""
        run,jobs=self.fixtures()
        with patch.object(evidence,'gh',side_effect=[json.dumps(run),json.dumps(jobs),'safe-marker']):
            self.assertEqual(evidence.log('1',SHA,'main','.github/workflows/ci.yml','Deploy mail API'),'safe-marker')

    def test_stale_source_wrong_realm_retries_and_duplicate_jobs(self):
        """Current-source claims cannot adopt staging, retried or duplicate evidence."""
        for field,value in (("head_branch","codex/amail-v0.1.0"),("head_sha","b"*40),("run_attempt",2),("event","push")):
            run,jobs=self.fixtures()
            run[field]=value
            with patch.object(evidence,'gh',side_effect=[json.dumps(run),json.dumps(jobs),'marker']),self.assertRaises(ValueError):
                evidence.log('1',SHA,'main','.github/workflows/ci.yml','Deploy mail API')
        run,jobs=self.fixtures()
        jobs['jobs'].append(deepcopy(jobs['jobs'][0]));jobs['total_count']=2
        with patch.object(evidence,'gh',side_effect=[json.dumps(run),json.dumps(jobs),'marker']),self.assertRaises(ValueError):
            evidence.log('1',SHA,'main','.github/workflows/ci.yml','Deploy mail API')

    def test_staging_confirmation_cannot_enter_production_deploy(self):
        """The shared secret wrapper does not authorize production through its default."""
        with patch.dict(os.environ,{"GITHUB_REF":"refs/heads/main","AMAIL_ROLE_ROLLOUT_CONFIRM":"RUN_STAGING_ROLE_TRACE_ROLLOUT"}),patch.object(deploy.staging,'deploy') as mutation:
            self.assertEqual(deploy.main(),1)
        mutation.assert_not_called()

if __name__=='__main__':
    unittest.main()
