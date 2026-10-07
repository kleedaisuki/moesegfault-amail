"""Repair only the exact staging scheduled cohort missing its Billing realm issuer.

Uses same-run tested modules, full immutable graph brackets, one normal submit,
and unchanged cadence. No API/sink/queue/adapter/Identity or production writes.
"""
import json
import os
from pathlib import Path

import check_mail_split_graph as graph
from check_mail_maintenance import MISSING_ISSUER_PREDECESSOR
from staging_rollout import deploy_maintenance

CONFIRM = 'RUN_STAGING_MAINTENANCE_ISSUER_REPAIR_V020'
PINS = {'AMAIL_EXPECTED_WORKER_VERSION':'1f4a056f-5342-46a5-8e32-7eebaea5f7a2',
        'AMAIL_EXPECTED_MAINTENANCE_VERSION':MISSING_ISSUER_PREDECESSOR,
        'AMAIL_EXPECTED_TRACE_SINK_VERSION':'56c17824-679f-4427-bcc9-4584d2510208',
        'AMAIL_TRACE_QUEUE_ID':'fcee510036af42c189e28c0b6ff9508e',
        'AMAIL_TRACE_DLQ_ID':'f023f804b7bd4d8691fbfcb60416a001',
        'AMAIL_TRACE_TOPOLOGY':'api-scheduled'}

def execute():
    """Accept one pinned predecessor, submit once, and verify unchanged non-targets."""
    if (os.getenv('AMAIL_STAGING_ISSUER_REPAIR_CONFIRM')!=CONFIRM
            or os.getenv('GITHUB_REF')!='refs/heads/codex/v0.2.0-billing'
            or os.getenv('GITHUB_ACTIONS')!='true'
            or any(os.getenv(key)!=value for key,value in PINS.items())):
        raise ValueError('staging_issuer_repair_not_confirmed')
    before=graph.verify('staging','active',allow_missing_issuer_predecessor=True)
    version=deploy_maintenance(True)
    os.environ['AMAIL_EXPECTED_MAINTENANCE_VERSION']=version
    after=graph.verify('staging','active')
    for script in ('amail-mail-staging','amail-trace-sink-staging'):
        if before['pins'][script]!=after['pins'][script]:
            raise ValueError('staging_issuer_repair_non_target_changed')
    evidence={'schema_version':1,'source_sha':os.environ['GITHUB_SHA'],
              'run_id':os.environ['GITHUB_RUN_ID'],'api_version':PINS['AMAIL_EXPECTED_WORKER_VERSION'],
              'sink_version':PINS['AMAIL_EXPECTED_TRACE_SINK_VERSION'],
              'old_maintenance_version':MISSING_ISSUER_PREDECESSOR,'maintenance_version':version,
              'maintenance_crons':['*/5 * * * *'],'production_changed':False}
    target=Path(__file__).resolve().parents[2]/'.temp/staging-maintenance-issuer-repair.json'
    target.write_text(json.dumps(evidence,sort_keys=True),encoding='utf-8')
    print('staging_maintenance_billing_issuer_repair_verified')

if __name__=='__main__':
    try:
        execute()
    except Exception:
        raise SystemExit('staging_maintenance_billing_issuer_repair_unverified') from None
