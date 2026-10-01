"""Collect bounded first-production bootstrap facts on an authorized hosted runner.

No deploy, resource creation, migration, policy/grant write or send is possible
here. A successful collection proves bounded current inventory and held empty
state, not universal historical absence or an old invocation end. Only a closed
aggregate evidence artifact is persisted; raw configurations remain in memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import fnmatch
import json
import os
from pathlib import Path
import re
import sys
import tomllib
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from control_plane_trace import endpoint, response_facts, span
from mail_schema_contract import ROOT, verify_recorded_schema
from production_bootstrap_contract import ProductionResources, held_state, stable_digest
from pin_staging_mail import mail_resources

ACCOUNT = re.compile(r"[a-f0-9]{32}\Z")
NAME = re.compile(r"[A-Za-z0-9_-]{1,63}\Z")
API = "https://api.cloudflare.com/client/v4"
LIMIT = 1048576
POLICY = "SELECT state FROM send_policy WHERE scope='global' AND owner_iss='*' AND owner_sub='*'"
GATES = ("SELECT feedback_verified,abuse_contact_verified,delivery_canary_verified,preview_reviewed,"
         "CASE WHEN canary_expires_at>unixepoch() THEN 1 ELSE 0 END AS live_grant "
         "FROM send_release_gates WHERE id=1")
INITIAL_SCHEMA = ("SELECT type,name FROM sqlite_master "
                  "WHERE name NOT IN ('sqlite_sequence','_cf_KV') ORDER BY type,name")


class Stage(str, Enum):
    """Fixed inspection capability boundaries, never paths or provider names."""
    AUTHORIZATION = "authorization"
    RESOURCES = "resources"
    SDK = "sdk"
    R2 = "r2_inventory"
    SCRIPTS = "worker_inventory"
    ROUTES = "route_inventory"
    DOMAIN_IMPORT = "domain_reader_import"
    DOMAINS = "custom_domain_inventory"
    SCHEMA = "schema"
    HOLD = "held_state"
    MAIL = "empty_mail_state"
    STABILITY = "stability"
    EVIDENCE = "evidence"


@dataclass
class Progress:
    """Invocation-local stage only; no secret, object key or provider envelope retained."""
    stage: Stage = Stage.AUTHORIZATION



def http_reason(status: object) -> str:
    """Project only an actual numeric HTTP status into the shared closed bins."""
    if type(status) is not int:
        return "unexpected"
    category = str(status) if status in (401, 403, 404, 429) else ("5xx" if 500 <= status <= 599 else "other")
    return "production_provider_http_" + category


def failure_reason(error: Exception) -> str:
    """Project errors and SDK refusals become closed diagnostic bins, not error prose."""
    known = {
        "production_inspection_not_authorized", "production_resources_unverified",
        "production_isolation_or_paused_config_unverified", "production_capabilities_unverified",
        "production_r2_read_capability_missing", "production_provider_read_unverified",
        "production_provider_http_401", "production_provider_http_403", "production_provider_http_404",
        "production_provider_http_429", "production_provider_http_5xx", "production_provider_http_other",
        "production_provider_transport_unverified", "production_scripts_completeness_unverified",
        "production_inventory_unverified", "production_partial_bootstrap_or_prior_worker",
        "production_settings_unverified", "production_binding_unverified",
        "production_binding_target_unverified", "production_binding_target_conflict",
        "production_unexpected_store_or_service_caller", "production_zone_unverified",
        "production_zone_ownership_unverified", "production_routes_completeness_unverified",
        "production_route_shape_unverified", "production_route_already_attached",
        "production_domain_already_attached", "production_domain_hostname_unverified", "production_r2_inventory_unverified",
        "production_r2_inventory_incomplete", "production_d1_read_unverified",
        "bootstrap_schema_prefix_unverified", "schema_objects_unverified", "schema_object_drift",
        "bootstrap_unrecorded_schema", "bootstrap_schema_inventory_unverified",
        "schema_columns_unverified", "schema_indexes_unverified", "schema_index_columns_unverified",
        "schema_migration_provenance_unverified", "bootstrap_hold_unverified",
        "bootstrap_grant_or_release_gate_unverified", "bootstrap_retained_state_requires_reconciliation",
        "production_retained_mail_requires_recovery", "production_inventory_drift",
        "production_evidence_context_unverified", "production_evidence_path_unverified",
    }
    if isinstance(error, ValueError) and len(error.args) == 1 and isinstance(error.args[0], str) and error.args[0] in known:
        return error.args[0]
    # Legacy isolation readers chain HTTPError into their own fixed ValueError.
    # Inspect only the status, never args/URL/body, and bound/cycle-check traversal.
    cause, seen = error, set()
    for _ in range(4):
        if id(cause) in seen:
            break
        seen.add(id(cause))
        if isinstance(cause, HTTPError):
            return http_reason(cause.code)
        cause = cause.__cause__
        if cause is None:
            break
    if isinstance(error, ImportError):
        return "domain_reader_dependency_missing"
    if isinstance(error, ValueError) and len(error.args) == 1 and isinstance(error.args[0], str):
        # Only reviewed enum values become structural bins. Never interpolate a
        # provider value or an arbitrary exception attribute into diagnostics.
        domain_reason = getattr(error, "domain_reason", None)
        allowed = {
            "envelope", "rows", "row", "id_type", "id_uuid_format", "id_format", "id_duplicate",
            "service", "info", "count_type", "count_mismatch", "total_count_type", "total_count_mismatch",
            "page_type", "page_mismatch", "pages_type", "pages_mismatch", "per_page_type", "per_page_mismatch",
        }
        if (error.args[0] == "sink_domains_unverified" and isinstance(domain_reason, str)
                and domain_reason in allowed):
            return "custom_domain_" + domain_reason
        legacy = {
            "sink_readback_unavailable": "custom_domain_read_unavailable",
            "sink_domains_unverified": "custom_domain_inventory_unverified",
        }
        if error.args[0] in legacy:
            return legacy[error.args[0]]
    response = getattr(error, "response", None)
    detail = response.get("Error") if isinstance(response, dict) else None
    code = detail.get("Code") if isinstance(detail, dict) else None
    return {
        "AccessDenied": "r2_access_denied", "NoSuchBucket": "r2_bucket_missing",
        "InvalidAccessKeyId": "r2_key_invalid", "SignatureDoesNotMatch": "r2_signature_invalid",
        "ExpiredToken": "r2_key_expired", "RequestTimeTooSkewed": "r2_clock_skew",
    }.get(code, "unexpected") if isinstance(code, str) else "unexpected"


class NoRedirect(HTTPRedirectHandler):
    """Never forward a protected provider token to a redirected authority."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Convert redirects into private failures rather than retry/fallback."""
        return None


class Provider:
    """Exact-account private GET and SELECT/PRAGMA-only D1 transport."""

    def __init__(self, account: str, token: str, resources: ProductionResources):
        """Validate fixed realm identities before exposing the provider transport."""
        resources.validate()
        if not ACCOUNT.fullmatch(account) or not token:
            raise ValueError("production_capabilities_unverified")
        self.account, self.token, self.resources = account, token, resources
        self.opener = build_opener(NoRedirect)

    def envelope(self, suffix: str, data: dict | None = None) -> dict:
        """Read one bounded successful response, suppressing raw envelopes/errors."""
        with span("cloudflare.request", "response", method="GET" if data is None else "POST",
                  **endpoint(suffix)) as facts:
            request = Request(API + suffix, data=None if data is None else json.dumps(data).encode(),
                              headers={"Authorization": "Bearer " + self.token,
                                       "Accept": "application/json", "Content-Type": "application/json"})
            try:
                with self.opener.open(request, timeout=30) as response:
                    response_facts(facts, getattr(response, "status", None), getattr(response, "headers", None))
                    raw = response.read(LIMIT + 1)
                if len(raw) > LIMIT:
                    facts.reason = "body_limit"
                    raise ValueError()
                value = json.loads(raw)
                if not isinstance(value, dict):
                    facts.reason, facts.schema_expected = "schema_type", "object"
                    facts.schema_actual_type = type(value).__name__
                    raise ValueError()
                if value.get("success") is not True:
                    facts.reason, facts.schema_field, facts.schema_expected = "provider_unsuccessful", "success", "true"
                    facts.schema_actual_type = type(value.get("success")).__name__
                    errors = value.get("errors")
                    if isinstance(errors, list):
                        facts.provider_error_codes = [item["code"] for item in errors[:10]
                            if isinstance(item, dict) and type(item.get("code")) is int and 0 <= item["code"] <= 2**31-1]
                    raise ValueError()
                return value
            except HTTPError as error:
                response_facts(facts, error.code, error.headers)
                facts.error_type = type(error).__name__
                raise ValueError(http_reason(error.code)) from None
            except (URLError, TimeoutError) as error:
                facts.error_type = type(error).__name__
                raise ValueError("production_provider_transport_unverified") from None
            except Exception as error:
                facts.error_type = type(error).__name__
                raise ValueError("production_provider_read_unverified") from None

    def get(self, suffix: str):
        """Return exact result; inventory callers must separately prove completeness."""
        return self.envelope(suffix)["result"]

    def query(self, sql: str) -> list[dict]:
        """Read only source-owned SELECT/PRAGMA SQL from the exact production UUID."""
        if not sql.startswith(("SELECT ", "PRAGMA ")) or ";" in sql:
            raise ValueError("production_query_unverified")
        result = self.envelope(f"/accounts/{self.account}/d1/database/{self.resources.database}/query",
                               {"sql": sql, "params": []}).get("result")
        if (not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], dict)
                or result[0].get("success") is not True or not isinstance(result[0].get("results"), list)
                or len(result[0]["results"]) > 1000
                or not all(isinstance(row, dict) for row in result[0]["results"])):
            raise ValueError("production_d1_read_unverified")
        return result[0]["results"]


def configured_resources(source_sha: str) -> ProductionResources:
    """Read immutable reviewed production config, preserving staging isolation."""
    with (ROOT / "crates/mail-worker/wrangler.toml").open("rb") as file:
        config = tomllib.load(file)
    database, bucket = mail_resources(config)
    staging_db, staging_bucket = mail_resources(config["env"]["staging"])
    variables = config.get("vars", {})
    resources = ProductionResources(database, bucket, source_sha, config.get("name"),
                                    variables.get("IDENTITY_ISSUER"), variables.get("OIDC_CLIENT_ID"),
                                    variables.get("MAIL_DOMAIN"))
    resources.validate()
    if database == staging_db or bucket == staging_bucket or config.get("triggers", {}).get("crons") != []:
        raise ValueError("production_isolation_or_paused_config_unverified")
    return resources


def exact_rows(values: object, key: str, limit: int) -> list[dict]:
    """Require complete unique named records, never truncate or overwrite duplicates."""
    if (not isinstance(values, list) or len(values) > limit
            or not all(isinstance(value, dict) and isinstance(value.get(key), str) and value[key]
                       for value in values) or len({value[key] for value in values}) != len(values)):
        raise ValueError("production_inventory_unverified")
    return sorted(values, key=lambda value: value[key])


def script_inventory(provider: Provider) -> dict:
    """Collect successful SinglePage scripts and bracket every current binding set.

    This is current capability inventory, not deleted/historical version proof.
    A complete independently reviewed deployment/audit history remains necessary
    for the operational no-known-prior-writer disposition.
    """
    base = f"/accounts/{provider.account}/workers/scripts"
    response = provider.envelope(base)
    if response.get("result_info") not in (None, {}):
        raise ValueError("production_scripts_completeness_unverified")
    scripts = exact_rows(response.get("result"), "id", 1000)
    forbidden = {provider.resources.api, "amail-role-monitor", "amail-mail-maintenance"}
    result = {}
    for script in scripts:
        name = script["id"]
        if not NAME.fullmatch(name) or name in forbidden:
            raise ValueError("production_partial_bootstrap_or_prior_worker")
        settings = provider.get(f"{base}/{name}/settings")
        if not isinstance(settings, dict):
            raise ValueError("production_settings_unverified")
        bindings = exact_rows(settings.get("bindings"), "name", 100)
        for binding in bindings:
            kind = binding.get("type")
            if not isinstance(kind, str) or not kind:
                raise ValueError("production_binding_unverified")
            field = {"d1": "database_id", "r2_bucket": "bucket_name", "service": "service"}.get(kind)
            target = binding.get(field, binding.get("id") if kind == "d1" else None) if field else None
            if field and (not isinstance(target, str) or not target):
                raise ValueError("production_binding_target_unverified")
            if (kind == "d1" and "id" in binding and "database_id" in binding
                    and binding["id"] != binding["database_id"]):
                raise ValueError("production_binding_target_conflict")
            if (kind == "d1" and binding.get("id", binding.get("database_id")) == provider.resources.database
                    or kind == "r2_bucket" and binding.get("bucket_name") == provider.resources.bucket
                    or kind == "service" and binding.get("service") in forbidden):
                raise ValueError("production_unexpected_store_or_service_caller")
        # Capture settings stay private and do not become an all-off attestation.
        result[name] = {"script": script, "settings": settings}
    return result


def unattached_route(provider: Provider, zone: str, *, progress: Progress | None = None) -> dict:
    """Reject any Worker route or custom domain covering the intended Mail host."""
    if not ACCOUNT.fullmatch(zone):
        raise ValueError("production_zone_unverified")
    info = provider.get(f"/zones/{zone}")
    if (not isinstance(info, dict) or info.get("name") != "moesegfault.dev"
            or not isinstance(info.get("account"), dict) or info["account"].get("id") != provider.account):
        raise ValueError("production_zone_ownership_unverified")
    response = provider.envelope(f"/zones/{zone}/workers/routes")
    if response.get("result_info") not in (None, {}):
        raise ValueError("production_routes_completeness_unverified")
    routes = exact_rows(response.get("result"), "id", 1000)
    for route in routes:
        pattern = route.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError("production_route_shape_unverified")
        host = re.sub(r"^https?://", "", pattern).split("/", 1)[0]
        if fnmatch.fnmatchcase(provider.resources.domain, host) or route.get("script") in {
                provider.resources.api, "amail-role-monitor", "amail-mail-maintenance"}:
            raise ValueError("production_route_already_attached")
    # Reuse the strict single-response validator with this invocation's bounded
    # no-redirect transport. The response stays in memory; no extra read occurs.
    progress = progress or Progress()
    progress.stage = Stage.DOMAIN_IMPORT
    sys.path.insert(0, str(ROOT / "crates/mail-worker"))
    import check_trace_sink_isolation as isolation
    progress.stage = Stage.DOMAINS
    domains = isolation.worker_domain_rows(provider.envelope(f"/accounts/{provider.account}/workers/domains"))
    # DNS presentation normalizes only for host comparison, never for provider IDs.
    hosts = []
    for row in domains:
        hostname = row.get("hostname")
        if (not isinstance(hostname, str) or not 1 <= len(hostname) <= 254
                or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.?", hostname)
                or any(not 1 <= len(label) <= 63 or label.startswith("-") or label.endswith("-")
                       for label in hostname.removesuffix(".").split("."))):
            raise ValueError("production_domain_hostname_unverified")
        hosts.append(hostname.lower().removesuffix("."))
    if any(host == provider.resources.domain or row.get("service") == provider.resources.api
           for host, row in zip(hosts, domains)):
        raise ValueError("production_domain_already_attached")
    return {"routes": routes, "domains": domains}


def r2_count(client, bucket: str) -> int:
    """Enumerate the whole bucket metadata only; prefixes/partial pages never prove empty."""
    total, seen, keys = 0, set(), set()
    continuation = None
    for _ in range(100):
        args = {"Bucket": bucket, "MaxKeys": 1000}
        if continuation is not None:
            args["ContinuationToken"] = continuation
        page = client.list_objects_v2(**args)
        if (not isinstance(page, dict) or page.get("Name") != bucket
                or page.get("Prefix", "") != "" or page.get("Delimiter", "") != ""
                or type(page.get("IsTruncated")) is not bool):
            raise ValueError("production_r2_inventory_unverified")
        entries = exact_rows(page.get("Contents", []), "Key", 1000)
        if type(page.get("KeyCount")) is not int or page["KeyCount"] != len(entries):
            raise ValueError("production_r2_inventory_unverified")
        for entry in entries:
            if entry["Key"] in keys or type(entry.get("Size")) is not int or entry["Size"] < 0:
                raise ValueError("production_r2_inventory_unverified")
            keys.add(entry["Key"])
        total += len(entries)
        if not page["IsTruncated"]:
            return total
        continuation = page.get("NextContinuationToken")
        if not isinstance(continuation, str) or not continuation or continuation in seen:
            raise ValueError("production_r2_inventory_unverified")
        seen.add(continuation)
    raise ValueError("production_r2_inventory_incomplete")


def uninitialized_schema(provider: Provider) -> bool:
    """Recognize a truly empty cold database from successful metadata, never HTTP failure.

    D1 databases need not have Wrangler's migration table before their first
    migration. Any application object without that table is unknown retained
    schema, not an empty store. Existing recorded schemas still undergo the
    original exact-prefix verifier; this does not authorize migration of old D1.
    """
    with span("production.schema", "initial_inventory") as facts:
        objects = exact_rows(provider.query(INITIAL_SCHEMA), "name", 1000)
        if any(set(row) != {"type", "name"} or row["type"] not in
               {"table", "index", "view", "trigger"} for row in objects):
            raise ValueError("bootstrap_schema_inventory_unverified")
        if not objects:
            facts.reason = "uninitialized_database"
            return True
        if {"type": "table", "name": "d1_migrations"} not in objects:
            facts.reason = "bootstrap_unrecorded_schema"
            facts.schema_field = "d1_migrations"
            facts.schema_expected = "table_or_empty_database"
            facts.schema_actual_type = "missing_with_application_objects"
            raise ValueError("bootstrap_unrecorded_schema")
        return False


def collect(provider: Provider, zone: str, object_count: int, *, progress: Progress | None = None,
            allow_uninitialized: bool = False) -> dict:
    """Return current facts; only fresh bootstrap may inspect uninitialized old D1.

    An uninitialized store has no policy or grant, rather than a fictitious held
    row. Positive schema absence plus empty whole-bucket R2 and absent callers
    are necessary; history/old-work and external activation remain unverified.
    """
    progress = progress or Progress()
    progress.stage = Stage.SCRIPTS
    scripts = script_inventory(provider)
    progress.stage = Stage.ROUTES
    routes = unattached_route(provider, zone, progress=progress)
    progress.stage = Stage.SCHEMA
    if allow_uninitialized and uninitialized_schema(provider):
        if type(object_count) is not int or object_count != 0:
            raise ValueError("bootstrap_retained_state_requires_reconciliation")
        return {"scripts": scripts, "routes": routes, "policy": [], "gates": [],
                "journals": [{"n": 0}], "reservations": [{"n": 0}],
                "addresses": [{"n": 0}], "messages": [{"n": 0}], "objects": object_count,
                "database": provider.resources.database, "bucket": provider.resources.bucket,
                "source_sha": provider.resources.source_sha, "schema_prefix": 0}
    schema_prefix = verify_recorded_schema(provider.query)
    progress.stage = Stage.HOLD
    policy, gates = provider.query(POLICY), provider.query(GATES)
    journals = provider.query("SELECT COUNT(*) AS n FROM send_requests")
    reservations = provider.query("SELECT COUNT(*) AS n FROM storage_reservations")
    held_state(policy, gates, journals, reservations, object_count)
    progress.stage = Stage.MAIL
    addresses = provider.query("SELECT COUNT(*) AS n FROM addresses")
    messages = provider.query("SELECT COUNT(*) AS n FROM messages")
    if (addresses != [{"n": 0}] or messages != [{"n": 0}]
            or type(addresses[0].get("n")) is not int or type(messages[0].get("n")) is not int):
        raise ValueError("production_retained_mail_requires_recovery")
    return {"scripts": scripts, "routes": routes, "policy": policy, "gates": gates,
            "journals": journals, "reservations": reservations, "addresses": addresses,
            "messages": messages, "objects": object_count,
            "database": provider.resources.database, "bucket": provider.resources.bucket,
            "source_sha": provider.resources.source_sha, "schema_prefix": schema_prefix}



def write_summary(snapshot: dict) -> None:
    """Persist only source/run-bound digests and aggregate facts, never provider envelopes."""
    run_id = os.getenv("GITHUB_RUN_ID", "")
    if (not re.fullmatch(r"[1-9][0-9]{0,19}", run_id)
            or os.getenv("GITHUB_RUN_ATTEMPT") != "1"
            or os.getenv("GITHUB_REPOSITORY") != "kleedaisuki/moesegfault-amail"):
        raise ValueError("production_evidence_context_unverified")
    value = {
        "schema": "held-production-inspection/v1", "source_sha": snapshot["source_sha"],
        "run_id": run_id, "run_attempt": 1, "snapshot_sha256": stable_digest(snapshot),
        "schema_prefix": snapshot["schema_prefix"], "current_script_count": len(snapshot["scripts"]),
        "api_maintenance_role_absent": True, "current_store_callers_absent": True,
        "mail_route_unattached": True, "global_send_held": True, "live_grant_absent": True,
        "journal_count": 0, "reservation_count": 0, "address_count": 0, "message_count": 0,
        "r2_object_count": snapshot["objects"],
        "historical_absence": "UNVERIFIED", "old_work_end": "UNVERIFIED",
        "admission": "NOT_GRANTED",
    }
    folder = ROOT / ".temp"
    folder.mkdir(exist_ok=True)
    if folder.is_symlink():
        raise ValueError("production_evidence_path_unverified")
    target = folder / "held-production-inspection.json"
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(value, output, sort_keys=True, allow_nan=False)


def main() -> int:
    """Guard remote facts behind reviewed hosted main/production/freeze authorization."""
    progress = Progress()
    try:
        if (os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("GITHUB_REF") != "refs/heads/main"
                or os.getenv("AMAIL_PRODUCTION_PREFLIGHT_CONFIRM") != "INSPECT_HELD_PRODUCTION_BOOTSTRAP"
                or os.getenv("AMAIL_PRODUCTION_GRAPH_FREEZE") != "FREEZE_PRODUCTION_GRAPH_WRITERS"
                or os.getenv("AMAIL_PRODUCTION_ENVIRONMENT") != "production"):
            raise ValueError("production_inspection_not_authorized")
        progress.stage = Stage.RESOURCES
        resources = configured_resources(os.getenv("GITHUB_SHA", ""))
        provider = Provider(os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
                            os.getenv("CLOUDFLARE_API_TOKEN", ""), resources)
        # No boto/provider dependency is imported before all local safety guards.
        progress.stage = Stage.SDK
        import boto3
        from botocore.config import Config
        access, secret = os.getenv("CLOUDFLARE_ACCESS_KEY_ID", ""), os.getenv("CLOUDFLARE_SECRET_ACCESS_KEY", "")
        if not access or not secret:
            raise ValueError("production_r2_read_capability_missing")
        client = boto3.client("s3", endpoint_url=f"https://{provider.account}.r2.cloudflarestorage.com",
                              aws_access_key_id=access, aws_secret_access_key=secret, region_name="auto",
                              config=Config(connect_timeout=15, read_timeout=30, retries={"max_attempts": 0}))
        zone = os.getenv("CLOUDFLARE_ZONE_ID", "")
        progress.stage = Stage.R2
        first = collect(provider, zone, r2_count(client, resources.bucket), progress=progress)
        progress.stage = Stage.R2
        second = collect(provider, zone, r2_count(client, resources.bucket), progress=progress)
        progress.stage = Stage.STABILITY
        if stable_digest(first) != stable_digest(second):
            raise ValueError("production_inventory_drift")
        progress.stage = Stage.EVIDENCE
        write_summary(first)
        print("held_production_bootstrap_facts=verified_no_admission")
        print("held_production_bootstrap_provenance=current_inventory_only")
        return 0
    except Exception as error:
        print("held_production_bootstrap_facts=UNVERIFIED")
        print(f"held_production_bootstrap_stage={progress.stage.value} reason={failure_reason(error)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
