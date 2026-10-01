"""Single-attempt, receipt-owned ingress for the fixed native tracing canary.

Provider writes never target existing mail, identity, domains or certificates.
Only a positively new DNS record and Route may be removed by this module.
"""

from datetime import datetime, timezone
from fnmatch import fnmatchcase
from ipaddress import IPv6Address
import re
from urllib.error import HTTPError
from urllib.parse import quote

ZONE_ID = "6edff81c6ed02f412e70868076411a5e"
ZONE_NAME = "moesegfault.dev"
HOST = "amail-native-trace-canary.moesegfault.dev"
PROBE = "amail-native-trace-probe"
CALLER = "amail-native-trace-caller"
PATTERN = f"https://{HOST}/*"
ZONE = f"/zones/{ZONE_ID}"


def opaque_id(value):
    """Accept provider identifiers as bounded opaque path segments, not hashes."""
    if not isinstance(value, str) or not 1 <= len(value) <= 256 or any(
            char.isspace() or ord(char) < 33 or ord(char) == 127 for char in value):
        raise ValueError("native_ingress_identifier_invalid")
    return value


def hostname(value):
    """Normalize a public DNS name without accepting URL or wildcard syntax."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.*-]+\.?", value):
        raise ValueError("native_ingress_hostname_invalid")
    return value.lower().rstrip(".")


def inventory(provider, path):
    """Require complete, count-consistent paginated inventories before absence."""
    rows, expected, seen = [], None, set()
    for page in range(1, 101):
        value = provider.request("GET", f"{path}?per_page=100&page={page}", envelope=True)
        items, info = value.get("result"), value.get("result_info")
        if not isinstance(items, list) or not isinstance(info, dict):
            raise ValueError("native_ingress_inventory_incomplete")
        count, total, pages = info.get("count"), info.get("total_count"), info.get("total_pages")
        if (any(type(number) is not int for number in (count, total, pages))
                or count != len(items) or not 0 <= total <= 10000
                or not 0 <= pages <= 100 or info.get("page") != page
                or (expected is not None and expected != (total, pages))):
            raise ValueError("native_ingress_inventory_incomplete")
        expected = total, pages
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("native_ingress_inventory_invalid")
            key = opaque_id(item.get("id"))
            if key in seen:
                raise ValueError("native_ingress_inventory_duplicate")
            seen.add(key)
            rows.append(item)
        if page >= max(pages, 1):
            if len(rows) != total:
                raise ValueError("native_ingress_inventory_incomplete")
            return rows
    raise ValueError("native_ingress_inventory_limit")


def routes(provider):
    """Routes list has no pagination contract; preserve its complete array."""
    rows = provider.request("GET", ZONE + "/workers/routes")
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError("native_ingress_routes_invalid")
    ids = [opaque_id(row.get("id")) for row in rows if isinstance(row, dict)]
    if len(ids) != len(rows) or len(ids) != len(set(ids)):
        raise ValueError("native_ingress_routes_invalid")
    return rows


def overlaps(pattern):
    """Check the fixed hostname, refusing unrecognized route pattern grammar."""
    if not isinstance(pattern, str):
        raise ValueError("native_ingress_route_pattern_invalid")
    match = re.fullmatch(r"(?:(https?)://)?([A-Za-z0-9.*-]+)(/[^?#\s]*)?", pattern)
    if not match:
        raise ValueError("native_ingress_route_pattern_invalid")
    host = match.group(2).lower().rstrip(".")
    # All paths on our hostname are reserved, including more-specific paths.
    return fnmatchcase(HOST, host)


def dns_rows(provider):
    """Inspect all DNS types at the reserved hostname, never just AAAA."""
    return [row for row in inventory(provider, ZONE + "/dns_records")
            if hostname(row.get("name")) == HOST]


def ssl_ready(provider):
    """Require an already active covering Universal certificate; do not order one."""
    settings = provider.request("GET", ZONE + "/ssl/universal/settings")
    if not isinstance(settings, dict) or settings.get("enabled") is not True:
        raise ValueError("native_ingress_ssl_disabled")
    now = datetime.now(timezone.utc)
    for pack in inventory(provider, ZONE + "/ssl/certificate_packs"):
        if pack.get("type") != "universal" or pack.get("status") != "active":
            continue
        certificates = pack.get("certificates")
        if not isinstance(certificates, list):
            continue
        for cert in certificates:
            if not isinstance(cert, dict) or cert.get("status") != "active":
                continue
            hosts = cert.get("hosts")
            if not isinstance(hosts, list) or not any(
                    hostname(host) in (HOST, "*." + ZONE_NAME) for host in hosts):
                continue
            try:
                expiry = datetime.fromisoformat(cert["expires_on"].replace("Z", "+00:00"))
                uploaded = cert.get("uploaded_on")
                start = datetime.fromisoformat(uploaded.replace("Z", "+00:00")) if uploaded else now
                if expiry.utcoffset() is not None and start.utcoffset() is not None and start <= now < expiry:
                    return
            except (KeyError, ValueError, TypeError, AttributeError):
                continue
    raise ValueError("native_ingress_ssl_unready")


def preflight(provider):
    """Read-only absence/TLS admission; read permission never implies write grant."""
    zone = provider.request("GET", ZONE)
    if (not isinstance(zone, dict) or zone.get("id") != ZONE_ID
            or zone.get("name") != ZONE_NAME or zone.get("status") != "active"
            or zone.get("paused") is not False or zone.get("type") != "full"
            or not isinstance(zone.get("account"), dict)
            or zone["account"].get("id") != provider.account):
        raise ValueError("native_ingress_zone_mismatch")
    ssl_ready(provider)
    if dns_rows(provider):
        raise ValueError("native_ingress_dns_conflict")
    if any(overlaps(row.get("pattern")) for row in routes(provider)):
        raise ValueError("native_ingress_route_conflict")
    domains = inventory(provider, f"/accounts/{provider.account}/workers/domains")
    if any(hostname(row.get("hostname")) == HOST for row in domains):
        raise ValueError("native_ingress_domain_conflict")
    for name in (PROBE, CALLER):
        if read_optional(provider, provider.script(name)) is not None:
            raise ValueError("native_ingress_script_conflict")
    return {"schema": "native-route-preflight/v1", "zone_id": ZONE_ID,
            "hostname": HOST, "account_id": provider.account, "zone_active": True,
            "universal_ssl_active": True, "inventory_absent": True, "scripts_absent": True}


def read_optional(provider, path):
    """Only a successful exact 404 means absence; authorization failures propagate."""
    try:
        result = provider.request("GET", path)
        if not isinstance(result, dict):
            raise ValueError("native_ingress_readback_invalid")
        return result
    except HTTPError as error:
        if error.code != 404:
            raise
        return None


def state(provider, receipt):
    """Bind public operation coordinates to the original run, not user input."""
    if (not re.fullmatch(r"[0-9a-f]{32}", str(receipt.get("probe_id", "")))
            or not re.fullmatch(r"[0-9a-f]{40}", str(receipt.get("source_sha", "")))
            or not re.fullmatch(r"[0-9]+", str(receipt.get("run_id", "")))):
        raise ValueError("native_ingress_receipt_invalid")
    ingress = receipt.get("ingress")
    if (not isinstance(ingress, dict) or ingress.get("schema") != "native-route-ingress/v1"
            or ingress.get("zone_id") != ZONE_ID or ingress.get("hostname") != HOST
            or ingress.get("preflight") != {
                "schema": "native-route-preflight/v1", "zone_id": ZONE_ID,
                "hostname": HOST, "account_id": provider.account, "zone_active": True,
                "universal_ssl_active": True, "inventory_absent": True, "scripts_absent": True}):
        raise ValueError("native_ingress_preflight_missing")
    return ingress


def assert_pair(provider, receipt):
    """Verify exact run-owned roles and serving versions before route exposure."""
    state(provider, receipt)
    for name, role in ((PROBE, "probe"), (CALLER, "caller")):
        settings = provider.request("GET", provider.script(name))
        bindings = settings.get("bindings") if isinstance(settings, dict) else None
        if not isinstance(bindings, list):
            raise ValueError("native_ingress_script_ownership")
        values = {key: [item.get("text") for item in bindings if isinstance(item, dict)
                       and item.get("type") == "plain_text" and item.get("name") == key]
                  for key in ("PROBE_ID", "CANARY_ROLE")}
        if values != {"PROBE_ID": [receipt["probe_id"]], "CANARY_ROLE": [role]}:
            raise ValueError("native_ingress_script_ownership")
        result = provider.request("GET", provider.script(name, "deployments"))
        deployments = result.get("deployments") if isinstance(result, dict) else None
        versions = receipt.get("versions")
        version = versions.get(name) if isinstance(versions, dict) else None
        if (not version or not isinstance(deployments, list) or not deployments
                or not isinstance(deployments[0], dict)
                or deployments[0].get("versions") != [{"version_id": version, "percentage": 100}]):
            raise ValueError("native_ingress_script_version")


def dns_matches(row, receipt, identifier=None):
    """A nonce comment alone is insufficient: compare every intended DNS field."""
    try:
        return (isinstance(row, dict) and opaque_id(row.get("id")) == (identifier or row["id"])
                and hostname(row.get("name")) == HOST and row.get("type") == "AAAA"
                and IPv6Address(row.get("content")) == IPv6Address("100::")
                and row.get("proxied") is True and row.get("ttl") == 1
                and row.get("comment") == "amail-native-tracing/" + receipt["probe_id"])
    except (ValueError, TypeError, KeyError):
        return False


def route_matches(row, identifier):
    """The Route has no nonce field; pair ownership is a separate mandatory gate."""
    return (isinstance(row, dict) and row.get("id") == identifier
            and row.get("pattern") == PATTERN and row.get("script") == CALLER)


def resource_path(kind, identifier):
    """Encode opaque identifiers to prevent provider path injection."""
    family = "dns_records" if kind == "dns" else "workers/routes"
    return ZONE + "/" + family + "/" + quote(opaque_id(identifier), safe="")


def create_dns(provider, receipt, persist):
    """Attempt the smallest new owned resource once, before deploying the pair."""
    ingress = state(provider, receipt)
    if "dns" in ingress or dns_rows(provider):
        raise ValueError("native_ingress_dns_create_refused")
    body = {"type": "AAAA", "name": HOST, "content": "100::", "proxied": True,
            "ttl": 1, "comment": "amail-native-tracing/" + receipt["probe_id"]}
    item = ingress["dns"] = {"phase": "attempted"}
    persist(receipt)
    try:
        result = provider.request("POST", ZONE + "/dns_records", body)
        identifier = opaque_id(result.get("id")) if isinstance(result, dict) else opaque_id(None)
        if not dns_matches(result, receipt, identifier):
            raise ValueError("native_ingress_dns_acknowledgement")
        item["id"] = identifier
        persist(receipt)
        actual = provider.request("GET", resource_path("dns", identifier))
        if not dns_matches(actual, receipt, identifier):
            raise ValueError("native_ingress_dns_readback")
        item["phase"] = "verified"
        persist(receipt)
    except Exception:
        item["phase"] = "unknown"
        persist(receipt)
        raise


def create_route(provider, receipt, persist):
    """Expose only the verified owned pair after exact DNS and route absence."""
    ingress = state(provider, receipt)
    assert_pair(provider, receipt)
    dns = ingress.get("dns", {})
    rows = dns_rows(provider)
    if dns.get("phase") != "verified" or len(rows) != 1 or not dns_matches(
            rows[0], receipt, dns.get("id")):
        raise ValueError("native_ingress_dns_unverified")
    if "route" in ingress or any(overlaps(row.get("pattern")) for row in routes(provider)):
        raise ValueError("native_ingress_route_create_refused")
    item = ingress["route"] = {"phase": "attempted"}
    persist(receipt)
    try:
        result = provider.request("POST", ZONE + "/workers/routes", {"pattern": PATTERN, "script": CALLER})
        identifier = opaque_id(result.get("id")) if isinstance(result, dict) else opaque_id(None)
        if not route_matches(result, identifier):
            raise ValueError("native_ingress_route_acknowledgement")
        item["id"] = identifier
        persist(receipt)
        if not route_matches(provider.request("GET", resource_path("route", identifier)), identifier):
            raise ValueError("native_ingress_route_readback")
        item["phase"] = "verified"
        persist(receipt)
    except Exception:
        item["phase"] = "unknown"
        persist(receipt)
        raise


def assert_ingress(provider, receipt):
    """Recheck ownership, exclusive ingress and serving pair immediately before POST."""
    ingress = state(provider, receipt)
    assert_pair(provider, receipt)
    ssl_ready(provider)
    domains = inventory(provider, f"/accounts/{provider.account}/workers/domains")
    if any(hostname(row.get("hostname")) == HOST for row in domains):
        raise ValueError("native_ingress_domain_conflict")
    dns, route = ingress.get("dns", {}), ingress.get("route", {})
    if dns.get("phase") != "verified" or route.get("phase") != "verified":
        raise ValueError("native_ingress_not_verified")
    rows = dns_rows(provider)
    if len(rows) != 1 or not dns_matches(rows[0], receipt, dns.get("id")):
        raise ValueError("native_ingress_dns_ownership")
    rows = [row for row in routes(provider) if overlaps(row.get("pattern"))]
    if len(rows) != 1 or not route_matches(rows[0], route.get("id")):
        raise ValueError("native_ingress_route_ownership")


def cleanup_ingress(provider, receipt, persist):
    """Remove Route then DNS; any ambiguous ownership stops downstream script cleanup.

    An unknown create may be located only by one exact run-owned inventory match.
    An unknown DELETE is resolved by reads only and is never submitted a second time.
    """
    ingress = state(provider, receipt)
    for kind in ("route", "dns"):
        item = ingress.get(kind)
        rows = ([row for row in routes(provider) if overlaps(row.get("pattern"))]
                if kind == "route" else dns_rows(provider))
        if item is None:
            if rows:
                raise ValueError("native_ingress_unowned_resource")
            continue
        if not isinstance(item, dict) or item.get("phase") not in (
                "attempted", "verified", "unknown", "delete_attempted", "delete_unknown", "deleted"):
            raise ValueError("native_ingress_phase_invalid")
        if not rows:
            item["phase"] = "deleted"
            persist(receipt)
            continue
        if len(rows) != 1:
            raise ValueError("native_ingress_cleanup_ambiguous")
        row = rows[0]
        identifier = opaque_id(row.get("id"))
        if item.get("id") is not None and item["id"] != identifier:
            raise ValueError("native_ingress_replaced")
        if kind == "route":
            assert_pair(provider, receipt)
            matches = route_matches(row, identifier)
        else:
            matches = dns_matches(row, receipt, identifier)
        if not matches or item["phase"] in ("delete_attempted", "delete_unknown", "deleted"):
            raise ValueError("native_ingress_cleanup_unresolved")
        item.update(id=identifier, phase="delete_attempted")
        persist(receipt)
        try:
            result = provider.request("DELETE", resource_path(kind, identifier))
            if not isinstance(result, dict) or result.get("id") != identifier:
                raise ValueError("native_ingress_delete_acknowledgement")
            if read_optional(provider, resource_path(kind, identifier)) is not None:
                raise ValueError("native_ingress_delete_readback")
            remaining = ([row for row in routes(provider) if overlaps(row.get("pattern"))]
                         if kind == "route" else dns_rows(provider))
            if remaining:
                raise ValueError("native_ingress_cleanup_replacement")
            item["phase"] = "deleted"
            persist(receipt)
        except Exception:
            item["phase"] = "delete_unknown"
            persist(receipt)
            raise
