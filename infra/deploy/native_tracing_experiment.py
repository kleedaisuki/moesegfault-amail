"""Deploy/observe/remove one synthetic native-tracing pair from checked artifact bytes.

No Mail, account, storage, SMTP or send-policy capability is present. The separately
admitted route transport owns only one reserved infrastructure DNS record/route.
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
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid

from control_plane_trace import response_facts, span
import native_route_lifecycle as ingress

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / ".temp/native-tracing"
RECEIPT = FOLDER / "experiment.json"
PROBE = "amail-native-trace-probe"
CALLER = "amail-native-trace-caller"
NAMES = (PROBE, CALLER)
API = "https://api.cloudflare.com/client/v4"
# A fixed, truthful client identity tests the documented browser-signature boundary.
# This is not a browser impersonation, credential, or security-policy change.
CLIENT_USER_AGENT = "Mozilla/5.0 (compatible; amail-native-tracing-canary/1.0)"
CLIENT_PROFILE = "self_identified_compatibility_v1"


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
        self.last_request = None

    def request(self, method: str, suffix: str, data=None, *, token=None, envelope=False):
        """No automatic retry, query/SQL/body log or guessed absence on read failure."""
        path = urlsplit(suffix).path
        family = path.rsplit("/", 1)[-1]
        endpoint = "workers.canary." + family if family in ("settings", "deployments", "subdomain", "query") else "workers.canary.script"
        if path.startswith(ingress.ZONE + "/dns_records"):
            endpoint = "workers.canary.dns"
        elif path.startswith(ingress.ZONE + "/workers/routes"):
            endpoint = "workers.canary.route"
        elif path.startswith(ingress.ZONE + "/ssl/"):
            endpoint = "workers.canary.existing_tls"
        elif path == ingress.ZONE:
            endpoint = "workers.canary.zone"
        elif path == f"/accounts/{self.account}/workers/domains":
            endpoint = "workers.canary.domain_inventory"
        with span("cloudflare.canary", method.lower(), component="native_tracing", account_id=self.account, endpoint=endpoint) as facts:
            started = time.monotonic()
            self.last_request = {"endpoint": endpoint, "method": method,
                                 "started_at": datetime.now(timezone.utc).isoformat()}
            # Keep the specific preread boundary even when tracing groups several
            # resources as existing_tls; never copy the input suffix/query itself.
            resources = {ingress.ZONE: "zone",
                         ingress.ZONE + "/ssl/universal/settings": "universal_ssl_settings",
                         ingress.ZONE + "/ssl/certificate_packs": "certificate_inventory",
                         ingress.ZONE + "/dns_records": "dns_inventory",
                         ingress.ZONE + "/workers/routes": "route_inventory",
                         f"/accounts/{self.account}/workers/domains": "domain_inventory"}
            resources.update({self.script(name): "probe_settings" if name == PROBE else "caller_settings"
                              for name in NAMES})
            if path in resources:
                self.last_request["resource"] = resources[path]
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
                return value if envelope else value["result"]
            except HTTPError as error:
                response_facts(facts, error.code, error.headers)
                try:
                    raw = error.read(65537)
                    envelope = json.loads(raw) if len(raw) <= 65536 else {}
                    codes = envelope.get("errors", []) if isinstance(envelope, dict) else []
                    facts.provider_error_codes = [item["code"] for item in codes[:20]
                        if isinstance(item, dict) and type(item.get("code")) is int] if isinstance(codes, list) else []
                except (ValueError, OSError):
                    pass
                raise
            finally:
                # Only typed fields already admitted to control-plane diagnostics
                # cross into the receipt; suffixes, bodies and exception prose do not.
                self.last_request.update({"finished_at": datetime.now(timezone.utc).isoformat(),
                                          "duration_ms": round((time.monotonic() - started) * 1000, 3)})
                for key in ("http_status", "cf_ray", "provider_error_codes"):
                    value = getattr(facts, key)
                    if value is not None:
                        self.last_request[key] = value

    def script(self, name: str, suffix: str = "settings") -> str:
        """Only the two source-owned scripts can be read, deployed or removed."""
        if name not in NAMES:
            raise ValueError("foreign_canary_script_refused")
        return f"/accounts/{self.account}/workers/scripts/{name}" + (f"/{suffix}" if suffix else "")


def write_receipt(value: dict) -> None:
    """Persist public operational state before advancing to the next side effect."""
    FOLDER.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def config(name: str, probe_id: str, *, route: bool = False) -> dict:
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
    if route:
        # The alternate ingress is explicit in this runtime config, not a new
        # Rust build input or accidental second public endpoint.
        result["workers_dev"] = False
    return result


def owned(settings: dict, nonce: str, role: str) -> bool:
    """A recovery/cleanup operation cannot delete a foreign or replaced script."""
    values = {item.get("name"): item.get("text") for item in settings.get("bindings", [])
              if isinstance(item, dict) and item.get("type") == "plain_text"}
    return values.get("PROBE_ID") == nonce and values.get("CANARY_ROLE") == role


def capture_readback(settings: dict) -> dict:
    """Retain only reviewed capture fields, including missing/type diagnostics.

    The provider may omit optional per-signal objects when observability is
    disabled. Missing is not false: it is recorded separately, and admission
    checks the source-owned disabled representation and rejects any signal enable.
    """
    observation = settings.get("observability")
    result = {"observability": "missing" if "observability" not in settings else "null" if observation is None else type(observation).__name__}
    for path in (("enabled",), ("logs", "enabled"), ("traces", "enabled")):
        value = observation
        label = None
        for key in path:
            if not isinstance(value, dict):
                label = "parent_" + type(value).__name__
                break
            if key not in value:
                label = "missing"
                break
            value = value[key]
        result[".".join(path)] = label if label is not None else value if type(value) is bool else type(value).__name__
    return result


def capture_accepted(settings: dict, name: str) -> bool:
    """Check effective source policy without requiring optional object repetition.

    Script Settings defines logs/traces as optional. Explicit observability false
    disables capture; optional signal objects may be absent but, when returned,
    must affirm false. The provider may omit the whole disabled object.
    A true/ill-typed override is never treated as disabled.
    """
    observation = settings.get("observability")
    # The freshly deployed, source-owned disabled caller returns no capture
    # object on the real provider. Ownership/version checks are separate gates;
    # collection also queries this caller and refuses any retained caller record.
    if observation is None:
        return name == CALLER
    if not isinstance(observation, dict):
        return False
    if name == PROBE:
        traces = observation.get("traces")
        return isinstance(traces, dict) and traces.get("enabled") is True
    if name != CALLER or observation.get("enabled") is not False:
        return False
    return all(key not in observation or
               (isinstance(observation[key], dict) and observation[key].get("enabled") is False)
               for key in ("logs", "traces"))


def deploy(*, route: bool = False) -> None:
    """Create only absent scripts; an ambiguous process result is never retried."""
    receipt = {"schema": "native-tracing-experiment/v1", "source_sha": os.environ["GITHUB_SHA"],
               "run_id": os.environ["GITHUB_RUN_ID"], "probe_id": uuid.uuid4().hex, "versions": {},
               "build_identity": json.loads((ROOT / ".temp/ci/validated-worker-build.json").read_text())}
    receipt["preflight_state"] = {"phase": "attempted", "mutation_admitted": False,
                                  "started_at": datetime.now(timezone.utc).isoformat()}
    if route:
        receipt["transport"] = "owned_zone_route_v1"
        receipt["ingress"] = {"schema": "native-route-ingress/v1", "zone_id": ingress.ZONE_ID,
                              "hostname": ingress.HOST}
    write_receipt(receipt)
    provider = None
    try:
        provider = Provider()
        preflight = ingress.preflight(provider) if route else None
        if not route:
            for name in NAMES:
                try:
                    provider.request("GET", provider.script(name))
                except HTTPError as error:
                    if error.code != 404:
                        raise
                else:
                    raise ValueError(f"canary_script_already_exists: {name}")
    except Exception as error:
        state = receipt["preflight_state"]
        state.update({"phase": "refused", "finished_at": datetime.now(timezone.utc).isoformat(),
                      "error_type": type(error).__name__ if type(error).__name__ in
                      ("HTTPError", "URLError", "ValueError", "KeyError", "TypeError", "TimeoutError", "OSError") else "other"})
        if provider is not None and isinstance(provider.last_request, dict):
            state["last_request"] = provider.last_request
        write_receipt(receipt)
        raise
    if route:
        receipt["ingress"]["preflight"] = preflight
    receipt["preflight_state"].update({"phase": "verified", "mutation_admitted": True,
                                       "finished_at": datetime.now(timezone.utc).isoformat()})
    write_receipt(receipt)
    if route:
        # This bounded first mutation establishes actual DNS permission; GETs
        # never substitute for a successful nonce-owned write/readback.
        ingress.create_dns(provider, receipt, write_receipt)
    for name in NAMES:
        path = FOLDER / f"{name}.json"
        path.write_text(json.dumps(config(name, receipt["probe_id"], route=route)), encoding="utf-8")
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
        receipt.setdefault("capture_readback", {})[name] = capture_readback(settings)
        write_receipt(receipt)
        if not capture_accepted(settings, name):
            raise ValueError("canary_capture_settings_readback_failed")
        deployed = provider.request("GET", provider.script(name, "deployments"))["deployments"]
        active = deployed[0]["versions"]
        if len(active) != 1 or active[0].get("version_id") != receipt["versions"][name] or active[0].get("percentage") != 100:
            raise ValueError("canary_serving_version_readback_failed")
        domain = provider.request("GET", provider.script(name, "subdomain"))
        if domain.get("enabled") is not (name == CALLER and not route) or domain.get("previews_enabled") is not False:
            raise ValueError("canary_endpoint_isolation_readback_failed")
    if route:
        ingress.create_route(provider, receipt, write_receipt)
        receipt["url"] = f"https://{ingress.HOST}"
        write_receipt(receipt)
        return
    subdomain = provider.request("GET", f"/accounts/{provider.account}/workers/subdomain")["subdomain"]
    if not re.fullmatch(r"[a-z0-9-]{1,63}", subdomain):
        raise ValueError("canary_account_subdomain_invalid")
    receipt["url"] = f"https://{CALLER}.{subdomain}.workers.dev"
    write_receipt(receipt)


def trigger_facts(response, raw: bytes) -> dict:
    """Classify a credential-free synthetic endpoint reply, never dump a challenge body.

    Header names are public schema facts; values are restricted to reviewed
    operational fields. Cookies, challenge tokens, redirect URLs and prose never
    enter the receipt. A bare Forbidden response differs from our JSON receipt.
    """
    headers = response.headers
    result = {"http_status": response.code, "body_bytes": len(raw),
              "body_class": "bare_forbidden" if raw.strip() == b"Forbidden" else "other",
              "header_names": sorted(key.lower() for key in headers.keys())}
    media = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    result["media_type"] = media if media in ("application/json", "text/html", "text/plain") else "other"
    ray = headers.get("cf-ray", "")
    if re.fullmatch(r"[A-Za-z0-9-]{1,64}", ray):
        result["cf_ray"] = ray
    result["cloudflare_server"] = headers.get("server", "").lower() == "cloudflare"
    result["cloudflare_challenge"] = headers.get("cf-mitigated", "").lower() == "challenge"
    code = re.fullmatch(rb"error code:\s*([0-9]{4})\s*", raw, re.IGNORECASE)
    if code:
        result["body_class"] = "cloudflare_error_code"
        result["provider_error_code"] = int(code[1])
    return result


def diagnose_endpoint(*, client_signature: bool = False) -> None:
    """Read an absent caller hostname without deploying or invoking a Worker.

    Both fixed scripts must be absent before the anonymous GET. The writer lock
    remains held, and the public request never receives provider credentials.
    The separately admitted client-signature variant changes only User-Agent.
    It does not sweep headers, retry the default request, or weaken provider rules.
    """
    provider = Provider()
    for name in NAMES:
        try:
            provider.request("GET", provider.script(name))
        except HTTPError as error:
            if error.code != 404:
                raise
        else:
            raise ValueError("endpoint_diagnostic_requires_absent_scripts")
    subdomain = provider.request("GET", f"/accounts/{provider.account}/workers/subdomain")["subdomain"]
    if not re.fullmatch(r"[a-z0-9-]{1,63}", subdomain):
        raise ValueError("canary_account_subdomain_invalid")
    url = f"https://{CALLER}.{subdomain}.workers.dev"
    headers = {"User-Agent": CLIENT_USER_AGENT} if client_signature else {}
    request = Request(url, method="GET", headers=headers)
    try:
        response = build_opener(NoRedirect).open(request, timeout=30)
    except HTTPError as error:
        response = error
    with response:
        facts = trigger_facts(response, response.read(65537))
    write_receipt({"schema": "native-endpoint-diagnostic/v1", "source_sha": os.environ["GITHUB_SHA"],
                   "run_id": os.environ["GITHUB_RUN_ID"], "scripts_absent": True, "url": url,
                   "client_profile": CLIENT_PROFILE if client_signature else "python_urllib_default",
                   "response": facts})
    print(json.dumps({"event": "absent_canary_endpoint_diagnostic", **facts}, sort_keys=True))


def trigger(*, route: bool = False) -> None:
    """Single trigger with persisted failure boundary; never retry an uncertain invocation."""
    receipt = json.loads(RECEIPT.read_text())
    if route:
        if receipt.get("transport") != "owned_zone_route_v1" or receipt.get("url") != f"https://{ingress.HOST}":
            raise ValueError("canary_route_transport_receipt_required")
        # Revalidate ingress plus nonce/role/serving versions immediately before
        # the one anonymous POST. Provider credentials never enter that request.
        ingress.assert_ingress(Provider(), receipt)
    elif receipt.get("transport") == "owned_zone_route_v1":
        raise ValueError("canary_route_transport_confirmation_required")
    receipt["from"] = int(time.time() * 1000) - 2000
    receipt["client_profile"] = CLIENT_PROFILE
    write_receipt(receipt)
    request = Request(receipt["url"], data=b"", method="POST", headers={"User-Agent": CLIENT_USER_AGENT})
    try:
        with span("canary.trigger", "post", component="native_tracing", script_name=CALLER) as facts:
            try:
                response = build_opener(NoRedirect).open(request, timeout=60)
            except HTTPError as error:
                response_facts(facts, error.code, error.headers)
                with error:
                    raw = error.read(65537)
                    receipt["trigger"] = trigger_facts(error, raw)
                facts.reason = "http_status"
                raise ValueError("canary_trigger_http_failed") from None
            with response:
                response_facts(facts, response.status, response.headers)
                raw = response.read(65537)
                receipt["trigger"] = trigger_facts(response, raw)
        if len(raw) > 65536:
            raise ValueError("canary_receipt_body_limit")
        value = json.loads(raw)
        rows = value.get("receipts", [])
        if len(rows) != 4:
            raise ValueError("four_canary_case_receipts_required")
        # The caller constructs all reports itself, without reading user data.
        receipt["receipts"] = rows
        observed = set()
        expected = {f"{mode}.{kind}" for mode in ("baseline", "redacted") for kind in ("success", "failure")}
        for row in rows:
            report = row["report"]
            if (report.get("available") is not True or report.get("sampled") is not True
                    or report.get("stage") != "complete" or report["case"]["run"] != receipt["probe_id"]):
                raise ValueError("native_api_not_accepted")
            key = report["case"].get("mode", "") + "." + report["case"].get("kind", "")
            if key not in expected or key in observed:
                raise ValueError("four_distinct_canary_cases_required")
            observed.add(key)
            if row.get("status") != (200 if report["case"]["kind"] == "success" else 500):
                raise ValueError("canary_case_status_mismatch")
    finally:
        receipt["to"] = int(time.time() * 1000) + 2000
        write_receipt(receipt)
    print(json.dumps({"event": "native_canary_invoked", "probe_id": receipt["probe_id"], "cases": 4}, sort_keys=True))


def verify_case_parentage(summary: dict) -> None:
    """Each controlled invocation needs its own child and same-trace native parent.

    A global count or a parent observed in another invocation cannot establish
    the causal relationship. Public native coordinates are retained unchanged.
    """
    expected = {f"{mode}.{kind}" for mode in ("baseline", "redacted") for kind in ("success", "failure")}
    if set(summary["cases"]) != expected:
        raise ValueError("four_distinct_native_cases_required")
    for case in summary["cases"].values():
        spans = case["spans"]
        children = [item for item in spans if item.get("spanName") == "amail.canary.operation"]
        if len(children) != 1:
            raise ValueError("native_case_child_unverified")
        child = children[0]
        parent_id, trace_id = child.get("parentSpanId"), child.get("traceId")
        if (not isinstance(parent_id, str) or not parent_id or parent_id == child.get("spanId")
                or not isinstance(trace_id, str) or not trace_id
                or not any(item.get("spanId") == parent_id and item.get("traceId") == trace_id for item in spans)):
            raise ValueError("native_case_parentage_unverified")


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
    unassigned_markers = {name: set() for name in markers}
    shapes = {}
    for record in records:
        metadata = record.get("$metadata", {})
        request_id = metadata.get("requestId") or record.get("$workers", {}).get("requestId")
        case = cases.get(request_cases.get(request_id))
        # The first real provider view must be inspectable without preserving
        # arbitrary text/attribute values or guessing another span wrapper.
        shape = tuple((key, type(record[key]).__name__) for key in ("$metadata", "$workers", "source") if key in record)
        shapes[shape] = shapes.get(shape, 0) + 1
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
                    else:
                        unassigned_markers[name].add(location)
    for case in cases.values():
        case["marker_locations"] = {key: sorted(value) for key, value in case["marker_locations"].items()}
    return {"record_count": len(records), "spans": spans, "cases": cases,
            "marker_locations": {key: sorted(value) for key, value in markers.items()},
            "unassigned_marker_locations": {key: sorted(value) for key, value in unassigned_markers.items()},
            "record_shapes": [{"fields": dict(shape), "count": count} for shape, count in sorted(shapes.items())],
            "retained_context": "unverified", "retained_exception": "unverified",
            "retained_replacement_attributes": "unverified"}


def collect() -> None:
    """Read the complete narrow source-only window; partial/no native span is not proof."""
    provider = Provider()
    receipt = json.loads(RECEIPT.read_text())
    body = {"queryId": str(uuid.uuid4()), "timeframe": {"from": receipt["from"], "to": receipt["to"]},
            "dry": True, "limit": 200, "view": "events", "parameters": {"datasets": [],
            "filterCombination": "or", "filters": [{"key": "$metadata.service", "operation": "eq",
            "type": "string", "value": name} for name in NAMES]}}
    deadline = time.monotonic() + 180
    while True:
        result = provider.request("POST", f"/accounts/{provider.account}/workers/observability/telemetry/query",
                                  body, token=os.environ["CF_OBSERVABILITY_TOKEN"])
        run = result.get("run", {})
        if run.get("status") != "COMPLETED":
            raise ValueError("canary_query_not_completed")
        if (run.get("timeframe") != body["timeframe"] or run.get("dry") is not True
                or run.get("query", {}).get("parameters", {}).get("filters") != body["parameters"]["filters"]
                or run.get("query", {}).get("parameters", {}).get("filterCombination") != "or"):
            raise ValueError("canary_query_scope_echo_mismatch")
        events = result.get("events", {})
        rows = events.get("events", [])
        if type(events.get("count")) is not int or events["count"] != len(rows) or len(rows) >= 200:
            raise ValueError("canary_window_incomplete_or_too_busy")
        if any(row.get("$metadata", {}).get("service") == CALLER for row in rows):
            raise ValueError("disabled_caller_retained_record")
        summary = summarize(rows, receipt["probe_id"])
        receipt["summary"] = summary
        write_receipt(receipt)
        try:
            verify_case_parentage(summary)
            parentage_ready = True
        except ValueError:
            parentage_ready = False
        if parentage_ready and all(case["marker_locations"]["path"]
                                  for key, case in summary["cases"].items() if key.startswith("baseline.")):
            break
        if time.monotonic() >= deadline:
            raise ValueError("native_span_or_baseline_control_missing")
        time.sleep(10)
    verify_case_parentage(summary)
    for key, case in summary["cases"].items():
        if key.startswith("baseline.") and not case["marker_locations"]["path"]:
            raise ValueError("baseline_marker_control_missing")
    summary["root_replacement_eliminates_retained_markers"] = all(
        not values for key, case in summary["cases"].items() if key.startswith("redacted.")
        for values in case["marker_locations"].values()) and not any(summary["unassigned_marker_locations"].values())
    summary["native_parentage_verified"] = True
    receipt["summary"] = summary
    write_receipt(receipt)
    print(json.dumps({"event": "native_tracing_experiment_observed", **summary}, sort_keys=True))


def cleanup() -> None:
    """Delete only receipt-owned scripts, caller first; unknown replacement is retained."""
    if not RECEIPT.exists():
        return
    receipt = json.loads(RECEIPT.read_text())
    preflight = receipt.get("preflight_state")
    if isinstance(preflight, dict) and preflight.get("phase") in ("attempted", "refused"):
        # A persisted preread is not write ownership. Do not turn an early refusal
        # into fresh provider reads, deletion, or a verified-absence claim.
        child = receipt.get("ingress", {})
        if (preflight.get("mutation_admitted") is not False or receipt.get("versions") != {}
                or not isinstance(child, dict) or "dns" in child or "route" in child
                or "url" in receipt or "cases" in receipt):
            raise ValueError("canary_preflight_no_write_state_invalid")
        receipt["cleanup"] = {"outcome": "not_needed_no_mutation_admitted",
                              "resource_absence_verified": False,
                              "recorded_at": datetime.now(timezone.utc).isoformat()}
        write_receipt(receipt)
        return
    if preflight is not None and (not isinstance(preflight, dict)
            or preflight.get("phase") != "verified" or preflight.get("mutation_admitted") is not True):
        raise ValueError("canary_preflight_state_invalid")
    provider = Provider()
    if receipt.get("transport") == "owned_zone_route_v1":
        # A live/uncertain route or DNS ownership conflict must stop script
        # removal; never leave the route pointing at a deleted caller.
        ingress.cleanup_ingress(provider, receipt, write_receipt)
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
    operations = {"deploy": deploy, "trigger": trigger, "collect": collect, "cleanup": cleanup,
                  "deploy-route": lambda: deploy(route=True),
                  "trigger-route": lambda: trigger(route=True),
                  "collect-route": collect, "cleanup-route": cleanup,
                  "diagnose": diagnose_endpoint,
                  "diagnose-client-signature": lambda: diagnose_endpoint(client_signature=True)}
    operation = sys.argv[1] if len(sys.argv) == 2 else ""
    expected = {"diagnose": "DIAGNOSE_NATIVE_TRACING_ENDPOINT",
                "diagnose-client-signature": "DIAGNOSE_NATIVE_TRACING_CLIENT_SIGNATURE"}.get(
                    operation, "RUN_NATIVE_TRACING_ROUTE_CANARY" if operation.endswith("-route") else "RUN_NATIVE_TRACING_CANARY")
    if (operation not in operations or os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("GITHUB_REF") != "refs/heads/main"
            or os.getenv("GITHUB_RUN_ATTEMPT") != "1" or os.getenv("CANARY_CONFIRM") != expected):
        raise SystemExit("Explicit hosted main first-attempt canary context required.")
    operations[operation]()


if __name__ == "__main__":
    main()
