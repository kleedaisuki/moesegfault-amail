"""Dormant, side-effect-free ten-address manifest and recovery contracts.

There is no live entry point or Cloudflare/CLI adapter. A future hosted wrapper
must attest normal B login, prior isolation and serving provenance independently.
Only authenticated ciphertext may leave repository .temp. The optional crypto
dependency is loaded only when sealing/opening; ordinary CI tests use synthetic
AEAD fixtures, not a substitute production cipher.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import re
from typing import Callable

DOMAIN = "mail-staging.moesegfault.dev"
ISSUER = "https://identity-staging.moesegfault.dev"
REPOSITORY = "kleedaisuki/moesegfault-amail"
BRANCH = "refs/heads/codex/amail-v0.1.0"
RESERVED = (
    "admin", "administrator", "amail", "moesegfault", "mail", "login",
    "identity", "account", "api", "auth", "support", "security",
    "postmaster", "abuse", "noreply", "no-reply", "billing", "status",
    "cdn", "www", "root", "hostmaster", "webmaster", "help", "contact",
)
LIMIT = 2_000_000
ROW_KEYS = {"owner_iss", "owner_sub", "state", "created_at", "cf_rule_id",
            "needs_reconcile", "local_part", "slot", "next_reconcile_at"}
RULE_KEYS = {"id", "address", "enabled", "source", "name", "worker"}


class ContractFailure(Exception):
    """Carry only a static code chosen by this module, never private values."""


def require(condition: bool, code: str) -> None:
    """Fail closed at a contract boundary without rendering observed data."""

    if not condition:
        raise ContractFailure(code)


def canonical(value: object) -> bytes:
    """Encode bounded JSON; callers retain this private material in memory."""

    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError):
        raise ContractFailure("manifest_shape_invalid") from None
    require(len(encoded) <= LIMIT, "manifest_oversized")
    return encoded


def key_bytes(secret: str) -> bytes:
    """Require a separately generated 256-bit repository recovery key."""

    require(isinstance(secret, str) and re.fullmatch(r"[a-f0-9]{64}", secret) is not None,
            "recovery_key_invalid")
    return bytes.fromhex(secret)


def coordinates(run: str, attempt: str) -> None:
    """Allow original attempt 1 only; subsequent attempts cannot create aliases."""

    require(isinstance(run, str) and re.fullmatch(r"[1-9][0-9]{0,19}", run) is not None
            and attempt == "1", "run_coordinates_invalid")


def candidates(secret: str, run: str, attempt: str = "1") -> list[str]:
    """Reconstruct eleven exact aliases without any provider or identity writes."""

    coordinates(run, attempt)
    material = f"amail-ten-address/v1:{REPOSITORY}:{run}:{attempt}".encode("ascii")
    digest = hmac.new(key_bytes(secret), material, hashlib.sha256).digest()[:16]
    nonce = base64.b32encode(digest).decode("ascii").rstrip("=").lower()
    return [f"qt{index}-{nonce}@{DOMAIN}" for index in range(11)]


def submissions() -> list[str]:
    """Keep ordered raw normalization probes separate from canonical resources."""

    return [*RESERVED, "ADMIN", "MoeSegFault", "POSTMASTER"]


@dataclass(frozen=True, repr=False)
class Snapshot:
    """Complete normalized D1/rule readback plus independent aggregate count.

    Rows contain every global non-retired allocation and any candidate retired
    baseline. Rules contain the entire zone, normalized only after a future
    adapter validates every raw matcher/action. Unknown shapes must be rejected
    by that adapter, not filtered away. This class performs no network I/O.
    The map key represents the migration's address primary key; each row keeps
    every other addresses column, including slot and signed reconciliation
    schedule. Projecting either away could conceal unrelated Cron/state drift.
    """

    rows: dict[str, dict]
    rules: list[dict]
    global_count: int

    def validate(self) -> None:
        """Reject incomplete counts, unsupported row state and duplicate rule IDs."""

        require(isinstance(self.rows, dict) and isinstance(self.rules, list)
                and type(self.global_count) is int, "snapshot_shape_invalid")
        canonical(self.value())
        for address, row in self.rows.items():
            require(isinstance(address, str) and isinstance(row, dict)
                    and set(row) == ROW_KEYS, "row_shape_invalid")
            require(isinstance(row["state"], str)
                    and row["state"] in {"pending", "provisioning", "active", "deleting", "retired"}
                    and isinstance(row["owner_iss"], str) and bool(row["owner_iss"])
                    and isinstance(row["owner_sub"], str) and bool(row["owner_sub"])
                    and type(row["created_at"]) is int and row["created_at"] >= 0
                    and isinstance(row["local_part"], str) and bool(row["local_part"])
                    and len(row["local_part"]) <= 32
                    and type(row["slot"]) is int and 0 <= row["slot"] <= 9
                    and type(row["next_reconcile_at"]) is int
                    and -(2 ** 63) <= row["next_reconcile_at"] < 2 ** 63
                    and (row["cf_rule_id"] is None or
                         isinstance(row["cf_rule_id"], str) and bool(row["cf_rule_id"]))
                    and type(row["needs_reconcile"]) is int and row["needs_reconcile"] in (0, 1),
                    "row_shape_invalid")
        require(sum(row["state"] != "retired" for row in self.rows.values())
                == self.global_count, "global_inventory_incomplete")
        ids = set()
        for rule in self.rules:
            require(isinstance(rule, dict) and set(rule) == RULE_KEYS,
                    "rule_shape_invalid")
            require(all(isinstance(rule[field], str) and bool(rule[field])
                        for field in RULE_KEYS - {"enabled"})
                    and type(rule["enabled"]) is bool and rule["id"] not in ids,
                    "rule_shape_invalid")
            ids.add(rule["id"])

    def value(self) -> dict:
        """Return private JSON material; never print or upload without sealing."""

        return {"rows": self.rows, "rules": self.rules, "global_count": self.global_count}


def preflight(snapshot: Snapshot, owner: str, allowed: list[str]) -> None:
    """Separate global D1 headroom from provider rule headroom and B slots."""

    snapshot.validate()
    require(isinstance(owner, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,256}", owner) is not None,
            "owner_invalid")
    require(snapshot.global_count <= 187, "global_headroom_missing")
    require(len(snapshot.rules) <= 188, "provider_headroom_missing")
    require(not any(row["owner_iss"] == ISSUER and row["owner_sub"] == owner
                    and row["state"] != "retired" for row in snapshot.rows.values()),
            "owner_not_empty")
    require(not any(address in snapshot.rows for address in allowed)
            and not any(rule["address"] in allowed for rule in snapshot.rules),
            "candidate_preexisting")


def build(secret: str, run: str, key_generation: str, owner: str,
          checkout: str, mail_version: str, now_ms: int, snapshot: Snapshot) -> dict:
    """Build a private complete plan, not authorization to invoke a mutator."""

    allowed = candidates(secret, run)
    preflight(snapshot, owner, allowed)
    require(isinstance(key_generation, str) and re.fullmatch(r"[a-z0-9-]{1,40}", key_generation) is not None
            and isinstance(checkout, str) and re.fullmatch(r"[a-f0-9]{40}", checkout) is not None
            and isinstance(mail_version, str) and re.fullmatch(r"[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}", mail_version) is not None
            and type(now_ms) is int and now_ms > 0, "provenance_shape_invalid")
    resources = sorted(set(allowed) | {f"{part.lower()}@{DOMAIN}" for part in submissions()})
    return {"schema": 1, "repository": REPOSITORY, "run": run, "attempt": "1",
            "key_generation": key_generation, "owner_iss": ISSUER, "owner_sub": owner,
            "checkout": checkout, "mail_version": mail_version, "created_at": now_ms,
            "allowed": allowed, "submissions": submissions(), "resources": resources,
            "baseline": snapshot.value()}


def validate(plan: dict, secret: str, run: str, generation: str) -> Snapshot:
    """Authenticate structural bindings after opening and before recovery use."""

    require(isinstance(plan, dict) and set(plan) == {
        "schema", "repository", "run", "attempt", "key_generation", "owner_iss", "owner_sub",
        "checkout", "mail_version", "created_at", "allowed", "submissions", "resources", "baseline",
    }, "manifest_shape_invalid")
    require(plan["schema"] == 1 and type(plan["schema"]) is int
            and plan["repository"] == REPOSITORY and plan["run"] == run
            and plan["attempt"] == "1" and plan["key_generation"] == generation
            and plan["owner_iss"] == ISSUER, "manifest_binding_invalid")
    baseline = plan["baseline"]
    require(isinstance(baseline, dict) and set(baseline) == {"rows", "rules", "global_count"},
            "manifest_shape_invalid")
    snapshot = Snapshot(**baseline)
    expected = build(secret, run, generation, plan["owner_sub"], plan["checkout"],
                     plan["mail_version"], plan["created_at"], snapshot)
    require(canonical(expected) == canonical(plan), "manifest_plan_invalid")
    return snapshot


def _cipher(key: bytes):
    """Load reviewed AEAD; fail closed if the future hosted dependency is absent."""

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        derived = hmac.new(key, b"amail-ten-address/aead-key/v1", hashlib.sha256).digest()
        return AESGCM(derived)
    except Exception:
        raise ContractFailure("crypto_unavailable") from None


def associated(run: str, generation: str) -> bytes:
    """Bind ciphertext to this original repository/run/schema/key generation."""

    coordinates(run, "1")
    require(isinstance(generation, str) and re.fullmatch(r"[a-z0-9-]{1,40}", generation) is not None,
            "key_generation_invalid")
    return canonical([REPOSITORY, run, "1", 1, generation])


def seal(plan: dict, secret: str, run: str, generation: str) -> bytes:
    """Encrypt authenticated complete plan with a fresh 96-bit AES-GCM nonce."""

    validate(plan, secret, run, generation)
    aad = associated(run, generation)
    try:
        nonce = os.urandom(12)
        encrypted = _cipher(key_bytes(secret)).encrypt(nonce, canonical(plan), aad)
        return b"AMAIL-TEN-V1\x00" + nonce + encrypted
    except ContractFailure:
        raise
    except Exception:
        raise ContractFailure("manifest_seal_failed") from None


def open_manifest(blob: bytes, secret: str, run: str, generation: str) -> dict:
    """Reject malformed/tampered ciphertext; raw decode errors never escape."""

    require(isinstance(blob, bytes) and 40 <= len(blob) <= LIMIT + 256
            and blob.startswith(b"AMAIL-TEN-V1\x00"), "manifest_envelope_invalid")
    prefix = len(b"AMAIL-TEN-V1\x00")
    try:
        raw = _cipher(key_bytes(secret)).decrypt(blob[prefix:prefix + 12], blob[prefix + 12:],
                                                associated(run, generation))
        plan = json.loads(raw)
    except ContractFailure:
        raise
    except Exception:
        raise ContractFailure("manifest_authentication_failed") from None
    validate(plan, secret, run, generation)
    return plan


def artifact_readback(local: bytes, downloaded: bytes, artifact_id: str,
                      secret: str, run: str, generation: str) -> dict:
    """Gate mutation on immutable artifact ID and authenticated exact byte readback."""

    require(isinstance(artifact_id, str) and re.fullmatch(r"[1-9][0-9]{0,19}", artifact_id) is not None
            and isinstance(local, bytes) and isinstance(downloaded, bytes)
            and hmac.compare_digest(local, downloaded), "artifact_not_durable")
    return open_manifest(downloaded, secret, run, generation)


def rule_safe(snapshot: Snapshot, address: str, row: dict) -> bool:
    """Audit the complete matching set AND saved ID before supported CLI deletion."""

    matches = [rule for rule in snapshot.rules if rule["address"] == address]
    saved = [rule for rule in snapshot.rules if rule["id"] == row["cf_rule_id"]]
    if not matches:
        return not saved
    if len(matches) != 1 or saved != matches:
        return False
    rule = matches[0]
    return (rule["enabled"] is True and rule["source"] == "api"
            and rule["name"] == f"amail {address}" and rule["worker"] == "amail-inbound-staging")


def recovery_actions(plan: dict, current: Snapshot, verified_owner: str,
                     secret: str, run: str, generation: str) -> tuple[str, ...]:
    """Return exact eligible deletes, without executing any CLI/provider mutation.

    A foreign row/rule or changed operational baseline rejects the entire plan
    before any deletion. Caller must freshly attest normal B login/serving pins
    and re-audit each candidate immediately before any later CLI DELETE.
    """

    baseline = validate(plan, secret, run, generation)
    current.validate()
    require(verified_owner == plan["owner_sub"], "recovery_owner_mismatch")
    actions = []
    for address in plan["resources"]:
        prior = baseline.rows.get(address)
        before = [rule for rule in baseline.rules if rule["address"] == address]
        row = current.rows.get(address)
        after = [rule for rule in current.rules if rule["address"] == address]
        if prior is not None or before:
            require(row == prior and canonical(sorted(after, key=lambda rule: rule["id"])) ==
                    canonical(sorted(before, key=lambda rule: rule["id"])), "baseline_resource_changed")
            continue
        if row is None:
            require(not after, "unowned_rule_orphan")
            continue
        require(row["owner_iss"] == ISSUER and row["owner_sub"] == verified_owner
                and row["created_at"] >= plan["created_at"]
                and row["local_part"] == address.split("@", 1)[0], "recovery_resource_not_owned")
        require(rule_safe(current, address, row), "recovery_rule_unsafe")
        if row["state"] == "retired":
            require(not after and row["cf_rule_id"] is None and row["needs_reconcile"] == 0,
                    "retirement_unsettled")
            # Production leaves the old next_reconcile_at value after settling.
            # It is journal state, not pending work when retired + needs=0.
        else:
            actions.append(address)
    return tuple(actions)


def assert_prefix(plan: dict, current: Snapshot, prefix: int,
                  secret: str, run: str, generation: str) -> None:
    """Reject external D1/rule drift and count mismatch around quota observations."""

    baseline = validate(plan, secret, run, generation)
    current.validate()
    require(type(prefix) is int and 0 <= prefix <= 10, "prefix_invalid")
    expected = set(plan["allowed"][:prefix])
    observed = {address for address in current.rows if address not in baseline.rows}
    require(observed == expected and current.global_count == baseline.global_count + prefix
            and current.global_count <= 197, "global_or_owner_drift")
    require(all(current.rows.get(address) == row for address, row in baseline.rows.items()),
            "unrelated_row_drift")
    for address in expected:
        row = current.rows[address]
        require(row["state"] == "active" and row["needs_reconcile"] == 0
                and row["owner_iss"] == ISSUER and row["owner_sub"] == plan["owner_sub"]
                and row["local_part"] == address.split("@", 1)[0]
                and row["created_at"] >= plan["created_at"] and rule_safe(current, address, row)
                and any(rule["address"] == address for rule in current.rules), "prefix_not_active")
    unrelated = [rule for rule in current.rules if rule["address"] not in expected]
    require(canonical(sorted(unrelated, key=lambda rule: rule["id"])) ==
            canonical(sorted(baseline.rules, key=lambda rule: rule["id"])), "unrelated_rule_drift")


def reconcile(plan: dict, read: Callable[[], Snapshot], delete: Callable[[str], None],
              owner: str, secret: str, run: str, generation: str) -> None:
    """Re-audit each exact delete once; stop on ambiguity with no automatic replay."""

    def snapshot() -> Snapshot:
        """Capture adapter failures without rendering third-party exception text."""
        try:
            value = read()
        except Exception:
            raise ContractFailure("snapshot_read_failed") from None
        require(isinstance(value, Snapshot), "snapshot_shape_invalid")
        return value

    actions = recovery_actions(plan, snapshot(), owner, secret, run, generation)
    for address in actions:
        latest = recovery_actions(plan, snapshot(), owner, secret, run, generation)
        if address not in latest:
            continue
        try:
            delete(address)
        except Exception:
            raise ContractFailure("delete_outcome_ambiguous") from None
    final = snapshot()
    require(not recovery_actions(plan, final, owner, secret, run, generation), "cleanup_required")
    baseline = validate(plan, secret, run, generation)
    resources = set(plan["resources"])
    require(final.global_count == baseline.global_count and
            {a: r for a, r in final.rows.items() if a not in resources} ==
            {a: r for a, r in baseline.rows.items() if a not in resources}, "cleanup_unrelated_drift")
    require(canonical(sorted(final.rules, key=lambda rule: rule["id"])) ==
            canonical(sorted(baseline.rules, key=lambda rule: rule["id"])), "cleanup_rule_drift")
