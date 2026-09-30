"""Audit the deployed staging role monitor without exposing mail or secret values.

This is a read-only deployment check, not the SMTP/Cron acceptance test. All
provider responses stay in memory; output is limited to fixed status labels.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request


API = "https://api.cloudflare.com/client/v4"
ROOT = Path(__file__).resolve().parents[2]
# Reuse the reviewed pure no-capture policy; do not copy or soften missing/null semantics.
sys.path.insert(0, str(ROOT / "crates/mail-worker"))
sys.path.insert(0, str(Path(__file__).parent))
from check_observability import effective_api_settings
from pin_staging_mail import serving_deployment

WORKER = "amail-role-monitor-staging"
ZONE = "6edff81c6ed02f412e70868076411a5e"
DATABASE = "272e024c-453a-461b-bea0-c37a62c89d24"
MAX_RESPONSE = 262_144
UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
QUEUE_ID = re.compile(r"(?:[0-9a-f]{32}|[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})\Z")


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    """Constrain a deployment bearer to the original provider API request."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        """Treat redirects as failed audits without inspecting Location."""

        return None


_NO_REDIRECT = urllib.request.build_opener(RejectRedirect)


def api_get(path: str, token: str) -> object:
    """Fetch bounded Cloudflare JSON, suppressing sensitive response bodies."""

    request = urllib.request.Request(
        API + path, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    try:
        with _NO_REDIRECT.open(request, timeout=30) as response:
            status, raw = response.status, response.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as error:
        if 300 <= error.code < 400:
            raise RuntimeError(f"Cloudflare API read failed: HTTP {error.code}") from None
        status, raw = error.code, error.read(MAX_RESPONSE + 1)
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError("Cloudflare API unavailable") from error
    if status != 200 or len(raw) > MAX_RESPONSE:
        raise RuntimeError(f"Cloudflare API read failed: HTTP {status}")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as error:
        raise RuntimeError("Cloudflare API response malformed") from error
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise RuntimeError("Cloudflare API response unsuccessful")
    return payload.get("result")


def require(condition: bool, label: str) -> None:
    """Fail closed without rendering provider data."""

    if not condition:
        raise RuntimeError(label)


def inspect_bindings(settings: object, queue_id: str) -> None:
    """Check effective D1 and sending bindings, without showing secrets."""

    require(isinstance(settings, dict), "Worker settings unavailable")
    bindings = settings.get("bindings")
    require(isinstance(bindings, list), "Worker bindings unavailable")
    require(all(isinstance(binding, dict) for binding in bindings), "Worker bindings malformed")
    allowed = {
        ("d1", "ROLE_MONITOR"),
        ("send_email", "ROLE_ALERT"),
        ("queue", "ROLE_TRACE_EVENTS"),
        ("plain_text", "ROLE_REALM"),
        ("plain_text", "CF_ZONE_ID"),
        ("secret_text", "ROLE_FORWARD_DESTINATION"),
        ("secret_text", "CF_EMAIL_ROUTING_TOKEN"),
        ("secret_text", "CF_ACCOUNT_ID"),
        ("secret_text", "ROLE_TEST_FAULT"),  # Optional staging fault-injection hook.
    }
    require(
        all((binding.get("type"), binding.get("name")) in allowed for binding in bindings),
        "Worker has an unexpected capability binding",
    )
    d1 = [binding for binding in bindings if isinstance(binding, dict) and binding.get("type") == "d1"]
    send = [binding for binding in bindings if isinstance(binding, dict) and binding.get("type") == "send_email"]
    require(len(d1) == 1 and d1[0].get("name") == "ROLE_MONITOR", "D1 binding differs")
    # Cloudflare's API may use `id` or `database_id` for a D1 binding.
    require(d1[0].get("database_id", d1[0].get("id")) == DATABASE, "D1 database differs")
    require(len(send) == 1 and send[0].get("name") == "ROLE_ALERT", "send binding differs")
    queue = [binding for binding in bindings if binding.get("type") == "queue"]
    require(QUEUE_ID.fullmatch(queue_id) is not None, "reviewed Queue pin unavailable")
    require(
        len(queue) == 1 and queue[0].get("name") == "ROLE_TRACE_EVENTS"
        and queue[0].get("queue_id", queue[0].get("id")) == queue_id,
        "Queue binding differs",
    )
    if "allowed_sender_addresses" in send[0]:
        require(send[0]["allowed_sender_addresses"] == ["mail@moesegfault.dev"], "send binding sender differs")
    require(
        any(
            binding.get("type") == "plain_text"
            and binding.get("name") == "ROLE_REALM"
            and binding.get("text") == "staging"
            for binding in bindings if isinstance(binding, dict)
        ),
        "staging realm binding differs",
    )
    require(
        any(
            binding.get("type") == "plain_text"
            and binding.get("name") == "CF_ZONE_ID"
            and binding.get("text") == ZONE
            for binding in bindings if isinstance(binding, dict)
        ),
        "staging zone binding differs",
    )


def inspect_observability(script: object, version: object, worker: object) -> None:
    """Require exact Worker-level Logs/traces/Issues-off, not legacy omission or source intent."""

    require(
        effective_api_settings(worker, WORKER, script, version),
        "effective original-context capture not disabled",
    )


def inspect_surfaces(subdomain: object, routes: object, domains: object) -> None:
    """Require no HTTP publication for this Email/Cron-only Worker."""

    require(
        isinstance(subdomain, dict)
        and subdomain.get("enabled") is False
        and subdomain.get("previews_enabled") is False,
        "workers.dev or preview URL exposed",
    )
    require(isinstance(routes, list) and all(isinstance(item, dict) for item in routes), "HTTP routes unavailable")
    require(not any(item.get("script") == WORKER for item in routes), "Worker has an HTTP zone route")
    require(isinstance(domains, list) and all(isinstance(item, dict) for item in domains), "Worker domains unavailable")
    require(
        not any(item.get("service") == WORKER for item in domains),
        "Worker has an HTTP custom domain",
    )


def d1_query(sql: str) -> list[dict]:
    """Run a bounded remote read through Wrangler; never print raw query data."""

    result = subprocess.run(
        ["wrangler.cmd" if sys.platform == "win32" else "wrangler", "d1", "execute", "ROLE_MONITOR", "--env", "staging", "--remote", "--command", sql, "--json"],
        cwd=ROOT / "workers/role-monitor",
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    require(result.returncode == 0 and len(result.stdout) <= MAX_RESPONSE, "staging D1 read unavailable")
    try:
        data = json.loads(result.stdout)
        rows = data[0]["results"]
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise RuntimeError("staging D1 response malformed") from error
    require(isinstance(rows, list) and all(isinstance(row, dict) for row in rows), "staging D1 rows malformed")
    return rows


def inspect_d1() -> None:
    """Confirm isolated role schema and an initially expired singleton lease."""

    tables = d1_query("SELECT name FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*' AND name <> 'd1_migrations' AND name <> '_cf_KV'")
    require({row.get("name") for row in tables} == {"role_arrivals", "role_monitor_health"}, "role D1 table set differs")
    arrivals = d1_query("PRAGMA table_info(role_arrivals)")
    health = d1_query("PRAGMA table_info(role_monitor_health)")
    require(
        {row.get("name") for row in arrivals}
        == {"arrival_seq", "id", "role", "received_at", "forward_state", "forward_updated_at", "alerted_at"},
        "role arrival columns differ",
    )
    require(
        {row.get("name") for row in health} == {"singleton", "lease_until", "checked_at"},
        "role health columns differ",
    )
    require(
        any(row.get("name") == "arrival_seq" and row.get("type") == "INTEGER" and row.get("pk") == 1 for row in arrivals)
        and any(row.get("name") == "singleton" and row.get("type") == "INTEGER" and row.get("pk") == 1 for row in health),
        "role primary keys differ",
    )
    indexes = d1_query("SELECT name FROM sqlite_master WHERE type='index' AND name NOT GLOB 'sqlite_*' AND name NOT GLOB 'd1_*' AND name NOT GLOB '_cf_*'")
    require(
        {row.get("name") for row in indexes} == {"role_arrivals_unalerted", "role_arrivals_forward"},
        "role indexes differ",
    )
    state = d1_query("SELECT singleton, lease_until, checked_at FROM role_monitor_health")
    require(state == [{"singleton": 1, "lease_until": 0, "checked_at": 0}], "role lease not at initial default")
    count = d1_query("SELECT COUNT(*) AS n FROM role_arrivals")
    require(count == [{"n": 0}], "role arrival ledger not empty")


def audit() -> None:
    """Verify one live staging deployment using read-only provider endpoints."""

    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    zone = os.environ.get("CF_ZONE_ID", ZONE)
    require(len(account) == 32 and bool(token) and zone == ZONE, "scoped credentials unavailable")
    expected_version = os.environ.get("AMAIL_EXPECTED_ROLE_WORKER_VERSION", "")
    expected_queue = os.environ.get("AMAIL_EXPECTED_TRACE_QUEUE_ID", "")
    require(UUID.fullmatch(expected_version) is not None, "reviewed serving pin unavailable")
    require(QUEUE_ID.fullmatch(expected_queue) is not None, "reviewed Queue pin unavailable")
    base = f"/accounts/{account}/workers/scripts/{WORKER}"
    first = api_get(f"{base}/deployments?per_page=1&page=1", token)
    require(isinstance(first, dict), "serving deployment unavailable")
    before = serving_deployment(first)
    require(before is not None and before[1] == expected_version, "serving version differs")
    version = api_get(f"{base}/settings", token)
    script = api_get(f"{base}/script-settings", token)
    worker = api_get(f"/accounts/{account}/workers/workers/{WORKER}", token)
    subdomain = api_get(f"{base}/subdomain", token)
    routes = api_get(f"/zones/{zone}/workers/routes", token)
    domains = api_get(f"/accounts/{account}/workers/domains?service={WORKER}", token)
    inspect_bindings(version, expected_queue)
    inspect_observability(script, version, worker)
    inspect_surfaces(subdomain, routes, domains)
    last = api_get(f"{base}/deployments?per_page=1&page=1", token)
    require(isinstance(last, dict), "serving deployment unavailable")
    after = serving_deployment(last)
    require(before == after, "serving version changed during readback")

    # The reviewed helper paginates all Email Routing rules and rejects conflict.
    route = subprocess.run(
        [sys.executable, str(ROOT / "workers/role-monitor/staging_route.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
        env={**os.environ, "CF_EMAIL_ROUTING_TOKEN": os.environ.get("CF_EMAIL_ROUTING_TOKEN", token), "CF_ZONE_ID": zone},
    )
    require(route.returncode == 0 and route.stdout.strip() == "absent", "synthetic role route not absent")
    inspect_d1()


def main() -> int:
    """Report a sanitized verdict for CI or an authorized local operator."""

    try:
        audit()
    except (RuntimeError, OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        print("staging_role_monitor_audit=UNVERIFIED", file=sys.stderr)
        return 1
    print("staging role monitor: private Worker, isolated empty D1, expired lease, synthetic route absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
