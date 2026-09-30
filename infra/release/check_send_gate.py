"""Fail a tag release unless production mail and outbound policy are ready.

中文：只读检查生产健康与 D1 出站发布确认；日志不含标识符或用户数据。
English: Read only production health and D1 send attestations, never identities.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


API = "https://api.cloudflare.com/client/v4"
MAIL_HEALTH = "https://mail.moesegfault.dev/health"
PRODUCTION_D1_ID = "ad06f7f3-8897-4150-b9a9-7a46a8e55b30"
MAX_REPLY = 65536
READINESS_SQL = """
SELECT
  (SELECT COUNT(*) FROM send_policy WHERE scope='global') AS global_rows,
  (SELECT COUNT(*) FROM send_policy
     WHERE scope='global' AND owner_iss='*' AND owner_sub='*'
       AND state='allowed') AS global_allowed,
  (SELECT COUNT(*) FROM send_release_gates) AS gate_rows,
  (SELECT COUNT(*) FROM send_release_gates
     WHERE id=1 AND feedback_verified=1 AND abuse_contact_verified=1
       AND delivery_canary_verified=1 AND preview_reviewed=1) AS gates_ready,
  (SELECT COUNT(*) FROM direct_role_contact_ready) AS contact_ready
"""


class GateError(Exception):
    """失败关闭，不携带远端响应。 / Fail closed without remote response data."""


def _json_request(request: urllib.request.Request) -> dict:
    """只解析有界 JSON，不泄漏 URL 或正文。 / Parse bounded JSON without logging inputs."""

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise GateError("production gate endpoint rejected the request")
            raw = response.read(MAX_REPLY + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        raise GateError("production gate endpoint unavailable") from None
    if len(raw) > MAX_REPLY:
        raise GateError("production gate response exceeded its size bound")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise GateError("production gate response was not JSON") from None
    if not isinstance(payload, dict):
        raise GateError("production gate response had an invalid shape")
    return payload


def release_ready(payload: dict) -> bool:
    """要求唯一全局许可与四项确认均为 1。 / Require exactly one allowed global row and four attestations."""

    if payload.get("success") is not True:
        return False
    batches = payload.get("result")
    if not isinstance(batches, list) or len(batches) != 1:
        return False
    batch = batches[0]
    if not isinstance(batch, dict) or batch.get("success") is not True:
        return False
    rows = batch.get("results")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        return False
    row = rows[0]
    return all(type(row.get(key)) is int and row[key] == 1 for key in (
        "global_rows", "global_allowed", "gate_rows", "gates_ready", "contact_ready"
    ))


def run() -> None:
    """读取健康与生产 D1，未确认则阻止发布。 / Block publication until prod attests readiness."""

    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if len(account) != 32 or not token:
        raise GateError("production gate credentials are unavailable")

    health = _json_request(urllib.request.Request(MAIL_HEALTH))
    if health.get("status") != "ok":
        raise GateError("production mail health is not OK")

    url = f"{API}/accounts/{account}/d1/database/{PRODUCTION_D1_ID}/query"
    body = json.dumps({"sql": READINESS_SQL}, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    if not release_ready(_json_request(request)):
        raise GateError("production send policy or release attestations are not ready")
    print("Production mail health and send release attestations are ready")


def main() -> int:
    """保持日志不含提供商正文、令牌或 DB 标识。 / Emit only sanitized gate status."""

    try:
        run()
    except GateError as error:
        print(f"Release blocked: {error}", file=sys.stderr)
        return 1
    except Exception:
        print("Release blocked: unexpected production gate failure", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
