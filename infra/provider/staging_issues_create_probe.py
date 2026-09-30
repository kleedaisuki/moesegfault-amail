"""One code-free Issues-off creation discriminator, never a Mail attestation.

The fixed resource is not adopted, deployed, patched, invoked, or automatically
deleted. Every provider response stays in memory. Only non-secret recovery pins
and closed categorical output can leave this process.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
from pin_staging_mail import API, SCRIPT, containment_bindings_match, serving_deployment
sys.path.insert(0, str(ROOT / "crates/mail-worker"))
from check_observability import capture_disabled

NAME = "amail-issues-contract-staging"
VERSION = "c3f6401a-1e84-4f51-91df-ae77d90683e9"
DATABASE = "74f35f95-42ce-482c-86e6-dffbdd35cbbe"
REPOSITORY = "kleedaisuki/moesegfault-amail"
REF = "refs/heads/main"
CONFIRM = "CREATE_STAGING_CODE_FREE_ISSUES_PROBE_ONCE"
FREEZE = "FREEZE_STAGING_MAIL_SETTINGS_ROUTING_AND_PROBE_WRITERS"
LIMIT = 262_144
MAX_PAGES = 5
ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
REFERENCES = {"dispatch_namespace_outbounds", "domains", "durable_objects", "queues", "workers"}
FIELDS = ("absence", "original_pin", "hold", "create", "identity", "isolation", "readback", "recovery")
HOLD_SQL = """
SELECT (SELECT COUNT(*) FROM send_policy WHERE scope='global') AS global_rows,
(SELECT COUNT(*) FROM send_policy WHERE scope='global' AND owner_iss='*'
 AND owner_sub='*' AND state='held') AS global_held,
(SELECT COUNT(*) FROM send_release_gates WHERE id=1) AS gate_rows,
(SELECT COUNT(*) FROM send_release_gates WHERE id=1 AND
 (canary_expires_at IS NULL OR canary_expires_at<=unixepoch()
  OR canary_used_by IS NOT NULL)) AS idle_rows
"""


def need(condition: bool) -> None:
    """Discard arbitrary error text; callers expose only completed phase bins."""
    if not condition:
        raise ValueError("unverified")


def unique_object(pairs: list) -> dict:
    """Never choose the last of conflicting capture flags or resource IDs."""
    result = {}
    for key, value in pairs:
        need(key not in result)
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    """Reject non-JSON NaN and infinity before any classification."""
    raise ValueError("unverified")


def decode(raw: bytes) -> dict:
    """Require a bounded, unambiguous successful raw provider envelope."""
    need(len(raw) <= LIMIT)
    payload = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    need(isinstance(payload, dict) and payload.get("success") is True
         and payload.get("errors") == [])
    return payload


class NoRedirect(HTTPRedirectHandler):
    """Do not leak authorization or turn one request into an unreviewed traversal."""

    def redirect_request(self, request, response, code, message, headers, url):
        """Reject even same-host redirects, without emitting their destination."""
        return None


class Client:
    """Expose only the fixed discriminator's documented control-plane operations."""

    def __init__(self, account: str, token: str):
        """Keep credentials in memory; no CLI, shell, SDK defaults, or retries."""
        need(re.fullmatch(r"[0-9a-f]{32}", account) is not None and bool(token))
        self.account = account
        self.token = token

    def _request(self, path: str, body: dict | None = None) -> dict:
        """Read one 200 response bounded to 256 KiB and reject redirect/error bodies."""
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, separators=(",", ":"), allow_nan=False).encode()
        request = Request(f"{API}/accounts/{self.account}/{path}", data=data,
                          headers=headers, method="GET" if data is None else "POST")
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            need(response.status == 200)
            return decode(response.read(LIMIT + 1))

    def workers_page(self, page: int) -> dict:
        """Read at most five complete namespace pages, never suffix-search/adopt."""
        need(type(page) is int and 1 <= page <= MAX_PAGES)
        return self._request(f"workers/workers?page={page}&per_page=100&order_by=name&order=asc")

    def original(self) -> tuple:
        """Pin original Mail serving/version/bindings and current resource privately."""
        base = f"workers/scripts/{SCRIPT}"
        serving = serving_deployment(self._request(base + "/deployments?per_page=1&page=1")["result"])
        need(serving is not None and serving[1] == VERSION)
        version = self._request(base + f"/versions/{VERSION}")["result"]
        need(containment_bindings_match(version, VERSION))
        worker = self._request(f"workers/workers/{SCRIPT}")["result"]
        need(isinstance(worker, dict) and worker.get("name") == SCRIPT and valid_id(worker.get("id")))
        return serving, version, worker

    def held_idle(self) -> None:
        """Read only aggregate counts; require global held and no usable canary."""
        batches = self._request(f"d1/database/{DATABASE}/query", {"sql": HOLD_SQL, "params": []})["result"]
        need(isinstance(batches, list) and len(batches) == 1 and isinstance(batches[0], dict)
             and batches[0].get("success") is True)
        rows = batches[0].get("results")
        need(isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict))
        need(all(type(rows[0].get(key)) is int and rows[0][key] == 1
                 for key in ("global_rows", "global_held", "gate_rows", "idle_rows")))

    def create(self) -> dict:
        """POST exactly one fixed, explicit all-off Worker, with no code/config copy."""
        return self._request("workers/workers", create_body())["result"]

    def worker(self, identity: str) -> dict:
        """Address the newly returned immutable ID, never a configurable target."""
        need(valid_id(identity))
        return self._request(f"workers/workers/{identity}")["result"]

    def no_versions(self, identity: str) -> None:
        """Independently prove no uploaded code, not merely no deployment date."""
        need(valid_id(identity))
        envelope = self._request(f"workers/workers/{identity}/versions?page=1&per_page=1")
        need(envelope.get("result") == [])
        info = envelope.get("result_info")
        need(isinstance(info, dict) and type(info.get("total_count")) is int
             and info["total_count"] == 0 and type(info.get("count")) is int and info["count"] == 0
             and type(info.get("page")) is int and info["page"] == 1
             and type(info.get("per_page")) is int and info["per_page"] == 1
             and type(info.get("total_pages")) is int and info["total_pages"] in (0, 1))


def valid_id(value: object) -> bool:
    """Allow only a bounded opaque ID; exclude both Mail names and the probe name."""
    return isinstance(value, str) and ID.fullmatch(value) is not None and value not in (
        NAME, SCRIPT, "amail-mail")


def create_body() -> dict:
    """Build the six writable fields; no version, route, preview template, or binding.

    Example: create_body()['observability']['issues'] == {'enabled': False}.
    Sampling one is a retained preference, never the capture-off mechanism.
    """
    return {"name": NAME, "logpush": False, "tags": [], "tail_consumers": [],
            "subdomain": {"enabled": False, "previews_enabled": False},
            "observability": {"enabled": False, "head_sampling_rate": 1,
                              "redact_query_string": True,
                              "logs": {"enabled": False, "invocation_logs": False},
                              "traces": {"enabled": False}, "issues": {"enabled": False}}}


def name_absent(client: Client) -> bool:
    """Require complete typed pagination under the externally attested writer freeze.

    This intentionally replaces the design's unsupported not-found-code premise.
    No failed GET or arbitrary 404 permits creation. Missing metadata, >500
    Workers, changed totals, duplicate IDs/names, or incomplete pages fail closed.
    """
    ids, names = set(), set()
    totals = None
    for page in range(1, MAX_PAGES + 1):
        envelope = client.workers_page(page)
        items, info = envelope.get("result"), envelope.get("result_info")
        need(isinstance(items, list) and isinstance(info, dict))
        need(all(type(info.get(key)) is int for key in (
            "count", "page", "per_page", "total_count", "total_pages")))
        count, total = info["count"], info["total_count"]
        pages = max(1, (total + 99) // 100)
        need(0 <= total <= 100 * MAX_PAGES and info["page"] == page and info["per_page"] == 100
             and info["total_pages"] in ((0, 1) if total == 0 else (pages,))
             and count == len(items) == min(100, max(0, total - 100 * (page - 1))))
        current = (total, info["total_pages"])
        need(totals is None or totals == current)
        totals = current
        for item in items:
            need(isinstance(item, dict))
            identity, name = item.get("id"), item.get("name")
            need(valid_id(identity) and isinstance(name, str) and 0 < len(name) <= 128
                 and identity not in ids and name not in names)
            ids.add(identity)
            names.add(name)
        if NAME in names:
            return False
        if page == pages:
            need(len(names) == total)
            return True
    raise ValueError("unverified")


def check_identity(worker: object, identity: str | None = None) -> str:
    """Require fixed name and typed immutable ID before preserving recovery pins."""
    need(isinstance(worker, dict) and worker.get("name") == NAME and valid_id(worker.get("id")))
    need(identity is None or worker["id"] == identity)
    return worker["id"]


def isolated(worker: dict) -> None:
    """Validate independent current flags and reject unknown capability/export paths."""
    allowed = {"id", "name", "created_on", "updated_on", "deployed_on", "logpush", "tags",
               "tail_consumers", "subdomain", "references", "observability", "previews_base_config"}
    need(not (set(worker) - allowed) and worker.get("logpush") is False
         and worker.get("tail_consumers") == [] and worker.get("tags") == []
         and "deployed_on" in worker and worker["deployed_on"] is None
         and worker.get("previews_base_config") in (None, {}))
    subdomain = worker.get("subdomain")
    need(isinstance(subdomain, dict) and not (set(subdomain) - {
        "enabled", "previews_enabled", "url", "preview_url_suffix"})
        and subdomain.get("enabled") is False and subdomain.get("previews_enabled") is False)
    references = worker.get("references")
    need(isinstance(references, dict) and set(references) == REFERENCES
         and all(references[key] == [] for key in REFERENCES))


def issues_bin(worker: dict) -> str:
    """Keep omitted Issues distinct from null/malformed/unknown and explicit false.

    A temporary copy permits checking all other capture flags, but that copy is
    never returned, persisted, or claimed as provider evidence.
    """
    obs = worker.get("observability")
    need(isinstance(obs, dict))
    normalized = copy.deepcopy(obs)
    normalized["issues"] = {"enabled": False}
    need(capture_disabled(normalized) and obs.get("head_sampling_rate") == 1
         and type(obs.get("head_sampling_rate")) in (int, float)
         and obs.get("redact_query_string") is True
         and isinstance(obs.get("logs"), dict) and obs["logs"].get("invocation_logs") is False)
    if "issues" not in obs:
        return "omitted"
    issues = obs["issues"]
    need(isinstance(issues, dict) and not (set(issues) - {"enabled"}))
    if "enabled" not in issues:
        return "omitted"
    need(type(issues["enabled"]) is bool)
    return "explicit_off" if issues["enabled"] is False else "true"


def guard(env: dict) -> dict:
    """Verify immutable main dispatch, confirmations and debug-off before secrets."""
    sha, run = env.get("GITHUB_SHA", ""), env.get("GITHUB_RUN_ID", "")
    need(env.get("GITHUB_EVENT_NAME") == "workflow_dispatch" and env.get("GITHUB_REF") == REF
         and env.get("GITHUB_REPOSITORY") == REPOSITORY and env.get("GITHUB_RUN_ATTEMPT") == "1"
         and re.fullmatch(r"[0-9a-f]{40}", sha) is not None and sha == env.get("ISSUES_REVIEWED_SHA")
         and sha == env.get("ISSUES_APPROVED_SHA")
         and re.fullmatch(r"[1-9][0-9]{0,19}", run) is not None
         and env.get("ISSUES_CONFIRM") == CONFIRM and env.get("ISSUES_FREEZE") == FREEZE)
    need(env.get("RUNNER_DEBUG") != "1" and all(env.get(key, "").lower() != "true"
         for key in ("ACTIONS_RUNNER_DEBUG", "ACTIONS_STEP_DEBUG")))
    return {"repository": REPOSITORY, "workflow": ".github/workflows/staging-issues-create-probe.yml",
            "source_sha": sha, "run": run, "attempt": "1"}


class Recovery:
    """Persist only non-secret exact resource/run/SHA/UTC pins, never provider objects."""

    def __init__(self, metadata: dict):
        """Validate root-local exclusive artifact destination before any provider operation."""
        self.metadata = metadata
        self.directory = ROOT / ".temp/issues-create-probe"
        for path in (ROOT / ".temp", self.directory):
            need(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)())
        self.directory.mkdir(parents=True, exist_ok=True)
        need(not any(self.directory.iterdir()))

    def save(self, identity: str) -> None:
        """Save returned immutable ID immediately; missing/ambiguous identity stays unresolved."""
        need(valid_id(identity))
        record = {"name": NAME, "utc": datetime.now(timezone.utc).isoformat(),
                  "worker_id": identity,
                  **self.metadata}
        path = self.directory / "resource.json"
        need(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)())
        with path.open("xb") as file:
            file.write(json.dumps(record, separators=(",", ":"), allow_nan=False).encode())


def probe(client: Client, recovery: Recovery, phases: dict) -> str:
    """Create once, read independently once, and bracket original pin/hold without cleanup."""
    phases["original_pin"] = "checking_before"
    original = client.original()
    phases["original_pin"] = "before_match"
    phases["hold"] = "checking_before"
    client.held_idle()
    phases["hold"] = "before_match"
    phases["absence"] = "checking"
    if not name_absent(client):
        phases["absence"] = "name_occupied"
        return "UNVERIFIED"
    phases["absence"] = "complete_absent"
    phases["create"] = "attempted"
    created = client.create()
    identity = check_identity(created)
    recovery.save(identity)
    phases["recovery"] = "identity_saved"
    phases["create"] = "accepted"
    phases["identity"] = "checking"
    worker = client.worker(identity)
    check_identity(worker, identity)
    phases["identity"] = "match"
    phases["isolation"] = "checking"
    isolated(worker)
    client.no_versions(identity)
    phases["isolation"] = "code_free"
    phases["readback"] = "checking"
    result = issues_bin(worker)
    phases["readback"] = result
    phases["original_pin"] = "checking_after"
    need(client.original() == original)
    phases["original_pin"] = "match"
    phases["hold"] = "checking_after"
    client.held_idle()
    phases["hold"] = "match"
    return result


def main() -> int:
    """Emit closed labels only, including when errors contain credentials or responses."""
    phases = dict.fromkeys(FIELDS, "skipped")
    result = "UNVERIFIED"
    try:
        metadata = guard(dict(os.environ))
        if sys.argv[1:] == ["--guard"]:
            print("staging_issues_create_guard=verified")
            return 0
        need(not sys.argv[1:])
        recovery = Recovery(metadata)
        client = Client(os.getenv("CLOUDFLARE_ACCOUNT_ID", ""), os.getenv("CLOUDFLARE_API_TOKEN", ""))
        result = probe(client, recovery, phases)
    except Exception:
        # Do not print arbitrary exception text, provider errors, URLs, or tracebacks.
        pass
    print("staging_issues_create_probe=" + result)
    print("staging_issues_create_phases=" + " ".join(f"{key}:{phases[key]}" for key in FIELDS))
    return 0 if result in ("explicit_off", "omitted") else 1


if __name__ == "__main__":
    raise SystemExit(main())
