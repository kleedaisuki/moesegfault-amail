"""Dormant B-only hosted quota controller, with no live command entry point.

Adapters must independently establish complete snapshots, normal PKCE identity,
immutable artifact readback and prior hosted isolation provenance. This module
contains no network, subprocess, account creation or SMTP implementation. It
never treats a caller boolean as deployment evidence; wiring remains gated.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Callable

import staging_ten_address_manifest as manifest

require = manifest.require


@dataclass(frozen=True, repr=False)
class Evidence:
    """Reviewed-wrapper observations, not user-supplied workflow overrides.

    Source CI and earlier isolation must be independently read from successful
    GitHub runs. Both subjects come from current verified Identity readback;
    the B username binding and fresh native PKCE must be established upstream.
    Serving and binding validation must inspect actual Cloudflare resources.
    The dormant controller cannot establish those facts by itself.
    """

    event: str
    branch: str
    repository: str
    environment: str
    confirm: str
    run: str
    attempt: str
    checkout: str
    source_ci_sha: str
    source_ci_conclusion: str
    isolation_sha: str
    isolation_conclusion: str
    owner_a: str
    owner_b: str
    verified_b_username: str
    expected_b_username: str
    pkce_owner: str
    mail_version: str
    isolation_mail_version: str
    identity_revision: str
    login_revision: str
    bindings: tuple[str, ...]
    sending_state: str

    def validate(self) -> None:
        """Reject unconfirmed/retried/foreign or missing-provenance campaigns."""
        require(all(isinstance(value, str) for name, value in vars(self).items()
                    if name != "bindings") and isinstance(self.bindings, tuple),
                "evidence_shape_invalid")
        require(self.event == "workflow_dispatch" and self.branch == manifest.BRANCH
                and self.repository == manifest.REPOSITORY and self.environment == "staging"
                and self.confirm == "RUN_STAGING_TEN_ADDRESSES", "dispatch_unconfirmed")
        manifest.coordinates(self.run, self.attempt)
        require(re.fullmatch(r"[a-f0-9]{40}", self.checkout) is not None
                and self.source_ci_sha == self.checkout and self.source_ci_conclusion == "success",
                "source_ci_unverified")
        require(re.fullmatch(r"[a-f0-9]{40}", self.isolation_sha) is not None
                and self.isolation_conclusion == "success"
                and self.isolation_mail_version == self.mail_version,
                "prior_isolation_unverified")
        require(bool(self.owner_a) and bool(self.owner_b) and self.owner_a != self.owner_b
                and self.pkce_owner == self.owner_b and bool(self.expected_b_username)
                and self.verified_b_username == self.expected_b_username,
                "verified_identity_unverified")
        require(bool(self.identity_revision) and bool(self.login_revision)
                and self.bindings == ("amail-mail-staging", "amail-inbound-staging",
                                      manifest.DOMAIN, manifest.ISSUER)
                and self.sending_state == "held", "staging_provenance_unverified")


@dataclass(frozen=True, repr=False)
class CliResult:
    """Captured bounded CLI bytes, retained privately and never formatted."""

    returncode: int
    stdout: bytes
    stderr: bytes

    def validate(self) -> None:
        """Refuse malformed/unbounded captures without emitting captured bytes."""
        require(type(self.returncode) is int and isinstance(self.stdout, bytes)
                and isinstance(self.stderr, bytes) and len(self.stdout) < 65_536
                and len(self.stderr) < 65_536, "cli_capture_invalid")


def negative(result: CliResult, code: str) -> None:
    """Require exact HTTP status and typed code; generic failures never pass."""
    require(isinstance(result, CliResult), "cli_capture_invalid")
    result.validate()
    require(code in {"reserved_or_invalid_name", "address_limit"}, "negative_oracle_invalid")
    pattern = (rb"amail: mail API addresses\.add failed: HTTP 409, code="
               + code.encode("ascii") + rb", correlation_id=[A-Za-z0-9_-]+(?:, [^\r\n]*)?(?:\r?\n|$)")
    require(result.returncode != 0 and result.stdout == b""
            and re.fullmatch(pattern, result.stderr) is not None, "negative_cli_mismatch")


def accepted(result: CliResult, address: str) -> None:
    """Validate one JSON address result before read-only activation polling."""
    require(isinstance(result, CliResult), "cli_capture_invalid")
    result.validate()
    require(result.returncode == 0 and result.stderr == b"", "add_outcome_ambiguous")
    try:
        value = json.loads(result.stdout)
    except Exception:
        raise manifest.ContractFailure("add_output_invalid") from None
    require(isinstance(value, dict) and value.get("address") == address
            and value.get("state") in {"active", "pending"}, "add_output_invalid")


@dataclass(repr=False)
class Adapter:
    """Explicit capabilities supplied only by a reviewed hosted wrapper.

    read must return a complete validated global snapshot; list_owned must
    contain every live B alias without filtering. settled performs read-only
    bounded polling, never another add. storage_empty independently verifies
    no messages/objects for all candidates. pin checks single 100% serving
    version and staging-only bindings. add/delete invoke only the B CLI.
    No exception text is allowed to escape through the controller.
    """

    read: Callable[[], manifest.Snapshot]
    list_owned: Callable[[], set[str]]
    add: Callable[[str], CliResult]
    delete: Callable[[str], None]
    settled: Callable[[], manifest.Snapshot]
    pin: Callable[[], str]
    storage_empty: Callable[[tuple[str, ...]], bool]


def _observe(adapter: Adapter, plan: dict, prefix: int, secret: str,
             run: str, generation: str, *, settled: bool = False) -> manifest.Snapshot:
    """Join independent owner API, global D1 and full provider observations."""
    current = adapter.settled() if settled else adapter.read()
    manifest.assert_prefix(plan, current, prefix, secret, run, generation)
    require(adapter.list_owned() == set(plan["allowed"][:prefix]), "owner_api_drift")
    require(adapter.pin() == plan["mail_version"], "serving_pin_changed")
    require(adapter.storage_empty(tuple(plan["resources"])) is True, "unexpected_message_storage")
    return current


def prepare(evidence: Evidence, secret: str, generation: str, now_ms: int,
            adapter: Adapter) -> tuple[dict, bytes]:
    """Build/seal complete pre-mutation plan; caller uploads exact ciphertext.

    No mutation capability is used here. The later campaign must authenticate
    immutable artifact ID and downloaded bytes before calling add even once.
    """
    try:
        evidence.validate()
        require(adapter.pin() == evidence.mail_version, "serving_pin_changed")
        plan = manifest.build(secret, evidence.run, generation, evidence.owner_b,
                              evidence.checkout, evidence.mail_version, now_ms, adapter.read())
        _observe(adapter, plan, 0, secret, evidence.run, generation)
        return plan, manifest.seal(plan, secret, evidence.run, generation)
    except manifest.ContractFailure:
        raise
    except Exception:
        raise manifest.ContractFailure("preparation_unverified") from None


def campaign(evidence: Evidence, local: bytes, downloaded: bytes, artifact_id: str,
             secret: str, generation: str, now_ms: int, adapter: Adapter) -> tuple[str, ...]:
    """Execute one serial campaign; emit success only after exact cleanup.

    Calls are never replayed on ambiguous outcomes. A process kill can skip
    finally, so external recovery uses the uploaded full plan, not this stack.
    Re-entering campaign after partial progress fails the empty-baseline gate.
    """
    evidence.validate()
    plan = manifest.artifact_readback(local, downloaded, artifact_id, secret,
                                      evidence.run, generation)
    require(plan["checkout"] == evidence.checkout and plan["owner_sub"] == evidence.owner_b
            and plan["mail_version"] == evidence.mail_version, "campaign_manifest_mismatch")
    require(type(now_ms) is int and 0 <= now_ms - plan["created_at"] <= 86_400_000,
            "campaign_manifest_stale")
    primary = False
    try:
        _observe(adapter, plan, 0, secret, evidence.run, generation)
        for part in plan["submissions"]:
            negative(adapter.add(part), "reserved_or_invalid_name")
            _observe(adapter, plan, 0, secret, evidence.run, generation)
        for index, address in enumerate(plan["allowed"][:10], 1):
            accepted(adapter.add(address.split("@", 1)[0]), address)
            _observe(adapter, plan, index, secret, evidence.run, generation, settled=True)
        before = _observe(adapter, plan, 10, secret, evidence.run, generation)
        require(len(before.rules) <= 198, "provider_headroom_changed")
        negative(adapter.add(plan["allowed"][10].split("@", 1)[0]), "address_limit")
        after = _observe(adapter, plan, 10, secret, evidence.run, generation)
        require(manifest.canonical(before.value()) == manifest.canonical(after.value()),
                "quota_rejection_side_effect")
        primary = True
    except Exception:
        # Never format adapter errors or captured provider/CLI bodies.
        primary = False
    finally:
        try:
            recover(plan, secret, generation, evidence.owner_b, adapter)
        except Exception:
            raise manifest.ContractFailure("ten_address_cleanup_required") from None
    require(primary, "ten_address_mutation_ambiguous")
    return ("ten_address_reserved_verified", "ten_address_limit_verified",
            "ten_address_cleanup_verified")


def recover(plan: dict, secret: str, generation: str, verified_owner: str,
            adapter: Adapter) -> None:
    """Reconcile same authenticated plan, never resend add or delete blindly.

    Upstream recovery must freshly authenticate B and validate source/bindings.
    Age beyond 24 hours escalates operationally, but never abandons cleanup or
    authorizes a new campaign; this routine deliberately has no expiry delete.
    """
    try:
        manifest.validate(plan, secret, plan["run"], generation)
        require(adapter.pin() == plan["mail_version"], "serving_pin_changed")
        manifest.reconcile(plan, adapter.read, adapter.delete, verified_owner,
                           secret, plan["run"], generation)
        require(adapter.list_owned() == set(), "cleanup_owner_not_empty")
        require(adapter.storage_empty(tuple(plan["resources"])) is True,
                "unexpected_message_storage")
        require(adapter.pin() == plan["mail_version"], "serving_pin_changed")
    except manifest.ContractFailure:
        raise
    except Exception:
        raise manifest.ContractFailure("recovery_unverified") from None
