"""Deploy/observe/remove one synthetic native-tracing pair from checked artifact bytes.

No Mail, account, routing, storage, SMTP or send-policy capability is present.
All provider writes are single-attempt, source-owned and receipt-bound.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tomllib
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid

from control_plane_trace import response_facts, span

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / ".temp/native-tracing"
RECEIPT = FOLDER / "experiment.json"
PROBE = "amail-native-trace-probe"
CALLER = "amail-native-trace-caller"
NAMES = (PROBE, CALLER)
API = "https://api.cloudflare.com/client/v4"


class NoRedirect(HTTPRedirectHandler):
    """A protected provider request cannot redirect its token to another authority."""
    def redirect_request(self, *args, **kwargs):
        return None


class Provider:
    """Bounded exact-account transport, without raw response/exception printing."""
    def __init__(self):
        self.account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
        self.token = os.environ["CLOUDFLARE_API_TOKEN"]
        if not re.fullmatch(r"[0-9a-f]{32}", self.account) or not self.token:
            raise ValueError("canary_provider_context_missing")
        self.opener = build_opener(NoRedirect)

    def request(self, method: str, suffix: str, data=None, *, token=None):
        """No automatic retry, query/SQL/body log or guessed absence on read failure."""
        with span("cloudflare.canary", method.lower(), component="native_tracing", account_id=self.account) as facts:
            headers = {"Authorization": "Bearer " + (token or self.token), "Content-Type": "application/json"}
            request = Request(API + suffix, method=method, headers=headers,
                              data=None if data is None else json.dumps(data).encode())
            try:
                with self.opener.open(request, timeout=30) as response:
                    response_facts(facts, response.status, response.headers)
                    raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError("canary_provider_body_limit")
                value = json.loads(raw)
                if not isinstance(value, dict) or value.get("success") is not True:
                    raise ValueError("canary_provider_unsuccessful")
                return value["result"]
            except HTTPError as error:
                response_facts(facts, error.code, error.headers)
                raise

    def script(self, name: str, suffix: str = "settings") -> str:
        """Only the two source-owned scripts can be read, deployed or removed."""
        if name not in NAMES:
            raise ValueError("foreign_canary_script_refused")
        return f"/accounts/{self.account}/workers/scripts/{name}" + (f"/{suffix}" if suffix else "")


def write_receipt(value: dict) -> None:
    """Persist public operational state before advancing to the next side effect."""
    FOLDER.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def config(name: str, probe_id: str) -> dict:
    """Remove the custom Rust build command; Wrangler packages tested bytes only."""
    if name not in NAMES or not re.fullmatch(r"[0-9a-f]{32}", probe_id):
        raise ValueError("invalid_canary_config_coordinate")
    source = tomllib.loads((ROOT / "workers/native-trace-canary/wrangler.toml").read_text())
    role = "probe" if name == PROBE else "caller"
    selected = source if role == "probe" else {**source, **source["env"]["caller"]}
    result = {key: selected[key] for key in ("name", "compatibility_date", "workers_dev", "preview_urls", "observability")}
    result["main"] = str(ROOT / "workers/native-trace-canary/build/worker/shim.mjs")
    result["vars"] = {"CANARY_ROLE": role, "PROBE_ID": probe_id}
    if role == "caller":
        result["services"] = source["env"]["caller"]["services"]
    return result


def owned(settings: dict, nonce: str, role: str) -> bool:
    """A recovery/cleanup operation cannot delete a foreign or replaced script."""
    values = {item.get("name"): item.get("text") for item in settings.get("bindings", [])
              if isinstance(item, dict) and item.get("type") == "plain_text"}
    return values.get("PROBE_ID") == nonce and values.get("CANARY_ROLE") == role


def deploy() -> None:
    """Create only absent scripts; an ambiguous process result is never retried."""
    provider = Provider()
    for name in NAMES:
        try:
            provider.request("GET", provider.script(name))
        except HTTPError as error:
            if error.code != 404:
                raise
        else:
            raise ValueError(f"canary_script_already_exists: {name}")
    receipt = {"schema": "native-tracing-experiment/v1", "source_sha": os.environ["GITHUB_SHA"],
               "run_id": os.environ["GITHUB_RUN_ID"], "probe_id": uuid.uuid4().hex, "versions": {}}
    write_receipt(receipt)
    for name in NAMES:
        path = FOLDER / f"{name}.json"
        path.write_text(json.dumps(config(name, receipt["probe_id"])), encoding="utf-8")
        with span("workers.deploy", "submit", component="native_tracing", script_name=name) as facts:
            result = subprocess.run(["wrangler", "deploy", "--config", str(path)], cwd=ROOT,
                                    capture_output=True, text=True, timeout=180, check=False)
            facts.process_exit_code = result.returncode
            versions = re.findall(r"Current Version ID:\s*([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})(?=\s|$)", result.stdout + result.stderr)
            facts.version_count = len(versions)
            if len(versions) == 1:
                facts.version = versions[0]
                receipt["versions"][name] = versions[0]
                write_receipt(receipt)
            if result.returncode or len(versions) != 1:
                raise ValueError("canary_deployment_requires_readback")
        settings = provider.request("GET", provider.script(name))
        if not owned(settings, receipt["probe_id"], "probe" if name == PROBE else "caller"):
            raise ValueError("canary_deploy_ownership_readback_failed")
        observation = settings.get("observability", {})
        if name == CALLER:
            if (observation.get("enabled") is not False or observation.get("traces", {}).get("enabled") is not False
                    or observation.get("logs", {}).get("enabled") is not False):
                raise ValueError("untraced_caller_settings_readback_failed")
        elif observation.get("traces", {}).get("enabled") is not True:
            raise ValueError("traced_probe_settings_readback_failed")
        deployed = provider.request("GET", provider.script(name, "deployments"))["deployments"]
        active = deployed[0]["versions"]
        if len(active) != 1 or active[0].get("version_id") != receipt["versions"][name] or active[0].get("percentage") != 100:
            raise ValueError("canary_serving_version_readback_failed")
        domain = provider.request("GET", provider.script(name, "subdomain"))
        if domain.get("enabled") is not (name == CALLER) or domain.get("previews_enabled") is not False:
            raise ValueError("canary_endpoint_isolation_readback_failed")
    subdomain = provider.request("GET", f"/accounts/{provider.account}/workers/subdomain")["subdomain"]
    if not re.fullmatch(r"[a-z0-9-]{1,63}", subdomain):
        raise ValueError("canary_account_subdomain_invalid")
    receipt["url"] = f"https://{CALLER}.{subdomain}.workers.dev"
    write_receipt(receipt)


def trigger() -> None:
    """Single synthetic trigger; never send credentials or retry an uncertain invocation."""
    receipt = json.loads(RECEIPT.read_text())
    receipt["from"] = int(time.time() * 1000) - 2000
    write_receipt(receipt)
    request = Request(receipt["url"], data=b"", method="POST")
    with build_opener(NoRedirect).open(request, timeout=60) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError("canary_receipt_body_limit")
    value = json.loads(raw)
    rows = value.get("receipts", [])
    if len(rows) != 4:
        raise ValueError("four_canary_case_receipts_required")
    for row in rows:
        report = row["report"]
        if (report.get("available") is not True or report.get("sampled") is not True
                or report.get("stage") != "complete" or report["case"]["run"] != receipt["probe_id"]):
            raise ValueError(f"native_api_not_accepted: stage={report.get('stage')} sampled={report.get('sampled')}")
        if row.get("status") != (200 if report["case"]["kind"] == "success" else 500):
            raise ValueError("canary_case_status_mismatch")
    receipt["receipts"], receipt["to"] = rows, int(time.time() * 1000) + 2000
    write_receipt(receipt)
    print(json.dumps({"event": "native_canary_invoked", "probe_id": receipt["probe_id"], "cases": 4}, sort_keys=True))


def strings(value, path=()):
    """Find marker locations in the entire record, including metadata and JSON source."""
    if isinstance(value, str):
        yield path, value
        if len(value) < 65536 and value.lstrip().startswith(("{", "[")):
            try:
                yield from strings(json.loads(value), path + ("decoded",))
            except ValueError:
                pass
    elif isinstance(value, dict):
        for key, item in value.items():
            yield path + (str(key), "key"), str(key)
            yield from strings(item, path + (str(key),))
    elif isinstance(value, list):
        for item in value:
            yield from strings(item, path + ("*",))


def reports(value):
    """Decode safe source receipts independently of provider wrapper layout."""
    if isinstance(value, dict):
        if isinstance(value.get("case"), dict) and "available" in value and "stage" in value:
            yield value
        for item in value.values():
            yield from reports(item)
    elif isinstance(value, list):
        for item in value:
            yield from reports(item)
    elif isinstance(value, str) and len(value) < 65536 and value.lstrip().startswith(("{", "[")):
        try:
            yield from reports(json.loads(value))
        except ValueError:
            pass


def summarize(records: list[dict], nonce: str) -> dict:
    """Keep public native causal coordinates and marker paths, not raw provider records."""
    cases = {}
    request_cases = {}
    for record in records:
        meta = record.get("$metadata", {})
        if meta.get("service") != PROBE:
            raise ValueError("foreign_record_in_canary_window")
        for report in reports(record.get("source")):
            case = report["case"]
            if (case.get("run") == nonce and case.get("mode") in ("baseline", "redacted")
                    and case.get("kind") in ("success", "failure")):
                request_id = meta.get("requestId") or record.get("$workers", {}).get("requestId")
                if not isinstance(request_id, str) or not request_id:
                    raise ValueError("source_receipt_request_id_missing")
                key = case["mode"] + "." + case["kind"]
                if request_id in request_cases or key in cases:
                    raise ValueError("canary_duplicate_invocation_requires_inspection")
                request_cases[request_id] = key
                cases[key] = {"request_id": request_id, "records": 0, "spans": [],
                              "marker_locations": {name: set() for name in ("path", "query", "header", "body")}}
    spans, markers = [], {name: set() for name in ("path", "query", "header", "body")}
    for record in records:
        metadata = record.get("$metadata", {})
        request_id = metadata.get("requestId") or record.get("$workers", {}).get("requestId")
        case = cases.get(request_cases.get(request_id))
        if case is not None:
            case["records"] += 1
        if metadata.get("spanId"):
            item = {key: metadata[key] for key in ("spanId", "parentSpanId", "traceId", "spanName", "startTime", "endTime", "duration") if key in metadata}
            spans.append(item)
            if case is not None:
                case["spans"].append(item)
        for path, value in strings(record):
            for name in markers:
                if f"amail_native_{name}_{nonce}" in value:
                    location = ".".join(path)
                    markers[name].add(location)
                    if case is not None:
                        case["marker_locations"][name].add(location)
    for case in cases.values():
        case["marker_locations"] = {key: sorted(value) for key, value in case["marker_locations"].items()}
    return {"record_count": len(records), "spans": spans, "cases": cases,
            "marker_locations": {key: sorted(value) for key, value in markers.items()}}


def collect() -> None:
    """Read the complete narrow source-only window; partial/no native span is not proof."""
    provider = Provider()
    receipt = json.loads(RECEIPT.read_text())
    body = {"queryId": str(uuid.uuid4()), "timeframe": {"from": receipt["from"], "to": receipt["to"]},
            "dry": True, "limit": 200, "view": "events", "parameters": {"datasets": [],
            "filterCombination": "and", "filters": [{"key": "$metadata.service", "operation": "eq",
            "type": "string", "value": PROBE}]}}
    deadline = time.monotonic() + 180
    while True:
        result = provider.request("POST", f"/accounts/{provider.account}/workers/observability/telemetry/query",
                                  body, token=os.environ["CF_OBSERVABILITY_TOKEN"])
        run = result.get("run", {})
        if run.get("status") != "COMPLETED":
            raise ValueError("canary_query_not_completed")
        if (run.get("timeframe") != body["timeframe"] or run.get("dry") is not True
                or run.get("query", {}).get("parameters", {}).get("filters") != body["parameters"]["filters"]):
            raise ValueError("canary_query_scope_echo_mismatch")
        events = result.get("events", {})
        rows = events.get("events", [])
        if type(events.get("count")) is not int or events["count"] != len(rows) or len(rows) >= 200:
            raise ValueError("canary_window_incomplete_or_too_busy")
        summary = summarize(rows, receipt["probe_id"])
        if len(summary["spans"]) >= 8 and len(summary["cases"]) == 4 and summary["marker_locations"]["path"]:
            break
        if time.monotonic() >= deadline:
            raise ValueError("native_span_or_baseline_control_missing")
        time.sleep(10)
    children = [item for item in summary["spans"] if item.get("spanName") == "amail.canary.operation"]
    ids = {item["spanId"] for item in summary["spans"]}
    if len(children) != 4 or any(item.get("parentSpanId") not in ids for item in children):
        raise ValueError("native_child_parentage_unverified")
    for key, case in summary["cases"].items():
        if key.startswith("baseline.") and not case["marker_locations"]["path"]:
            raise ValueError("baseline_marker_control_missing")
    summary["root_replacement_eliminates_retained_markers"] = all(
        not values for key, case in summary["cases"].items() if key.startswith("redacted.")
        for values in case["marker_locations"].values())
    receipt["summary"] = summary
    write_receipt(receipt)
    print(json.dumps({"event": "native_tracing_experiment_observed", **summary}, sort_keys=True))


def cleanup() -> None:
    """Delete only receipt-owned scripts, caller first; unknown replacement is retained."""
    if not RECEIPT.exists():
        return
    provider = Provider()
    receipt = json.loads(RECEIPT.read_text())
    for name in reversed(NAMES):
        try:
            settings = provider.request("GET", provider.script(name))
        except HTTPError as error:
            if error.code == 404:
                continue
            raise
        if not owned(settings, receipt["probe_id"], "probe" if name == PROBE else "caller"):
            raise ValueError(f"foreign_canary_cleanup_refused: {name}")
        provider.request("DELETE", provider.script(name, ""))
        try:
            provider.request("GET", provider.script(name))
        except HTTPError as error:
            if error.code != 404:
                raise
        else:
            raise ValueError("canary_cleanup_readback_failed")
    receipt["cleaned_at"] = datetime.now(timezone.utc).isoformat()
    write_receipt(receipt)


def main() -> None:
    """Explicit hosted first-attempt experiment only, no mailbox or generic provider tool."""
    if (os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("GITHUB_REF") != "refs/heads/main"
            or os.getenv("GITHUB_RUN_ATTEMPT") != "1" or os.getenv("CANARY_CONFIRM") != "RUN_NATIVE_TRACING_CANARY"):
        raise SystemExit("Explicit hosted main first-attempt canary context required.")
    {"deploy": deploy, "trigger": trigger, "collect": collect, "cleanup": cleanup}[sys.argv[1]]()


if __name__ == "__main__":
    main()
