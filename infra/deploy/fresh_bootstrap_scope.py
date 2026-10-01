"""Single-attempt creation of source/run-owned fresh production Mail stores.

No command-line entrypoint, adoption, cleanup or automatic recovery is provided.
The protected controller owns admission; this module records write intent before
submission and keeps the original production/staging stores untouched.
"""

from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tomllib
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from control_plane_trace import response_facts, span
from fresh_bootstrap_contract import Epoch, Scope, ORIGINAL_BUCKET, ORIGINAL_DATABASE, STAGING_DATABASE, utc_timestamp
from pin_staging_mail import UUID

ROOT = Path(__file__).resolve().parents[2]
API = "https://api.cloudflare.com/client/v4"
LIMIT = 1_048_576
PAGE_SIZE = 1000
INVENTORY_LIMIT = 10000
SCRIPTS = "(?:amail-mail|amail-mail-maintenance|amail-trace-sink)"


class FreshError(ValueError):
    """Closed diagnostic reason; a failed POST never grants replay authority."""

    def __init__(self, reason: str):
        """Retain source-owned text only, never raw response or exception arguments."""
        super().__init__(reason)
        self.reason = reason


class NoRedirect(HTTPRedirectHandler):
    """Prevent bearer credentials from following a redirected authority."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Reject all redirects without submitting a second request."""
        return None


def _unique(pairs):
    """A repeated JSON key cannot overwrite an identity or successful verdict."""
    value = {}
    for key, item in pairs:
        if key in value:
            raise FreshError("fresh_provider_duplicate_key")
        value[key] = item
    return value


def _codes(value: object) -> list[int]:
    """Extract bounded numeric provider codes, excluding arbitrary error text."""
    errors = value.get("errors") if isinstance(value, dict) else None
    if not isinstance(errors, list):
        return []
    return [row["code"] for row in errors[:10] if isinstance(row, dict)
            and type(row.get("code")) is int and 0 <= row["code"] <= 2**31 - 1]


class FreshProvider:
    """One bounded Cloudflare request on an exact source-owned route family.

    Creation is disabled until create_scope binds an Epoch. D1 queries are
    disabled until successful scope creation, and accept read-only SQL only.
    Actual migration/deploy writes belong to the protected controller's existing
    source-owned Wrangler lane, not to a generic mutation capability here.
    """

    def __init__(self, account: str, token: str):
        """Validate account and private bearer without emitting either token text."""
        if (not isinstance(account, str) or re.fullmatch(r"[0-9a-f]{32}", account) is None
                or not isinstance(token, str) or not token or "\r" in token or "\n" in token):
            raise FreshError("fresh_provider_credentials_unreviewed")
        self.account, self.token = account, token
        self.opener = build_opener(NoRedirect)
        self._epoch = None
        self._scope = None
        self._submitted = set()

    def _route(self, method: str, suffix: str, body: object) -> str:
        """Review routes before token construction; no URL/query/path escape exists."""
        if not isinstance(suffix, str) or len(suffix) > 4096:
            raise FreshError("fresh_provider_route_unreviewed")
        url = urlsplit("/" + suffix if not suffix.startswith("/") else suffix)
        prefix = f"/accounts/{self.account}/"
        if url.scheme or url.netloc or url.fragment:
            raise FreshError("fresh_provider_route_unreviewed")
        try:
            query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            raise FreshError("fresh_provider_route_unreviewed") from None
        if any(len(values) != 1 for values in query.values()):
            raise FreshError("fresh_provider_route_unreviewed")
        if method == "GET" and body is None and url.path == "/zones":
            if (set(query) != {"account.id", "type", "per_page", "page"}
                    or query["account.id"] != [self.account]
                    or query["type"] != ["full,partial,secondary,internal"]
                    or query["per_page"] != ["50"]
                    or re.fullmatch(r"[1-9][0-9]{0,2}", query["page"][0]) is None):
                raise FreshError("fresh_provider_route_unreviewed")
            return "zones.inventory"
        if method == "GET" and body is None and not url.query and re.fullmatch(
                r"/zones/[0-9a-f]{32}(?:/workers/routes)?", url.path):
            return "zones.readback"
        if not url.path.startswith(prefix):
            raise FreshError("fresh_provider_route_unreviewed")
        path = url.path[len(prefix):]
        if method == "POST" and path in ("d1/database", "r2/buckets"):
            name = (self._epoch.database_name if path == "d1/database" else self._epoch.bucket_name) if self._epoch else None
            if query or name is None or body != {"name": name}:
                raise FreshError("fresh_provider_write_unreviewed")
            return "d1.create" if path == "d1/database" else "r2.create"
        if method == "POST" and self._scope and path == f"d1/database/{self._scope.database}/query":
            if (query or not isinstance(body, dict) or set(body) != {"sql", "params"}
                    or not isinstance(body["sql"], str) or not body["sql"].startswith(("SELECT ", "PRAGMA "))
                    or ";" in body["sql"] or body["params"] != []):
                raise FreshError("fresh_provider_write_unreviewed")
            if body["sql"].startswith("PRAGMA ") and re.fullmatch(
                    r"PRAGMA (?:table_xinfo|index_list|index_xinfo)\('[A-Za-z_][A-Za-z_0-9]*'\)", body["sql"]) is None:
                raise FreshError("fresh_provider_write_unreviewed")
            return "d1.query"
        if method != "GET" or body is not None:
            raise FreshError("fresh_provider_route_unreviewed")
        if path == "d1/database" and set(query) <= {"page", "per_page"}:
            if any(re.fullmatch(r"[1-9][0-9]{0,3}", values[0]) is None for values in query.values()):
                raise FreshError("fresh_provider_route_unreviewed")
            return "d1.list"
        if path == "r2/buckets" and set(query) <= {"cursor", "per_page"}:
            if ("per_page" in query and query["per_page"] != [str(PAGE_SIZE)]
                    or "cursor" in query and not 1 <= len(query["cursor"][0]) <= 2048):
                raise FreshError("fresh_provider_route_unreviewed")
            return "r2.list"
        if (re.fullmatch(rf"workers/scripts/{SCRIPTS}/deployments", path)
                and query == {"per_page": ["1"], "page": ["1"]}):
            return "workers.deployments"
        patterns = (
            (r"d1/database/[0-9a-f-]{36}", "d1.get"),
            (r"r2/buckets/moesegfault-mail-raw-production-[0-9a-f]{24}", "r2.get"),
            (r"workers/(?:scripts|domains)", "workers.inventory"),
            # Old-scope inspection must inventory every current potential writer,
            # not just the three intended new roles. Only settings are exposed.
            (r"workers/scripts/[A-Za-z0-9_-]{1,63}/settings", "workers.settings"),
            (r"queues", "queues.inventory"),
            (rf"workers/workers/{SCRIPTS}", "workers.current"),
            (rf"workers/scripts/{SCRIPTS}/(?:settings|script-settings|deployments|schedules|subdomain)", "workers.readback"),
            (rf"workers/scripts/{SCRIPTS}/versions/[0-9a-f-]{{36}}", "workers.version"),
            (r"queues/[0-9a-f]{32}(?:/consumers)?", "queues.readback"),
        )
        for pattern, family in patterns:
            if not query and re.fullmatch(pattern, path):
                return family
        raise FreshError("fresh_provider_route_unreviewed")

    def envelope(self, method: str, path: str, body: dict | None = None) -> dict:
        """Return one successful bounded envelope; never retry even an ambiguous POST."""
        family = self._route(method, path, body)
        path = "/" + path if not path.startswith("/") else path
        if family in ("d1.create", "r2.create"):
            if family in self._submitted:
                raise FreshError("fresh_scope_replay_refused")
            self._submitted.add(family)
        with span("fresh.cloudflare.request", "submit" if method == "POST" else "read",
                  method=method, endpoint=family, account_id=self.account) as facts:
            request = Request(API + path, method=method,
                              data=None if body is None else json.dumps(body).encode(),
                              headers={"Authorization": "Bearer " + self.token,
                                       "Accept": "application/json", "Content-Type": "application/json"})
            try:
                with self.opener.open(request, timeout=30) as response:
                    response_facts(facts, response.status, response.headers)
                    raw = response.read(LIMIT + 1)
                if len(raw) > LIMIT:
                    raise FreshError("fresh_provider_body_limit")
                value = json.loads(raw, object_pairs_hook=_unique)
                facts.provider_error_codes = _codes(value)
                if (not isinstance(value, dict) or value.get("success") is not True
                        or value.get("errors") != [] or "result" not in value
                        or facts.http_status is None or not 200 <= facts.http_status < 300):
                    raise FreshError("fresh_provider_envelope_unverified")
                return value
            except HTTPError as error:
                response_facts(facts, error.code, error.headers)
                try:
                    raw = error.read(LIMIT + 1)
                    if len(raw) <= LIMIT:
                        facts.provider_error_codes = _codes(json.loads(raw, object_pairs_hook=_unique))
                except Exception:
                    pass
                facts.error_type = type(error).__name__
                facts.reason = "existing_conflict" if error.code == 409 else "http_error"
                raise FreshError("fresh_create_existing_refused" if error.code == 409
                                 else "fresh_provider_http_failure") from None
            except (TimeoutError, URLError, OSError) as error:
                facts.error_type = type(error).__name__
                facts.reason = "write_ambiguous" if method == "POST" else "read_failed"
                raise FreshError("fresh_write_ambiguous" if method == "POST"
                                 else "fresh_provider_read_failed") from None
            except (ValueError, TypeError) as error:
                facts.reason = error.reason if isinstance(error, FreshError) else "schema_invalid"
                raise FreshError(facts.reason if isinstance(error, FreshError)
                                 else "fresh_provider_schema_invalid") from None

    def get(self, path: str):
        """Return a result only; inventory completeness requires the full envelope."""
        return self.envelope("GET", path)["result"]

    def post(self, path: str, body: dict):
        """Submit once and return result; existing/conflict is never success."""
        return self.envelope("POST", path, body)["result"]


def _timestamp(value: object) -> str:
    """Validate provider UTC ISO8601 first, then drop precision for the v2 contract."""
    if not isinstance(value, str) or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z", value) is None:
        raise FreshError("fresh_creation_time_unreviewed")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return utc_timestamp(parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        raise FreshError("fresh_creation_time_unreviewed") from None


def _absence(provider, epoch: Epoch) -> None:
    """Complete successful D1 and default-jurisdiction R2 lists precede every write."""
    prefix = f"/accounts/{provider.account}"
    seen, total = set(), None
    for page in range(1, 12):
        value = provider.envelope("GET", prefix + f"/d1/database?page={page}&per_page={PAGE_SIZE}")
        rows, info = value.get("result"), value.get("result_info")
        if (value.get("success") is not True or value.get("errors") != []
                or not isinstance(rows, list) or not isinstance(info, dict)
                or any(type(info.get(key)) is not int for key in ("count", "page", "per_page", "total_count"))
                or info["page"] != page or info["per_page"] != PAGE_SIZE
                or info["count"] != len(rows) or len(rows) > PAGE_SIZE
                or not 0 <= info["total_count"] <= INVENTORY_LIMIT
                or total is not None and total != info["total_count"]):
            raise FreshError("fresh_d1_inventory_incomplete")
        total = info["total_count"]
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get("uuid"), str)
                    or UUID.fullmatch(row["uuid"]) is None or row["uuid"] in seen
                    or not isinstance(row.get("name"), str) or not row["name"]):
                raise FreshError("fresh_d1_inventory_incomplete")
            seen.add(row["uuid"])
            if row["name"] == epoch.database_name:
                raise FreshError("fresh_create_existing_refused")
        if len(seen) == total:
            break
        if not rows or len(seen) > total:
            raise FreshError("fresh_d1_inventory_incomplete")
    else:
        raise FreshError("fresh_d1_inventory_incomplete")
    seen, cursors, cursor = set(), set(), ""
    for _ in range(11):
        query = {"per_page": PAGE_SIZE}
        if cursor:
            query["cursor"] = cursor
        value = provider.envelope("GET", prefix + "/r2/buckets?" + urlencode(query))
        result, info = value.get("result"), value.get("result_info", {})
        rows = result.get("buckets") if isinstance(result, dict) else None
        # R2 continuation metadata is optional, unlike D1's counted pages.
        # A present smaller server limit is valid; every returned cursor is followed.
        page_limit = info.get("per_page", PAGE_SIZE) if isinstance(info, dict) else None
        if (value.get("success") is not True or value.get("errors") != []
                or not isinstance(rows, list) or len(rows) > PAGE_SIZE or not isinstance(info, dict)
                or type(page_limit) is not int or not 1 <= page_limit <= PAGE_SIZE
                or len(rows) > page_limit
                or not isinstance(info.get("cursor", ""), str)
                or len(info.get("cursor", "")) > 2048):
            raise FreshError("fresh_r2_inventory_incomplete")
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get("name"), str)
                    or not row["name"] or row["name"] in seen):
                raise FreshError("fresh_r2_inventory_incomplete")
            seen.add(row["name"])
            if row["name"] == epoch.bucket_name:
                raise FreshError("fresh_create_existing_refused")
        cursor = info.get("cursor", "")
        if len(seen) > INVENTORY_LIMIT or cursor and (not rows or cursor in cursors):
            raise FreshError("fresh_r2_inventory_incomplete")
        if not cursor:
            return
        cursors.add(cursor)
    raise FreshError("fresh_r2_inventory_incomplete")


def _record(file, value: dict) -> None:
    """Flush/fsync a closed recovery record before any following provider operation."""
    file.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    file.flush()
    os.fsync(file.fileno())


def _identity(value: object, epoch: Epoch, database: bool) -> tuple[str, str]:
    """Successful response and exact GET must agree in name, UUID and timestamp."""
    name = epoch.database_name if database else epoch.bucket_name
    if not isinstance(value, dict) or value.get("name") != name:
        raise FreshError("fresh_created_identity_unverified")
    if not database and value.get("jurisdiction", "default") != "default":
        raise FreshError("fresh_created_identity_unverified")
    identifier = value.get("uuid") if database else name
    if database and (not isinstance(identifier, str) or UUID.fullmatch(identifier) is None
                     or identifier in (ORIGINAL_DATABASE, STAGING_DATABASE)):
        raise FreshError("fresh_created_identity_unverified")
    timestamp = value.get("created_at" if database else "creation_date")
    _timestamp(timestamp)
    return identifier, timestamp


def create_scope(provider, epoch: Epoch, recovery_path: Path) -> Scope:
    """Create only the derived epoch names once, retaining partial/ambiguous ownership.

    Existing recovery_path refuses replay even if the earlier journal is partial.
    The journal is recovery metadata, not an admission receipt. On any failure the
    protected controller must retain it; no delete, cleanup or new epoch fallback
    is authorized. Both absence inventories succeed before the first POST.
    """
    if not isinstance(epoch, Epoch):
        raise FreshError("fresh_epoch_unreviewed")
    with Path(recovery_path).open("x", encoding="utf-8") as file:
        _record(file, {"schema": "mail-fresh-scope-recovery/v1", "event": "ownership",
                       "epoch": asdict(epoch), "database_name": epoch.database_name,
                       "bucket": epoch.bucket_name, "may_replay_write": False})
        try:
            _absence(provider, epoch)
            if isinstance(provider, FreshProvider):
                if provider._epoch is not None:
                    raise FreshError("fresh_scope_replay_refused")
                provider._epoch = epoch
            prefix = f"/accounts/{provider.account}"
            _record(file, {"event": "d1_submit_intent", "name": epoch.database_name, "attempt": 1})
            created = _identity(provider.post(prefix + "/d1/database", {"name": epoch.database_name}), epoch, True)
            _record(file, {"event": "d1_created", "database": created[0], "created_at": created[1]})
            if _identity(provider.get(prefix + "/d1/database/" + created[0]), epoch, True) != created:
                raise FreshError("fresh_created_readback_mismatch")
            _record(file, {"event": "d1_readback_verified", "database": created[0]})
            _record(file, {"event": "r2_submit_intent", "name": epoch.bucket_name, "attempt": 1})
            bucket = _identity(provider.post(prefix + "/r2/buckets", {"name": epoch.bucket_name}), epoch, False)
            _record(file, {"event": "r2_created", "bucket": bucket[0], "creation_date": bucket[1]})
            if _identity(provider.get(prefix + "/r2/buckets/" + bucket[0]), epoch, False) != bucket:
                raise FreshError("fresh_created_readback_mismatch")
            scope = Scope(epoch, created[0], _timestamp(created[1]), _timestamp(bucket[1]))
            _record(file, {"event": "scope_readback_verified", "scope": asdict(scope)})
            if isinstance(provider, FreshProvider):
                provider._scope = scope
            return scope
        except Exception as error:
            _record(file, {"event": "recovery_only", "may_replay_write": False,
                           "reason": error.reason if isinstance(error, FreshError) else "fresh_scope_failed"})
            if isinstance(error, FreshError):
                raise
            raise FreshError("fresh_scope_failed") from None


def reconcile_scope(provider, epoch: Epoch, path: Path) -> dict:
    """Read known successful-create coordinates once; unknown never becomes absence.

    This bounded recovery observation grants neither adoption nor write replay.
    A timeout before the successful response leaves the affected identity UNKNOWN
    even if a similarly named store now exists. Operator reconciliation remains
    separately reviewed, and this function cannot create a successful receipt.
    """
    if not isinstance(epoch, Epoch):
        raise FreshError("fresh_epoch_unreviewed")
    with Path(path).open("rb") as file:
        raw = file.read(65537)
    if len(raw) > 65536:
        raise FreshError("fresh_recovery_journal_unverified")
    try:
        records = [json.loads(line, object_pairs_hook=_unique) for line in raw.splitlines()]
    except (ValueError, UnicodeError):
        raise FreshError("fresh_recovery_journal_unverified") from None
    if (not 1 <= len(records) <= 12 or not all(isinstance(row, dict) for row in records)
            or records[0] != {"schema": "mail-fresh-scope-recovery/v1", "event": "ownership",
                              "epoch": asdict(epoch), "database_name": epoch.database_name,
                              "bucket": epoch.bucket_name, "may_replay_write": False}):
        raise FreshError("fresh_recovery_journal_unverified")
    expected_events = ["d1_submit_intent", "d1_created", "d1_readback_verified",
                       "r2_submit_intent", "r2_created", "scope_readback_verified"]
    events = [row.get("event") for row in records[1:]]
    if events and events[-1] == "recovery_only":
        events = events[:-1]
    if events != expected_events[:len(events)]:
        raise FreshError("fresh_recovery_journal_unverified")
    for record in records[1:]:
        if record.get("event") in ("d1_submit_intent", "r2_submit_intent"):
            name = epoch.database_name if record["event"] == "d1_submit_intent" else epoch.bucket_name
            if record != {"event": record["event"], "name": name, "attempt": 1}:
                raise FreshError("fresh_recovery_journal_unverified")
    result = {"database": "UNKNOWN", "bucket": "UNKNOWN", "may_replay_write": False,
              "adoption": "NOT_GRANTED"}
    prefix = f"accounts/{provider.account}"
    for key, event, field, time_field, database, route in (
            ("database", "d1_created", "database", "created_at", True, "/d1/database/"),
            ("bucket", "r2_created", "bucket", "creation_date", False, "/r2/buckets/")):
        matches = [row for row in records if row.get("event") == event]
        if len(matches) > 1:
            raise FreshError("fresh_recovery_journal_unverified")
        if not matches:
            continue
        row = matches[0]
        expected = _identity({"name": epoch.database_name if database else row.get(field),
                              "uuid": row.get(field), time_field: row.get(time_field)}, epoch, database)
        try:
            observed = _identity(provider.get(prefix + route + expected[0]), epoch, database)
            if observed == expected:
                result[key] = "CREATED_IDENTITY_OBSERVED"
        except Exception:
            # An unavailable or missing resource is not proven absence and must
            # not authorize a replacement or replay of the original operation.
            pass
    return result


def render_configs(scope: Scope, folder: Path) -> dict[str, Path]:
    """Derive configs without rebuilding; preserve staging, routing, secrets and Cron.

    Only production store coordinates, absolute original source main/migration
    paths and explicit API preview disablement differ. The exact staging source
    text remains byte-for-byte. Preview disablement is held-surface source policy,
    not an operator-controlled configuration override.
    Existing output files refuse replacement; callers use their owned temp folder.
    """
    if not isinstance(scope, Scope):
        raise FreshError("fresh_scope_unreviewed")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    result = {}
    for key, name in (("api", "wrangler.toml"), ("maintenance", "wrangler-maintenance.toml")):
        source = ROOT / "crates/mail-worker" / name
        text = source.read_text(encoding="utf-8")
        production, marker, staging = text.partition("[env.staging]")
        original = tomllib.loads(text)
        if (original.get("triggers", {}).get("crons") != []
                or original.get("env", {}).get("staging", {}).get("triggers", {}).get("crons") != []):
            raise FreshError("fresh_config_cron_unreviewed")
        replacements = {
            'database_name = "moesegfault-mail-production"': f'database_name = "{scope.database_name}"',
            f'database_id = "{ORIGINAL_DATABASE}"': f'database_id = "{scope.database}"',
            f'bucket_name = "{ORIGINAL_BUCKET}"': f'bucket_name = "{scope.bucket}"',
            f'main = "entry/{key}.mjs"': 'main = ' + json.dumps((source.parent / f"entry/{key}.mjs").as_posix()),
        }
        if key == "api":
            replacements['migrations_dir = "migrations"'] = 'migrations_dir = ' + json.dumps((source.parent / "migrations").as_posix())
        for old, new in replacements.items():
            if production.count(old) != 1:
                raise FreshError("fresh_config_source_unreviewed")
            production = production.replace(old, new)
        if key == "api":
            if "preview_urls" in original:
                if original["preview_urls"] is not False:
                    raise FreshError("fresh_config_preview_unreviewed")
            else:
                if production.count("workers_dev = false") != 1:
                    raise FreshError("fresh_config_source_unreviewed")
                production = production.replace("workers_dev = false", "workers_dev = false\npreview_urls = false")
        rendered = production + marker + staging
        updated = tomllib.loads(rendered)
        if updated["env"] != original["env"]:
            raise FreshError("fresh_config_staging_drift")
        path = folder / name
        with path.open("x", encoding="utf-8", newline="\n") as file:
            file.write(rendered)
        result[key] = path
    return result
