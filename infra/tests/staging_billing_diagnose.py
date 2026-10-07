"""Diagnose one failed synthetic staging meter run with fixed read-only requests.

No email, owner, receipt, event identifier, URL or provider envelope is printed.
"""
import json
import os
import re
import urllib.request

from acceptance_realm import STAGING
from staging_billing_metering import read_json, usage_read
from staging_trace_witness import USER_AGENT, read_service_records

# The exact failed run's UTC window; never accept caller-supplied SQL or owners.
OWNER = "SELECT DISTINCT owner_iss,owner_sub FROM addresses WHERE address LIKE 'meter-%@mail-staging.moesegfault.dev' AND created_at BETWEEN unixepoch('2026-10-07 13:03:00')*1000 AND unixepoch('2026-10-07 13:16:00')*1000"
EVENTS = "SELECT billing_owner_id,meter,quantity,amount_micros,occurred_at,period_start,delivered_at,attempts,next_attempt_at,origin_traceparent,currency FROM resource_outbox WHERE owner_iss=?1 AND owner_sub=?2 ORDER BY occurred_at LIMIT 65"
ACCOUNT = "SELECT plan,currency,overage_budget_micros,address_count,accrued_micros FROM resource_current WHERE owner_iss=?1 AND owner_sub=?2"

def query(sql, params):
    """Admit exactly three reviewed reads into the pinned staging Mail D1."""
    if sql not in (OWNER, EVENTS, ACCOUNT):
        raise ValueError('diagnostic_query_invalid')
    account, token = os.environ['CLOUDFLARE_ACCOUNT_ID'], os.environ['CLOUDFLARE_API_TOKEN']
    if not re.fullmatch('[0-9a-f]{32}', account):
        raise ValueError('diagnostic_account_invalid')
    request = urllib.request.Request(
        f'https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{STAGING.mail_database_id}/query',
        data=json.dumps({'sql':sql,'params':params}).encode(),method='POST',
        headers={'Authorization':f'Bearer {token}','Content-Type':'application/json','User-Agent':USER_AGENT})
    data=read_json(request)
    if data.get('success') is not True or len(data.get('result',[])) != 1:
        raise ValueError('diagnostic_read_invalid')
    rows=data['result'][0].get('results')
    if not isinstance(rows,list) or len(rows)>64:
        raise ValueError('diagnostic_read_truncated')
    return rows

def main():
    """Inspect durable liabilities and closed typed Billing spans, never replay usage."""
    owners=query(OWNER,[])
    if len(owners)!=1:
        raise ValueError('diagnostic_owner_not_unique')
    scope=[owners[0]['owner_iss'],owners[0]['owner_sub']]
    events=query(EVENTS,scope)
    if not events:
        raise ValueError('diagnostic_outbox_missing')
    projected=[]
    traces=set()
    for row in events:
        projected.append({key:row[key] for key in ('currency','meter','quantity','amount_micros','occurred_at','delivered_at','attempts','next_attempt_at')})
        context=row.get('origin_traceparent')
        if isinstance(context,str) and re.fullmatch('00-[0-9a-f]{32}-[0-9a-f]{16}-01',context):
            traces.add(context[3:35])
    if len(traces)>8:
        raise ValueError('diagnostic_trace_scope_exceeded')
    print(json.dumps({'failed_run':37625486364,'account':query(ACCOUNT,scope),'outbox':projected},sort_keys=True))
    owner,period=events[0]['billing_owner_id'],events[0]['period_start']
    usage={currency:usage_read(owner,period,currency) for currency in ('CNY','USD')}
    spans=[]
    for trace in sorted(traces):
        for row in read_service_records('billing',os.environ['BILLING_SERVICE_KEY'],trace):
            if row['operation']=='billing_usage_record':
                spans.append({key:row[key] for key in ('trace_id','span_id','parent_span_id','operation','phase','outcome','http_status','occurred_at_ms')})
    print(json.dumps({'failed_run':37625486364,'account':query(ACCOUNT,scope),
        'outbox':projected,'billing':{currency:{key:value.get(key) for key in ('currency','amount_micros','events_count','overage_budget_micros','settlement_status')} for currency,value in usage.items()},
        'usage_spans':spans},sort_keys=True))

if __name__=='__main__':
    try:
        main()
    except Exception:
        raise SystemExit('staging_metering_diagnostic_unavailable') from None
