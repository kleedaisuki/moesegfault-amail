"""Grant one short-lived, recipient-pinned outbound canary while public send is held.

在公共发送停用期间授权一次短时、固定收件人的出站金丝雀测试。
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

from send_control import CASE, DATABASES

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SQL = (
    "UPDATE send_release_gates SET canary_owner_iss=?1,canary_owner_sub=?2,"
    "canary_recipient_sha256=?3,canary_expires_at=unixepoch()+900,"
    "canary_used_by=NULL,actor=?4,case_ref=?5,updated_at=unixepoch() "
    "WHERE id=1 AND EXISTS(SELECT 1 FROM send_policy WHERE scope='global' "
    "AND owner_iss='*' AND owner_sub='*' AND state='held')"
)


def main() -> int:
    """Record an auditable one-use grant without putting a raw test inbox in Actions. / 审计一次性授权，不把原始测试收件箱写入 Actions。"""
    target = os.getenv("INPUT_TARGET", "")
    subject = os.getenv("INPUT_OWNER_SUB", "").strip()
    digest = os.getenv("INPUT_RECIPIENT_SHA256", "").strip()
    case = os.getenv("INPUT_CASE_REF", "").strip()
    actor = os.getenv("GITHUB_ACTOR", "").strip()
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    if target not in DATABASES or not subject or len(subject) > 256 or "\n" in subject or not SHA256.fullmatch(digest) or not CASE.fullmatch(case) or not actor or not account or not token:
        print("canary_grant=invalid_request", file=sys.stderr)
        return 2
    database, issuer = DATABASES[target]
    body = json.dumps({"sql": SQL, "params": [issuer, subject, digest, f"github:{actor}", case]}).encode()
    request = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{database}/query",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
    except (urllib.error.URLError, ValueError):
        print("canary_grant=provider_failure", file=sys.stderr)
        return 1
    if not result.get("success") or not result.get("result") or not result["result"][0].get("success") or not result["result"][0].get("meta", {}).get("changes"):
        print("canary_grant=query_failed", file=sys.stderr)
        return 1
    print(f"canary_grant=recorded target={target} expires_in_seconds=900 case={case}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
