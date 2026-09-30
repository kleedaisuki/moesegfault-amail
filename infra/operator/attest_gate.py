"""Record human verification of outbound launch gates with D1 audit triggers.

通过 D1 审计触发器记录出站上线门槛的人工核验。
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

from send_control import CASE, DATABASES

GATES = frozenset(("feedback_verified", "abuse_contact_verified", "delivery_canary_verified", "preview_reviewed"))


CONTRACT = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
CONTACT_COVERAGE = "ACCEPT_INBOX_JUNK_AND_24H_CLOUDFLARE_RESPONSE"


def statement(gate: str) -> str:
    """Whitelist the only interpolated identifier; values remain bound parameters. / 白名单限定唯一插入的列名，值仍使用绑定参数。"""
    if gate not in GATES:
        raise ValueError("unknown release gate")
    if gate == "abuse_contact_verified":
        # Revocation is unconditional; verification binds to an explicitly
        # supplied contract instead of silently attesting whichever is current.
        return "UPDATE send_release_gates SET abuse_contact_verified=?1,abuse_contact_contract_id=(CASE WHEN ?1=1 THEN ?4 ELSE NULL END),actor=?2,case_ref=?3,updated_at=unixepoch() WHERE id=1 AND (?1=0 OR EXISTS(SELECT 1 FROM role_contact_policy WHERE id=1 AND version=1 AND contract_id=?4))"
    return f"UPDATE send_release_gates SET {gate}=?1,actor=?2,case_ref=?3,updated_at=unixepoch() WHERE id=1"


def main() -> int:
    """Apply one auditable operator attestation without logging provider results. / 应用一次可审计的人工确认，不记录供应商响应。"""
    target = os.getenv("INPUT_TARGET", "")
    gate = os.getenv("INPUT_GATE", "")
    verified = os.getenv("INPUT_VERIFIED", "")
    case = os.getenv("INPUT_CASE_REF", "")
    actor = os.getenv("GITHUB_ACTOR", "")
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    contract = os.getenv("INPUT_CONTACT_CONTRACT_ID", "")
    if target not in DATABASES or gate not in GATES or verified not in ("true", "false") or not CASE.fullmatch(case) or not actor or not account or not token:
        print("release_gate=invalid_request", file=sys.stderr)
        return 2
    if gate == "abuse_contact_verified" and verified == "true" and (
        not CONTRACT.fullmatch(contract)
        or os.getenv("INPUT_CONTACT_COVERAGE", "") != CONTACT_COVERAGE
    ):
        print("release_gate=contact_coverage_not_confirmed", file=sys.stderr)
        return 2
    db, _ = DATABASES[target]
    params = [1 if verified == "true" else 0, f"github:{actor}", case]
    if gate == "abuse_contact_verified":
        params.append(contract)
    body = json.dumps({"sql": statement(gate), "params": params}).encode()
    request = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{db}/query",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
    except (urllib.error.URLError, ValueError):
        print("release_gate=provider_failure", file=sys.stderr)
        return 1
    if not result.get("success") or not result.get("result") or not result["result"][0].get("success") or not result["result"][0].get("meta", {}).get("changes"):
        print("release_gate=query_failed", file=sys.stderr)
        return 1
    print(f"release_gate=recorded target={target} gate={gate} verified={verified} case={case}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
