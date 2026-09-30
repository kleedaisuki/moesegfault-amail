"""Staging-only encrypted D1 escrow; no migration or live CLI/workflow wiring.

Only fixed operations-table queries against the existing reviewed staging DB
are available. The adapter never writes keys/plain manifests or grants address
DELETE. A successful one-time arm response is distinct from already-armed or
ambiguous state; readback alone cannot manufacture a mutation permit.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Callable

import staging_ten_address_manifest as manifest
from staging_second_principal import request, json_result
from staging_ten_address_artifact import RECOVERY_WORKFLOW
from staging_ten_address_readback import DB

require = manifest.require
CHUNK = 65_536
MAX_CHUNKS = 31
MAX_RESPONSE = 131_072
MAX_ENVELOPE = manifest.LIMIT + 256
CHECK_SET = "quota-readonly-native-teardown-v1"
MIGRATION = Path(__file__).resolve().parents[1] / "deploy/staging-acceptance-migrations/0001_quota_escrow.sql"
PARENT = "staging_acceptance_escrows"
PARTS = "staging_acceptance_escrow_chunks"
FIELDS = ("original_run", "attempt", "repository", "workflow", "source_sha", "schema_version",
          "key_generation", "envelope_sha", "envelope_bytes", "chunk_count", "reserved_bytes",
          "artifact_id", "state", "created_at", "armed_at", "cleanup_verified_at", "cleanup_receipt_sha",
          "cleanup_verifier_run", "cleanup_verifier_sha", "cleanup_check_set", "issue_number")
BOUND = FIELDS[:11]
SQL = {
    "schema": "SELECT name,type,sql FROM sqlite_master WHERE name LIKE 'staging_acceptance_%' AND sql IS NOT NULL ORDER BY name",
    "parent": "SELECT " + ",".join(FIELDS) + f" FROM {PARENT} WHERE original_run=?1",
    "create": f"INSERT INTO {PARENT}(" + ",".join(BOUND) + ",state) VALUES(" + ",".join("?" + str(i+1) for i in range(len(BOUND))) + ", 'writing') ON CONFLICT(original_run) DO NOTHING",
    "part": f"SELECT chunk_index,chunk_bytes,chunk_sha,ciphertext_b64 FROM {PARTS} WHERE original_run=?1 AND chunk_index=?2",
    "part_create": f"INSERT INTO {PARTS}(original_run,chunk_index,chunk_bytes,chunk_sha,ciphertext_b64) VALUES(?1,?2,?3,?4,?5) ON CONFLICT(original_run,chunk_index) DO NOTHING",
    "aggregate": f"SELECT COUNT(*) AS n,COALESCE(SUM(chunk_bytes),0) AS bytes FROM {PARTS} WHERE original_run=?1",
    "seal": f"UPDATE {PARENT} SET state='sealed' WHERE original_run=?1 AND envelope_sha=?2 AND state='writing' AND (SELECT COUNT(*) FROM {PARTS} WHERE original_run=?1)=chunk_count",
    "artifact": f"UPDATE {PARENT} SET artifact_id=?3 WHERE original_run=?1 AND envelope_sha=?2 AND state='sealed' AND artifact_id IS NULL",
    "arm": f"UPDATE {PARENT} SET state='armed',armed_at=unixepoch() WHERE original_run=?1 AND envelope_sha=?2 AND artifact_id=?3 AND state='sealed' AND armed_at IS NULL",
    "clock": "SELECT unixepoch() AS now",
    "receipt": f"UPDATE {PARENT} SET state='cleanup_verified',cleanup_verified_at=?3,cleanup_receipt_sha=?4,cleanup_verifier_run=?5,cleanup_verifier_sha=?6,cleanup_check_set=?7 WHERE original_run=?1 AND envelope_sha=?2 AND state IN ('writing','sealed','armed') AND state=?8 AND artifact_id IS ?9 AND armed_at IS ?10 AND created_at=?11 AND cleanup_receipt_sha IS NULL AND ?3>=created_at AND ?3 BETWEEN unixepoch()-30 AND unixepoch()",
    "purge": f"DELETE FROM {PARTS} WHERE original_run=?1 AND chunk_index=?2 AND chunk_sha=?3 AND ciphertext_b64=?4 AND EXISTS(SELECT 1 FROM {PARENT} WHERE original_run=?1 AND state='cleanup_verified' AND cleanup_receipt_sha=?5)",
}


def hash_bytes(value: bytes) -> str:
    """Hash ciphertext only; no private plaintext fingerprint is persisted."""
    return hashlib.sha256(value).hexdigest()


def expected_schema() -> dict[str, tuple[str, str]]:
    """Compare complete namespaced DDL, not just existing table names."""
    source = MIGRATION.read_text(encoding="utf-8-sig")
    source = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("--"))
    starts = list(re.finditer(r"(?m)^CREATE (TABLE|(?:UNIQUE )?INDEX|TRIGGER) (staging_acceptance_[a-z_]+)\b", source))
    require(bool(starts), "escrow_schema_source_invalid")
    result = {}
    for index, match in enumerate(starts):
        end = starts[index+1].start() if index+1 < len(starts) else len(source)
        value = re.sub(r"\s+", " ", source[match.start():end].strip().removesuffix(";")).strip()
        require(match[2] not in result, "escrow_schema_source_invalid")
        result[match[2]] = ("index" if "INDEX" in match[1] else match[1].lower(), value)
    return result


def binding(blob: bytes, key: str, run: str, generation: str) -> tuple[dict, tuple]:
    """Authenticate existing ciphertext before extracting only nonprivate escrow coordinates."""
    plan = manifest.open_manifest(blob, key, run, generation)
    count = (len(blob) + CHUNK - 1) // CHUNK
    require(41 <= len(blob) <= MAX_ENVELOPE and 1 <= count <= MAX_CHUNKS, "escrow_envelope_bounds")
    reserved = ((len(blob)+2)//3)*4 + count*1028 + 4096
    values = (run, 1, manifest.REPOSITORY, RECOVERY_WORKFLOW, plan["checkout"], 2,
              generation, hash_bytes(blob), len(blob), count, reserved)
    return plan, values


def decode_part(part: dict, index: int, expected_bytes: int) -> bytes:
    """Validate one canonical chunk in isolation, without rendering provider data."""
    require(isinstance(part, dict) and set(part) == {"chunk_index", "chunk_bytes", "chunk_sha", "ciphertext_b64"}
            and type(part["chunk_index"]) is int and part["chunk_index"] == index
            and type(part["chunk_bytes"]) is int and part["chunk_bytes"] == expected_bytes
            and isinstance(part["ciphertext_b64"], str) and len(part["ciphertext_b64"]) <= 87_384,
            "escrow_chunk_unverified")
    try:
        raw = base64.b64decode(part["ciphertext_b64"], validate=True)
    except Exception:
        raise manifest.ContractFailure("escrow_chunk_unverified") from None
    require(len(raw) == expected_bytes and hash_bytes(raw) == part["chunk_sha"]
            and base64.b64encode(raw).decode() == part["ciphertext_b64"], "escrow_chunk_unverified")
    return raw


@dataclass(frozen=True, repr=False)
class Result:
    """A bounded parsed query observation; not a caller-supplied success boolean."""

    rows: list[dict]
    changes: int


@dataclass(frozen=True, repr=False)
class Arm:
    """Known current-invocation transition/readback, never inferred after a lost response."""

    original_run: str
    envelope_sha: str
    artifact_id: str
    armed_at: int


def query_result(value: dict) -> Result:
    """Parse the native single-query D1 REST shape, never infer a missing ACK.

    Provider metadata can contain additional fields; changes must be an actual
    nonnegative integer. This parser is shared by the fixed escrow adapter and
    the separately guarded synthetic provider proof, not a general SQL client.
    """
    batches = value.get("result") if isinstance(value, dict) else None
    require(isinstance(value, dict) and value.get("success") is True
            and isinstance(batches, list) and len(batches) == 1 and isinstance(batches[0], dict)
            and batches[0].get("success") is True and isinstance(batches[0].get("results"), list)
            and all(isinstance(row, dict) for row in batches[0]["results"])
            and isinstance(batches[0].get("meta"), dict)
            and type(batches[0]["meta"].get("changes")) is int and batches[0]["meta"]["changes"] >= 0,
            "escrow_response_unverified")
    return Result(batches[0]["results"], batches[0]["meta"]["changes"])


class Escrow:
    """Fixed staging operations; private receipt/purge requires a reviewed coordinator.

    Receipt and purge helpers cannot prove external cleanup themselves. They are
    deliberately private and unwired: only a concrete independently reviewed
    read-only recovery coordinator may call them after all checks and teardown.
    A public passed flag or caller-created success token is never accepted.
    """

    def __init__(self, account: str, token: str, *, query: Callable | None = None):
        """Admit exact account shape and protected existing D1 token, never DB selectors."""
        require(isinstance(account, str) and re.fullmatch(r"[a-f0-9]{32}", account) is not None
                and isinstance(token, str) and bool(token), "escrow_capability_invalid")
        self.account, self._token = account, token
        self._query = query or self._http

    def _http(self, sql: str, params: tuple) -> Result:
        """Bound query text/params/JSON response and suppress private provider failures."""
        require(sql in SQL.values() and len(sql.encode()) < 4096 and len(params) <= 100,
                "escrow_query_unreviewed")
        body = json.dumps({"sql": sql, "params": list(params)}).encode()
        require(len(body) < 100_000, "escrow_query_bounds")
        try:
            value = json_result(request("POST", f"/accounts/{self.account}/d1/database/{DB}/query",
                                        self._token, body, limit=MAX_RESPONSE))
        except Exception:
            raise manifest.ContractFailure("escrow_query_unverified") from None
        return query_result(value)

    def _run(self, kind: str, params: tuple = ()) -> Result:
        """Execute one source-owned statement once; unknown outcomes are never retried."""
        require(kind in SQL and isinstance(params, tuple), "escrow_query_unreviewed")
        try:
            value = self._query(SQL[kind], params)
        except Exception:
            raise manifest.ContractFailure("escrow_query_unverified") from None
        require(isinstance(value, Result) and isinstance(value.rows, list)
                and all(isinstance(row, dict) for row in value.rows)
                and type(value.changes) is int and value.changes >= 0
                and len(manifest.canonical(value.rows)) <= MAX_RESPONSE, "escrow_response_unverified")
        return value

    def schema(self) -> None:
        """Refuse missing/extra/changed DDL before touching any encrypted operations row."""
        rows = self._run("schema").rows
        observed = {}
        for row in rows:
            require(set(row) == {"name", "type", "sql"} and isinstance(row["name"], str)
                    and isinstance(row["type"], str) and isinstance(row["sql"], str)
                    and row["name"] not in observed, "escrow_schema_unverified")
            observed[row["name"]] = (row["type"], re.sub(r"\s+", " ", row["sql"]).strip().removesuffix(";"))
        require(observed == expected_schema(), "escrow_schema_unverified")

    def parent(self, run: str) -> dict | None:
        """Read one exact original record; metadata itself grants no mutation authority."""
        manifest.coordinates(run, "1")
        rows = self._run("parent", (run,)).rows
        require(len(rows) <= 1, "escrow_parent_unverified")
        if not rows:
            return None
        value = rows[0]
        require(set(value) == set(FIELDS) and value["original_run"] == run
                and all(type(value[field]) is int for field in (
                    "attempt", "schema_version", "envelope_bytes", "chunk_count", "reserved_bytes", "created_at"))
                and value["state"] in ("writing", "sealed", "armed", "cleanup_verified")
                and all(value[field] is None or type(value[field]) is int and value[field] >= 0
                        for field in ("armed_at", "cleanup_verified_at"))
                and (value["issue_number"] is None or type(value["issue_number"]) is int and value["issue_number"] > 0)
                and (value["artifact_id"] is None or isinstance(value["artifact_id"], str)
                     and re.fullmatch(r"[1-9][0-9]{0,19}", value["artifact_id"]) is not None)
                and (value["cleanup_verifier_run"] is None or isinstance(value["cleanup_verifier_run"], str)
                     and re.fullmatch(r"[1-9][0-9]{0,19}", value["cleanup_verifier_run"]) is not None)
                and (value["cleanup_verifier_sha"] is None or isinstance(value["cleanup_verifier_sha"], str)
                     and re.fullmatch(r"[a-f0-9]{40}", value["cleanup_verifier_sha"]) is not None)
                and value["cleanup_check_set"] in (None,CHECK_SET),
                "escrow_parent_unverified")
        return value

    def _same(self, row: dict | None, values: tuple) -> dict:
        """Bind every original field without replacing an existing envelope."""
        require(isinstance(row, dict) and tuple(row[name] for name in BOUND) == values
                and row["state"] in ("writing", "sealed", "armed", "cleanup_verified")
                and type(row["created_at"]) is int and row["created_at"] >= 0,
                "escrow_binding_mismatch")
        return row

    def _blob(self, row: dict) -> bytes:
        """Exhaust exact bounded chunks with independent count/byte aggregate."""
        require(type(row["chunk_count"]) is int and 1 <= row["chunk_count"] <= MAX_CHUNKS
                and type(row["envelope_bytes"]) is int and 41 <= row["envelope_bytes"] <= MAX_ENVELOPE,
                "escrow_envelope_bounds")
        total = self._run("aggregate", (row["original_run"],)).rows
        require(len(total) == 1 and set(total[0]) == {"n", "bytes"}
                and type(total[0]["n"]) is int and type(total[0]["bytes"]) is int
                and total == [{"n": row["chunk_count"], "bytes": row["envelope_bytes"]}], "escrow_chunks_incomplete")
        result = bytearray()
        for index in range(row["chunk_count"]):
            rows = self._run("part", (row["original_run"], index)).rows
            require(len(rows) == 1, "escrow_chunk_unverified")
            result.extend(decode_part(rows[0],index,min(CHUNK,row["envelope_bytes"]-index*CHUNK)))
        require(len(result) == row["envelope_bytes"] and hash_bytes(result) == row["envelope_sha"],
                "escrow_envelope_mismatch")
        return bytes(result)

    def read(self, run: str, key: str, generation: str) -> tuple[dict, bytes]:
        """Read/authenticate complete stable escrow without any write or alias permission."""
        self.schema()
        first = self.parent(run)
        require(first is not None, "escrow_parent_missing")
        blob = self._blob(first)
        _, values = binding(blob, key, run, generation)
        self._same(first, values)
        require(self.parent(run) == first and self._blob(first) == blob, "escrow_readback_changed")
        return first, blob

    def _parts_put(self, blob: bytes, row: dict) -> None:
        """Insert each exact slice once and read it back without replacement/retry."""
        run = row["original_run"]
        for index in range(row["chunk_count"]):
            raw = blob[index*CHUNK:(index+1)*CHUNK]
            data = (run,index,len(raw),hash_bytes(raw),base64.b64encode(raw).decode())
            self._run("part_create", data)
            require(self._run("part", (run,index)).rows == [{"chunk_index": index, "chunk_bytes": len(raw),
                    "chunk_sha": hash_bytes(raw), "ciphertext_b64": data[-1]}], "escrow_chunk_collision")

    def put(self, blob: bytes, key: str, run: str, generation: str) -> dict:
        """Insert/seal exact encrypted data once; an ambiguous write admits no alias.

        Readback of an existing writing/sealed matching envelope is recoverable
        durability work, not a lost arm acknowledgement or mutation permission.
        Any armed/terminal record rejects put. No automatic write retry occurs.
        """
        self.schema()
        _, values = binding(blob, key, run, generation)
        prior = self.parent(run)
        if prior is None:
            require(self._run("create", values).changes == 1, "escrow_create_unverified")
        row = self._same(self.parent(run), values)
        require(row["state"] in ("writing", "sealed"), "escrow_state_not_preparable")
        if row["state"] == "writing":
            self._parts_put(blob,row)
            require(self._blob(row) == blob, "escrow_envelope_mismatch")
            require(self._run("seal", (run,values[7])).changes == 1, "escrow_seal_unverified")
        sealed, actual = self.read(run,key,generation)
        require(sealed["state"] == "sealed" and actual == blob, "escrow_seal_unverified")
        return sealed

    def attach(self, run: str, key: str, generation: str, artifact_id: str, expected_blob: bytes) -> None:
        """Attach one independently validated artifact ID, never replace a prior relation."""
        require(isinstance(artifact_id, str) and re.fullmatch(r"[1-9][0-9]{0,19}", artifact_id) is not None,
                "escrow_artifact_unverified")
        row, blob = self.read(run,key,generation)
        require(row["state"] == "sealed" and blob == expected_blob, "escrow_artifact_unverified")
        if row["artifact_id"] is None:
            require(self._run("artifact", (run,row["envelope_sha"],artifact_id)).changes == 1,
                    "escrow_artifact_unverified")
        attached, actual = self.read(run,key,generation)
        require(attached["artifact_id"] == artifact_id and actual == blob, "escrow_artifact_unverified")

    def arm(self, run: str, key: str, generation: str, artifact_id: str, expected_blob: bytes) -> Arm:
        """Require this invocation's known one-time transition; never recover a lost ACK.

        Known response changes=1 AND independent authenticated readback are both
        necessary. Timeout, zero-change or already-armed state fails; reading
        armed after an exception does not produce an Arm result or authorize add.
        """
        row, blob = self.read(run,key,generation)
        require(row["state"] == "sealed" and row["artifact_id"] == artifact_id
                and blob == expected_blob and row["armed_at"] is None, "escrow_arm_not_available")
        require(self._run("arm", (run,row["envelope_sha"],artifact_id)).changes == 1,
                "escrow_arm_ack_unverified")
        armed, actual = self.read(run,key,generation)
        require(armed["state"] == "armed" and armed["artifact_id"] == artifact_id and actual == blob
                and type(armed["armed_at"]) is int and armed["armed_at"] >= row["created_at"],
                "escrow_arm_readback_unverified")
        return Arm(run,row["envelope_sha"],artifact_id,armed["armed_at"])

    @staticmethod
    def _receipt(row: dict) -> str:
        """Bind only public original/verifier coordinates, check-set and observed server time."""
        fields = BOUND + ("artifact_id", "created_at", "armed_at", "cleanup_verified_at",
                          "cleanup_verifier_run", "cleanup_verifier_sha", "cleanup_check_set")
        return hash_bytes(manifest.canonical({name: row[name] for name in fields}))

    def _terminal(self, row: dict, values: tuple) -> dict:
        """Validate an immutable receipt as metadata, never as independent cleanup proof."""
        self._same(row,values)
        require(row["state"] == "cleanup_verified" and type(row["cleanup_verified_at"]) is int
                and row["cleanup_verified_at"] >= row["created_at"]
                and isinstance(row["cleanup_verifier_run"],str)
                and isinstance(row["cleanup_verifier_sha"],str) and row["cleanup_check_set"] == CHECK_SET
                and self._receipt(row) == row["cleanup_receipt_sha"], "escrow_receipt_unverified")
        return row

    def _finalize(self, run: str, key: str, generation: str, verifier_run: str,
                  verifier_sha: str, expected_blob: bytes) -> dict:
        """Persist receipt once AFTER concrete independent recovery and native teardown.

        This private SQL boundary does not execute those checks. The forthcoming
        concrete coordinator owns that obligation; this helper has no entrypoint
        and must never be called from campaign-success or a passed=true switch.
        Lost/zero-change response fails without purge or readback-as-ACK repair.
        """
        manifest.coordinates(verifier_run,"1")
        require(isinstance(verifier_sha,str) and re.fullmatch(r"[a-f0-9]{40}",verifier_sha) is not None,
                "escrow_verifier_unverified")
        row,blob = self.read(run,key,generation)
        require(blob == expected_blob and row["state"] in ("writing","sealed","armed")
                and row["cleanup_receipt_sha"] is None, "escrow_receipt_not_available")
        clock = self._run("clock").rows
        require(len(clock) == 1 and set(clock[0]) == {"now"} and type(clock[0]["now"]) is int
                and clock[0]["now"] >= row["created_at"], "escrow_clock_unverified")
        expected = {**row,"state":"cleanup_verified","cleanup_verified_at":clock[0]["now"],
                    "cleanup_verifier_run":verifier_run,"cleanup_verifier_sha":verifier_sha,
                    "cleanup_check_set":CHECK_SET}
        expected["cleanup_receipt_sha"] = self._receipt(expected)
        require(self._run("receipt",(run,row["envelope_sha"],clock[0]["now"],
                    expected["cleanup_receipt_sha"],verifier_run,verifier_sha,CHECK_SET,
                    row["state"],row["artifact_id"],row["armed_at"],row["created_at"])).changes == 1,
                "escrow_receipt_ack_unverified")
        terminal,actual = self.read(run,key,generation)
        _,values = binding(blob,key,run,generation)
        self._terminal(terminal,values)
        require(terminal == expected and actual == blob, "escrow_receipt_readback_unverified")
        return terminal

    def _purge(self, run: str, key: str, generation: str, expected_blob: bytes) -> None:
        """Remove exact ciphertext only AFTER independently verified terminal cleanup.

        This private helper never removes the permanent public receipt. Separate
        recovery must repeat all external checks before resuming a partial purge.
        A receipt is necessary metadata, not a substitute for that attestation.
        Any ambiguous chunk DELETE stops immediately; no automatic retry occurs.
        Logical removal does not erase provider backups or the retained artifact.
        """
        self.schema()
        _,values = binding(expected_blob,key,run,generation)
        row = self._terminal(self.parent(run),values)
        for index in range(row["chunk_count"]):
            parts = self._run("part",(run,index)).rows
            require(len(parts) <= 1, "escrow_chunk_unverified")
            if not parts:
                continue
            expected = expected_blob[index*CHUNK:(index+1)*CHUNK]
            require(decode_part(parts[0],index,len(expected)) == expected, "escrow_chunk_collision")
            require(self._run("purge",(run,index,parts[0]["chunk_sha"],parts[0]["ciphertext_b64"],
                                      row["cleanup_receipt_sha"])).changes == 1, "escrow_purge_ack_unverified")
            require(self._run("part",(run,index)).rows == [], "escrow_purge_readback_unverified")
        total = self._run("aggregate",(run,)).rows
        require(len(total) == 1 and set(total[0]) == {"n","bytes"}
                and type(total[0]["n"]) is int and type(total[0]["bytes"]) is int
                and total == [{"n":0,"bytes":0}] and self.parent(run) == row,
                "escrow_purge_readback_unverified")
