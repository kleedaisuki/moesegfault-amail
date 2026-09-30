"""Protected, two-document staging oracle for v5 semantic pagination.

The caller owns the native PKCE session and the two SMTP fixtures. This module
never sends mail or mutates D1; all private responses remain process-local.
Only fixed labels and a bounded score error may be emitted by the caller.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import struct
import subprocess
import time
import urllib.request

from staging_semantic_e2e import DIMENSIONS, MODEL, SCORE_TOLERANCE, SemanticProbeError, check_exact_pages, cosine, require


API = "https://api.cloudflare.com/client/v4"
DATABASE = "74f35f95-42ce-482c-86e6-dffbdd35cbbe"
ISSUER = "https://identity-staging.moesegfault.dev"
QUERY = "synthetic staging notification"
GENERATION_SQL = "SELECT generation FROM search_generations WHERE owner_iss=?1 AND owner_sub=?2"
OWNER_SQL = "SELECT owner_iss,owner_sub FROM addresses WHERE address=?1 AND state='active'"
COUNT_SQL = "SELECT COUNT(*) AS n FROM messages WHERE owner_iss=?1 AND owner_sub=?2 AND deleted_at IS NULL"
VECTOR_SQL = ("SELECT id,address,direction,received_at,is_read,embedding_json,embedding_model,"
              "embedding_dimensions,embedding_input_version FROM messages WHERE owner_iss=?1 "
              "AND owner_sub=?2 AND address=?3 AND deleted_at IS NULL AND id IN (?4,?5)")
ORIGIN_SQL = ("SELECT id,state,expires_at,"
              "json_extract(state_json,'$.origin_job_id') AS origin_job_id,"
              "json_extract(state_json,'$.is_origin') AS is_origin,"
              "json_extract(state_json,'$.query_input_version') AS query_input_version,"
              "json_extract(state_json,'$.query_vector') AS query_vector_json,"
              "json_extract(state_json,'$.query_model') AS query_model,"
              "json_extract(state_json,'$.vector_commitment') AS vector_commitment "
              "FROM search_jobs WHERE id=?1 AND owner_iss=?2 AND owner_sub=?3")


class OracleError(Exception):
    """A fixed safe failure code, never a provider exception or private value."""


def guard(condition: bool, label: str) -> None:
    """Fail closed using only source-controlled diagnostic labels."""

    if not condition:
        raise OracleError(label)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward a control-plane or embedding bearer token to a redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Reject all redirects, including apparently same-host redirects."""

        return None


OPEN = urllib.request.build_opener(NoRedirect())


def bounded_json(req: urllib.request.Request, label: str, limit: int = 262_144) -> dict:
    """Read one exact-host JSON response without exposing its body or URL."""

    try:
        with OPEN.open(req, timeout=30) as response:
            guard(response.status == 200, label)
            raw = response.read(limit + 1)
        guard(len(raw) <= limit, label)
        value = json.loads(raw)
        guard(isinstance(value, dict), label)
        return value
    except OracleError:
        raise
    except Exception:
        raise OracleError(label) from None


def d1_rows(account: str, token: str, sql: str, params: list[object]) -> list[dict]:
    """Execute only embedded, parameterized SELECT templates against staging D1."""

    guard(sql in (OWNER_SQL, COUNT_SQL, VECTOR_SQL, GENERATION_SQL, ORIGIN_SQL), "oracle_sql_denied")
    guard(bool(re.fullmatch(r"[a-f0-9]{32}", account)) and bool(token), "oracle_d1_config")
    req = urllib.request.Request(
        f"{API}/accounts/{account}/d1/database/{DATABASE}/query",
        data=json.dumps({"sql": sql, "params": params}, separators=(",", ":")).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST",
    )
    data = bounded_json(req, "oracle_d1_read")
    batches = data.get("result") if data.get("success") is True else None
    guard(isinstance(batches, list) and len(batches) == 1 and isinstance(batches[0], dict), "oracle_d1_shape")
    batch = batches[0]
    rows = batch.get("results") if batch.get("success") is True else None
    guard(isinstance(rows, list) and all(isinstance(row, dict) for row in rows), "oracle_d1_shape")
    return rows


def f32(value: object) -> float:
    """Apply the Worker's f64-to-IEEE-f32 rounding, rejecting overflow/NaN."""

    guard(type(value) in (int, float), "oracle_vector_invalid")
    try:
        result = struct.unpack("<f", struct.pack("<f", float(value)))[0]
    except (OverflowError, ValueError, struct.error):
        raise OracleError("oracle_vector_invalid") from None
    guard(math.isfinite(result), "oracle_vector_invalid")
    return result


def validate_vector(values: object) -> list[float]:
    """Require precisely 256 finite, nonzero rounded coordinates."""

    guard(isinstance(values, list) and len(values) == DIMENSIONS, "oracle_vector_invalid")
    vector = [f32(value) for value in values]
    guard(sum(value * value for value in vector) > 0, "oracle_vector_invalid")
    return vector


def generation(account: str, token: str, owner: tuple[str, str]) -> int:
    """Read the owner generation, treating an absent row as the Worker's zero."""

    rows = d1_rows(account, token, GENERATION_SQL, list(owner))
    guard(len(rows) <= 1, "oracle_generation_shape")
    value = rows[0].get("generation") if rows else 0
    guard(type(value) is int and value >= 0, "oracle_generation_shape")
    return value


def snapshot(account: str, token: str, owner: tuple[str, str], address: str,
             ids: tuple[str, str]) -> dict[str, dict]:
    """Read only the two active run IDs and require an exhaustive owner count."""

    counts = d1_rows(account, token, COUNT_SQL, list(owner))
    guard(len(counts) == 1 and counts[0].get("n") == 2, "oracle_owner_inventory_changed")
    rows = d1_rows(account, token, VECTOR_SQL, [*owner, address, *ids])
    guard(len(rows) == 2, "oracle_vector_snapshot_incomplete")
    result = {}
    for row in rows:
        message_id = row.get("id")
        guard(isinstance(message_id, str) and message_id in ids and message_id not in result
              and row.get("address") == address and row.get("direction") == "inbound"
              and row.get("is_read") == 0 and row.get("embedding_model") == MODEL
              and row.get("embedding_dimensions") == DIMENSIONS
              and row.get("embedding_input_version") == 1, "oracle_vector_metadata")
        milliseconds = row.get("received_at")
        guard(type(milliseconds) is int and milliseconds > 0, "oracle_vector_metadata")
        try:
            when = datetime.fromtimestamp(milliseconds / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            vector = validate_vector(json.loads(row.get("embedding_json")))
        except (ValueError, TypeError, OverflowError):
            raise OracleError("oracle_vector_invalid") from None
        result[message_id] = {"vector": vector, "received_at": when,
                              "embedding_model": MODEL, "embedding_dimensions": DIMENSIONS}
    return result


def query_hash(owner: tuple[str, str], address: str, nonce: str) -> str:
    """Reproduce serde_json's sorted SearchRequest and v4 owner/query binding."""

    value = dict.fromkeys(("mailbox", "after", "before", "title", "from", "to", "body",
                           "metadata", "semantic", "regex", "case_sensitive", "read", "limit", "cursor"))
    value.update(mailbox=address, title=f"^AMAIL-E2E-{nonce}-(Signal|Distractor)$",
                 semantic=QUERY, regex=True, case_sensitive=False, read=False, limit=1)
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(f"{owner[0]}:{owner[1]}:{canonical}".encode()).hexdigest()


def commitment(hash_value: str, query: list[float]) -> str:
    """Reconstruct the versioned Worker commitment from independently rounded f32."""

    model = MODEL.encode()
    preimage = (b"amail-semantic-query-v4\0" + hash_value.encode("ascii") + b"\0"
                + struct.pack("<I", len(model)) + model + struct.pack("<II", 1, DIMENSIONS)
                + b"".join(struct.pack("<f", x) for x in validate_vector(query)))
    return hashlib.sha256(preimage).hexdigest()


def cursor_origin(cursor: str, expected_hash: str, expected_generation: int) -> tuple[str, str]:
    """Inspect the private v5 cursor without reading its signing key."""

    guard(isinstance(cursor, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,4096}", cursor)), "oracle_cursor_shape")
    try:
        value = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except (ValueError, TypeError, binascii.Error):
        raise OracleError("oracle_cursor_shape") from None
    guard(isinstance(value, dict) and value.get("version") == 5
          and value.get("hash") == expected_hash
          and value.get("generation") == expected_generation, "oracle_cursor_binding")
    digest = value.get("vector_commitment")
    origin_id, mac = value.get("origin_job_id"), value.get("cursor_mac")
    guard(isinstance(digest, str) and bool(re.fullmatch(r"[a-f0-9]{64}", digest))
          and isinstance(origin_id, str) and bool(re.fullmatch(
              r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", origin_id))
          and isinstance(mac, str) and bool(re.fullmatch(r"[a-f0-9]{64}", mac)),
          "oracle_cursor_binding")
    return origin_id, digest


def origin_vector(account: str, token: str, owner: tuple[str, str], origin_id: str,
                  expected_digest: str) -> list[float]:
    """Read only origin vector metadata, never the per-origin cursor MAC key."""

    rows = d1_rows(account, token, ORIGIN_SQL, [origin_id, *owner])
    guard(len(rows) == 1, "oracle_vector_unavailable")
    row = rows[0]
    guard(row.get("id") == origin_id and row.get("state") == "done"
          and type(row.get("expires_at")) is int and row["expires_at"] > int(time.time() * 1000)
          and row.get("origin_job_id") == origin_id and row.get("is_origin") == 1
          and row.get("query_input_version") == 1 and row.get("query_model") == MODEL
          and row.get("vector_commitment") == expected_digest,
          "oracle_vector_unavailable")
    value = row.get("query_vector_json")
    guard(isinstance(value, str), "oracle_vector_unavailable")
    try:
        return validate_vector(json.loads(value))
    except (ValueError, TypeError, OracleError):
        raise OracleError("oracle_vector_unavailable") from None


def cli_page(binary, env: dict[str, str], address: str, nonce: str, cursor: str | None) -> dict:
    """Capture one native authenticated HTTP page, including its JSONL cursor."""

    args = [str(binary), "search", "--mailbox", address, "--title",
            f"^AMAIL-E2E-{nonce}-(Signal|Distractor)$", "--regex", "--semantic", QUERY,
            "--unread", "--limit", "1", "--wait-seconds", "90"]
    if cursor is not None:
        args += ["--cursor", cursor]
    try:
        proc = subprocess.run(args, env=env, capture_output=True, timeout=110, check=False)
    except Exception:
        raise OracleError("oracle_cli_transport") from None
    guard(proc.returncode == 0 and len(proc.stdout) <= 65_536, "oracle_cli_page_failed")
    try:
        lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    except (ValueError, UnicodeDecodeError):
        raise OracleError("oracle_cli_page_shape") from None
    guard(len(lines) in (1, 2) and isinstance(lines[0], dict)
          and lines[0].get("id") is not None, "oracle_cli_page_shape")
    marker = lines[1] if len(lines) == 2 else None
    guard(marker is None or isinstance(marker, dict) and set(marker) == {"next_cursor"}
          and isinstance(marker["next_cursor"], str), "oracle_cli_page_shape")
    return {"messages": [lines[0]], "next_cursor": marker["next_cursor"] if marker else None}


def verify(account: str, d1_token: str, binary, env: dict[str, str],
           address: str, nonce: str, ids: tuple[str, str]) -> float:
    """Attest two pages against the actual first-page origin query vector."""

    guard(len(ids) == 2 and ids[0] != ids[1], "oracle_fixture_ids")
    owners = d1_rows(account, d1_token, OWNER_SQL, [address])
    guard(len(owners) == 1 and owners[0].get("owner_iss") == ISSUER
          and isinstance(owners[0].get("owner_sub"), str)
          and bool(owners[0]["owner_sub"]), "oracle_owner_unverified")
    owner = (owners[0]["owner_iss"], owners[0]["owner_sub"])
    before_generation = generation(account, d1_token, owner)
    documents = snapshot(account, d1_token, owner, address, ids)
    first = cli_page(binary, env, address, nonce, None)
    cursor = first["next_cursor"]
    guard(cursor is not None, "oracle_cursor_missing")
    binding = query_hash(owner, address, nonce)
    origin_id, cursor_digest = cursor_origin(cursor, binding, before_generation)
    first_query = origin_vector(account, d1_token, owner, origin_id, cursor_digest)
    digest = commitment(binding, first_query)
    guard(cursor_digest == digest,
          "oracle_query_commitment_mismatch")
    second = cli_page(binary, env, address, nonce, cursor)
    guard(second["next_cursor"] is None, "oracle_extra_page")
    pages = [first, second]
    expected_title = re.compile(rf"AMAIL-E2E-{nonce}-(Signal|Distractor)\Z")
    guard(all(len(page["messages"]) == 1 for page in pages), "oracle_page_size")
    guard(all(row.get("read") is False and row.get("mailbox") == address
              and row.get("direction") == "inbound"
              and isinstance(row.get("subject"), str)
              and expected_title.fullmatch(row["subject"]) is not None
              for page in pages for row in page["messages"]), "oracle_filter_mismatch")
    try:
        check_exact_pages(pages, first_query, documents)
    except SemanticProbeError as error:
        raise OracleError(str(error)) from None
    expected = sorted((cosine(first_query, doc["vector"]) for doc in documents.values()), reverse=True)
    guard(expected[0] - expected[1] > 2 * SCORE_TOLERANCE, "oracle_order_inconclusive")
    after_generation = generation(account, d1_token, owner)
    after = snapshot(account, d1_token, owner, address, ids)
    guard(after_generation == before_generation and after == documents, "oracle_snapshot_changed")
    final_query = origin_vector(account, d1_token, owner, origin_id, cursor_digest)
    guard(b"".join(struct.pack("<f", value) for value in final_query)
          == b"".join(struct.pack("<f", value) for value in first_query),
          "oracle_snapshot_changed")
    return max(abs(row["score"] - cosine(first_query, documents[row["id"]]["vector"]))
               for page in pages for row in page["messages"])
