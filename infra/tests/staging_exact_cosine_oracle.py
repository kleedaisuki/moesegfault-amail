"""Protected, two-document staging oracle for same-vector semantic pagination.

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

    guard(sql in (OWNER_SQL, COUNT_SQL, VECTOR_SQL, GENERATION_SQL), "oracle_sql_denied")
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


def provider_vector(key: str) -> list[float]:
    """Mirror the Worker's ZDR, uncached search-query embedding request."""

    guard(bool(key), "oracle_provider_config")
    payload = {"model": MODEL, "dimensions": DIMENSIONS, "input": QUERY,
               "input_type": "search_query", "provider": {"zdr": True, "data_collection": "deny"}}
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/embeddings",
        data=json.dumps(payload, separators=(",", ":")).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "HTTP-Referer": "https://amail.moesegfault.dev", "X-Title": "amail",
                 "X-OpenRouter-Cache": "false"}, method="POST",
    )
    data = bounded_json(req, "oracle_provider_unavailable", 2_000_000)
    entries = data.get("data")
    guard(isinstance(entries, list) and bool(entries) and isinstance(entries[0], dict), "oracle_provider_shape")
    values = entries[0].get("embedding")
    guard(isinstance(values, list) and len(values) == DIMENSIONS, "oracle_provider_shape")
    try:
        guard(all(type(x) in (float, int) and math.isfinite(float(x)) for x in values),
              "oracle_provider_shape")
        norm = math.sqrt(sum(float(x) * float(x) for x in values))
    except (OverflowError, ValueError):
        raise OracleError("oracle_provider_shape") from None
    guard(math.isfinite(norm) and norm > 1e-12, "oracle_provider_shape")
    return validate_vector([float(x) / norm for x in values])


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


def vector_bits(values: list[float]) -> bytes:
    """Compare normalized provider vectors by exact IEEE-f32 coordinates."""

    return b"".join(struct.pack("<f", value) for value in validate_vector(values))


def cursor_commitment(cursor: str, expected_hash: str, expected_generation: int) -> str:
    """Inspect the private v4 cursor without logging or persisting it."""

    guard(isinstance(cursor, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,4096}", cursor)), "oracle_cursor_shape")
    try:
        value = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    except (ValueError, TypeError, binascii.Error):
        raise OracleError("oracle_cursor_shape") from None
    guard(isinstance(value, dict) and value.get("version") == 4
          and value.get("hash") == expected_hash
          and value.get("generation") == expected_generation, "oracle_cursor_binding")
    digest = value.get("vector_commitment")
    guard(isinstance(digest, str) and bool(re.fullmatch(r"[a-f0-9]{64}", digest)), "oracle_cursor_binding")
    return digest


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


def verify(account: str, d1_token: str, openrouter_key: str, binary, env: dict[str, str],
           address: str, nonce: str, ids: tuple[str, str]) -> float:
    """Attest one complete owner snapshot, two same-vector pages, and exact cosine."""

    guard(len(ids) == 2 and ids[0] != ids[1], "oracle_fixture_ids")
    owners = d1_rows(account, d1_token, OWNER_SQL, [address])
    guard(len(owners) == 1 and owners[0].get("owner_iss") == ISSUER
          and isinstance(owners[0].get("owner_sub"), str)
          and bool(owners[0]["owner_sub"]), "oracle_owner_unverified")
    owner = (owners[0]["owner_iss"], owners[0]["owner_sub"])
    before_generation = generation(account, d1_token, owner)
    documents = snapshot(account, d1_token, owner, address, ids)
    first_query, second_query = provider_vector(openrouter_key), provider_vector(openrouter_key)
    guard(vector_bits(first_query) == vector_bits(second_query), "query_vector_unstable")
    first = cli_page(binary, env, address, nonce, None)
    cursor = first["next_cursor"]
    guard(cursor is not None, "oracle_cursor_missing")
    binding = query_hash(owner, address, nonce)
    digest = commitment(binding, first_query)
    guard(cursor_commitment(cursor, binding, before_generation) == digest,
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
    return max(abs(row["score"] - cosine(first_query, documents[row["id"]]["vector"]))
               for page in pages for row in page["messages"])
