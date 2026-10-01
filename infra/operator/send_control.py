"""Apply auditable send holds through parameterized Cloudflare D1 queries.

通过参数化 Cloudflare D1 查询应用可审计的发信停用策略。
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

DATABASES = {
    "staging": ("74f35f95-42ce-482c-86e6-dffbdd35cbbe", "https://identity-staging.moesegfault.dev"),
    "production": ("d9be9bb4-5a73-4223-85d6-b04763e6f03b", "https://identity.moesegfault.dev"),
}
REASON = re.compile(r"^[a-z][a-z0-9_]{2,47}$")
CASE = re.compile(r"^[A-Za-z0-9_-]{3,96}$")


def statement(scope: str, state: str, issuer: str, subject: str, reason: str, actor: str, case: str) -> tuple[str, list[str]]:
    """Return one constant SQL statement and bound strings, never interpolated SQL. / 返回固定 SQL 与绑定字符串，绝不拼接 SQL。"""
    if scope == "global":
        release_guard = " AND EXISTS(SELECT 1 FROM send_release_gates WHERE id=1 AND feedback_verified=1 AND abuse_contact_verified=1 AND delivery_canary_verified=1 AND preview_reviewed=1) AND EXISTS(SELECT 1 FROM direct_role_contact_ready)" if state == "allowed" else ""
        return (
            "UPDATE send_policy SET state=?1,reason_code=?2,actor=?3,note_ref=?4,updated_at=unixepoch() WHERE scope='global' AND owner_iss='*' AND owner_sub='*'" + release_guard,
            [state, reason, actor, case],
        )
    return (
        "INSERT INTO send_policy(scope,owner_iss,owner_sub,state,reason_code,actor,note_ref,updated_at) VALUES('account',?1,?2,?3,?4,?5,?6,unixepoch()) ON CONFLICT(scope,owner_iss,owner_sub) DO UPDATE SET state=excluded.state,reason_code=excluded.reason_code,actor=excluded.actor,note_ref=excluded.note_ref,updated_at=excluded.updated_at",
        [issuer, subject, state, reason, actor, case],
    )


def main() -> int:
    """Act only on reviewed target, reason, case and production-enable confirmation. / 仅在目标、原因、工单及生产启用确认均合规时执行。"""
    target = os.getenv("INPUT_TARGET", "")
    scope = os.getenv("INPUT_SCOPE", "")
    state = os.getenv("INPUT_STATE", "")
    subject = os.getenv("INPUT_OWNER_SUB", "").strip()
    reason = os.getenv("INPUT_REASON_CODE", "").strip()
    case = os.getenv("INPUT_CASE_REF", "").strip()
    confirm = os.getenv("INPUT_CONFIRM", "")
    actor_name = os.getenv("GITHUB_ACTOR", "").strip()
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    if (
        target not in DATABASES or scope not in ("global", "account")
        or state not in ("held", "allowed") or not REASON.fullmatch(reason)
        or not CASE.fullmatch(case) or not actor_name or not account or not token
        or (scope == "account" and (not subject or len(subject) > 256 or "\n" in subject))
        or (scope == "global" and subject)
    ):
        print("send_control=invalid_request", file=sys.stderr)
        return 2
    if target == "production" and scope == "global" and state == "allowed" and confirm != "ENABLE_PRODUCTION_SEND":
        print("send_control=production_enable_not_confirmed", file=sys.stderr)
        return 2
    database, issuer = DATABASES[target]
    sql, params = statement(scope, state, issuer, subject, reason, f"github:{actor_name}", case)
    body = json.dumps({"sql": sql, "params": params}).encode()
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
        print("send_control=provider_failure", file=sys.stderr)
        return 1
    if not result.get("success") or not result.get("result") or not result["result"][0].get("success"):
        print("send_control=query_failed", file=sys.stderr)
        return 1
    if not result["result"][0].get("meta", {}).get("changes"):
        print("send_control=no_policy_change_or_release_gate_missing", file=sys.stderr)
        return 1
    print(f"send_control=applied target={target} scope={scope} state={state} case={case}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
