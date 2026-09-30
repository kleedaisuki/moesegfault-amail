"""Read-only strict isolation gate for the exact serving Queue trace sink.

No provider bodies, bindings, identifiers or unknown exception text are printed.
The account-wide inventories require complete bounded pagination and readable zones.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEPLOY = Path(__file__).resolve().parents[2] / "infra" / "deploy"
if str(DEPLOY) not in sys.path:
    sys.path.insert(0, str(DEPLOY))
from pin_staging_mail import serving_deployment
import ensure_trace_queues as queues

API = "https://api.cloudflare.com/client/v4"
ID = re.compile(r"[0-9a-f]{32}\Z")
UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
LIMIT = 262144
ENVELOPE_FIELDS = {"success", "errors", "messages", "result", "result_info"}


def envelope(token: str, path: str) -> dict:
    """Read a bounded generated API path; redirect/body failures never enter output."""
    request = Request(API + path, headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError
        value = json.loads(raw)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        raise ValueError("sink_readback_unavailable") from error
    if (not isinstance(value, dict) or value.get("success") is not True
            or set(value) - ENVELOPE_FIELDS):
        raise ValueError("sink_readback_unavailable")
    return value


def inventory(token: str, path: str) -> list[dict]:
    """Require a stable, unique, count-complete inventory within twenty bounded pages."""
    rows, seen, expected_count, expected_pages = [], set(), None, None
    for page in range(1,21):
        separator = "&" if "?" in path else "?"
        value = envelope(token, f"{path}{separator}page={page}&per_page=50")
        batch, info = value.get("result"), value.get("result_info")
        if not isinstance(batch,list) or not isinstance(info,dict):
            raise ValueError("sink_inventory_unverified")
        count, pages = info.get("total_count"), info.get("total_pages")
        if (type(count) is not int or not 0 <= count <= 1000
                or type(pages) is not int or not 0 <= pages <= 20
                or type(info.get("page")) is not int or info["page"] != page
                or type(info.get("count")) is not int or info["count"] != len(batch)
                or type(info.get("per_page")) is not int or info["per_page"] != 50
                or len(batch) > 50 or pages not in ((0,1) if count == 0 else ((count + 49)//50,))):
            raise ValueError("sink_inventory_unverified")
        if expected_count is None:
            expected_count,expected_pages=count,pages
        if (count,pages) != (expected_count,expected_pages):
            raise ValueError("sink_inventory_changed")
        for row in batch:
            if not isinstance(row,dict) or not isinstance(row.get("id"),str) or not ID.fullmatch(row["id"]) or row["id"] in seen:
                raise ValueError("sink_inventory_unverified")
            seen.add(row["id"]); rows.append(row)
        if page >= max(1,pages):
            if len(rows) != count:
                raise ValueError("sink_inventory_unverified")
            return rows
    raise ValueError("sink_inventory_unverified")


def worker_domains(account: str, token: str) -> list[dict]:
    """Read the documented unfiltered SinglePage endpoint without invented pagination.

    Generic result_info is optional. Any supplied metadata must explicitly agree
    with the complete array and cannot claim another page or missing rows.
    """
    value = envelope(token, f"/accounts/{account}/workers/domains")
    if not isinstance(value, dict) or set(value) - ENVELOPE_FIELDS:
        raise ValueError("sink_domains_unverified")
    rows, info = value.get("result"), value.get("result_info")
    if not isinstance(rows, list) or len(rows) > 1000:
        raise ValueError("sink_domains_unverified")
    seen = set()
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                or not ID.fullmatch(row["id"]) or row["id"] in seen
                or not isinstance(row.get("service"), str) or not row["service"]):
            raise ValueError("sink_domains_unverified")
        seen.add(row["id"])
    if info is not None:
        if not isinstance(info, dict) or set(info) - {"count", "page", "per_page", "total_count", "total_pages"}:
            raise ValueError("sink_domains_unverified")
        for key in ("count", "total_count"):
            if key in info and (type(info[key]) is not int or info[key] != len(rows)):
                raise ValueError("sink_domains_unverified")
        if "page" in info and (type(info["page"]) is not int or info["page"] != 1):
            raise ValueError("sink_domains_unverified")
        if "total_pages" in info and (type(info["total_pages"]) is not int
                or info["total_pages"] not in ((0,1) if not rows else (1,))):
            raise ValueError("sink_domains_unverified")
        if "per_page" in info and (type(info["per_page"]) is not int
                or info["per_page"] <= 0 or info["per_page"] < len(rows)):
            raise ValueError("sink_domains_unverified")
    return rows


def version_isolated(value: dict, expected: str) -> bool:
    """Attest exact compiled queue-only handlers and an empty capability binding set."""
    resources=value.get("resources")
    if value.get("id") != expected or not isinstance(resources,dict):
        return False
    bindings=resources.get("bindings")
    if isinstance(bindings,dict) and set(bindings) == {"result"}:
        bindings=bindings["result"]
    script=resources.get("script")
    return (bindings == [] and isinstance(script,dict)
            and script.get("handlers") == ["queue"]
            and script.get("named_handlers",[]) == [])


def surfaces_private(account: str, token: str, script: str, readback) -> bool:
    """Verify no workers.dev, preview, Cron, account custom domain or zone route."""
    subdomain=readback(account,token,script,"subdomain")
    schedules=readback(account,token,script,"schedules")
    if (subdomain.get("enabled") is not False or subdomain.get("previews_enabled") is not False
            or schedules.get("schedules") != []):
        return False
    domains=worker_domains(account,token)
    if any(not isinstance(row.get("service"),str) or row["service"] == script for row in domains):
        return False
    zones=inventory(token,f"/zones?account.id={account}&type=full,partial,secondary,internal")
    if not zones or len(zones) > 20:
        return False
    for zone in zones:
        if not isinstance(zone.get("account"),dict) or zone["account"].get("id") != account:
            return False
        value=envelope(token,f"/zones/{zone['id']}/workers/routes")
        routes=value.get("result")
        # This endpoint returns its complete unpaginated array; require no contradictory pagination.
        if not isinstance(routes,list) or len(routes)>1000 or value.get("result_info") not in (None,{}):
            return False
        seen=set()
        for route in routes:
            if (not isinstance(route,dict) or not isinstance(route.get("id"),str)
                    or not ID.fullmatch(route["id"]) or route["id"] in seen
                    or not isinstance(route.get("pattern"),str)
                    or (route.get("script") is not None and not isinstance(route["script"],str))):
                return False
            seen.add(route["id"])
            if route.get("script") == script:
                return False
    return True


def queue_trigger_exact(account: str, token: str, realm: str, script: str) -> bool:
    """Require only the reviewed Queue subscription, never another Queue or DLQ."""
    topology=os.getenv("AMAIL_TRACE_TOPOLOGY", "api-only")
    if topology not in queues.TOPOLOGIES:
        return False
    suffix="-staging" if realm == "staging" else ""
    main_name,dlq_name=f"amail-trace-events{suffix}",f"amail-trace-dlq{suffix}"
    expected=os.getenv("AMAIL_TRACE_QUEUE_ID","")
    expected_dlq=os.getenv("AMAIL_TRACE_DLQ_ID","")
    if not ID.fullmatch(expected) or not ID.fullmatch(expected_dlq) or expected == expected_dlq:
        return False
    rows=queues.inventory(account,token)
    if len(rows)>100:
        return False
    main,dlq=queues.exact_queue(rows,main_name),queues.exact_queue(rows,dlq_name)
    if main is None or dlq is None or main["queue_id"] != expected or dlq["queue_id"] != expected_dlq:
        return False
    seen=set()
    for row in rows:
        queue_id=row.get("queue_id")
        if not isinstance(queue_id,str) or not ID.fullmatch(queue_id) or queue_id in seen:
            return False
        seen.add(queue_id)
        detail=queues.request(account,token,f"queues/{queue_id}").get("result")
        if not isinstance(detail,dict) or detail.get("queue_id") != queue_id:
            return False
        consumers=detail.get("consumers")
        if (not isinstance(consumers,list) or type(detail.get("consumers_total_count")) is not int
                or detail["consumers_total_count"] != len(consumers)
                or not all(isinstance(item,dict) and isinstance(item.get("script_name"),str) for item in consumers)):
            return False
        if queue_id in (expected,expected_dlq):
            name=main_name if queue_id == expected else dlq_name
            # Initial sink installation may precede the sole API producer. The
            # explicit role phase never inherits that empty-producer allowance.
            phase="readback" if topology == "api-role" else "queues"
            queues.validate_detail(detail,name,queue_id,suffix,phase,topology)
            if queue_id == expected and len(consumers) != 1:
                return False
        elif any(item["script_name"] == script for item in consumers):
            return False
    return True


def verify(account: str, token: str, realm: str, script: str, readback, safe_settings) -> bool:
    """Pin expected 100% serving version around read-only capability and surface checks."""
    expected=os.getenv("AMAIL_EXPECTED_TRACE_SINK_VERSION","")
    if not UUID.fullmatch(expected):
        return False
    before=serving_deployment(readback(account,token,script,"deployments?per_page=1&page=1"))
    if before is None or before[1] != expected:
        return False
    if not version_isolated(readback(account,token,script,f"versions/{expected}"),expected):
        return False
    if not all(safe_settings(readback(account,token,script,part),sink=True) for part in ("settings","script-settings")):
        return False
    if not surfaces_private(account,token,script,readback) or not queue_trigger_exact(account,token,realm,script):
        return False
    after=serving_deployment(readback(account,token,script,"deployments?per_page=1&page=1"))
    return before == after
