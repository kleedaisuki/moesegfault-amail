"""Complete staging quota readback, without an executable live entry point.

The future reviewed Windows wrapper may compose this read-only Cloudflare
adapter with fresh native PKCE, exact CLI capabilities and immutable artifact
orchestration. This module cannot create accounts, routes, mail or deployments.
Private provider records remain in memory/encrypted manifests, never logs.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Callable
from urllib.parse import parse_qs, quote
from urllib.request import Request

import staging_ten_address_manifest as manifest
from staging_mail_e2e import cf_rules, control_open

require = manifest.require
API = "https://api.cloudflare.com/client/v4"
DB = "74f35f95-42ce-482c-86e6-dffbdd35cbbe"
BUCKET = "moesegfault-mail-raw-staging"
MAX_ROWS = 2000
UUID = re.compile(r"[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}\Z")
HEX32 = re.compile(r"[a-f0-9]{32}\Z")
ADDRESS = re.compile(r"[^\s@]{1,64}@[a-z0-9.-]{1,253}\Z")


def digest(value: object) -> str:
    """Fingerprint every raw field so normalization cannot conceal drift."""
    return hashlib.sha256(manifest.canonical(value)).hexdigest()


def normalize_rules(raw: list[dict]) -> list[dict]:
    """Accept complete single-literal inventories; classify every supported action.

    Forward/drop rules elsewhere in the zone count toward headroom and are
    retained exactly by a raw digest. Unknown/multiple/nonliteral matchers or
    actions fail closed, rather than being filtered into apparently free slots.
    Only an exact worker action can be eligible for supported CLI recovery.
    """
    require(isinstance(raw, list) and len(raw) <= MAX_ROWS, "routing_inventory_invalid")
    result = []
    seen = set()
    for rule in raw:
        require(isinstance(rule, dict), "routing_inventory_invalid")
        identity = rule.get("id")
        matchers, actions = rule.get("matchers"), rule.get("actions")
        require(isinstance(identity, str) and HEX32.fullmatch(identity) is not None
                and identity not in seen and type(rule.get("enabled")) is bool
                and isinstance(rule.get("source"), str) and bool(rule["source"])
                and isinstance(rule.get("name"), str) and bool(rule["name"])
                and isinstance(matchers, list) and len(matchers) == 1
                and isinstance(actions, list) and len(actions) == 1,
                "routing_inventory_invalid")
        matcher, action = matchers[0], actions[0]
        require(isinstance(matcher, dict) and set(matcher) == {"type", "field", "value"}
                and matcher["type"] == "literal" and matcher["field"] == "to"
                and isinstance(matcher["value"], str) and ADDRESS.fullmatch(matcher["value"]) is not None
                and matcher["value"] == matcher["value"].lower(), "routing_matcher_unsupported")
        require(isinstance(action, dict) and set(action) in ({"type", "value"}, {"type"})
                and action.get("type") in ("worker", "forward", "drop"), "routing_action_unsupported")
        values = action.get("value", [])
        require(isinstance(values, list), "routing_action_unsupported")
        if action["type"] == "worker":
            require(set(action) == {"type", "value"} and len(values) == 1
                    and isinstance(values[0], str) and re.fullmatch(r"[a-z0-9-]{1,63}", values[0]) is not None,
                    "routing_action_unsupported")
            worker = values[0]
        elif action["type"] == "forward":
            require(set(action) == {"type", "value"} and 1 <= len(values) <= 200
                    and all(isinstance(v, str) and ADDRESS.fullmatch(v) is not None for v in values)
                    and len(set(values)) == len(values), "routing_action_unsupported")
            worker = "non-worker:forward"
        else:
            require(not values, "routing_action_unsupported")
            worker = "non-worker:drop"
        seen.add(identity)
        result.append({"id": identity, "address": matcher["value"], "enabled": rule["enabled"],
                       "source": rule["source"], "name": rule["name"], "worker": worker,
                       "raw_digest": digest(rule)})
    return sorted(result, key=lambda rule: rule["id"])


def rows_from_batch(rows: list[dict], count: int, resources: tuple[str, ...]) -> dict[str, dict]:
    """Validate complete unprojected global allocations plus candidate tombstones."""
    require(isinstance(rows, list) and len(rows) <= MAX_ROWS and type(count) is int
            and 0 <= count <= MAX_ROWS, "d1_inventory_invalid")
    result = {}
    for row in rows:
        require(isinstance(row, dict) and set(row) == manifest.ROW_KEYS | {"address"},
                "d1_inventory_invalid")
        address = row["address"]
        require(isinstance(address, str) and ADDRESS.fullmatch(address) is not None
                and address not in result and (row["state"] != "retired" or address in resources),
                "d1_inventory_invalid")
        result[address] = {key: value for key, value in row.items() if key != "address"}
    manifest.Snapshot(result, [], count).validate()
    return result


class Readback:
    """Read exactly configured staging D1/R2 and complete zone rules.

    Request injection is exclusively for hosted synthetic tests. The production
    reader accepts no URL/database/bucket selector and performs SELECT-only D1
    POSTs and provider GETs. A future wrapper must independently validate the
    serving-version bindings, current sending hold, source CI and Identity.
    """

    def __init__(self, account: str, zone: str, token: str, routing_token: str,
                 resources: tuple[str, ...], *, request: Callable | None = None,
                 rules: Callable | None = None):
        """Validate private capabilities before the first provider observation."""
        require(isinstance(account, str) and HEX32.fullmatch(account) is not None
                and isinstance(zone, str) and HEX32.fullmatch(zone) is not None
                and isinstance(token, str) and bool(token)
                and isinstance(routing_token, str) and bool(routing_token), "readback_capability_invalid")
        require(isinstance(resources, tuple) and 1 <= len(resources) <= 64
                and len(set(resources)) == len(resources)
                and all(isinstance(value, str) and ADDRESS.fullmatch(value) is not None
                        and value.endswith("@" + manifest.DOMAIN) for value in resources),
                "readback_resources_invalid")
        self.account, self.zone = account, zone
        self._token, self._routing_token = token, routing_token
        self.resources = resources
        self._request = request or self._http
        self._rules = rules or cf_rules

    def _http(self, method: str, path: str, body: dict | None = None) -> dict:
        """Read bounded JSON with redirects rejected and private errors suppressed."""
        require(method == "GET" and body is None or method == "POST"
                and path == f"/accounts/{self.account}/d1/database/{DB}/query"
                and isinstance(body, dict) and body.get("sql", "").startswith("SELECT "),
                "readback_request_unreviewed")
        if method == "GET":
            base, separator, query = path.partition("?")
            values = parse_qs(query, strict_parsing=True)
            require(base == f"/accounts/{self.account}/r2/buckets/{BUCKET}/objects"
                    and separator == "?" and values.get("per_page") == ["100"]
                    and set(values) <= {"per_page", "start_after"}
                    and ("start_after" not in values or len(values["start_after"]) == 1
                         and 1 <= len(values["start_after"][0]) <= 1024),
                    "readback_request_unreviewed")
        req = Request(API + path, method=method,
                      data=None if body is None else json.dumps(body).encode(),
                      headers={"Authorization": "Bearer " + self._token,
                               "Accept": "application/json", "Content-Type": "application/json"})
        try:
            with control_open(req, timeout=25) as response:
                require(response.status == 200, "readback_http_unverified")
                raw = response.read(manifest.LIMIT + 1)
            require(len(raw) <= manifest.LIMIT, "readback_response_oversized")
            value = json.loads(raw)
        except manifest.ContractFailure:
            raise
        except Exception:
            raise manifest.ContractFailure("readback_http_unverified") from None
        require(isinstance(value, dict) and value.get("success") is True, "readback_envelope_invalid")
        return value

    def _select(self, sql: str, params: tuple = ()) -> list[dict]:
        """Parse one successful SELECT batch; no raw errors escape the capability."""
        require(sql.startswith("SELECT ") and ";" not in sql, "d1_query_unreviewed")
        value = self._request("POST", f"/accounts/{self.account}/d1/database/{DB}/query",
                              {"sql": sql, "params": list(params)})
        require(isinstance(value, dict) and value.get("success") is True, "d1_readback_invalid")
        batches = value.get("result")
        require(isinstance(batches, list) and len(batches) == 1 and isinstance(batches[0], dict)
                and batches[0].get("success") is True and isinstance(batches[0].get("results"), list),
                "d1_readback_invalid")
        return batches[0]["results"]

    def _count(self, sql: str, params: tuple = ()) -> int:
        """Require an exact integer aggregate, never infer absence from truncation."""
        rows = self._select(sql, params)
        require(len(rows) == 1 and isinstance(rows[0], dict) and set(rows[0]) == {"n"}
                and type(rows[0]["n"]) is int and rows[0]["n"] >= 0, "d1_count_invalid")
        return rows[0]["n"]

    def _allocations(self) -> tuple[dict, int]:
        """Join complete bounded rows with independently repeated aggregate count."""
        count_sql = "SELECT COUNT(*) AS n FROM addresses WHERE state!='retired'"
        before = self._count(count_sql)
        require(before <= MAX_ROWS, "d1_inventory_oversized")
        columns = ",".join(["address", *sorted(manifest.ROW_KEYS)])
        placeholders = ",".join("?" + str(i + 1) for i in range(len(self.resources)))
        sql = (f"SELECT {columns} FROM addresses WHERE state!='retired' "
               f"OR address IN ({placeholders}) ORDER BY address LIMIT {MAX_ROWS + 1}")
        rows = rows_from_batch(self._select(sql, self.resources), before, self.resources)
        require(self._count(count_sql) == before, "d1_count_drift")
        return rows, before

    def objects(self) -> dict[str, str]:
        """Exhaust R2 keyset pages, including metadata digests and explicit empty end."""
        result = {}
        last = None
        for _ in range(22):
            suffix = "?per_page=100" + ("&start_after=" + quote(last, safe="") if last is not None else "")
            value = self._request("GET", f"/accounts/{self.account}/r2/buckets/{BUCKET}/objects" + suffix)
            require(isinstance(value, dict) and value.get("success") is True
                    and isinstance(value.get("result"), list) and len(value["result"]) <= 100,
                    "r2_inventory_invalid")
            info = value.get("result_info")
            require(info is None or isinstance(info, dict), "r2_inventory_invalid")
            if isinstance(info, dict) and "is_truncated" in info:
                require(type(info["is_truncated"]) is bool, "r2_inventory_invalid")
            batch = value["result"]
            if not batch:
                require(not isinstance(info, dict) or info.get("is_truncated") is not True,
                        "r2_inventory_truncated")
                return result
            for item in batch:
                require(isinstance(item, dict), "r2_inventory_invalid")
                key = item.get("key")
                require(isinstance(key, str) and 1 <= len(key) <= 1024
                        and key not in result and (last is None or key > last), "r2_inventory_invalid")
                require(isinstance(item.get("etag"), str) and bool(item["etag"])
                        and type(item.get("size")) is int and item["size"] >= 0
                        and isinstance(item.get("last_modified"), str)
                        and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+(?:Z|[+-][0-9]{2}:[0-9]{2})",
                                         item["last_modified"]) is not None,
                        "r2_metadata_unverified")
                result[key] = digest(item)
                last = key
                require(len(result) <= MAX_ROWS, "r2_inventory_oversized")
        raise manifest.ContractFailure("r2_inventory_page_bound")

    def _snapshot(self) -> manifest.Snapshot:
        """Observe all resources once; the public read repeats to reject drift."""
        rows, count = self._allocations()
        rules = normalize_rules(self._rules(self.zone, self._routing_token))
        value = manifest.Snapshot(rows, rules, count, self.objects())
        value.validate()
        return value

    def read(self) -> manifest.Snapshot:
        """Require consecutive complete equal snapshots before using a baseline.

        This detects observed change; it is not a provider reservation or an
        atomic D1+Cloudflare+R2 transaction. Campaign prefix/pin checks remain
        mandatory around every mutation. No automatic mutation retry exists.
        """
        try:
            first, second = self._snapshot(), self._snapshot()
            require(manifest.canonical(first.value()) == manifest.canonical(second.value()),
                    "readback_snapshot_drift")
            return second
        except manifest.ContractFailure:
            raise
        except Exception:
            raise manifest.ContractFailure("readback_unverified") from None

    def storage_empty(self, resources: tuple[str, ...]) -> bool:
        """Reject any candidate message, including tombstoned/outbound deliveries.

        Complete R2 inventory equality is separately checked against the sealed
        Snapshot baseline. This aggregate checks all candidate address rows,
        not only currently visible API messages or a filtered direction.
        """
        require(resources == self.resources, "readback_resources_changed")
        placeholders = ",".join("?" + str(i + 1) for i in range(len(resources)))
        return self._count(f"SELECT COUNT(*) AS n FROM messages WHERE address IN ({placeholders})", resources) == 0
